from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.db import players_collection

app = FastAPI()

# Recommended: Add CORS middleware if you plan to connect a frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return "HEllO WELCOME TO MY API HOPEFULLY IT WORKS AND YALL LIKE IT"

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