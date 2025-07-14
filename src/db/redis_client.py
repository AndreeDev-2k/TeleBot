import redis.asyncio as aioredis
from datetime import datetime
from config.settings import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def get_seen_ids(shopname: str) -> set[str]:
    return await redis.smembers(f"seen_ids:{shop_name}")

async def add_seen_id(shop_name: str, listing_id: str):
    await redis.sadd(f"seen_ids:{shop_name}", listing_id)

async def get_last_run(shop_name: str) -> float | None:
    ts = await redis.get(f"last_run:{shop_name}")

async def set_last_run(shop_name: str, ts: float):
    await redis.set(f"last_run:{shop_name}", ts)
