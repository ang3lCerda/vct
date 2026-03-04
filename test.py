import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

# Setup Connection
client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
db = client.vct_fantasy  # This is your database
players_collection = db.players  # This is where we'll store stats

async def insert_player_stat(player_data):
    # This will insert the dict exactly as you scraped it
    result = await players_collection.insert_one(player_data)
    print(f"Player inserted with ID: {result.inserted_id}")

# Example of the data you were scraping
sample_player = {
    "name": "Aspas",
    "team": "LEV",
    "stats": {
        "rating": 1.25,
        "acs": 240,
        "kd": 1.3,
        "adr": 155.2
    }
}

if __name__ == "__main__":
    asyncio.run(insert_player_stat(sample_player))