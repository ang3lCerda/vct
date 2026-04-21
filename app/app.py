from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.db import players_collection, performance_collection, scores_collection
from app.scrape import scrape_vlr_stats, get_matches_url, scrape_all_matches, scrape_match_scores

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return {"message": "WELCOME TO THE VCT SCALING API"}

@app.get("/matches/performance")
async def get_all_performance():
    try:
        cursor = performance_collection.find({})
        results = await cursor.to_list(length=1000)
        
        if not results:
            return {
                "status": "success", 
                "message": "Collection is empty", 
                "data": []
            }

        for doc in results:
            doc["_id"] = str(doc["_id"])
            
        return {
            "status": "success",
            "count": len(results),
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

@app.get("/matches/performance/{event_id}")
async def get_performance_by_event(event_id: str):
    try:

        query = {
            "$or": [
                {"stats.event_id": event_id},
            ]
        }
        
        cursor = performance_collection.find(query)
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
        players_cursor = players_collection.find()
        players = await players_cursor.to_list(length=100)
        
        for player in players:
            player["_id"] = str(player["_id"])
            
        return {"status": "success", "data": players}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/scrape_overall")
async def scrape_overall_stats(event_url: str):
    results = await scrape_vlr_stats(event_url)
    if results:
        return {"status": "success", "message": f"Inserted {len(results)} players"}
    raise HTTPException(status_code=500, detail="Scrape failed")

@app.post("/scrape_performance/{event_id}")
async def scrape_events_stats(event_id: str):
    match_data = await get_matches_url(event_id)
    event_matches = match_data["urls"] if isinstance(match_data, dict) else match_data
    
    event_performance = await scrape_all_matches(event_matches, 1, event_id)
    
    if event_performance:
        flattened_data = []
        for item in event_performance:
            if isinstance(item, list):
                flattened_data.extend(item)
            else:
                flattened_data.append(item)
        
        if flattened_data:
            await performance_collection.delete_many({"stats.event_id": event_id})
            await performance_collection.insert_many(flattened_data)
            return {"status": "success", "count": len(flattened_data)}
    

@app.post("/scrape_overview/{event_id}")
async def scrape_overview(event_id: str):
    try:
        match_data = await get_matches_url(event_id)
        event_matches = match_data["urls"] if isinstance(match_data, dict) else match_data
        
        if not event_matches:
            raise HTTPException(status_code=404, detail="No matches found for this event")

        event_performance = await scrape_all_matches(event_matches, 0, event_id)
        
        if event_performance:
            flattened_data = [item for sublist in event_performance for item in sublist if sublist]
            
            if flattened_data:
                await performance_collection.delete_many({"stats.event_id": event_id})
                
                await performance_collection.insert_many(flattened_data)
                
                return {
                    "status": "success", 
                    "message": f"Cleared duplicates and inserted {len(flattened_data)} records",
                    "event_id": event_id
                }
        
        return {"status": "error", "message": "Scrape completed but no data was found"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

    
@app.get("/matches/performance/count")
async def get_performance_count():
    try:
        count = await performance_collection.count_documents({})
        return {
            "status": "success",
            "count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.delete("/matches/performance")
async def clear_performance_collection():
    try:
        result = await performance_collection.delete_many({})
        return {
            "status": "success",
            "deleted_count": result.deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape_scores/{event_id}")
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