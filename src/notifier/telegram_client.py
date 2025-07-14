import aiohttp
from config.settings import settings

BASE_URL = f"https://api.telegram.org/bot{settings.BOT_TOKEN}"

async def send_message(chat_id: int, text: str, parse_mode='Markdown'):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    async with aiohttp.ClientSession() as session:
        await session.post(f"{BASE_URL}/sendMessage", json=payload)

async def notify_listing(shop_name: str, listing: dict, chat_ids: list[int]):
    dt_str = listing.get("create_date", "Unknown")

    text = (
        f"🛒 *{shop_name}* vừa đăng sản phẩm mới:\n"
        f"• *Title:* {listing.get('title', '')}\n"
        f"• *Price:* {listing.get('price', '?')} {listing.get('currency', '')}\n"
        f"• *Link:* [Xem chi tiết]({listing.get('url')})\n"
        f"• *Image:* {listing.get('thumbnail') or 'Không có'}\n"
        f"• *Datetime:* {dt_str}"
    )

    for chat_id in chat_ids:
        await send_message(chat_id, text)
