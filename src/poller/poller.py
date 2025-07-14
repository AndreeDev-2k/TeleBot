import asyncio
import time
from datetime import datetime

from db.postgres import init_pg_pool, get_all_shops, get_subscribers_for_shop
from api.client import fetch_latest_from_rss, scrape_listing_page
from db.redis_client import (get_seen_ids, add_seen_id, get_last_run, set_last_run)
from notifier.telegram_client import send_message

async def worker(pg_pool, semaphore):
    shops = await get_all_shops(pg_pool)
    tasks = []

    for shop in shops:
        async with semaphore:
            basic = await fetch_latest_from_rss(shop)
            if not basic:
                continue

            try:
                pub_ts = datetime.strptime(basic["pub_date"], "%Y-%m-%d %H:%M").timestamp()
            except Exception:
                pub_ts = 0.0

            last_run = await get_last_run(shop) or 0.0
            if pub_ts <= last_run:
                return

            seen = await get_seen_ids(shop_name)
            listing_id = basic["listing_id"]
       
            if listing_id not in seen:
                # Listing mới hoàn toàn
                details = await scrape_listing_page(basic["url"])

                create_date = details.get("create_date") or basic["pub_date"]

                # Gộp thông tin
                listing = {
                    "listing_id": listing_id,
                    "title": basic["title"],
                    "price": details["price"],
                    "currency": detail["currency"],
                    "url": basic["url"],
                    "thumbnail": details["thumbnail"],
                    "create_date": create_date,
                }

                chat_ids = await get_subcribers_for_shop(pg_pool, shop_name)
                if chat_ids:
                    await notify_listing(shop_name, listing, chat_ids)

                await add_seen_id(shop_name, listing_id)

            await set_last_run(shop_name, time.time())

        task.append(check(shop))

    await asyncio.gather(*tasks)


async def main():
    pg_pool = await init_pg_pool()
    semaphore = asyncio.Semaphore(10)
    while True:
        await worker(pg_pool, semaphore)
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())
