from playwright.async_api import async_playwright
from app.db import players_collection
import asyncio

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

        except Exception as e:
            print(f"Error during scrape: {e}")
            return None
        
        finally:
            await browser.close()
        return list(set(completed_matches))
    


async def scrape_performance(match_url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            base_url = match_url.rstrip('/')
            await page.goto(f"{base_url}/?game=all&tab=performance", wait_until="domcontentloaded")

            nav_item_selector = ".vm-stats-gamesnav-item.js-map-switch"
            await page.wait_for_selector(nav_item_selector, timeout=10000)
            map_tabs = await page.query_selector_all(nav_item_selector)
            
            map_urls = []
            for tab in map_tabs:
                game_id = await tab.get_attribute("data-game-id")
                if game_id:
                    map_urls.append(f"{base_url}/?game={game_id}&tab=performance")
            
            all_maps_data = []

            for url in map_urls:
                await page.goto(url, wait_until="domcontentloaded")

                table_locator = page.locator("table.mod-adv-stats:visible")
                try:
                    await table_locator.wait_for(state="visible", timeout=7000)
                    
                    rows = await table_locator.locator("tbody tr").all()
                    map_stats = []
                    
                    for i in range(1, len(rows)):
                        row = rows[i]
                        cells = await row.locator("td").all()
                        
                        if len(cells) >= 14:
                            name_el = row.locator("div > div").first
                            name_text = await name_el.inner_text()
                            player_name = name_text.split('\n')[0].strip()
                            
                            async def get_val(cell_locator):
                                text = (await cell_locator.inner_text()).strip()
                                return int(text) if text.isdigit() else 0

                            map_stats.append({
                                "name": player_name,
                                "multi_kills": {
                                    "4k": await get_val(cells[4]),
                                    "5k": await get_val(cells[5]),
                                }
                            })
                    
                    all_maps_data.append({"url": url, "stats": map_stats})
                    # print(f"Scraped {len(map_stats)} players.")

                except Exception as e:
                    print(f"Failed to find table on {url}: {e}")

            await browser.close()
            return all_maps_data

        except Exception as e:
            print(f"Critical error: {e}")
            await browser.close()
            return []


async def scrape_match_stats(match_url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            base_url = match_url.rstrip('/')
            await page.goto(base_url, wait_until="domcontentloaded")

            # 1. Get the map links
            map_tabs = await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch")
            map_urls = [f"{base_url}/?game={await t.get_attribute('data-game-id')}&tab=overview" for t in map_tabs if await t.get_attribute('data-game-id')]
            
            results = []

            for url in map_urls:
                await page.goto(url, wait_until="domcontentloaded")
                
                # Wait for the first table to show up
                table_selector = "table.wf-table-inset.mod-overview:visible"
                await page.locator(table_selector).first.wait_for(state="visible", timeout=10000)
                
                # Get both team tables
                tables = await page.locator(table_selector).all()
                map_data = {"url": url, "players": []}

                for table in tables:
                    rows = await table.locator("tbody tr").all()
                    for row in rows:
                        cells = await row.locator("td").all()
                        
                        if len(cells) >= 4:
                            # Get Name
                            name = (await row.locator(".mod-player").inner_text()).split('\n')[0].strip()
                            
                            # Get Stats as raw text first to avoid crashes
                            # index 2 = ACS, index 3 = Kills
                            raw_acs = await cells[2].locator("span.mod-both").first.inner_text()
                            raw_kills = await cells[3].locator("span.mod-both").first.inner_text()
                            
                            # Simple conversion: float -> int handles the '1.37' issue
                            map_data["players"].append({
                                "name": name,
                                "acs": float(raw_acs.strip()),  # Keeps it as 227.0 or 1.37
                                "kills": int(float(raw_kills.strip())) # Kills are usually whole numbers
                            })
                
                results.append(map_data)
                print(results)
                print(f"Done: {url}")

            await browser.close()
            return results

        except Exception as e:
            print(f"Error: {e}")
            await browser.close()
            return []

async def main():
    url = "https://www.vlr.gg/626547/paper-rex-vs-all-gamers-valorant-masters-santiago-2026-lr2"
    await scrape_match_stats(url)

if __name__ == "__main__":
    asyncio.run(main())