import redis.asyncio as aioredis
from datetime import datetime
from config.settings import settings
import logging


redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
logger = logging.getLogger(__name__)

def _key(shop_name: str) -> str:
    # strip spaces + chuyển về lowercase
    return f"seen_ids:{shop_name.strip().lower()}"

async def get_seen_ids(shop_name: str) -> set[str]:
    return await redis.smembers(_key(shop_name))

async def add_seen_id(shop_name: str, listing_id: str):
    await redis.sadd(_key(shop_name), listing_id)

async def get_last_run(shop_name: str) -> float | None:
    ts = await redis.get(f"last_run:{shop_name}")

async def set_last_run(shop_name: str, ts: float):
    await redis.set(f"last_run:{shop_name}", ts)

async def import_seen_ids(shop_name: str, ids: list[str]):
    if not ids:
        logger.info(f"[IMPORT] Shop {shop_name}: no IDs to import")
        return
    key = _key(shop_name)
    added = await redis.sadd(key, *ids)
    logger.info(f"[IMPORT] Shop {shop_name}: imported {len(ids)} IDs into {key} (added {added} new)")
