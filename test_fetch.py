"""
Test script để kiểm tra fetch_new_listings với phương án hybrid mới
"""

import asyncio
import logging
from datetime import datetime, timedelta
import sys

import pytz

# Add src to path
sys.path.insert(0, "src")

from config.settings import settings
from db.postgres import init_pg_pool
from poller.poller import fetch_new_listings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Bangkok")


async def test_fetch():
    """
    Test fetch với shop ID cụ thể
    """
    logger.info("=" * 80)
    logger.info("🧪 Testing optimized fetch_new_listings with HYBRID approach")
    logger.info("=" * 80)

    # Kết nối database
    pg = await init_pg_pool()
    logger.info("✓ Connected to PostgreSQL")

    # Test với shop ID từ log cũ của bạn
    test_shop_id = 36691862  # Shop ID từ log error 502 trước đó
    test_shop_name = "VinartsVn"

    # Cutoff 24h
    cutoff_local = datetime.now(TZ) - timedelta(days=1)
    cutoff = cutoff_local.astimezone(pytz.UTC)

    logger.info(f"📦 Shop ID: {test_shop_id}")
    logger.info(f"🏪 Shop Name: {test_shop_name}")
    logger.info(f"⏰ Cutoff time: {cutoff_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"🔍 Looking for listings created after this time...")
    logger.info("")

    # Fetch
    start_time = datetime.now()
    try:
        count = await fetch_new_listings(pg, test_shop_name, test_shop_id, cutoff)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"✅ Found {count} new listings in last 24h")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds")
        if duration > 0:
            logger.info(f"🚀 Performance: {count/duration:.2f} listings/second")
        logger.info("=" * 80)

        if count > 0:
            logger.info("\n✅ Test PASSED - Found new listings!")
        else:
            logger.info(
                "\n⚠️  No new listings found (shop might not have new items in 24h)"
            )

    except Exception as e:
        logger.error(f"❌ Error during fetch: {e}", exc_info=True)

    await pg.close()


if __name__ == "__main__":
    asyncio.run(test_fetch())
