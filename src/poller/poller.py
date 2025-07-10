import asyncio
from db.postgres import init_pg_pool, get_all_shops, get_subscribers_for_shop
from db.redis_client import get_last_seen, set_last_seen
from api.client import fetch_latest_from_rss, scrape_listing_page
from notifier.telegram_client import send_message

async def worker(pg_pool, semaphore):
    shops = await get_all_shops(pg_pool)
    for shop in shops:
        async with semaphore:
            latest = await fetch_latest_from_rss(shop)
        if not latest:
            continue
        prev = await get_last_seen(shop)
        if str(latest['listing_id']) == prev:
            continue
        await set_last_seen(shop, latest['listing_id'])
        details = await scrape_listing_page(latest['link'])
        chat_ids = await get_subscribers_for_shop(pg_pool, shop)
        text = (
            f"🛒 *{shop}* Etsy vừa up:\n"
            f"• Title: {latest['title']}\n"
            f"• Price: {details['price']} {details['currency']}\n"
            f"• Link: {latest['link']}\n"
            f"• Image: {details['thumbnail'] or 'Không có'}\n"
            f"• Datetime: {latest['pub_date']}"
        )
        for cid in chat_ids:
            await send_message(cid, text)

async def main():
    pg_pool = await init_pg_pool()
    semaphore = asyncio.Semaphore(10)
    while True:
        await worker(pg_pool, semaphore)
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())