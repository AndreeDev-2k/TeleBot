import asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.utils import executor
from config.settings import settings
from db.postgres import init_pg_pool
from bot.handlers import cmd_start, cmd_follow, cmd_unfollow, cmd_list

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
router = Router()

def register_handlers():
    router.message.register(cmd_start, commands=['start'])
    router.message.register(cmd_follow, commands=['follow'])
    router.message.register(cmd_unfollow, commands=['unfollow'])
    router.message.register(cmd_list, commands=['list'])

dp.include_router(router)

async def on_startup(dispatcher):
    dispatcher['pg'] = await init_pg_pool()
    register_handlers()

if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
