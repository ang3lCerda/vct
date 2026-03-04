from motor.motor_asyncio import AsyncIOMotorClient
import os

client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
db = client.vct_fantasy  # This is your database
players_collection = db.players  # This is where we'll store stats

