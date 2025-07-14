import asyncpg
from config.settings import settings

async def init_pg_pool():
    return await asyncpg.create_pool(dsn=settings.DATABASE_URL)

async def add_shop(pg_pool, shop_name: str):
    async with pg_pool.acquire() as con:
        rec = await con.fetchrow(
            'INSERT INTO shops (shop_name) VALUES ($1) ON CONFLICT (shop_name) DO NOTHING RETURNING id',
            shop_name
        )
        if rec:
            return rec['id']
        rec2 = await con.fetchrow(
            'SELECT id FROM shops WHERE shop_name=$1', shop_name
        )
        return rec2['id']

async def subscribe_group(pg_pool, chat_id: int, shop_name: str):
    await add_group(pg_pool, chat_id)
    await add_shop(pg_pool, shop_name)
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            INSERT INTO group_subscriptions (group_id, shop_name)
            VALUES ((SELECT id FROM groups WHERE chat_id=$1),$2)
            ON CONFLICT DO NOTHING
            ''',
            chat_id, shop_name
        )

async def unsubscribe_group(pg_pool, chat_id: int, shop_name: str):
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            DELETE FROM group_subscriptions
            WHERE group_id=(SELECT id FROM group WHERE chat_id=$1)
              AND shop_id=(SELECT id FROM shops WHERE shop_name=$2)
            ''',
            chat_id, shop_name
        )

async def get_shops_for_group(pg_pool, chat_id: int) -> list[str]:
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            '''
            SELECT sub.shop_name
            FROM group_subcriptions sub
            JOIN groups g ON g.id = sub.group_id
            JOIN users u ON u.id=sub.user_id
            WHERE sub.shop_name = $1
            ''',
            shop_name
        )
        return [r['chat_id'] for r in rows]

async def get_all_shops(pg_pool):
    async with pg_pool.acquire() as con:
        rows = await con.fetch('SELECT shop_name FROM shops')
        return [r['shop_name'] for r in rows]

async def add_group(pg_pool: async.Pool, chat_id: int) -> None:
    async with pg_pool.acquire() as con:
        await con.excute(
            """
            INSERT INTO groups (chat_id)
            VALUES ($1)
            ON CONFLICT (chat_id) DO NOTHING
            """,
            chat_id
            )  

async def get_groups_for_shop(pg_pool, shop_name: str) -> list[int]:
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            '''
            SELECT g.chat_id
            FROM group_subscriptions sub
            JOIN groups g ON g.id = sub.group_id
            WHERE sub.shop_name = $1
            ''',
            shop_name
        )
        return [r['chat_id'] for r in rows]

async def get_all_group_ids(pg_pool) -> list[int]:
    async with pg_pool.acquire() as con:
        rows = await con.fetch('SELECT chat_id FROM groups')
    return [r['chat_id'] for r in rows]
