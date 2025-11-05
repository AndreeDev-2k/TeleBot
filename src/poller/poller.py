import asyncio
import logging
from datetime import datetime, timedelta
import sys
import random

import aiohttp
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from db.postgres import (
    init_pg_pool,
    get_all_group_ids,
    get_shops_for_group,
    ensure_seen_table,
)
from notifier.telegram_client import send_message

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Constants
TZ = pytz.timezone("Asia/Bangkok")
API_BASE = "https://service.sidcorp.co/api/v3/etsy"
API_KEY = settings.API_KEY

daily_counts: dict[str, int] = {}

# Transient statuses - lỗi tạm thời cần retry
TRANSIENT_STATUSES = {429, 500, 502, 503, 504, 522, 523, 524}


async def get_with_retries(
    sess: aiohttp.ClientSession,
    url: str,
    *,
    params: dict,
    max_attempts: int = 5,
    base_backoff: float = 1.0,
    timeout: int = 30,
):
    """
    GET request với retry logic cho lỗi tạm thời.
    Trả về (status, data, is_json).
    """
    backoff = base_backoff
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = await sess.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)
            )
            status = resp.status
            ctype = (resp.headers.get("Content-Type") or "").lower()
            is_json = "application/json" in ctype

            if is_json:
                try:
                    data = await resp.json()
                except Exception:
                    # Server trả HTML nhưng header ghi json
                    data = await resp.text()
                    is_json = False
            else:
                data = await resp.text()

            # Thành công hoặc lỗi không-transient → trả về
            if status < 400 or status not in TRANSIENT_STATUSES:
                return status, data, is_json

            # Lỗi transient → retry
            last_error = f"Status {status}"
            logger.warning(
                f"[Retry {attempt}/{max_attempts}] {url} -> {status}, "
                f"waiting {backoff:.1f}s..."
            )

        except asyncio.TimeoutError as e:
            last_error = f"Timeout: {e}"
            logger.warning(
                f"[Retry {attempt}/{max_attempts}] {url} timeout, "
                f"waiting {backoff:.1f}s..."
            )
        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"[Retry {attempt}/{max_attempts}] {url} error: {e}, "
                f"waiting {backoff:.1f}s..."
            )

        if attempt < max_attempts:
            # Exponential backoff + jitter
            await asyncio.sleep(backoff + random.uniform(0, 0.5))
            backoff = min(backoff * 2, 10.0)

    # Hết retry attempts
    logger.error(
        f"Failed after {max_attempts} attempts: {url}. Last error: {last_error}"
    )
    return 503, {"error": f"Max retries exceeded. Last error: {last_error}"}, True


async def ensure_shop_table(pg, shop_id: int) -> str:
    table = f"listing_{shop_id}"
    # Drop and recreate table
    await pg.execute(f'DROP TABLE IF EXISTS "{table}";')
    await pg.execute(
        f"""
        CREATE TABLE "{table}" (
            listing_id     TEXT PRIMARY KEY,
            url            TEXT,
            listing_images TEXT,
            created_at     TIMESTAMPTZ
        );
    """
    )
    return table


async def fetch_new_listings(pg, shop_name: str, shop_id: int, cutoff: datetime) -> int:
    # Normalize cutoff to UTC-aware
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        cutoff = cutoff.replace(tzinfo=pytz.UTC)

    headers = {"x-api-key": API_KEY, "Accept": "application/json"}
    limit, offset = 100, 0
    new_count = 0
    table = await ensure_shop_table(pg, shop_id)

    async with aiohttp.ClientSession(headers=headers) as sess:
        all_items = []
        # Pagination asc
        while True:
            params = {
                "shop_id": shop_id,
                "offset": offset,
                "limit": limit,
                "sort_by": "created",
                "sort_order": "asc",
                "state": "active",
            }

            # Sử dụng retry logic
            status, data, is_json = await get_with_retries(
                sess, f"{API_BASE}/listings", params=params
            )

            logger.info(f"[{shop_name}] GET listings {params} -> {status}")

            if status != 200:
                error_msg = data if isinstance(data, str) else str(data)
                logger.error(f"[{shop_name}] Listing API error {status}: {error_msg}")
                break

            # Data phải là dict nếu is_json=True
            if not is_json or not isinstance(data, dict):
                logger.error(f"[{shop_name}] Invalid response format")
                break

            # Handle new API format: data is in 'data' field, not 'results'
            if "data" in data and isinstance(data["data"], list):
                items = data["data"]  # New format
                metadata = data.get("metadata", {})
            else:
                items = data.get("results", []) or []  # Old format fallback
                metadata = data.get("metadata", {})

            if not items:
                break
            all_items.extend(items)

            # Check pagination from metadata
            if isinstance(metadata, dict):
                meta = metadata.get("pagination", {})
                if isinstance(meta, dict) and not meta.get(
                    "has_next", metadata.get("has_more", False)
                ):
                    break
            offset += limit

        # Filter by created_at in last 24h
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        last24 = now_utc - timedelta(hours=24)
        recent = []
        for it in all_items:
            created = it.get("created_at")
            if not created:
                continue
            dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(
                tzinfo=pytz.UTC
            )
            if dt >= last24:
                recent.append((str(it.get("listing_id")), it.get("url"), dt))
        logger.info(f"[{shop_name}] {len(recent)} recent listings")

        # Insert with image URLs
        for lid, url_field, dt in recent:
            # Fetch listing images với retry
            img_status, img_data, img_is_json = await get_with_retries(
                sess, f"{API_BASE}/listing-images", params={"listing_ids": lid}
            )

            img_url = ""
            if img_status == 200 and img_is_json and isinstance(img_data, dict):
                # Handle new API format for listing-images
                mapping = {}
                if "data" in img_data:
                    data_dict = img_data.get("data")
                    if isinstance(data_dict, dict) and "listing_images" in data_dict:
                        listing_imgs = data_dict.get("listing_images")
                        if isinstance(listing_imgs, dict):
                            mapping = listing_imgs
                elif "results" in img_data:
                    results = img_data.get("results")
                    if isinstance(results, dict):
                        listing_imgs = results.get("listing_images")
                        if isinstance(listing_imgs, dict):
                            mapping = listing_imgs

                if mapping:
                    imgs = mapping.get(lid, [])
                    if imgs and isinstance(imgs, list) and len(imgs) > 0:
                        first_img = imgs[0]
                        if isinstance(first_img, dict):
                            img_url = first_img.get("url_570xN", "")
            else:
                logger.warning(f"[{shop_name}] Images API {lid} failed: {img_status}")

            img_str = img_url or ""

            try:
                await pg.execute(
                    f"INSERT INTO {table} (listing_id, url, listing_images, created_at) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING;",
                    lid,
                    url_field,
                    img_str,
                    dt,
                )
                new_count += 1
            except Exception as e:
                logger.debug(f"[{shop_name}] DB insert error: {e}")

    logger.info(f"[{shop_name}] Total new: {new_count}")
    return new_count


async def collect_listings():
    pg = await init_pg_pool()
    await ensure_seen_table(pg)
    cutoff_local = datetime.now(TZ) - timedelta(days=1)
    cutoff = cutoff_local.astimezone(pytz.UTC)
    daily_counts.clear()
    shops = set()
    for gid in await get_all_group_ids(pg):
        for name, sid in await get_shops_for_group(pg, gid):
            shops.add((name, sid))
    for name, sid in shops:
        cnt = await fetch_new_listings(pg, name, sid, cutoff)
        daily_counts[name] = cnt


async def send_daily_summary():
    pg = await init_pg_pool()
    label = (datetime.now(TZ).date() - timedelta(days=1)).isoformat()
    for gid in await get_all_group_ids(pg):
        lines = []
        for name, sid in await get_shops_for_group(pg, gid):
            cnt = daily_counts.get(name, 0)
            link = f"https://dakuho.com/topics/{gid}/shops/{sid}"
            lines.append(f"• {name}: {cnt} new [Xem thêm]({link})")
        text = f"📊 *Daily Report {label}*\n\n" + (
            "\n".join(lines) if lines else "No subscriptions."
        )
        await send_message(gid, text)


def main():
    loop = asyncio.get_event_loop()
    sched = AsyncIOScheduler(event_loop=loop, timezone="Asia/Bangkok")
    sched.add_job(collect_listings, "cron", hour=5, minute=0)
    sched.add_job(send_daily_summary, "cron", hour=6, minute=0)
    sched.start()
    loop.run_forever()


if __name__ == "__main__":
    main()
