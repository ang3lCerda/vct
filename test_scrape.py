import asyncio
import sys
sys.path.insert(0, "/Users/angelcerda/vct")

from app.scrape import get_matches_url

async def main():
    urls = await get_matches_url("2860")
    print(f"Total completed matches: {len(urls)}\n")
    for url in sorted(urls):
        print(url)

asyncio.run(main())
