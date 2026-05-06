from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime, timezone
from app.db import players_collection, performance_collection, scores_collection, comp_analysis_collection, events_collection, comparisons_collection, journal_collection
from app.scrape import scrape_vlr_stats, get_matches_url, scrape_all_matches, scrape_match_scores, scrape_events, scrape_ongoing_events
from app.auth import get_current_user
import httpx
import os

app = FastAPI()

api_key_header = APIKeyHeader(name="X-API-Key")

async def require_api_key(key: str = Security(api_key_header)):
    if key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return {"message": "WELCOME TO THE VCT ANALYSIS API"}

@app.post("/scrape/events", dependencies=[Depends(require_api_key)])
async def scrape_and_store_events():
    try:
        events = await scrape_events()
        if not events:
            raise HTTPException(status_code=500, detail="Scrape returned no events")
        await events_collection.delete_many({})
        await events_collection.insert_many(events)
        return {"status": "success", "count": len(events)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events")
async def get_events():
    try:
        cursor = events_collection.find({}, {"_id": 0})
        events = await cursor.to_list(length=500)
        return {"status": "success", "count": len(events), "data": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/{event_id}")
async def get_event_by_id(event_id: str):
    try:
        event = await events_collection.find_one({"event_id": event_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return {"status": "success", "data": event}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/scrape/overall", dependencies=[Depends(require_api_key)])
async def scrape_overall_stats(event_url: str):
    results = await scrape_vlr_stats(event_url)
    if results:
        return {"status": "success", "message": f"Inserted {len(results)} players"}
    raise HTTPException(status_code=500, detail="Scrape failed")

@app.post("/scrape/performance/{event_id}", dependencies=[Depends(require_api_key)])
async def scrape_event_performance(event_id: str):
    match_urls = await get_matches_url(event_id)
    if not match_urls:
        raise HTTPException(status_code=404, detail="No matches found for this event")

    results = await scrape_all_matches(match_urls, 1, event_id)
    if results:
        await performance_collection.delete_many({"stats.event_id": event_id})
        await performance_collection.insert_many(results)
        return {"status": "success", "count": len(results)}
    return {"status": "error", "message": "Scrape completed but no data was found"}

@app.post("/scrape/overview/{event_id}", dependencies=[Depends(require_api_key)])
async def scrape_event_overview(event_id: str):
    try:
        match_urls = await get_matches_url(event_id)
        if not match_urls:
            raise HTTPException(status_code=404, detail="No matches found for this event")

        results = await scrape_all_matches(match_urls, 0, event_id)
        if results:
            await performance_collection.delete_many({"stats.event_id": event_id})
            await performance_collection.insert_many(results)
            return {"status": "success", "count": len(results), "event_id": event_id}

        return {"status": "error", "message": "Scrape completed but no data was found"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/matches/performance/count")
async def get_performance_count():
    try:
        count = await performance_collection.count_documents({})
        return {"status": "success", "count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/matches/performance", dependencies=[Depends(require_api_key)])
async def clear_performance_collection():
    try:
        result = await performance_collection.delete_many({})
        return {"status": "success", "deleted_count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/scores/{event_id}", dependencies=[Depends(require_api_key)])
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

        all_comps = await scrape_all_matches(match_urls, 3, event_id)

        if all_comps:
            await comp_analysis_collection.delete_many({"event_id": event_id})
            await comp_analysis_collection.insert_many(all_comps)
            print(f"[comp-analysis] Done — inserted {len(all_comps)} records for event {event_id}")
        else:
            print(f"[comp-analysis] No data found for event {event_id}")
    except Exception as e:
        print(f"[comp-analysis] Error: {e}")

@app.post("/scrape/comp-analysis/{event_id}", dependencies=[Depends(require_api_key)])
async def scrape_comp_analysis(event_id: str, background_tasks: BackgroundTasks):
    match_urls = await get_matches_url(event_id)
    if not match_urls:
        raise HTTPException(status_code=404, detail="No matches found for this event")
    background_tasks.add_task(_run_comp_analysis_scrape, event_id)
    return {"status": "started", "matches": len(match_urls), "event_id": event_id}


async def _run_update_ongoing_events(events: list[dict]):
    try:
        print(f"[update-ongoing] Updating {len(events)} events")
        for event in events:
            event_id = event["event_id"]
            print(f"[update-ongoing] Processing event {event_id} ({event['name']})")
            match_urls = await get_matches_url(event_id)
            if not match_urls:
                print(f"[update-ongoing] No matches found for event {event_id}")
                continue

            all_comps = await scrape_all_matches(match_urls, 3, event_id)

            if all_comps:
                await comp_analysis_collection.delete_many({"event_id": event_id})
                await comp_analysis_collection.insert_many(all_comps)
                print(f"[update-ongoing] {event_id} — {len(all_comps)} comp records")

        print("[update-ongoing] Done")
    except Exception as e:
        print(f"[update-ongoing] Error: {e}")

@app.post("/scrape/update-ongoing-events", dependencies=[Depends(require_api_key)])
async def update_ongoing_events(background_tasks: BackgroundTasks):
    events = await scrape_ongoing_events()
    if not events:
        raise HTTPException(status_code=404, detail="No ongoing tier-60 events found")
    background_tasks.add_task(_run_update_ongoing_events, events)
    return {
        "status": "started",
        "event_count": len(events),
        "event_ids": [e["event_id"] for e in events],
    }

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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class AuthRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/register")
async def register(body: AuthRequest):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{os.getenv('SUPABASE_URL')}/auth/v1/signup",
            headers={"apikey": os.getenv("SUPABASE_ANON_KEY"), "Content-Type": "application/json"},
            json={"email": body.email, "password": body.password},
        )
    if r.status_code not in (200, 201):
        body = r.json()
        raise HTTPException(status_code=400, detail=body.get("error_description") or body.get("msg", "Registration failed"))
    return {"status": "success", "message": "Check your email to confirm your account"}

@app.post("/auth/login")
async def login(body: AuthRequest):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{os.getenv('SUPABASE_URL')}/auth/v1/token?grant_type=password",
            headers={"apikey": os.getenv("SUPABASE_ANON_KEY"), "Content-Type": "application/json"},
            json={"email": body.email, "password": body.password},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    data = r.json()
    return {"access_token": data["access_token"], "refresh_token": data.get("refresh_token"), "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------

class ComparisonCreate(BaseModel):
    name: str
    data: dict

@app.post("/comparisons")
async def save_comparison(body: ComparisonCreate, current_user=Depends(get_current_user)):
    doc = {
        "user_id": current_user["id"],
        "name": body.name,
        "data": body.data,
        "created_at": datetime.now(timezone.utc),
    }
    result = await comparisons_collection.insert_one(doc)
    return {"status": "success", "id": str(result.inserted_id)}

@app.get("/comparisons")
async def get_comparisons(current_user=Depends(get_current_user)):
    cursor = comparisons_collection.find({"user_id": current_user["id"]}, {"_id": 1, "name": 1, "data": 1, "created_at": 1})
    results = await cursor.to_list(length=500)
    for doc in results:
        doc["_id"] = str(doc["_id"])
    return {"status": "success", "count": len(results), "data": results}

@app.delete("/comparisons/{comparison_id}")
async def delete_comparison(comparison_id: str, current_user=Depends(get_current_user)):
    result = await comparisons_collection.delete_one({"_id": ObjectId(comparison_id), "user_id": current_user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

class JournalCreate(BaseModel):
    name: str
    analysis_type: str
    data: dict
    event_id: str | None = None

@app.post("/journal")
async def create_journal_entry(body: JournalCreate, current_user=Depends(get_current_user)):
    doc = {
        "user_id": current_user["id"],
        "name": body.name,
        "analysis_type": body.analysis_type,
        "data": body.data,
        "event_id": body.event_id,
        "created_at": datetime.now(timezone.utc),
    }
    result = await journal_collection.insert_one(doc)
    return {"status": "success", "id": str(result.inserted_id)}

@app.get("/journal")
async def get_journal(
    current_user=Depends(get_current_user),
    analysis_type: str | None = None,
    event_id: str | None = None,
):
    query = {"user_id": current_user["id"]}
    if analysis_type:
        query["analysis_type"] = analysis_type
    if event_id:
        query["event_id"] = event_id
    cursor = journal_collection.find(query).sort("created_at", -1)
    results = await cursor.to_list(length=500)
    for doc in results:
        doc["_id"] = str(doc["_id"])
    return {"status": "success", "count": len(results), "data": results}

@app.get("/journal/{entry_id}")
async def get_journal_entry(entry_id: str, current_user=Depends(get_current_user)):
    doc = await journal_collection.find_one({"_id": ObjectId(entry_id), "user_id": current_user["id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Entry not found")
    doc["_id"] = str(doc["_id"])
    return {"status": "success", "data": doc}

@app.delete("/journal/{entry_id}")
async def delete_journal_entry(entry_id: str, current_user=Depends(get_current_user)):
    result = await journal_collection.delete_one({"_id": ObjectId(entry_id), "user_id": current_user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "success"}
