import asyncpg
from config.settings import settings

async def init_pg_pool():
    return await asyncpg.create_pool(dsn=settings.DATABASE_URL)

async def add_user(pg_pool, telegram_id: int):
    async with pg_pool.acquire() as con:
        await con.execute(
            'INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT (telegram_id) DO NOTHING',
            telegram_id
        )

async def add_shop(pg_pool, shop_name: str):
    async with pg_pool.acquire() as con:
        rec = await con.fetchrow(
            'INSERT INTO shops (shop_name) VALUES ($1) ON CONFLICT (shop_name) DO NOTHING RETURNING id',
            shop_name
        )
        return rec and rec['id']

async def subscribe(pg_pool, telegram_id: int, shop_name: str):
    async with pg_pool.acquire() as con:
        await add_user(pg_pool, telegram_id)
        # lấy shop_id
        shop = await con.fetchrow('SELECT id FROM shops WHERE shop_name=$1', shop_name)
        if not shop:
            shop_id = await add_shop(pg_pool, shop_name)
        else:
            shop_id = shop['id']
        # insert subscription
        await con.execute(
            'INSERT INTO subscriptions (user_id, shop_id) VALUES ((SELECT id FROM users WHERE telegram_id=$1), $2) ON CONFLICT DO NOTHING',
            telegram_id, shop_id
        )

async def unsubscribe(pg_pool, telegram_id: int, shop_name: str):
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            DELETE FROM subscriptions
            WHERE user_id=(SELECT id FROM users WHERE telegram_id=$1)
              AND shop_id=(SELECT id FROM shops WHERE shop_name=$2)
            ''',
            telegram_id, shop_name
        )

async def get_user_subscriptions(pg_pool, telegram_id: int):
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            '''
            SELECT s.shop_name
            FROM shops s
            JOIN subscriptions sub ON sub.shop_id=s.id
            JOIN users u ON u.id=sub.user_id
            WHERE u.telegram_id=$1
            ''',
            telegram_id
        )
        return [r['shop_name'] for r in rows]

async def get_all_shops(pg_pool):
    async with pg_pool.acquire() as con:
        rows = await con.fetch('SELECT shop_name FROM shops')
        return [r['shop_name'] for r in rows]

async def get_subscribers_for_shop(pg_pool, shop_name: str):
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            '''
            SELECT u.telegram_id
            FROM users u
            JOIN subscriptions sub ON sub.user_id=u.id
            JOIN shops s ON s.id=sub.shop_id
            WHERE s.shop_name=$1
            ''',
            shop_name
        )
        return [r['telegram_id'] for r in rows]
