"""
Test tích hợp Facebook fanpage — xác minh poll_fb_pages() lấy 20 bài mới nhất mỗi 6 tiếng.
Chạy: python test_fb.py
"""

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta

import pytz

sys.path.insert(0, "src")

from config.settings import settings
from db.postgres import (
    init_pg_pool,
    init_groups_tables,
    init_fb_tables,
    subscribe_fb_group,
)
from poller.poller import poll_fb_pages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Bangkok")

TEST_PAGES = [
    {"page_id": "100064129956082", "page_name": "Merchize"},
    {"page_id": "100054540785932", "page_name": "Printway Fulfillment"},
]

TEST_CHAT_ID = -1001234567890


def sep(title=""):
    print("\n" + "=" * 70)
    if title:
        print(f"  {title}")
        print("=" * 70)


# ── STEP 1: Kiểm tra API key ──────────────────────────────────────────────────
async def step1_check_api_key() -> bool:
    sep("STEP 1 — Kiểm tra TOOLVN_API_KEY")
    key = settings.TOOLVN_API_KEY
    if not key:
        logger.error("❌ TOOLVN_API_KEY chưa được set trong .env!")
        return False
    masked = key[:8] + "*" * (len(key) - 8)
    logger.info(f"✅ TOOLVN_API_KEY = {masked}")
    return True


# ── STEP 2: Kết nối DB và khởi tạo bảng ──────────────────────────────────────
async def step2_init_db():
    sep("STEP 2 — Kết nối DB và khởi tạo bảng")
    pg = await init_pg_pool()
    await init_groups_tables(pg)
    await init_fb_tables(pg)
    logger.info("✅ PostgreSQL OK — bảng fb_posts, fb_pages, fb_group_subscriptions sẵn sàng.")
    return pg


# ── STEP 3: Subscribe test fanpage ───────────────────────────────────────────
async def step3_subscribe(pg):
    sep(f"STEP 3 — Subscribe {len(TEST_PAGES)} fanpage vào chat_id={TEST_CHAT_ID}")
    async with pg.acquire() as con:
        await con.execute(
            "INSERT INTO groups (chat_id, chat_title) VALUES ($1, $2) "
            "ON CONFLICT (chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title",
            TEST_CHAT_ID,
            "Test Group",
        )
    for page in TEST_PAGES:
        await subscribe_fb_group(pg, TEST_CHAT_ID, page["page_id"], page["page_name"])
        logger.info(f"  ✅ {page['page_name']} ({page['page_id']})")


# ── STEP 4: Chạy poll và xem kết quả ─────────────────────────────────────────
async def step4_poll_and_verify(pg):
    yesterday = date.today() - timedelta(days=1)
    sep(f"STEP 4 — Chạy poll_fb_pages (chỉ lấy bài ngày {yesterday})")
    await poll_fb_pages()

    sep(f"STEP 5 — Xem dữ liệu fb_posts ngày {yesterday}")
    async with pg.acquire() as con:
        rows = await con.fetch(
            """
            SELECT page_name, post_id, created_at, reaction_count, comment_count,
                   SUBSTRING(message, 1, 80) AS msg_preview, post_url
            FROM fb_posts
            WHERE (created_at AT TIME ZONE 'Asia/Bangkok')::date = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            yesterday,
        )

    if not rows:
        logger.warning("⚠️  Không có bài nào ngày hôm qua — kiểm tra lại API hoặc subscription.")
        return

    logger.info(f"✅ Có {len(rows)} bài đăng ngày {yesterday} (hiển thị tối đa 20):\n")
    for r in rows:
        ts = r["created_at"].astimezone(TZ).strftime("%d/%m/%Y %H:%M") if r["created_at"] else "?"
        print(
            f"  [{r['page_name']}] {ts} | 👍{r['reaction_count']} 💬{r['comment_count']}\n"
            f"  {r['msg_preview'] or '(no text)'}...\n"
            f"  {r['post_url'] or '(no url)'}\n"
        )


# ── STEP 6: Chạy lần 2 — kiểm tra dedup ──────────────────────────────────────
async def step6_dedup_check(pg):
    sep("STEP 6 — Kiểm tra dedup (chạy poll lần 2)")
    async with pg.acquire() as con:
        count_before = await con.fetchval("SELECT COUNT(*) FROM fb_posts")

    await poll_fb_pages()

    async with pg.acquire() as con:
        count_after = await con.fetchval("SELECT COUNT(*) FROM fb_posts")

    if count_before == count_after:
        logger.info(f"✅ Dedup hoạt động đúng — số bài không thay đổi: {count_after}")
    else:
        logger.warning(
            f"⚠️  Số bài tăng từ {count_before} → {count_after} "
            "(có thể có bài mới được đăng giữa 2 lần chạy)"
        )


# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    print("\n" + "=" * 70)
    print("  FACEBOOK FANPAGE — INTEGRATION TEST")
    print(f"  Ngày chạy test : {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} (Asia/Bangkok)")
    print("=" * 70)

    if not await step1_check_api_key():
        sys.exit(1)

    pg = await step2_init_db()
    await step3_subscribe(pg)
    await step4_poll_and_verify(pg)
    await step6_dedup_check(pg)

    sep("KẾT QUẢ")
    print("✅ Test hoàn thành.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
