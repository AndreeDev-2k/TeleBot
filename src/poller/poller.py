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
    init_fb_tables,
    get_all_fb_page_subscriptions,
    save_fb_post,
)
from api.client import fetch_fb_posts
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
    limit = 100
    offset = 0
    new_count = 0
    table = await ensure_shop_table(pg, shop_id)

    max_pages = 10
    current_page = 0

    # Tính thời gian 24h trước
    now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
    last24 = now_utc - timedelta(hours=24)

    async with aiohttp.ClientSession(headers=headers) as sess:
        recent = []

        # Pagination với order=desc (mới nhất trước)
        while current_page < max_pages:
            params = {
                "shop_id": shop_id,
                "offset": offset,
                "limit": limit,
                "sort_by": "created",
                "order": "desc",  # Mới nhất trước để tối ưu
            }

            # Sử dụng retry logic
            status, data, is_json = await get_with_retries(
                sess, f"{API_BASE}/listings", params=params
            )

            logger.info(
                f"[{shop_name}] GET listings page {current_page + 1}/{max_pages} "
                f"(offset={offset}) -> {status}"
            )

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
                logger.info(f"[{shop_name}] No more items, stopping pagination")
                break

            # Đếm listings mới và cũ trong page này
            new_in_page = 0
            old_in_page = 0

            for it in items:
                if not isinstance(it, dict):
                    continue

                created = it.get("created_at")
                if not created:
                    continue

                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(
                        tzinfo=pytz.UTC
                    )

                    if dt >= last24:
                        # Listing mới trong 24h
                        recent.append((str(it.get("listing_id")), it.get("url"), dt))
                        new_in_page += 1
                    else:
                        # Listing cũ hơn 24h
                        old_in_page += 1
                except Exception as e:
                    logger.debug(f"[{shop_name}] Parse date error: {e}")
                    continue

            logger.info(
                f"[{shop_name}] Page {current_page + 1}: "
                f"{new_in_page} new, {old_in_page} old listings"
            )

            # Check pagination từ metadata
            has_more = False
            if isinstance(metadata, dict):
                meta = metadata.get("pagination", {})
                if isinstance(meta, dict):
                    has_more = meta.get("has_next", metadata.get("has_more", False))

            if not has_more:
                logger.info(f"[{shop_name}] No more pages available")
                break

            offset += limit
            current_page += 1

        # Log tổng kết
        if current_page >= max_pages:
            logger.info(
                f"[{shop_name}] Reached max pages limit ({max_pages}), "
                f"checked {current_page * limit} listings total"
            )

        logger.info(f"[{shop_name}] Total {len(recent)} recent listings found")

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


def _format_fb_post(post: dict, page_name: str) -> str:
    """
    Định dạng bài đăng Facebook (từ tool.vn) thành message Telegram.

    Cấu trúc response tool.vn:
      - strong_id__: ID số của post (dùng để dedup)
      - message.text: nội dung văn bản
      - creation_time: Unix timestamp
      - url: link trực tiếp đến bài viết
    """
    from datetime import datetime

    TZ_VN = pytz.timezone("Asia/Bangkok")

    # Nội dung bài viết
    msg_field = post.get("message")
    if isinstance(msg_field, dict):
        text = msg_field.get("text", "")
    else:
        text = msg_field or ""

    # Thời gian đăng
    ts = post.get("creation_time")
    if ts:
        try:
            created_str = datetime.fromtimestamp(int(ts), tz=TZ_VN).strftime(
                "%d/%m/%Y %H:%M"
            )
        except Exception:
            created_str = str(ts)
    else:
        created_str = ""

    # URL bài viết
    link = post.get("url") or post.get("permalink_url") or ""

    lines = [f"📢 *{page_name}*"]
    if created_str:
        lines.append(f"🕐 {created_str}")
    if text:
        preview = text[:800] + "…" if len(text) > 800 else text
        lines.append(f"\n{preview}")
    if link:
        lines.append(f"\n🔗 [Xem bài đăng]({link})")

    return "\n".join(lines)


async def poll_fb_pages():
    """Lấy bài đăng ngày hôm qua từ các Facebook fanpage và gửi thông báo."""
    logger.info("[FB] Bắt đầu poll Facebook pages...")
    pg = await init_pg_pool()
    await init_fb_tables(pg)

    all_subs = await get_all_fb_page_subscriptions(pg)
    if not all_subs:
        logger.info("[FB] Chưa có subscription nào.")
        return

    # Tính khoảng thời gian "hôm qua" theo múi giờ Asia/Bangkok
    today_local = datetime.now(TZ).date()
    yesterday_local = today_local - timedelta(days=1)
    yesterday_start = TZ.localize(
        datetime(
            yesterday_local.year, yesterday_local.month, yesterday_local.day, 0, 0, 0
        )
    )
    yesterday_end = TZ.localize(
        datetime(today_local.year, today_local.month, today_local.day, 0, 0, 0)
    )
    logger.info(
        f"[FB] Chỉ lấy bài đăng ngày {yesterday_local} ({yesterday_start} → {yesterday_end})"
    )

    # Gom theo page_id để mỗi page chỉ fetch 1 lần
    pages: dict[str, dict] = {}
    for chat_id, page_id, page_name in all_subs:
        if page_id not in pages:
            pages[page_id] = {"page_name": page_name, "chat_ids": []}
        pages[page_id]["chat_ids"].append(chat_id)

    for page_id, info in pages.items():
        page_name = info["page_name"]
        try:
            posts = await fetch_fb_posts(page_id, limit=50)
            logger.info(
                f"[FB] Page '{page_name}' ({page_id}): {len(posts)} posts fetched"
            )
        except Exception as e:
            logger.error(f"[FB] Lỗi khi fetch page '{page_name}' ({page_id}): {e}")
            continue

        new_count = 0
        for post in posts:
            post_id = str(
                post.get("strong_id__") or post.get("post_id") or post.get("id") or ""
            )
            if not post_id:
                continue

            # ── Thời gian đăng ──────────────────────────────────────────────
            ts = post.get("creation_time")
            created_at = None
            if ts:
                try:
                    created_at = datetime.fromtimestamp(int(ts), tz=pytz.UTC)
                except Exception:
                    pass

            # Chỉ lưu bài đăng trong ngày hôm qua; bỏ qua nếu không có timestamp
            if created_at is None:
                continue
            if not (yesterday_start <= created_at < yesterday_end):
                continue

            # ── Nội dung văn bản ─────────────────────────────────────────────
            msg_field = post.get("message")
            message = (
                msg_field.get("text", "")
                if isinstance(msg_field, dict)
                else (msg_field or "")
            )

            # ── Ảnh đầu tiên từ attachments ──────────────────────────────────
            image_url = ""
            for att in post.get("attachments") or []:
                if not isinstance(att, dict):
                    continue
                media = att.get("media") or {}
                img = media.get("image") or {}
                uri = img.get("uri", "")
                if uri:
                    image_url = uri
                    break

            # ── URL bài viết ─────────────────────────────────────────────────
            post_url = post.get("url") or post.get("permalink_url") or ""

            # ── Tương tác ────────────────────────────────────────────────────
            feedback = post.get("feedback") or {}
            reaction_count = int(feedback.get("reaction_count") or 0)
            comment_count_obj = feedback.get("comment_count") or {}
            comment_count = int(
                comment_count_obj.get("total_count") or 0
                if isinstance(comment_count_obj, dict)
                else comment_count_obj or 0
            )

            is_new = await save_fb_post(
                pg,
                page_id,
                post_id,
                page_name,
                created_at,
                message,
                image_url,
                post_url,
                reaction_count,
                comment_count,
            )
            if is_new:
                new_count += 1

        logger.info(
            f"[FB] Page '{page_name}': {new_count} bài mới đã lưu vào fb_posts."
        )

    logger.info("[FB] Hoàn thành thu thập bài đăng Facebook.")


def main():
    loop = asyncio.get_event_loop()
    sched = AsyncIOScheduler(event_loop=loop, timezone="Asia/Bangkok")
    sched.add_job(collect_listings, "cron", hour=5, minute=0)
    sched.add_job(poll_fb_pages, "cron", hour=5, minute=30)
    sched.add_job(send_daily_summary, "cron", hour=6, minute=0)
    sched.start()
    loop.run_forever()


if __name__ == "__main__":
    main()
