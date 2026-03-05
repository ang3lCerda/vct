from playwright.async_api import async_playwright
from app.db import players_collection

async def scrape_vlr_stats( event_url : str):
    await players_collection.delete_many({})

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            await page.wait_for_selector(".wf-table")

            # Extract rows
            rows = await page.query_selector_all(".wf-table tbody tr")
            results = []

            for index, row in enumerate(rows):
                cells = await row.query_selector_all("td")
                
                # Get player name and team
                player_div = await row.query_selector(".mod-player .text-of")
                team_div = await row.query_selector(".stats-player-country")
                
                player_name = await player_div.inner_text() if player_div else "Unknown"
                team_name = await team_div.inner_text() if team_div else "N/A"
                
                # Build the player document
                player_data = {
                    "player_id": index + 1,
                    "player": player_name.strip(),
                    "team": team_name.strip(),
                    "rnd": (await cells[2].inner_text()).strip(),
                    "rating": (await cells[3].inner_text()).strip(),
                    "acs": (await cells[4].inner_text()).strip(),
                    "kd": (await cells[5].inner_text()).strip(),
                    "kast": (await cells[6].inner_text()).strip(),
                    "adr": (await cells[7].inner_text()).strip(),
                    "kpr": (await cells[8].inner_text()).strip(),
                    "apr": (await cells[9].inner_text()).strip(),
                    "fkpr": (await cells[10].inner_text()).strip(),
                    "fdpr": (await cells[11].inner_text()).strip(),
                    "hs_percent": (await cells[12].inner_text()).strip(),
                    "cl_percent": (await cells[13].inner_text()).strip(),
                    "cl": (await cells[14].inner_text()).strip(),
                    "kmax": (await cells[15].inner_text()).strip(),
                    "k": (await cells[16].inner_text()).strip(),
                    "d": (await cells[17].inner_text()).strip(),
                    "a": (await cells[18].inner_text()).strip(),
                    "fk": (await cells[19].inner_text()).strip(),
                    "fd": (await cells[20].inner_text()).strip()
                }
                results.append(player_data)

            if results:
                await players_collection.insert_many(results)
                print(f"Successfully inserted {len(results)} players.")

            await browser.close()
            return results
            
        except Exception as e:
            print(f"Error during scrape: {e}")
            await browser.close()
            return None
        
async def get_matches_url(event_url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        completed_matches = []  

        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            matches = await page.query_selector_all("a.wf-module-item")   

            for match in matches:
                href = await match.get_attribute("href")
                
                if href:
                    if "tbd-valorant" not in href.lower():
                        full_url = f"https://www.vlr.gg{href}"
                        completed_matches.append(full_url)
                    else:
                        print(f"Skipping TBD match: {href}")

        except Exception as e:
            print(f"Error during scrape: {e}")
            return None
        
        finally:
            await browser.close()
        return list(set(completed_matches))

async def scrape_match_multikills(match_url : str ):


        return None

import asyncio

if __name__ == "__main__":
    urls = asyncio.run(get_matches_url("https://www.vlr.gg/event/matches/2760/valorant-masters-santiago-2026/?series_id=all"))
    print(urls)