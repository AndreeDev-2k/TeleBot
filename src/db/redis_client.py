import redis.asyncio as aioredis
from config.settings import settings

redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def get_last_seen(shop_name: str):
    return await redis.get(f"seen:{shop_name}")

async def set_last_seen(shop_name: str, listing_id: str):
    await redis.set(f"seen:{shop_name}", listing_id)
