import asyncio
from datetime import datetime, timedelta, timezone

import feedparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.postgres import (
    init_pg_pool,
    get_all_group_ids,
    get_shops_for_group,
)
from db.redis_client import get_seen_ids, add_seen_id
from etsy.rss_client import fetch_latest_from_rss, scrape_listing_page
from notifier.telegram_client import send_message

# Thời gian tối thiểu để tính “24h qua” (UTC)
def utc_cutoff(hours: int = 24) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)

async def count_and_mark_new(shop_name: str, cutoff: datetime) -> int:
    """
    - Đọc RSS feed của shop.
    - Với mỗi entry, tách listing_id.
    - Nếu listing_id chưa seen, scrape JSON‑LD để lấy datePublished.
    - Nếu datePublished >= cutoff, đếm vào và mark seen.
    """
    seen: set[str] = await get_seen_ids(shop_name)
    new_count = 0

    feed = feedparser.parse(f"https://www.etsy.com/shop/{shop_name}/rss")
    for entry in feed.entries:
        link = entry.link
        if "/listing/" in link:
            listing_id = link.rstrip("/").split("/")[-2]
        else:
            continue

        if listing_id in seen:
            continue

        details = await scrape_listing_page(link)
        date_str = details.get("create_date")
        try:
            dt = datetime.fromisoformat(date_str)
        except Exception:
            continue

        if dt >= cutoff:
            new_count += 1
            await add_seen_id(shop_name, listing_id)

    return new_count

async def send_daily_summary():
    """
    Job báo cáo hàng ngày cho mỗi group lúc 07:00 Asia/Bangkok.
    """
    pg_pool = await init_pg_pool()
    cutoff = utc_cutoff(24)
    today = datetime.now().strftime("%Y-%m-%d")

    group_ids = await get_all_group_ids(pg_pool)
    for group_id in group_ids:
        shops = await get_shops_for_group(pg_pool, group_id)
        lines = []
        for shop in shops:
            cnt = await count_and_mark_new(shop, cutoff)
            lines.append(f"• {shop}: {cnt} sản phẩm mới trong 24h qua")

        if not lines:
            text = (
                f"📊 Báo cáo hàng ngày ({today}):\n"
                "Nhóm chưa theo dõi shop nào."
            )
        else:
            text = (
                f"📊 *Báo cáo hàng ngày* ({today}):\n\n" +
                "\n".join(lines)
            )

        await send_message(group_id, text)

def main():
    # Tạo trước event loop
    loop = asyncio.get_event_loop()

    # Khởi AsyncIOScheduler với loop đó
    scheduler = AsyncIOScheduler(event_loop=loop, timezone="Asia/Bangkok")
    scheduler.add_job(send_daily_summary, "cron", hour=7, minute=0)
    scheduler.start()

    # Giữ loop chạy liên tục
    loop.run_forever()

if __name__ == "__main__":
    main()
