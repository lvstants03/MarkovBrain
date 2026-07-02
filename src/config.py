import os

class Config:
    # URL websocket can scrap du lieu
    TARGET_WS_URL = os.getenv("TARGET_WS_URL", "wss://vip.ee8822.me/ws/?token=1_362202_1782925349_626538bcd1703dada5f619821c2b9d1e&x-device=pc")
    
    # Cau hinh Web API
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", 8000))
    
    # Kich thuoc du lieu lich su toi da de luu trong bo nho de tinh toan
    MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", 10000))

config = Config()
