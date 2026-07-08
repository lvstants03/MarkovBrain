import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    # URL websocket can scrap du lieu
    TARGET_WS_URL = os.getenv("TARGET_WS_URL", "wss://vip.ee8822.me/ws/?token=1_362202_1782925349_626538bcd1703dada5f619821c2b9d1e&x-device=pc")
    
    # Cau hinh Loai Xo So (Mac dinh: Mien Bac 5 Phut)
    LOTTERY_ID = int(os.getenv("LOTTERY_ID", 45))
    LOTTERY_CODE = os.getenv("LOTTERY_CODE", "pmb5p")

    # Cau hinh Web API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 8000))
    
    # Kich thuoc du lieu lich su toi da de luu trong bo nho de tinh toan
    MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", 10000))

    # URL API HTTP de lay ket qua tu dong lam fallback/nap lich su
    DRAWS_RESULT_URL = os.getenv("DRAWS_RESULT_URL", "")
    AUTO_FETCH_INTERVAL = int(os.getenv("AUTO_FETCH_INTERVAL", 60))
    DRAWS_RESULT_HEADERS = {}

config = Config()
