import asyncpg
import asyncio
import logging
from typing import List, Tuple, Set
from config.settings import settings

logger = logging.getLogger(__name__)


async def init_pg_pool(max_retries: int = 5, retry_delay: int = 2) -> asyncpg.Pool:
    """
    Khởi tạo connection pool đến PostgreSQL với retry logic.

    Args:
        max_retries: Số lần thử lại tối đa
        retry_delay: Thời gian chờ giữa các lần thử (giây)

    Returns:
        asyncpg.Pool: Connection pool

    Raises:
        Exception: Nếu không thể kết nối sau max_retries lần
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Đang kết nối đến PostgreSQL (lần thử {attempt}/{max_retries})..."
            )
            pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=60,
                timeout=30,  # Connection timeout
                server_settings={
                    "application_name": "telebot",
                },
            )
            logger.info("✅ Kết nối PostgreSQL thành công!")
            return pool
        except (asyncio.TimeoutError, OSError, asyncpg.PostgresError) as e:
            if attempt == max_retries:
                logger.error(
                    f"❌ Không thể kết nối PostgreSQL sau {max_retries} lần thử: {e}"
                )
                raise
            logger.warning(
                f"⚠️ Kết nối thất bại (lần {attempt}): {e}. Thử lại sau {retry_delay}s..."
            )
            await asyncio.sleep(retry_delay)


# ── XỬ LÝ SHOPS ───────────────────────────────────────────────────────────────
async def import_shops_from_csv(pg_pool, shops: List[Tuple[str, int]]) -> None:
    """
    Import danh sách shops từ CSV (shop_name, shop_id).
    """
    async with pg_pool.acquire() as con:
        await con.executemany(
            """
            INSERT INTO shops (shop_name, shop_id)
            VALUES ($1, $2)
            ON CONFLICT (shop_name) DO UPDATE
              SET shop_id = EXCLUDED.shop_id;
            """,
            shops,
        )


async def get_all_shops(pg_pool) -> List[Tuple[str, int]]:
    """
    Trả về toàn bộ danh sách shops.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch("SELECT shop_name, shop_id FROM shops;")
    return [(r["shop_name"], r["shop_id"]) for r in rows]


# ── XỬ LÝ seen_ids ────────────────────────────────────────────────────────────
async def ensure_seen_table(pg_pool) -> None:
    """
    Tạo bảng seen_ids nếu chưa có.
    """
    async with pg_pool.acquire() as con:
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_ids (
              shop_name   TEXT NOT NULL,
              listing_id  TEXT NOT NULL,
              seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (shop_name, listing_id)
            );
            """
        )


async def add_seen_id(pg_pool, shop_name: str, listing_id: str) -> bool:
    """
    Ghi nhận listing đã xem, trả về True nếu chèn mới.
    """
    async with pg_pool.acquire() as con:
        result = await con.execute(
            """
            INSERT INTO seen_ids (shop_name, listing_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING;
            """,
            shop_name,
            listing_id,
        )
    # asyncpg.execute returns e.g. 'INSERT 0 1' if inserted
    return result.split()[-1] == "1"


async def get_seen_ids(pg_pool, shop_name: str) -> Set[str]:
    """
    Lấy tập listing_id đã seen cho shop.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            "SELECT listing_id FROM seen_ids WHERE shop_name = $1;", shop_name
        )
    return {r["listing_id"] for r in rows}


# ── XỬ LÝ NHÓM & SUBSCRIPTIONS ─────────────────────────────────────────────────
async def init_groups_tables(pg_pool) -> None:
    """
    Tạo hoặc migrate các bảng groups, shops, group_subscriptions nếu chưa.
    """
    async with pg_pool.acquire() as con:

        # Bảng groups
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id          SERIAL PRIMARY KEY,
                chat_id     BIGINT    NOT NULL UNIQUE,
                chat_title  TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                deleted_at   TIMESTAMPTZ
            );
            """
        )
        # Bảng shops
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS shops (
                shop_name TEXT PRIMARY KEY,
                shop_id   BIGINT NOT NULL
            );
            """
        )
        # Bảng group_subscriptions
        await con.execute(
            """
            CREATE TABLE IF NOT EXISTS group_subscriptions (
                id            SERIAL PRIMARY KEY,
                chat_id       BIGINT    NOT NULL REFERENCES groups(chat_id) ON DELETE CASCADE,
                shop_name     TEXT      NOT NULL REFERENCES shops(shop_name) ON DELETE CASCADE,
                shop_id       BIGINT    NOT NULL REFERENCES shops(shop_id) ON DELETE CASCADE,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                deleted_at     TIMESTAMPTZ,
                UNIQUE (chat_id, shop_name)
            );
            """
        )


async def add_group(pg_pool, chat_id: int, chat_title: str) -> None:
    """
    Ghi nhận bot được thêm vào group/chat riêng.
    """
    async with pg_pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO groups (chat_id, chat_title)
            VALUES ($1, $2)
            ON CONFLICT (chat_id) DO UPDATE SET
                chat_title = EXCLUDED.chat_title,
                updated_at = now(),
                deleted_at = NULL
            """,
            chat_id,
            chat_title,
        )


async def subscribe_group(pg_pool, chat_id: int, shop_name: str, shop_id: int, chat_title: str | None = None) -> None:
    """
    Đăng ký shop cho group.
    """
    async with pg_pool.acquire() as con:
        # Đảm bảo group tồn tại với chat_title
        if chat_title:
            await con.execute(
                """
                INSERT INTO groups (chat_id, chat_title) 
                VALUES ($1, $2) 
                ON CONFLICT (chat_id) DO UPDATE SET 
                    chat_title = EXCLUDED.chat_title,
                    updated_at = now();
                """,
                chat_id,
                chat_title,
            )
        else:
            # Fallback: chỉ insert nếu chưa tồn tại, không update
            await con.execute(
                "INSERT INTO groups (chat_id, chat_title) VALUES ($1, $2) ON CONFLICT DO NOTHING;", 
                chat_id, 
                str(chat_id)
            )
        # Đảm bảo shop tồn tại và cập nhật shop_id nếu cần
        await con.execute(
            """
            INSERT INTO shops (shop_name, shop_id)
            VALUES ($1, $2)
            ON CONFLICT (shop_name) DO UPDATE SET shop_id = EXCLUDED.shop_id;
            """,
            shop_name,
            shop_id,
        )
        # Thêm subscription
        try:
            await con.execute(
                "INSERT INTO group_subscriptions (chat_id, shop_name, shop_id) VALUES ($1, $2, $3);",
                chat_id,
                shop_name,
                shop_id,
            )
        except asyncpg.exceptions.UniqueViolationError:
            # subscription already exists
            pass


async def unsubscribe_group(pg_pool, chat_id: int, shop_name: str) -> None:
    """
    Hủy đăng ký shop khỏi group.
    """
    async with pg_pool.acquire() as con:
        await con.execute(
            "DELETE FROM group_subscriptions WHERE chat_id = $1 AND shop_name = $2;",
            chat_id,
            shop_name,
        )


async def get_shops_for_group(pg_pool, chat_id: int) -> List[Tuple[str, int]]:
    """
    Trả về danh sách (shop_name, shop_id) cho group.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT s.shop_name, s.shop_id
              FROM group_subscriptions gs
              JOIN shops s ON s.shop_name = gs.shop_name
             WHERE gs.chat_id = $1;
            """,
            chat_id,
        )
    return [(r["shop_name"], r["shop_id"]) for r in rows]


async def get_all_group_ids(pg_pool) -> List[int]:
    """
    Trả về list tất cả chat_id đã đăng ký.
    """
    async with pg_pool.acquire() as con:
        rows = await con.fetch("SELECT chat_id FROM groups;")
    return [r["chat_id"] for r in rows]
