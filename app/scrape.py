from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
import asyncio
import re
from urllib.parse import urlparse, parse_qs

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_stat(value: str) -> str:
    return value.split("\n")[0].strip() if value else ""

def extract_game_id(url: str):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    return query_params.get("game", [None])[0]

def extract_event_id(url: str):
    match = re.search(r"/event/(?:matches/|stats/|performance/)?(\d+)", url)
    return match.group(1) if match else None

def extract_match_id(url: str):
    match = re.search(r"vlr\.gg/(\d+)", url)
    return match.group(1) if match else None

@asynccontextmanager
async def browser_page(block_resources: bool = False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_UA)
        if block_resources:
            await context.route("**/*", lambda route: (
                route.abort() if route.request.resource_type in ["image", "font", "stylesheet"]
                else route.continue_()
            ))
        page = await context.new_page()
        try:
            yield page
        finally:
            await browser.close()

async def get_enabled_game_ids(page) -> list[str]:
    game_ids = []
    for tab in await page.query_selector_all(".vm-stats-gamesnav-item.js-map-switch"):
        game_id = await tab.get_attribute("data-game-id")
        is_disabled = await tab.get_attribute("data-disabled")
        if game_id and game_id != "all" and is_disabled == "0":
            game_ids.append(game_id)
    return game_ids

async def player_name_from_row(row) -> str:
    return (await row.locator(".mod-player").inner_text()).split("\n")[0].strip()


async def scrape_events() -> list[dict]:
    async with browser_page(block_resources=True) as page:
        try:
            ## vct tier events only
            await page.goto("https://www.vlr.gg/events/?tier=60", wait_until="domcontentloaded")
            items = await page.query_selector_all("a.wf-card.mod-flex.event-item")
            events = []
            for item in items:
                href = await item.get_attribute("href")
                name_el = await item.query_selector(".event-item-title")
                name = (await name_el.inner_text()).strip() if name_el else None
                event_id_match = re.search(r"/event/(\d+)/", href or "")
                if event_id_match and name:
                    events.append({"event_id": event_id_match.group(1), "name": name})
            return events
        except Exception as e:
            print(f"Error scraping events: {e}")
            return []



async def scrape_ongoing_events() -> list[dict]:
    async with browser_page(block_resources=True) as page:
        try:
            await page.goto("https://www.vlr.gg/events/?tier=60", wait_until="domcontentloaded")

            events = []
            for item in await page.query_selector_all("a.wf-card.mod-flex.event-item"):
                status_el = await item.query_selector("span.event-item-desc-item-status.mod-ongoing")
                if not status_el:
                    continue
                href = await item.get_attribute("href")
                name_el = await item.query_selector(".event-item-title")
                name = (await name_el.inner_text()).strip() if name_el else None
                event_id_match = re.search(r"/event/(\d+)/", href or "")
                if event_id_match and name:
                    events.append({"event_id": event_id_match.group(1), "name": name})
            return events
        except Exception as e:
            print(f"Error scraping ongoing events: {e}")
            return []


async def scrape_vlr_stats(event_url: str):
    await players_collection.delete_many({})

    async with browser_page() as page:
        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            await page.wait_for_selector(".wf-table")

            rows = await page.query_selector_all(".wf-table tbody tr")
            results = []

            for index, row in enumerate(rows):
                cells = await row.query_selector_all("td")

                player_div = await row.query_selector(".mod-player .text-of")
                team_div = await row.query_selector(".stats-player-country")

                player_name = await player_div.inner_text() if player_div else "Unknown"
                team_name = await team_div.inner_text() if team_div else "N/A"

                results.append({
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
                    "fd": (await cells[20].inner_text()).strip(),
                })

            if results:
                await players_collection.insert_many(results)
                print(f"Successfully inserted {len(results)} players.")

            return results

        except Exception as e:
            print(f"Error during scrape: {e}")
            return None


async def get_matches_url(event_id: str):
    event_url = f"https://www.vlr.gg/event/matches/{event_id}"

    async with browser_page() as page:
        completed_matches = []
        try:
            await page.goto(event_url, wait_until="domcontentloaded")
            matches = await page.query_selector_all("a.wf-module-item")

            for match in matches:
                href = await match.get_attribute("href")
                if not href:
                    continue
                is_upcoming = await match.query_selector(".match-item-vs-team-score.mod-upcoming")
                if not is_upcoming:
                    completed_matches.append(f"https://www.vlr.gg{href}")

        except Exception as e:
            print(f"Error during scrape: {e}")
            return None

        return list(set(completed_matches))


async def scrape_performance(match_url: str, event_id: str):
    match_id = extract_match_id(match_url)

    async with browser_page(block_resources=True) as page:
        try:
            base_url = match_url.rstrip("/")
            await page.goto(f"{base_url}/?game=all&tab=performance", wait_until="domcontentloaded")

            game_ids = await get_enabled_game_ids(page)
            all_maps_data = []

            for game_id in game_ids:
                url = f"{base_url}/?game={game_id}&tab=performance"
                await page.goto(url, wait_until="domcontentloaded")

                try:
                    await page.wait_for_selector("table.mod-adv-stats")

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
                            "game_id": game_id,
                        })

                    all_maps_data.append({"url": url, "stats": map_stats})

                except Exception as e:
                    print(f"Failed to parse {url}: {e}")

            return all_maps_data

        except Exception as e:
            print(f"Critical error: {e}")
            return []


async def scrape_match_stats(match_url: str, event_id: str):
    async with browser_page() as page:
        try:
            base_url = match_url.rstrip("/")
            match_id = extract_match_id(match_url)

            await page.goto(base_url, wait_until="domcontentloaded")

            game_ids = await get_enabled_game_ids(page)
            results = []
            table_selector = "table.wf-table-inset.mod-overview:visible"

            for game_id in game_ids:
                url = f"{base_url}/?game={game_id}&tab=overview"
                await page.goto(url, wait_until="domcontentloaded")
                await page.locator(table_selector).first.wait_for(state="visible", timeout=10000)

                tables = await page.locator(table_selector).all()
                map_data = {"url": url, "players": []}

                for table in tables:
                    for row in await table.locator("tbody tr").all():
                        cells = await row.locator("td").all()
                        if len(cells) < 13:
                            continue
                        map_data["players"].append({
                            "name": await player_name_from_row(row),
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
                            "game_id": game_id,
                        })

                results.append(map_data)

            return results

        except Exception as e:
            print(f"Error: {e}")
            return []


async def scrape_match_scores(match_url: str, event_id: str):
    async with browser_page(block_resources=True) as page:
        try:
            base_url = match_url.rstrip("/")
            match_id = extract_match_id(match_url)

            await page.goto(base_url, wait_until="domcontentloaded")

            team_names = []
            for el in await page.query_selector_all(".match-header-team .wf-title-med"):
                team_names.append((await el.inner_text()).strip())

            winner_el = await page.query_selector(".match-header-vs-score-winner")
            loser_el = await page.query_selector(".match-header-vs-score-loser")
            series_score = {
                "team1": team_names[0] if team_names else "Team 1",
                "team1_maps_won": (await winner_el.inner_text()).strip() if winner_el else "?",
                "team2": team_names[1] if len(team_names) > 1 else "Team 2",
                "team2_maps_won": (await loser_el.inner_text()).strip() if loser_el else "?",
            }

            game_ids = await get_enabled_game_ids(page)
            results = []
            table_selector = "table.wf-table-inset.mod-overview:visible"

            for game_id in game_ids:
                url = f"{base_url}/?game={game_id}&tab=overview"
                await page.goto(url, wait_until="domcontentloaded")
                await page.locator(table_selector).first.wait_for(state="visible", timeout=10000)

                game_container = page.locator(
                    f'div.vm-stats-game[data-game-id="{game_id}"]:visible'
                ).first

                t1_rounds, t2_rounds = "?", "?"
                try:
                    t1_t = (await game_container.locator(".mod-left .score.mod-t").inner_text()).strip()
                    t1_ct = (await game_container.locator(".mod-left .score.mod-ct").inner_text()).strip()
                    t2_t = (await game_container.locator(".mod-right .score.mod-t").inner_text()).strip()
                    t2_ct = (await game_container.locator(".mod-right .score.mod-ct").inner_text()).strip()
                    t1_rounds = str(int(t1_t) + int(t1_ct))
                    t2_rounds = str(int(t2_t) + int(t2_ct))
                except Exception:
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

                tables = await page.locator(table_selector).all()
                players = []

                for table_idx, table in enumerate(tables):
                    team_name = team_names[table_idx] if table_idx < len(team_names) else f"Team {table_idx + 1}"
                    for row in await table.locator("tbody tr").all():
                        cells = await row.locator("td").all()
                        if len(cells) < 14:
                            continue
                        players.append({
                            "name": await player_name_from_row(row),
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

            return results

        except Exception as e:
            print(f"Error: {e}")
            return []


async def scrape_match_comps(match_url: str, event_id: str):
    """For each map in a match, returns each team's name and the agents they played."""
    match_id = extract_match_id(match_url)

    async with browser_page(block_resources=True) as page:
        try:
            base_url = match_url.rstrip("/")
            await page.goto(base_url, wait_until="domcontentloaded")

            await page.wait_for_selector("a.match-header-link.wf-link-hover.mod-1", timeout=10000)
            teams = []
            for selector in ["a.match-header-link.wf-link-hover.mod-1", "a.match-header-link.wf-link-hover.mod-2"]:
                el = await page.query_selector(selector)
                if el:
                    href = await el.get_attribute("href")
                    name = (await el.inner_text()).strip()
                    team_id_match = re.search(r"/team/(\d+)/", href or "")
                    teams.append({
                        "name": name,
                        "id": team_id_match.group(1) if team_id_match else None,
                    })

            game_ids = await get_enabled_game_ids(page)
            results = []
            table_selector = "table.wf-table-inset.mod-overview"

            for game_id in game_ids:
                url = f"{base_url}/?game={game_id}&tab=overview"
                await page.goto(url, wait_until="domcontentloaded")

                game_container = page.locator(f'div.vm-stats-game[data-game-id="{game_id}"]:visible').first
                await game_container.wait_for(state="visible", timeout=10000)

                # Parse game header — map name, scores, attack/defense splits, winner
                header = game_container.locator(".vm-stats-game-header")
                map_name = "Unknown"
                t1_rounds = t2_rounds = "?"
                t1_atk = t1_def = t2_atk = t2_def = "?"
                winner_idx = None
                try:
                    # Map name — first text node of the span, strips child spans like PICK/BAN
                    map_span = header.locator(".map > div > span").first
                    map_name = await page.evaluate(
                        "el => el.firstChild.textContent.trim()", await map_span.element_handle()
                    )

                    # Left team (index 0)
                    left = header.locator(".team:not(.mod-right)")
                    t1_rounds = (await left.locator(".score").inner_text()).strip()
                    t1_atk = (await left.locator("span.mod-t").inner_text()).strip()
                    t1_def = (await left.locator("span.mod-ct").inner_text()).strip()

                    # Right team (index 1)
                    right = header.locator(".team.mod-right")
                    t2_rounds = (await right.locator(".score").inner_text()).strip()
                    t2_atk = (await right.locator("span.mod-t").inner_text()).strip()
                    t2_def = (await right.locator("span.mod-ct").inner_text()).strip()

                    # Winner — whichever score div has mod-win
                    win_el = await header.locator(".score.mod-win").count()
                    if win_el:
                        win_html = await header.locator(".score.mod-win").evaluate("el => el.closest('.team').className")
                        winner_idx = 1 if "mod-right" in win_html else 0
                except Exception:
                    pass

                tables = await game_container.locator(table_selector).all()
                team_agents = []

                for table_idx, table in enumerate(tables):
                    team = teams[table_idx] if table_idx < len(teams) else {"name": f"Team {table_idx + 1}", "id": None}
                    agents = []

                    for row in await table.locator("tbody tr").all():
                        cells = await row.locator("td").all()
                        if len(cells) < 2:
                            continue
                        try:
                            agent_img = cells[1].locator("img").first
                            agent_name = (
                                await agent_img.get_attribute("title") or
                                await agent_img.get_attribute("alt") or
                                "Unknown"
                            )
                            agents.append(agent_name)
                        except Exception:
                            pass

                    team_agents.append({"team": team["name"], "team_id": team["id"], "comp": agents})

                t1 = team_agents[0] if len(team_agents) > 0 else {"team": "Unknown", "team_id": None, "comp": []}
                t2 = team_agents[1] if len(team_agents) > 1 else {"team": "Unknown", "team_id": None, "comp": []}

                winner_id = None
                if winner_idx == 0:
                    winner_id = t1["team_id"]
                elif winner_idx == 1:
                    winner_id = t2["team_id"]

                results.append({
                    "map_id": game_id,
                    "match_id": match_id,
                    "event_id": event_id,
                    "map_name": map_name,
                    "team1": t1["team"],
                    "team1_id": t1["team_id"],
                    "team1_comp": t1["comp"],
                    "team1_rounds": t1_rounds,
                    "team1_attack_rounds": t1_atk,
                    "team1_defense_rounds": t1_def,
                    "team2": t2["team"],
                    "team2_id": t2["team_id"],
                    "team2_comp": t2["comp"],
                    "team2_rounds": t2_rounds,
                    "team2_attack_rounds": t2_atk,
                    "team2_defense_rounds": t2_def,
                    "winner_id": winner_id,
                })

            return results

        except Exception as e:
            print(f"Error scraping comps for {match_url}: {e}")
            return []


async def _collect_roster_from_stage(page, stage_url: str, roster: dict):
    try:
        await page.goto(stage_url, wait_until="domcontentloaded")
        await page.wait_for_selector("div.wf-card.event-team", timeout=10000)

        for block in await page.query_selector_all("div.wf-card.event-team"):
            team_el = await block.query_selector("a.event-team-name")
            if not team_el:
                continue
            team_name = (await team_el.inner_text()).strip()

            for link in await block.query_selector_all("a.event-team-players-item"):
                href = await link.get_attribute("href")
                if not href or href in roster:
                    continue
                roster[href] = {"name": (await link.inner_text()).strip(), "team": team_name}

    except Exception as e:
        print(f"Failed to collect roster from {stage_url}: {e}")


async def scrape_event_roster(event_id: str, event_slug: str):
    swiss_url   = f"https://www.vlr.gg/event/{event_id}/{event_slug}/swiss-stage"
    playoff_url = f"https://www.vlr.gg/event/{event_id}/{event_slug}/playoffs"

    async with browser_page() as page:
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

                    results.append({"name": player["name"], "team": player["team"], "img": img_src})
                except Exception as e:
                    print(f"Failed to scrape player {player_href}: {e}")
                    results.append({"name": player["name"], "team": player["team"], "img": None})

            return results

        except Exception as e:
            print(f"Error scraping event roster {event_id}: {e}")
            return []


async def scrape_all_matches(matches: list[str], match_type: int, event_id: str):
    scraper = {0: scrape_match_stats, 1: scrape_performance, 2: scrape_match_scores, 3: scrape_match_comps}[match_type]
    all_results = []
    for match_url in matches:
        data = await scraper(match_url, event_id)
        if data:
            all_results.extend(data)
    return all_results


async def main():
    event_id = "2760"
    print("Fetching match URLs...")
    matches_url = await get_matches_url(event_id)
    print(matches_url)
    print(f"Found {len(matches_url)} matches. Starting sequential test loop...")
    results = await scrape_all_matches(matches_url, match_type=1, event_id=event_id)
    print(f"Scraped {len(results)} matches successfully.")

if __name__ == "__main__":
    asyncio.run(main())
