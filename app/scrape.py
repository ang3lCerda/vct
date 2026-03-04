from fastapi import FastAPI
from playwright.async_api import async_playwright
import time
import asyncio

app = FastAPI()

internal_store = {
    "last_scrape_time": 0,
    "data": []
}

async def scrape_vlr_stats():
    async with async_playwright() as p:
        # Launching with a specific user_agent to look like a real Mac user
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto("https://www.vlr.gg/event/stats/2760/valorant-masters-santiago-2026", wait_until="domcontentloaded")
            # Wait for the table to render
            await page.wait_for_selector(".wf-table")

            # Extract rows
            rows = await page.query_selector_all(".wf-table tbody tr")
            results = []

            for row in rows: 
                cells = await row.query_selector_all("td")
                
                # Get player name and team
                player_div = await row.query_selector(".mod-player .text-of")
                team_div = await row.query_selector(".stats-player-country")
                
                player_name = await player_div.inner_text() if player_div else "Unknown"
                team_name = await team_div.inner_text() if team_div else "N/A"
                
                # Column 2 is Rating, 3 is ACS, 4 is K:D
                results.append({
                    "player": player_name.strip(),
                    "team": team_name.strip(),
                    "rnd": (await cells[1].inner_text()).strip(),
                    "rating": (await cells[2].inner_text()).strip(),
                    "acs": (await cells[3].inner_text()).strip(),
                    "kd": (await cells[4].inner_text()).strip(),
                    "kast": (await cells[5].inner_text()).strip(),
                    "adr": (await cells[6].inner_text()).strip(),
                    "kpr": (await cells[7].inner_text()).strip(),
                    "apr": (await cells[8].inner_text()).strip(),
                    "fkpr": (await cells[9].inner_text()).strip(),
                    "fdpr": (await cells[10].inner_text()).strip(),
                    "hs_percent": (await cells[11].inner_text()).strip(),
                    "cl_percent": (await cells[12].inner_text()).strip(),
                    "cl": (await cells[13].inner_text()).strip(),
                    "kmax": (await cells[14].inner_text()).strip(),
                    "k": (await cells[15].inner_text()).strip(),
                    "d": (await cells[16].inner_text()).strip(),
                    "a": (await cells[17].inner_text()).strip(),
                    "fk": (await cells[18].inner_text()).strip(),
                    "fd": (await cells[19].inner_text()).strip()
                })

            await browser.close()
            return results
        except Exception as e:
            print(f"Error during scrape: {e}")
            await browser.close()
            return None

@app.get("/stats")
async def get_vlr_stats():
    now = time.time()
    
    # Cache logic: 1800 seconds = 30 minutes
    if internal_store["data"] and (now - internal_store["last_scrape_time"] < 1800):
        return {"source": "cache", "data": internal_store["data"]}

    # Fetch fresh data
    fresh_data = await scrape_vlr_stats()
    
    if fresh_data:
        internal_store["data"] = fresh_data
        internal_store["last_scrape_time"] = now
        return {"source": "live", "data": fresh_data}
    
    return {"error": "Could not fetch data from VLR"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)