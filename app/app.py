from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.db import players_collection

app = FastAPI()

@app.get("/")
async def home():
    return("HEllO WELCOME TO MY API HOPEFULLY IT WORKS AND YALL LIKE IT")
