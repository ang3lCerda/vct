import asyncio
import sys
import json
sys.path.insert(0, "/Users/angelcerda/vct")

from app.scrape import scrape_match_comps

MATCH_URL = "https://www.vlr.gg/626549/paper-rex-vs-g2-esports-valorant-masters-santiago-2026-lr3"

async def main():
    results = await scrape_match_comps(MATCH_URL, "2760")
    print(f"Records returned: {len(results)}\n")
    print(json.dumps(results, indent=2))

asyncio.run(main())
