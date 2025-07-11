import feedparser
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup

async def fetch_latest_from_rss(shop_name: str) -> dict | None:
    url = f"https://www.etsy.com/shop/{shop_name}/rss"
    feed = feedparser.parse(url)
    if not feed.entries:
        return None
    entry = feed.entries[0]
    link = entry.link
    listing_id = str(link).rstrip('/').split('/')[-2] if '/listing/' in str(link) else entry.id
    if isinstance(entry.published_parsed, tuple):
        pub_date = datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d %H:%M')
    else:
        pub_date = "Unknown"
    return {'listing_id': listing_id, 'title': entry.title, 'link': link, 'pub_date': pub_date}

async def scrape_listing_page(listing_url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(listing_url) as resp:
            html = await resp.text()
    soup = BeautifulSoup(html, 'html.parser')
    price_tag = soup.find('meta', property='og:price:amount')
    currency_tag = soup.find('meta', property='og:price:currency')
    img_tag = soup.find('meta', property='og:image')
    return {
        'price': price_tag['content'] if price_tag else '?',
        'currency': currency_tag['content'] if currency_tag else '',
        'thumbnail': img_tag['content'] if img_tag else None,
    }==-=-=-==--=--=--=-=--=-=-=-=-