import csv
from io import StringIO
import html

from aiogram import types, Dispatcher
from config.settings import settings
from db.postgres import (
    init_pg_pool,
    init_groups_tables,
    add_group,
    import_shops_from_csv,
    subscribe_group,
    unsubscribe_group,
    get_shops_for_group,
    init_fb_tables,
    subscribe_fb_group,
    unsubscribe_fb_group,
    get_fb_pages_for_group,
)


async def cmd_start(message: types.Message):
    """
    Khi bot được /start trong group hoặc chat riêng,
    khởi tạo tables nếu cần, lưu nhóm và phản hồi.
    """
    pg = await init_pg_pool()
    await init_groups_tables(pg)
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.username or str(chat_id)
    await add_group(pg, chat_id, chat_title)

    await message.reply(
        "👋 Chào! Dùng các lệnh sau:\n"
        "• `/import` + đính kèm CSV có 2 cột `shop_name,shop_id` để bulk add.\n"
        "• `/unsubscribe shop_name` để hủy đăng ký shop.\n"
        "• `/list` để xem danh sách shop đã subscribe."
    )


async def _get_caption_cmd(message: types.Message) -> str:
    """Trả về lệnh đầu tiên trong caption (vd: '/importfb'), chữ thường."""
    raw = (message.caption or "").strip()
    return raw.lower().split()[0] if raw else ""


async def cmd_document(message: types.Message):
    """Handler duy nhất cho mọi tin nhắn gửi kèm file — điều phối theo caption."""
    cmd = await _get_caption_cmd(message)
    if cmd == "/import":
        await _handle_import(message)
    elif cmd == "/importfb":
        await _handle_importfb(message)
    # caption khác → bỏ qua


async def _handle_import(message: types.Message):
    """
    Xử lý /import + file CSV (Etsy shops).
    """
    if not message.document:
        return

    pg = await init_pg_pool()
    await init_groups_tables(pg)
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.username or str(chat_id)
    await add_group(pg, chat_id, chat_title)

    file = await message.bot.get_file(message.document.file_id)
    data = await message.bot.download_file(file.file_path)
    text = data.read().decode("utf-8-sig", errors="ignore")

    reader = csv.DictReader(StringIO(text))
    # Chuẩn hóa fieldnames
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    shops = []
    for row in reader:
        # chuyển key về lowercase đã strip
        row = {k.strip().lower(): v for k, v in row.items()}

        name = row.get("shop_name")
        sid_str = row.get("shop_id")
        if not name or not sid_str:
            continue
        try:
            sid = int(sid_str)
        except ValueError:
            continue
        shops.append((name, sid))

    if not shops:
        await message.reply(
            "❌ CSV không tìm thấy cột `shop_name` hoặc `shop_id` nào hợp lệ."
        )
        return

    await import_shops_from_csv(pg, shops)
    for shop_name, shop_id in shops:
        await subscribe_group(pg, chat_id, shop_name, shop_id, chat_title)

    await message.reply(
        f"✅ Đã thêm và subscribe {len(shops)} shop. 5h thu thập & 6h báo cáo."
    )


async def cmd_unsubscribe(message: types.Message):
    """
    Xử lý /unsubscribe <shop_name>.
    """
    args = message.get_args().strip()
    if not args:
        await message.reply(
            "❌ Vui lòng cung cấp tên shop cần hủy, ví dụ: /unsubscribe MyShop"
        )
        return
    shop_name = args
    pg = await init_pg_pool()
    chat_id = message.chat.id
    # bỏ đăng ký
    await unsubscribe_group(pg, chat_id, shop_name)
    await message.reply(f"✅ Đã hủy subscribe shop '{shop_name}' cho nhóm.")


async def cmd_list(message: types.Message):
    """
    Xử lý /list, liệt kê shop đã subscribe.
    """
    pg = await init_pg_pool()
    chat_id = message.chat.id
    shops = await get_shops_for_group(pg, chat_id)  # [(shop_name, shop_id)]
    if not shops:
        await message.reply("❌ Nhóm chưa subscribe shop nào.")
        return

    lines = [f"• {name} (ID: {sid})" for name, sid in shops]
    text = "📦 *Danh sách shop đã subscribe:*\n\n" + "\n".join(lines)
    await message.reply(text)


async def _handle_importfb(message: types.Message):
    """
    /importfb + đính kèm file CSV có 2 cột: page_id, page_name
    Đăng ký theo dõi nhiều Facebook fanpage cùng lúc.
    """
    if not message.document:
        return

    pg = await init_pg_pool()
    await init_groups_tables(pg)
    await init_fb_tables(pg)
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.username or str(chat_id)
    await add_group(pg, chat_id, chat_title)

    file = await message.bot.get_file(message.document.file_id)
    data = await message.bot.download_file(file.file_path)
    text = data.read().decode("utf-8-sig", errors="ignore")

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        await message.reply("❌ File CSV rỗng hoặc không đọc được.")
        return
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    pages = []
    for row in reader:
        row = {k.strip().lower(): v for k, v in row.items()}
        page_id = (row.get("page_id") or "").strip()
        page_name = (row.get("page_name") or "").strip()
        if not page_id:
            continue
        if not page_name:
            page_name = page_id
        pages.append((page_id, page_name))

    if not pages:
        await message.reply(
            "❌ CSV không tìm thấy cột `page_id` hoặc không có dữ liệu hợp lệ."
        )
        return

    for page_id, page_name in pages:
        await subscribe_fb_group(pg, chat_id, page_id, page_name)

    lines = [f"• {name} (`{pid}`)" for pid, name in pages]
    await message.reply(
        f"✅ Đã subscribe *{len(pages)} fanpage*:\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def cmd_addfb(message: types.Message):
    """
    /addfb <page_id> <page_name>
    Đăng ký theo dõi Facebook fanpage. page_name có thể có khoảng trắng.
    Ví dụ: /addfb 123456789 Trang Của Tôi
    """
    args = message.get_args().strip()
    if not args:
        await message.reply(
            "❌ Cú pháp: `/addfb <page_id> <tên_trang>`\n"
            "Ví dụ: `/addfb 123456789 Fanpage Của Tôi`"
        )
        return

    parts = args.split(None, 1)
    page_id = parts[0]
    page_name = parts[1] if len(parts) > 1 else page_id

    pg = await init_pg_pool()
    await init_groups_tables(pg)
    await init_fb_tables(pg)
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.username or str(chat_id)
    await add_group(pg, chat_id, chat_title)
    await subscribe_fb_group(pg, chat_id, page_id, page_name)
    await message.reply(
        f"✅ Đã subscribe fanpage *{page_name}* (`{page_id}`).\n"
        "Bot sẽ tự động thông báo bài đăng mới mỗi 30 phút."
    )


async def cmd_removefb(message: types.Message):
    """
    /removefb <page_id>
    Hủy đăng ký theo dõi Facebook fanpage.
    """
    page_id = message.get_args().strip()
    if not page_id:
        await message.reply("❌ Cú pháp: `/removefb <page_id>`")
        return

    pg = await init_pg_pool()
    await init_fb_tables(pg)
    chat_id = message.chat.id
    await unsubscribe_fb_group(pg, chat_id, page_id)
    await message.reply(f"✅ Đã hủy subscribe fanpage `{page_id}`.")


async def cmd_listfb(message: types.Message):
    """
    /listfb — Liệt kê các Facebook fanpage đang theo dõi.
    """
    pg = await init_pg_pool()
    await init_fb_tables(pg)
    chat_id = message.chat.id
    pages = await get_fb_pages_for_group(pg, chat_id)
    if not pages:
        await message.reply(
            "❌ Nhóm chưa subscribe fanpage nào.\nDùng `/addfb <page_id> <tên>` để thêm."
        )
        return

    lines = [
        f"• [{name}](https://www.facebook.com/{pid}) (`{pid}`)" for pid, name in pages
    ]
    text = "📰 *Danh sách Facebook fanpage đang theo dõi:*\n\n" + "\n".join(lines)
    await message.reply(text, disable_web_page_preview=True)


def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"])
    dp.register_message_handler(cmd_document, content_types=["document"])
    dp.register_message_handler(cmd_unsubscribe, commands=["unsubscribe"])
    dp.register_message_handler(cmd_list, commands=["list"])
    dp.register_message_handler(cmd_addfb, commands=["addfb"])
    dp.register_message_handler(cmd_removefb, commands=["removefb"])
    dp.register_message_handler(cmd_listfb, commands=["listfb"])
