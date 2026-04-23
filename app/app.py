from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.db import players_collection, performance_collection, scores_collection, comp_analysis_collection
from app.scrape import scrape_vlr_stats, get_matches_url, scrape_all_matches, scrape_match_scores, scrape_match_comps

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return {"message": "WELCOME TO THE VCT ANALYSIS API"}

@app.get("/matches/performance")
async def get_all_performance():
    try:
        cursor = performance_collection.find({})
        results = await cursor.to_list(length=1000)

        if not results:
            return {"status": "success", "message": "Collection is empty", "data": []}

        for doc in results:
            doc["_id"] = str(doc["_id"])

        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/matches/performance/{event_id}")
async def get_performance_by_event(event_id: str):
    try:
        cursor = performance_collection.find({"$or": [{"stats.event_id": event_id}]})
        results = await cursor.to_list(length=1000)

        if not results:
            return {"status": "success", "message": "No data found", "data": []}

        for doc in results:
            doc["_id"] = str(doc["_id"])

        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/players")
async def get_players():
    try:
        cursor = players_collection.find()
        players = await cursor.to_list(length=100)

        for player in players:
            player["_id"] = str(player["_id"])

        return {"status": "success", "data": players}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/overall")
async def scrape_overall_stats(event_url: str):
    results = await scrape_vlr_stats(event_url)
    if results:
        return {"status": "success", "message": f"Inserted {len(results)} players"}
    raise HTTPException(status_code=500, detail="Scrape failed")

@app.post("/scrape/performance/{event_id}")
async def scrape_event_performance(event_id: str):
    match_urls = await get_matches_url(event_id)
    event_matches = match_urls if isinstance(match_urls, list) else match_urls.get("urls", [])

    event_performance = await scrape_all_matches(event_matches, 1, event_id)

    if event_performance:
        flattened = [item for sublist in event_performance for item in (sublist if isinstance(sublist, list) else [sublist])]
        if flattened:
            await performance_collection.delete_many({"stats.event_id": event_id})
            await performance_collection.insert_many(flattened)
            return {"status": "success", "count": len(flattened)}

@app.post("/scrape/overview/{event_id}")
async def scrape_event_overview(event_id: str):
    try:
        match_urls = await get_matches_url(event_id)
        if not match_urls:
            raise HTTPException(status_code=404, detail="No matches found for this event")

        event_performance = await scrape_all_matches(match_urls, 0, event_id)

        if event_performance:
            flattened = [item for sublist in event_performance for item in sublist if sublist]
            if flattened:
                await performance_collection.delete_many({"stats.event_id": event_id})
                await performance_collection.insert_many(flattened)
                return {"status": "success", "count": len(flattened), "event_id": event_id}

        return {"status": "error", "message": "Scrape completed but no data was found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/matches/performance/count")
async def get_performance_count():
    try:
        count = await performance_collection.count_documents({})
        return {"status": "success", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/matches/performance")
async def clear_performance_collection():
    try:
        result = await performance_collection.delete_many({})
        return {"status": "success", "deleted_count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/scores/{event_id}")
async def scrape_event_scores(event_id: str):
    try:
        match_urls = await get_matches_url(event_id)
        if not match_urls:
            raise HTTPException(status_code=404, detail="No matches found for this event")

        all_maps = []
        for match_url in match_urls:
            maps = await scrape_match_scores(match_url, event_id)
            all_maps.extend(maps)

        if not all_maps:
            return {"status": "error", "message": "Scrape completed but no data was found"}

        await scores_collection.delete_many({"event_id": event_id})
        await scores_collection.insert_many(all_maps)

        return {"status": "success", "count": len(all_maps), "event_id": event_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/matches/scores/{event_id}")
async def get_scores_by_event(event_id: str):
    try:
        cursor = scores_collection.find({"event_id": event_id})
        results = await cursor.to_list(length=1000)
        if not results:
            return {"status": "success", "message": "No data found", "data": []}
        for doc in results:
            doc["_id"] = str(doc["_id"])
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Comp analysis
# ---------------------------------------------------------------------------

@app.get("/comp-analysis/events")
async def get_comp_analysis_events():
    try:
        event_ids = await comp_analysis_collection.distinct("event_id")
        return {"status": "success", "count": len(event_ids), "data": event_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def _run_comp_analysis_scrape(event_id: str):
    try:
        match_urls = await get_matches_url(event_id)
        if not match_urls:
            print(f"[comp-analysis] No matches found for event {event_id}")
            return

        all_comps = []
        for url in match_urls:
            comps = await scrape_match_comps(url, event_id)
            all_comps.extend(comps)
            print(f"[comp-analysis] {url} → {len(comps)} records ({len(all_comps)} total)")

        if all_comps:
            await comp_analysis_collection.delete_many({"event_id": event_id})
            await comp_analysis_collection.insert_many(all_comps)
            print(f"[comp-analysis] Done — inserted {len(all_comps)} records for event {event_id}")
        else:
            print(f"[comp-analysis] No data found for event {event_id}")
    except Exception as e:
        print(f"[comp-analysis] Error: {e}")

@app.post("/scrape/comp-analysis/{event_id}")
async def scrape_comp_analysis(event_id: str, background_tasks: BackgroundTasks):
    match_urls = await get_matches_url(event_id)
    if not match_urls:
        raise HTTPException(status_code=404, detail="No matches found for this event")
    background_tasks.add_task(_run_comp_analysis_scrape, event_id)
    return {"status": "started", "matches": len(match_urls), "event_id": event_id}


@app.get("/comp-analysis/{event_id}")
async def get_comp_analysis(event_id: str):
    try:
        cursor = comp_analysis_collection.find({"event_id": event_id})
        results = await cursor.to_list(length=5000)
        if not results:
            return {"status": "success", "message": "No data found", "data": []}
        for doc in results:
            doc["_id"] = str(doc["_id"])
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
