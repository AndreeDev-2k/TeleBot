# src/bot/bot.py

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from bot.handlers import register_handlers
from db.postgres import init_pg_pool
from config.settings import settings

# Khởi tạo Bot & Dispatcher
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(bot)

# Đăng ký tất cả handlers
register_handlers(dp)


async def on_startup(dispatcher: Dispatcher):
    pg = await init_pg_pool()
    dispatcher.data["pg"] = pg


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
