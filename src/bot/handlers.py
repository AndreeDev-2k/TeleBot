from aiogram import types
from db.postgres import (
    add_group,
    subscribe_group,
    unsubscribe_group,
    get_shops_for_group
)

async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    await add_group(message.bot['pg'], chat_id)
    await message.reply(
        "👋 Chào! Dùng:\n"
        "/follow <shop> — nhóm theo dõi shop\n"
        "/unfollow <shop> — nhóm bỏ theo dõi\n"
        "/list — xem shop nhóm đang theo dõi"
    )

async def cmd_follow(message: types.Message):
    shop = message.get_args().strip()
    if not shop:
        return await message.reply("❗ Vui lòng cung cấp tên shop. Ví dụ: /follow myshop")
    chat_id = message.chat.id
    await subscribe_group(message.bot['pg'], chat_id, shop)
    await message.reply(f"✅ Nhóm đã theo dõi *{shop}*", parse_mode='Markdown')

async def cmd_unfollow(message: types.Message):
    shop = message.get_args().strip()
    if not shop:
        return await message.reply("❗ Vui lòng cung cấp tên shop. Ví dụ: /unfollow myshop")
    chat_id = message.chat.id
    await unsubscribe_group(message.bot['pg'], chat_id, shop)
    await message.reply(f"❌ Nhóm đã bỏ theo dõi *{shop}*", parse_mode='Markdown')

async def cmd_list(message: types.Message):
    chat_id = message.chat.id
    shops = await get_shops_for_group(message.bot['pg'], chat_id)
    if not shops:
        return await message.reply("📭 Nhóm chưa theo dõi shop nào.")
    text = "📦 Shop nhóm đang theo dõi:\n" + "\n".join(f"• {s}" for s in shops)
    await message.reply(text)
