import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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

@app.get("/")
async def root():
    return {
        "app": "Lottery Probability Analyzer",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=True
    )
