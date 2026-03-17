import re
from datetime import datetime, timezone
import aiohttp
from typing import List, Dict, Optional

from config.settings import settings

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


async def fetch_fb_posts(page_id: str, limit: int = 10) -> List[Dict]:
    """
    Lấy những bài đăng mới nhất từ Facebook fanpage qua API tool.vn.

    tool.vn yêu cầu:
      - POST tới URL có ?key=... (query string)
      - Body dạng form-urlencoded: id=<page_id>&limit=<N>

    Args:
        page_id: Facebook page ID.
        limit: Số lượng bài đăng cần lấy.

    Returns:
        Danh sách các bài đăng (mỗi bài là một dict).
    """
    url = f"{TOOLVN_FB_URL}?key={settings.TOOLVN_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            data={"id": page_id, "limit": limit},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

    # Response structure: {"status": "success", "posts": [...]}
    if isinstance(data, dict) and "posts" in data:
        return data["posts"]
    if isinstance(data, list):
        return data
    return []
