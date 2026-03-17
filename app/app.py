from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.db import players_collection
from app.scrape import scrape_vlr_stats

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return "HEllO WELCOME TO MY API"

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

@app.post("/scrape")
async def scrape_overall_stats(event_url:str):
    results = await scrape_vlr_stats(event_url)
    if results:
        return {"status": "success", "message": f"Inserted {len(results)} players"}
    raise HTTPException(status_code=500, detail="Scrape failed")

