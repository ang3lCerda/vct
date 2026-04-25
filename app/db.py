from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi
import os

load_dotenv()

client = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
db = client.vct_fantasy  
players_collection = db.players
matches_collection = db.matches
performance_collection = db.performance
overview_collection = db.overview
scores_collection = db.scores
comp_analysis_collection = db.comp_analysis
events_collection = db.events


