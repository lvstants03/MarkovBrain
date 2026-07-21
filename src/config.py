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

    # Cau hinh DKM Pro (Dynamic Kelly & Martingale)
    DKM_ENABLED = True
    DKM_KELLY_FRACTION = 0.25
    DKM_MAX_MARTINGALE_MULTIPLIER = 2.0
    DKM_MAX_MARTINGALE_STEPS = 3
    DKM_DAILY_LOSS_LIMIT_PERCENT = 5.0
    DKM_MIN_BALANCE = 500000.0
    DKM_TIME_SLOTS = [
        {"start": "10:00", "end": "12:00", "weight": 1.0},
        {"start": "15:00", "end": "16:00", "weight": 1.0}
    ]
    DKM_BLACKOUT_SLOTS = [
        {"start": "19:30", "end": "21:00"}
    ]

    # Cau hinh Co So Du Lieu (PostgreSQL / SQLite)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lottery.db")

config = Config()
