from playwright.async_api import async_playwright
import asyncio
import json
from datetime import datetime
import re
from urllib.parse import urlparse, parse_qs

def extract_game_id(url: str):
  
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    game_id = query_params.get("game", [None])[0]
    return game_id

def extract_event_id(url: str):
    match = re.search(r"/event/(?:matches/|stats/|performance/)?(\d+)", url)
    if match:
        return match.group(1) 
    return None

def extract_match_id(url: str):
    match = re.search(r"vlr\.gg/(\d+)", url)
    if match:
        return match.group(1)
    return None

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
        
async def get_matches_url(event_id: str):

    event_url= f"https://www.vlr.gg/event/matches/{event_id}"

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
        return  list(set(completed_matches))

    


async def scrape_performance(match_url: str, event_id:str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        )

        await context.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in ["image", "font", "stylesheet"]
            else route.continue_()
        ))
        match_id=extract_match_id(match_url)
        page = await context.new_page()

        try:
            base_url = match_url.rstrip('/')
            await page.goto(f"{base_url}/?game=all&tab=performance", wait_until="domcontentloaded")

            # collect map URLs
            tabs = await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch")

            map_urls = []
            for tab in tabs:
                game_id = await tab.get_attribute("data-game-id")
                is_disabled = await tab.get_attribute("data-disabled")
                if game_id and is_disabled == "0":
                    map_urls.append(f"{base_url}/?game={game_id}&tab=performance")

            all_maps_data = []

            for url in map_urls:
                await page.goto(url, wait_until="domcontentloaded")
                game_id=extract_game_id(url)

                try:
                    rows = await page.locator("table.mod-adv-stats tbody tr").all()

                    map_stats = []

                    for row in rows[1:]:  
                        cells = await row.locator("td").all_inner_texts()
                        if len(cells) < 14:
                            continue

                        name_text = await row.locator("div > div").first.inner_text()
                        player_name = name_text.split('\n')[0].strip()

                        map_stats.append({
                            "name": player_name,
                            "2k": cells[2].strip(),
                            "3k": cells[3].strip(),
                            "4k": cells[4].strip(),
                            "5k": cells[5].strip(),
                            "1v1": cells[6].strip(),
                            "1v2": cells[7].strip(),
                            "1v3": cells[8].strip(),
                            "1v4": cells[9].strip(),
                            "1v5": cells[10].strip(),
                            "econ": cells[11].strip(),
                            "pl": cells[12].strip(),
                            "de": cells[13].strip(),
                            "event_id": event_id,
                            "match_id": match_id,
                            "game_id": game_id
                        })

                    all_maps_data.append({
                        "url": url,
                        "stats": map_stats
                    })

                    print(f"Done: {url}")

                except Exception as e:
                    print(f"Failed to parse {url}: {e}")

            await browser.close()
            return all_maps_data

        except Exception as e:
            print(f"Critical error: {e}")
            await browser.close()
            return []

async def scrape_match_stats(match_url: str, event_id: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            base_url = match_url.rstrip('/')
            await page.goto(base_url, wait_until="domcontentloaded")
            match_id=extract_match_id(match_url)


            map_tabs = await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch")
            map_urls = []
            
            for t in map_tabs:
                game_id = await t.get_attribute("data-game-id")
                is_disabled = await t.get_attribute("data-disabled")
                
                if game_id and is_disabled == "0":
                    map_urls.append(f"{base_url}/?game={game_id}&tab=overview")
            
            results = []

            for url in map_urls:
                await page.goto(url, wait_until="domcontentloaded")
                game_id=extract_game_id(url)

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
                        if len(cells) >= 13:
                            map_data["players"].append({
                                "name": (await row.locator(".mod-player").inner_text()).split('\n')[0].strip(),
                                "acs": (await cells[2].locator("span.mod-both").first.inner_text()).strip(),
                                "kills": (await cells[3].locator("span.mod-both").first.inner_text()).strip(),
                                "deaths": (await cells[4].locator("span.mod-both").first.inner_text()).strip(),
                                "assists": (await cells[5].locator("span.mod-both").first.inner_text()).strip(),
                                "k_diff": (await cells[6].locator("span.mod-both").first.inner_text()).strip(),
                                "kast": (await cells[7].locator("span.mod-both").first.inner_text()).strip(),
                                "adr": (await cells[8].locator("span.mod-both").first.inner_text()).strip(),
                                "hs_perc": (await cells[9].locator("span.mod-both").first.inner_text()).strip(),
                                "fk": (await cells[10].locator("span.mod-both").first.inner_text()).strip(),
                                "fd": (await cells[11].locator("span.mod-both").first.inner_text()).strip(),
                                "fk_diff": (await cells[12].locator("span.mod-both").first.inner_text()).strip(),
                                "event_id": event_id,
                                "match_id": match_id,
                                "game_id": game_id
                            })
                
                results.append(map_data)
                print(f"Done: {url}")

            await browser.close()
            return results

        except Exception as e:
            print(f"Error: {e}")
            await browser.close()
            return []

async def scrape_all_matches(matches: list[str], match_type: int, event_id:str):
    results = []
    prefix = "performance" if match_type != 0 else "overview"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_scrape_{timestamp}.json"
    for match_url in matches:
        print(f"Testing match: {match_url}")
        
        if match_type != 0:
                data = await scrape_performance(match_url,event_id)
        else:
                data = await scrape_match_stats(match_url,event_id)
            
        results.append(data)
        print(f"Successfully finished: {match_url}")
            
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4)
            
    return results

async def main():
    event_id="2760"
    
    print("Fetching match URLs...")

    matches_url = await get_matches_url(event_id)
    print (matches_url)

    print(f"Found {len(matches_url)} matches. Starting sequential test loop...")
    
    results = await scrape_all_matches(matches_url, match_type=1, event_id=event_id)
    
    print(f"Scraped {len(results)} matches successfully.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())