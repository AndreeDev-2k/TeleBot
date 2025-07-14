import asyncio
from datetime import datetime, date, time, timedelta
import feedparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

from db.postgres import init_pg_pool, get_all_group_ids, get_shops_for_group
from api.client import scrape_listing_page
from notifier.telegram_client import send_message

# Timezone Asia/Bangkok
TZ = timezone("Asia/Bangkok")

def get_prev_day_window():
    today = datetime.now(TZ).date()
    start = datetime.combine(today - timedelta(days=1), time(0, 0), tzinfo=TZ)
    end   = datetime.combine(today,             time(0, 0), tzinfo=TZ)
    return start, end

async def count_listings_between(shop_name: str, start: datetime, end: datetime) -> int:
    url = f"https://www.etsy.com/shop/{shop_name}/rss"
    feed = feedparser.parse(url)
    count = 0

    for entry in feed.entries:
        link = entry.link
        if "/listing/" not in link:
            continue
        details = await scrape_listing_page(link)
        date_str = details.get("create_date")
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            else:
                dt = dt.astimezone(TZ)
        except Exception:
            continue

        if start <= dt < end:
            count += 1

    return count

async def send_daily_summary():
    pg_pool = await init_pg_pool()
    start, end = get_prev_day_window()
    label = start.strftime("%Y-%m-%d")

    group_ids = await get_all_group_ids(pg_pool)
    for group_id in group_ids:
        shops = await get_shops_for_group(pg_pool, group_id)
        lines = []
        for shop in shops:
            cnt = await count_listings_between(shop, start, end)
            lines.append(f"• {shop}: {cnt} sản phẩm mới ngày {label}")

        if not lines:
            text = f"📊 Báo cáo ngày {label}:\nNhóm chưa theo dõi shop nào."
        else:
            text = "📊 *Báo cáo ngày* " + label + ":\n\n" + "\n".join(lines)

        await send_message(group_id, text)

def main():
    scheduler = AsyncIOScheduler(timezone="Asia/Bangkok")
    scheduler.add_job(send_daily_summary, "cron", hour=7, minute=0)
    scheduler.start()
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    main()
