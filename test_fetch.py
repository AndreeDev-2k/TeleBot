import asyncio
from datetime import datetime, timedelta
import pytz

from db.postgres import init_pg_pool
from poller import fetch_new_listings

async def main():
    # Khởi pool
    pg = await init_pg_pool()

    # Chọn shop bạn muốn test
    shop_name = "GiveGoodWorks"    # hoặc shop_name bất kỳ trong DB
    shop_id   = 41241109          # shop_id tương ứng
    # Đặt cutoff về 24h trước hoặc xa hơn để chắc có data
    tz = pytz.timezone("Asia/Bangkok")
    cutoff_local = datetime.now(tz) - timedelta(days=1)
    cutoff_utc = cutoff_local.astimezone(pytz.UTC)

    count = await fetch_new_listings(pg, shop_name, str(shop_id), cutoff_utc)
    print(f"Found {count} new listings for {shop_name} since {cutoff_utc.isoformat()}")

    await pg.close()

if __name__ == "__main__":
    asyncio.run(main())

