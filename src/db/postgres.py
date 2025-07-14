import asyncpg
from config.settings import settings

async def init_pg_pool():
    return await asyncpg.create_pool(dsn=settings.DATABASE_URL)

async def add_group(pg_pool, chat_id: int):
    """
    Thêm một group chat nếu chưa tồn tại.
    """
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            INSERT INTO groups (chat_id)
            VALUES ($1)
            ON CONFLICT (chat_id) DO NOTHING
            ''',
            chat_id
        )

async def add_shop(pg_pool, shop_name: str):
    """
    Đảm bảo shop tồn tại trong bảng shops, trả về shop_id.
    """
    async with pg_pool.acquire() as con:
        rec = await con.fetchrow(
            '''
            INSERT INTO shops (shop_name)
            VALUES ($1)
            ON CONFLICT (shop_name) DO NOTHING
            RETURNING id
            ''',
            shop_name
        )
        if rec:
            print(f"[+] Đã thêm shop mới vào database: {shop_name}")
            return rec['id']
        # Nếu đã tồn tại, lấy lại id
        rec2 = await con.fetchrow(
            'SELECT id FROM shops WHERE shop_name=$1', shop_name
        )
        return rec2['id']

async def subscribe_group(pg_pool, chat_id: int, shop_name: str):
    """
    Cho group chat theo dõi một shop.
    """
    # Đảm bảo group và shop đã tồn tại
    await add_group(pg_pool, chat_id)
    await add_shop(pg_pool, shop_name)
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            INSERT INTO group_subscriptions (group_id, shop_name)
            VALUES (
                (SELECT id FROM groups WHERE chat_id=$1),
                $2
            )
            ON CONFLICT DO NOTHING
            ''',
            chat_id, shop_name
        )

async def unsubscribe_group(pg_pool, chat_id: int, shop_name: str):
    """
    Hủy theo dõi shop cho group chat.
    """
    async with pg_pool.acquire() as con:
        await con.execute(
            '''
            DELETE FROM group_subscriptions
            WHERE group_id = (SELECT id FROM groups WHERE chat_id=$1)
              AND shop_name = $2
            ''',
            chat_id, shop_name
        )

async def get_shops_for_group(pg_pool, chat_id: int) -> list[str]:
    """
    Lấy danh sách shop mà một group đang theo dõi.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            '''
            SELECT sub.shop_name
            FROM group_subscriptions sub
            JOIN groups g ON g.id = sub.group_id
            WHERE g.chat_id = $1
            ''',
            chat_id
        )
    return [r['shop_name'] for r in rows]

async def get_all_shops(pg_pool) -> list[str]:
    """
    Lấy tất cả shop có trong hệ thống.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch('SELECT shop_name FROM shops')
    return [r['shop_name'] for r in rows]

async def get_groups_for_shop(pg_pool, shop_name: str) -> list[int]:
    """
    Lấy danh sách chat_id của các group đang theo dõi một shop.
    """
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
    """
    Lấy tất cả chat_id của groups đã đăng ký.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch('SELECT chat_id FROM groups')
    return [r['chat_id'] for r in rows]
