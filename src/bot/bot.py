import asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from config.settings import settings
from db.postgres import init_pg_pool
from bot.handlers import cmd_start, cmd_follow, cmd_unfollow, cmd_list

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(bot)

def register_handlers():
    dp.register_message_handler(cmd_start, commands=['start'])
    dp.register_message_handler(cmd_follow, commands=['follow'])
    dp.register_message_handler(cmd_unfollow, commands=['unfollow'])
    dp.register_message_handler(cmd_list, commands=['list'])

async def on_startup(dispatcher):
    pool = await init_pg_pool()
    dispatcher["pg"] = pool
    dispatcher.bot['pg'] = pool
    register_handlers()

if __name__ == '__main__':
<<<<<<< HEAD
    executor.start_polling(dp, on_startup=on_startup)
=======
    executor.start_polling(dp, on_startup=on_startup)

>>>>>>> 8058252 ( local changes)
