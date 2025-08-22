# src/bot/bot.py

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from bot.handlers import cmd_start, cmd_import
from db.postgres import init_pg_pool
from config.settings import settings

# Khởi tạo Bot & Dispatcher
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(bot)

# 1) Đăng ký /start như bình thường
dp.register_message_handler(cmd_start, commands=['start'])

# 2) Đăng ký cmd_import cho các message chứa document và caption bắt đầu bằng "/import"
dp.register_message_handler(
    cmd_import,
    lambda msg: msg.document is not None
                and (msg.caption or "").strip().lower().startswith('/import'),
    content_types=['document']
)

async def on_startup(dispatcher: Dispatcher):
    # 3) Tạo pool Postgres và gán vào dispatcher.data để handler dùng chung
    pg = await init_pg_pool()
    dispatcher.data['pg'] = pg

if __name__ == '__main__':
    # 4) Bắt đầu polling
    executor.start_polling(dp, on_startup=on_startup)

