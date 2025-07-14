import aiohttp
from config.settings import settings

BASE_URL = f"https://api.telegram.org/bot{settings.BOT_TOKEN}"

async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """
    Gửi 1 message đơn, dùng cho daily summary và mọi trường hợp khác.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BASE_URL}/sendMessage", json=payload)
