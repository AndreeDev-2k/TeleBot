import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

BASE = "https://www.etsy.com"
TOOLVN_FB_URL = "https://tool.vn/api/facebook/get-post-facebook"


async def get_shop_id(session: aiohttp.ClientSession, shop_name: str) -> Optional[str]:
    url = f"{BASE}/shop/{shop_name}"
    async with session.get(url) as resp:
        html = await resp.text()
    m = re.search(r'"(?:shopId|shop_id|deep_link_shop_id)"\s*:\s*"?(\d+)"?', html)
    if m:
        sid = m.group(1)
        print(f"[API] Found shopId={sid} for {shop_name}")
        return sid
    else:
        print(f"[API] Cannot find shopId for {shop_name}")
        return None


async def fetch_recent_listings(
    shop_name: str, cutoff: datetime, limit: int = 100
) -> List[Dict[str, datetime]]:
    listings = []
    offset = 0

    async with aiohttp.ClientSession() as session:
        shop_id = await get_shop_id(session, shop_name)
        if not shop_id:
            return []

        while True:
            api = (
                f"{BASE}/api/v3/internal/shops/{shop_id}/listings/active"
                f"?limit={limit}&offset={offset}"
                "&sort_on=created&sort_order=desc"
            )
            print(f"[API] GET {api}")
            async with session.get(api) as resp:
                if resp.status != 200:
                    print(f"[API] {shop_name} offset={offset} → HTTP {resp.status}")
                    break
                data = await resp.json()
            results = data.get("results", [])
            print(
                f"[API] {shop_name}: fetched {len(results)} items " f"(offset={offset})"
            )
            if not results:
                break

            for item in results:
                ts = item.get("creation_tsz")
                if not ts:
                    continue
                created = datetime.fromtimestamp(ts, tz=timezone.utc)
                if created < cutoff:
                    return listings
                listings.append(
                    {"listing_id": str(item["listing_id"]), "created": created}
                )

            offset += limit

    return listings


# Headers dùng chung cho mọi request tới tool.vn
TOOLVN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Origin": "https://tool.vn",
    "Referer": "https://tool.vn/",
}


def create_toolvn_session() -> aiohttp.ClientSession:
    """Tạo một aiohttp session dùng chung cho nhiều request tới tool.vn."""
    return aiohttp.ClientSession(
        headers=TOOLVN_HEADERS,
        timeout=aiohttp.ClientTimeout(total=60),
    )


async def fetch_fb_posts(
    page_id: str, limit: int = 10, session: Optional[aiohttp.ClientSession] = None
) -> List[Dict]:
    """
    Lấy những bài đăng mới nhất từ Facebook fanpage qua API tool.vn.

    Args:
        page_id: Facebook page ID.
        limit: Số lượng bài đăng cần lấy.
        session: aiohttp session dùng chung (tái sử dụng connection pool).
                 Nếu None sẽ tự tạo session mới.

    Returns:
        Danh sách các bài đăng (mỗi bài là một dict).
    """
    limit = min(limit, 20)
    url = f"{TOOLVN_FB_URL}?key={settings.TOOLVN_API_KEY}"
    max_attempts = 3
    backoff = 2.0

    # Dùng session được truyền vào hoặc tự tạo mới
    own_session = session is None
    sess = session or create_toolvn_session()

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                async with sess.post(
                    url,
                    data={"id": page_id, "limit": limit},
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)

                if isinstance(data, dict):
                    inner = data.get("data") or {}
                    if isinstance(inner, dict) and "posts" in inner:
                        return inner["posts"]
                    if "posts" in data:
                        return data["posts"]
                if isinstance(data, list):
                    return data
                logger.warning(
                    f"[FB] Unexpected response format for page {page_id}: {str(data)[:200]}"
                )
                return []

            except (asyncio.TimeoutError, aiohttp.ServerConnectionError, aiohttp.ServerDisconnectedError) as e:
                logger.warning(
                    f"[FB] Attempt {attempt}/{max_attempts} transient error for page {page_id}: "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < max_attempts:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise
            except aiohttp.ClientResponseError as e:
                logger.error(
                    f"[FB] HTTP error {e.status} for page {page_id}: {e.message}"
                )
                raise
    finally:
        if own_session:
            await sess.close()

    return []
