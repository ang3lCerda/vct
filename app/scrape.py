from playwright.async_api import async_playwright
import asyncio
import json
from datetime import datetime
import re
from urllib.parse import urlparse, parse_qs

def clean_stat(value: str) -> str:
    return value.split("\n")[0].strip() if value else ""

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

    
async def scrape_performance(match_url: str, event_id: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        )

        await context.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in ["image", "font", "stylesheet"]
            else route.continue_()
        ))

        match_id = extract_match_id(match_url)
        page = await context.new_page()

        try:
            base_url = match_url.rstrip("/")
            await page.goto(f"{base_url}/?game=all&tab=performance", wait_until="domcontentloaded")

            # collect valid game_ids
            tabs = await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch")

            map_urls = []
            for tab in tabs:
                game_id = await tab.get_attribute("data-game-id")
                is_disabled = await tab.get_attribute("data-disabled")

                if game_id and is_disabled == "0":
                    map_urls.append((game_id, f"{base_url}/?game={game_id}&tab=performance"))

            all_maps_data = []

            for game_id, url in map_urls:
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    # wait for page to render stats
                    await page.wait_for_selector("table.mod-adv-stats")

                    # ✅ FIX: anchor to correct game container (NOT XPath)
                    game_container = page.locator(
                        f'div.vm-stats-game[data-game-id="{game_id}"]:visible'
                    ).first

                    await game_container.wait_for(state="visible")

                    table = game_container.locator("table.mod-adv-stats").first
                    await table.wait_for(state="visible")

                    rows = await table.locator("tbody tr").all()

                    map_stats = []

                    for row in rows[1:]:
                        cells = await row.locator("td").all_inner_texts()
                        if len(cells) < 14:
                            continue

                        name_text = await row.locator("div > div").first.inner_text()
                        player_name = name_text.split("\n")[0].strip()

                        map_stats.append({
                            "name": player_name,

                            "2k": clean_stat(cells[2]),
                            "3k": clean_stat(cells[3]),
                            "4k": clean_stat(cells[4]),
                            "5k": clean_stat(cells[5]),
                            "1v1": clean_stat(cells[6]),
                            "1v2": clean_stat(cells[7]),
                            "1v3": clean_stat(cells[8]),
                            "1v4": clean_stat(cells[9]),
                            "1v5": clean_stat(cells[10]),

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

                    # print(f"Done: {url}")

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
                # print(f"`: {url}")

            await browser.close()
            return results

        except Exception as e:
            print(f"Error: {e}")
            await browser.close()
            return []


async def scrape_match_scores(match_url: str, event_id: str):
    """Scrapes all data needed for scoring: series result, per-map round scores, and
    per-map player stats with rating and team assignment."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        await context.route("**/*", lambda route: (
            route.abort() if route.request.resource_type in ["image", "font", "stylesheet"]
            else route.continue_()
        ))
        page = await context.new_page()

        try:
            base_url = match_url.rstrip("/")
            match_id = extract_match_id(match_url)

            await page.goto(base_url, wait_until="domcontentloaded")

            # Team names from match header
            team_names = []
            for el in await page.query_selector_all(".match-header-team .wf-title-med"):
                team_names.append((await el.inner_text()).strip())

            # Series score — winner span has the higher map count
            winner_el = await page.query_selector(".match-header-vs-score-winner")
            loser_el = await page.query_selector(".match-header-vs-score-loser")
            team1_maps = (await winner_el.inner_text()).strip() if winner_el else "?"
            team2_maps = (await loser_el.inner_text()).strip() if loser_el else "?"

            series_score = {
                "team1": team_names[0] if len(team_names) > 0 else "Team 1",
                "team1_maps_won": team1_maps,
                "team2": team_names[1] if len(team_names) > 1 else "Team 2",
                "team2_maps_won": team2_maps,
            }

            # Enabled map game IDs
            map_game_ids = []
            for tab in await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch"):
                game_id = await tab.get_attribute("data-game-id")
                is_disabled = await tab.get_attribute("data-disabled")
                if game_id and is_disabled == "0":
                    map_game_ids.append(game_id)

            results = []

            for game_id in map_game_ids:
                url = f"{base_url}/?game={game_id}&tab=overview"
                await page.goto(url, wait_until="domcontentloaded")

                table_selector = "table.wf-table-inset.mod-overview:visible"
                await page.locator(table_selector).first.wait_for(state="visible", timeout=10000)

                # Map round score from visible game container
                game_container = page.locator(
                    f'div.vm-stats-game[data-game-id="{game_id}"]:visible'
                ).first

                # VLR shows T-side and CT-side scores separately; sum them for the total
                t1_rounds, t2_rounds = "?", "?"
                try:
                    t1_t = (await game_container.locator(".mod-left .score.mod-t").inner_text()).strip()
                    t1_ct = (await game_container.locator(".mod-left .score.mod-ct").inner_text()).strip()
                    t2_t = (await game_container.locator(".mod-right .score.mod-t").inner_text()).strip()
                    t2_ct = (await game_container.locator(".mod-right .score.mod-ct").inner_text()).strip()
                    t1_rounds = str(int(t1_t) + int(t1_ct))
                    t2_rounds = str(int(t2_t) + int(t2_ct))
                except Exception:
                    # Fallback: grab all numeric .score values in order
                    try:
                        all_scores = [
                            s.strip() for s in
                            await game_container.locator(".score").all_inner_texts()
                            if s.strip().isdigit()
                        ]
                        if len(all_scores) >= 2:
                            t1_rounds, t2_rounds = all_scores[0], all_scores[-1]
                    except Exception:
                        pass

                map_score = {
                    "team1": team_names[0] if team_names else "Team 1",
                    "team1_rounds": t1_rounds,
                    "team2": team_names[1] if len(team_names) > 1 else "Team 2",
                    "team2_rounds": t2_rounds,
                }

                # Per-player stats — two tables (one per team)
                # VLR overview columns: Player | Agents | Rating | ACS | K | D | A | +/- | KAST | ADR | HS% | FK | FD | FK+/-
                tables = await page.locator(table_selector).all()
                players = []

                for table_idx, table in enumerate(tables):
                    team_name = team_names[table_idx] if table_idx < len(team_names) else f"Team {table_idx + 1}"
                    for row in await table.locator("tbody tr").all():
                        cells = await row.locator("td").all()
                        if len(cells) < 14:
                            continue
                        player_name = (await row.locator(".mod-player").inner_text()).split("\n")[0].strip()
                        players.append({
                            "name": player_name,
                            "team": team_name,
                            "rating": (await cells[2].locator("span.mod-both").first.inner_text()).strip(),
                            "acs": (await cells[3].locator("span.mod-both").first.inner_text()).strip(),
                            "kills": (await cells[4].locator("span.mod-both").first.inner_text()).strip(),
                            "deaths": (await cells[5].locator("span.mod-both").first.inner_text()).strip(),
                            "assists": (await cells[6].locator("span.mod-both").first.inner_text()).strip(),
                            "k_diff": (await cells[7].locator("span.mod-both").first.inner_text()).strip(),
                            "kast": (await cells[8].locator("span.mod-both").first.inner_text()).strip(),
                            "adr": (await cells[9].locator("span.mod-both").first.inner_text()).strip(),
                            "hs_perc": (await cells[10].locator("span.mod-both").first.inner_text()).strip(),
                            "fk": (await cells[11].locator("span.mod-both").first.inner_text()).strip(),
                            "fd": (await cells[12].locator("span.mod-both").first.inner_text()).strip(),
                            "fk_diff": (await cells[13].locator("span.mod-both").first.inner_text()).strip(),
                            "event_id": event_id,
                            "match_id": match_id,
                            "game_id": game_id,
                        })

                results.append({
                    "url": url,
                    "game_id": game_id,
                    "match_id": match_id,
                    "event_id": event_id,
                    "map_score": map_score,
                    "series_score": series_score,
                    "players": players,
                })
                # print(f"Done: {url}")

            await browser.close()
            return results

        except Exception as e:
            print(f"Error: {e}")
            await browser.close()
            return []


async def _collect_roster_from_stage(page, stage_url: str, roster: dict):
    """Scrapes a stage page and adds players to roster dict keyed by player href.
    Existing entries are not overwritten, so the first stage seen wins on conflict."""
    try:
        await page.goto(stage_url, wait_until="domcontentloaded")
        await page.wait_for_selector("div.wf-card.event-team", timeout=10000)

        team_blocks = await page.query_selector_all("div.wf-card.event-team")
        for block in team_blocks:
            team_el = await block.query_selector("a.event-team-name")
            if not team_el:
                continue
            team_name = (await team_el.inner_text()).strip()

            for link in await block.query_selector_all("a.event-team-players-item"):
                href = await link.get_attribute("href")
                if not href or href in roster:
                    continue
                alias = (await link.inner_text()).strip()
                roster[href] = {"name": alias, "team": team_name}

    except Exception as e:
        print(f"Failed to collect roster from {stage_url}: {e}")


async def scrape_event_roster(event_id: str, event_slug: str):
    swiss_url  = f"https://www.vlr.gg/event/{event_id}/{event_slug}/swiss-stage"
    playoff_url = f"https://www.vlr.gg/event/{event_id}/{event_slug}/playoffs"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            roster: dict[str, dict] = {}

            await _collect_roster_from_stage(page, swiss_url, roster)
            await _collect_roster_from_stage(page, playoff_url, roster)

            print(f"Unique players after dedup: {len(roster)}")

            results = []

            for player_href, player in roster.items():
                player_url = f"https://www.vlr.gg{player_href}"
                try:
                    await page.goto(player_url, wait_until="domcontentloaded")
                    await page.wait_for_selector(".player-header", timeout=8000)

                    img_el = await page.query_selector(".player-header-headshot img")
                    img_src = await img_el.get_attribute("src") if img_el else None
                    if img_src and img_src.startswith("//"):
                        img_src = "https:" + img_src

                    results.append({
                        "name": player["name"],
                        "team": player["team"],
                        "img": img_src,
                    })
                except Exception as e:
                    print(f"Failed to scrape player {player_href}: {e}")
                    results.append({"name": player["name"], "team": player["team"], "img": None})

            await browser.close()
            return results

        except Exception as e:
            print(f"Error scraping event roster {event_id}: {e}")
            await browser.close()
            return []


import json

async def scrape_all_matches(matches: list[str], match_type: int, event_id: str):
    if match_type == 0:
        prefix = "overview"
    elif match_type == 1:
        prefix = "performance"
    else:
        prefix = "scores"
    filename = f"{prefix}_scrape.json"

    first = True

    with open(filename, "w", encoding="utf-8") as f:
        f.write("[\n")

    for match_url in matches:
        if match_type == 0:
            data = await scrape_match_stats(match_url, event_id)
        elif match_type == 1:
            data = await scrape_performance(match_url, event_id)
        else:
            data = await scrape_match_scores(match_url, event_id)

        with open(filename, "a", encoding="utf-8") as f:
            if not first:
                f.write(",\n")
            json.dump(data, f, indent=4)
            first = False

    with open(filename, "a", encoding="utf-8") as f:
        f.write("\n]")

    return None

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