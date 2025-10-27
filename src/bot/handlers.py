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
    get_shops_for_group
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

async def cmd_import(message: types.Message):
    """
    Xử lý /import + file CSV.
    """
    if not message.document or not (message.caption or "").strip().lower().startswith("/import"):
        return

    pg = await init_pg_pool()
    await init_groups_tables(pg)
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.username or str(chat_id)
    await add_group(pg, chat_id, chat_title)

    file = await message.bot.get_file(message.document.file_id)
    data = await message.bot.download_file(file.file_path)
    text = data.read().decode('utf-8-sig', errors='ignore')

    reader = csv.DictReader(StringIO(text))
    # Chuẩn hóa fieldnames
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    shops = []
    for row in reader:
        # chuyển key về lowercase đã strip
        row = {k.strip().lower(): v for k, v in row.items()}

        name = row.get('shop_name')
        sid_str  = row.get('shop_id')
        if not name or not sid_str:
            continue
        try:
            sid = int(sid_str)
        except ValueError:
            continue
        shops.append((name, sid))

    if not shops:
        await message.reply("❌ CSV không tìm thấy cột `shop_name` hoặc `shop_id` nào hợp lệ.")
        return

    await import_shops_from_csv(pg, shops)
    for shop_name, shop_id in shops:
        await subscribe_group(pg, chat_id, shop_name, shop_id, chat_title)

    await message.reply(f"✅ Đã thêm và subscribe {len(shops)} shop. 5h thu thập & 6h báo cáo.")

async def cmd_unsubscribe(message: types.Message):
    """
    Xử lý /unsubscribe <shop_name>.
    """
    args = message.get_args().strip()
    if not args:
        await message.reply("❌ Vui lòng cung cấp tên shop cần hủy, ví dụ: /unsubscribe MyShop")
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


def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'])
    dp.register_message_handler(cmd_import, content_types=['document'])
    dp.register_message_handler(cmd_unsubscribe, commands=['unsubscribe'])
    dp.register_message_handler(cmd_list, commands=['list'])

