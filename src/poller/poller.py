import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import feedparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.postgres import init_pg_pool, get_all_group_ids, get_shops_for_group
from etsy.rss_client import scrape_listing_page
from notifier.telegram_client import send_message

# Khai báo timezone
TZ = ZoneInfo("Asia/Bangkok")


def get_prev_day_window():
    """
    Trả về tuple (start, end) của khoảng 00:00–00:00 ngày trước đó,
    aware datetime theo TZ.
    """
    now = datetime.now(TZ)
    today_mid = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_mid = today_mid - timedelta(days=1)
    return yesterday_mid, today_mid


async def count_listings_between(shop_name: str, start: datetime, end: datetime) -> int:
    """
    Đếm số listing của shop được tạo trong khoảng [start, end),
    dựa vào datePublished trong JSON‑LD.
    """
    url = f"https://www.etsy.com/shop/{shop_name}/rss"
    feed = feedparser.parse(url)
    count = 0
    seen_ids = set()

    for entry in feed.entries:
        link = entry.link
        if "/listing/" not in link:
            continue
        listing_id = link.rstrip("/").split("/")[-2]
        if listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        # Scrape JSON‑LD để lấy datePublished
        details = await scrape_listing_page(link)
        date_str = details.get("create_date")
        try:
            # ISO format từ JSON‑LD, e.g. "2025-07-14T09:30:00Z" hoặc without Z
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Chuyển về timezone Asia/Bangkok
            dt = dt.astimezone(TZ)
        except Exception:
            continue

        if start <= dt < end:
            count += 1

    return count


async def send_daily_summary():
    """
    Job chạy lúc 07:00 Asia/Bangkok, gửi báo cáo listing mới của ngày trước.
    """
    pg_pool = await init_pg_pool()
    start, end = get_prev_day_window()
    label = start.strftime("%Y-%m-%d")

    group_ids = await get_all_group_ids(pg_pool)
    for group_id in group_ids:
        shops = await get_shops_for_group(pg_pool, group_id)
        lines = []
        for shop in shops:
            cnt = await count_listings_between(shop, start, end)
            lines.append(f"• {shop}: {cnt} sản phẩm mới trong ngày {label}")

        if not lines:
            text = f"📊 Báo cáo ngày {label}:\nNhóm chưa theo dõi shop nào."
        else:
            text = "📊 *Báo cáo ngày* " + label + ":\n\n" + "\n".join(lines)

        await send_message(group_id, text)


def main():
    scheduler = AsyncIOScheduler(timezone=TZ)
    # Chạy job vào 07:00 mỗi ngày
    scheduler.add_job(send_daily_summary, "cron", hour=7, minute=0)
    scheduler.start()

    # Giữ event loop chạy
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
