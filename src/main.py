import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
import os
import logging

# Giam log API - chi hien WARNING va ERROR, tat INFO cua uvicorn.access
logging.getLogger("uvicorn.access").disabled = True

from src.config import config
from src.core.scraper import scraper
from src.api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifecycle startup: khoi chay scraper running in background
    await scraper.start()
    yield
    # Lifecycle shutdown: dung scraper
    await scraper.stop()

app = FastAPI(
    title="Lottery Probability Analyzer API",
    description="API phan tich xac suat Chan/Le, Tai/Xiu tu du lieu xo so cao bang WebSocket",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware de ho tro Frontend goi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dang ky routes
app.include_router(router)

# Get views directory path
views_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "views")

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(os.path.join(views_dir, "index.html"))

@app.get("/style.css")
async def get_css():
    return FileResponse(os.path.join(views_dir, "style.css"), media_type="text/css")

@app.get("/app.js")
async def get_js():
    return FileResponse(os.path.join(views_dir, "app.js"), media_type="application/javascript")


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True,
        log_level="warning"
    )
