from aiogram import types
from db.postgres import (add_group, subscribe_group, unsubscribe_group, get_shops_for_group)

async def cmd_start(message: types.Message):
    await add_group(message.bot['pg'], message.chat.id)
    print(f">>> cmd_start: added group {message.chat.id}")
    await message.reply(
        "👋 Chào! Bạn có thể dùng:\n"
        "/follow <shop_name> – theo dõi shop\n"
        "/unfollow <shop_name> – bỏ theo dõi\n"
        "/list – xem shop đang theo dõi"
    )


async def cmd_follow(message: types.Message):
    shop = message.get_args().strip()
    if not shop:
        return await message.reply("❗ Vui lòng cung cấp tên shop. Ví dụ: /follow abcestore")
    await add_group(message.bot['pg'], message.chat.id)
    await subscribe_group(message.bot['pg'], message.chat.id, shop)
    await message.reply(f"✅ Bạn đã theo dõi *{shop}*", parse_mode='Markdown')

async def cmd_unfollow(message: types.Message):
    await add_group(message.bot['pg'], message.chat.id)
    shop = message.get_args().strip()
    if not shop:
        return await message.reply("❗ Vui lòng cung cấp tên shop. Ví dụ: /unfollow abcestore")
    await unsubscribe_group(message.bot['pg'], message.chat.id, shop)
    await message.reply(f"❌ Bạn đã bỏ theo dõi *{shop}*", parse_mode='Markdown')

async def cmd_list(message: types.Message):
    await add_group(message.bot['pg'], message.chat.id)
    shops = await get_shops_for_group(message.bot['pg'], message.chat.id)
    if not shops:
        return await message.reply("📭 Bạn chưa theo dõi shop nào.")
    text = "📦 Danh sách shop bạn đang theo dõi:\n" + "\n".join(f"• {s}" for s in shops)
    await message.reply(text)
