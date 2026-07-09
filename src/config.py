import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    TARGET_WS_URL = os.getenv("TARGET_WS_URL", "")
    # Domain chinh cua trang web muc tieu (tach tu WS URL khi khong set)
    TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "vip.ee8833.me")
    
    # Cau hinh Loai Xo So (Mac dinh: Mien Bac 5 Phut)
    LOTTERY_ID = int(os.getenv("LOTTERY_ID", 45))
    LOTTERY_CODE = os.getenv("LOTTERY_CODE", "pmb5p")

    # Cau hinh Gemini AI
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1beta")

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
