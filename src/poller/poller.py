import asyncio
import logging
from datetime import datetime, timedelta
import sys

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
            resp = await sess.get(f"{API_BASE}/listings", params=params)
            logger.info(f"[{shop_name}] GET listings {params} -> {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"[{shop_name}] Listing API error {resp.status}: {text}")
                break
            data = await resp.json()
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
            meta = metadata.get("pagination", {})
            if not meta.get("has_next", metadata.get("has_more", False)):
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
            # fetch listing images
            img_resp = await sess.get(
                f"{API_BASE}/listing-images", params={"listing_ids": lid}
            )
            img_url = ""
            if img_resp.status == 200:
                j = await img_resp.json()
                # Handle new API format for listing-images
                if "data" in j and "listing_images" in j["data"]:
                    mapping = j["data"]["listing_images"]  # New format
                else:
                    mapping = j.get("results", {}).get(
                        "listing_images", {}
                    )  # Old format fallback

                imgs = mapping.get(lid, [])
                if imgs:
                    img_url = imgs[0].get("url_570xN", "")
            else:
                logger.warning(
                    f"[{shop_name}] Images API {lid} failed: {img_resp.status}"
                )

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
