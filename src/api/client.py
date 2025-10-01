import re
from datetime import datetime, timezone
import aiohttp
from typing import List, Dict, Optional

BASE = "https://www.etsy.com"


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
