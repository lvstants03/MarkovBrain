import os
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.database.store import store
from src.core.scraper import scraper
from src.config import config

router = APIRouter()

class ConfigUrlRequest(BaseModel):
    url: str = Field(..., description="Duong dan WebSocket moi, vi du: wss://domain/ws")

@router.post("/config-url")
async def config_url(payload: ConfigUrlRequest):
    if not payload.url.startswith("ws://") and not payload.url.startswith("wss://"):
        raise HTTPException(status_code=400, detail="Duong dan phai bat dau bang ws:// hoac wss://")
    await scraper.update_url(payload.url)
    return {
        "status": "success",
        "message": f"Da cap nhat duong dan va khoi dong lai ket noi WebSocket toi: {payload.url}"
    }


class ConfigTokenRequest(BaseModel):
    token: str = Field(..., description="Token dang nhap moi cua he thong game")
    cf_auth_token: Optional[str] = Field(None, description="cf-auth-token dung cho HTTP requests")
    cookie: Optional[str] = Field(None, description="Cookie cua trinh duyet dung cho HTTP requests")

def update_env_ws_url(ws_url: str):
    import os
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    ws_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("TARGET_WS_URL="):
            new_lines.append(f"TARGET_WS_URL=\"{ws_url}\"\n")
            ws_found = True
        else:
            new_lines.append(line)
            
    if not ws_found:
        new_lines.append(f"TARGET_WS_URL=\"{ws_url}\"\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

@router.post("/config-token")
async def config_token(payload: ConfigTokenRequest):
    token = payload.token
    if "token=" in token:
        try:
            token = token.split("token=")[1].split("&")[0]
        except Exception:
            pass
    token = token.strip()
    
    new_url = f"wss://{config.TARGET_DOMAIN}/ws/?token={token}&x-device=pc"
    await scraper.update_url(new_url)
    
    try:
        update_env_ws_url(new_url)
    except Exception as e:
        pass
        
    # Luu HTTP headers va cookie neu co de dung cho fetch_user_balance
    if payload.cf_auth_token:
        store.update_http_headers(payload.cf_auth_token, payload.cookie)
        
    return {
        "status": "success",
        "message": f"Da cap nhat token moi va tai khoi dong ket noi WebSocket. Token: {token}"
    }


class ConfigFetcherRequest(BaseModel):
    url: str = Field(..., description="Duong dan HTTP API lay ket qua, vi du: https://domain/api/drawResult")
    interval: int = Field(default=60, ge=10, le=3600, description="Tan suat lay tu dong tinh bang giay (10s - 3600s)")
    headers: Optional[dict] = Field(default=None, description="HTTP Headers duoi dang JSON object (cookie, x-device, etc.)")

@router.post("/config-fetcher")
async def config_fetcher(payload: ConfigFetcherRequest):
    if not payload.url.startswith("http://") and not payload.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Duong dan phai bat dau bang http:// hoac https://")
    await scraper.update_fetch_config(payload.url, payload.interval, payload.headers)
    return {
        "status": "success",
        "message": f"Da cap nhat HTTP fetcher: URL={payload.url}, interval={payload.interval} giay va headers."
    }

@router.post("/trigger-fetch")
async def trigger_fetch():
    if not scraper.fetch_url and not scraper.ws_url:
        raise HTTPException(status_code=400, detail="Chua cau hinh URL de fetch hoac WebSocket URL")
    imported = await scraper.trigger_fetch()
    return {
        "status": "success",
        "message": f"Da dong bo xong tu dong. Da them moi {imported} ky quay vao store."
    }

@router.post("/reconnect")
async def trigger_reconnect():
    # Chu dong dong va ket noi lai WebSocket hien tai
    if scraper.is_running:
        await scraper.stop()
        await scraper.start()
        return {
            "status": "success",
            "message": "Da chu dong tai khoi dong lai ket noi WebSocket"
        }
    else:
        raise HTTPException(status_code=400, detail="Scraper hien dang khong chay")


class ConfigLotteryRequest(BaseModel):
    lottery_id: int = Field(..., description="ID cua xo so, vi du: 43 (45s), 44 (75s), 45 (5p)")
    lottery_code: str = Field(..., description="Code cua xo so, vi du: pmb45s, pmb75s, pmb5p")

def update_env_file(lottery_id: int, lottery_code: str):
    import os
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    id_found = False
    code_found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith("LOTTERY_ID="):
            new_lines.append(f"LOTTERY_ID={lottery_id}\n")
            id_found = True
        elif line.strip().startswith("LOTTERY_CODE="):
            new_lines.append(f"LOTTERY_CODE=\"{lottery_code}\"\n")
            code_found = True
        else:
            new_lines.append(line)
            
    if not id_found:
        new_lines.append(f"LOTTERY_ID={lottery_id}\n")
    if not code_found:
        new_lines.append(f"LOTTERY_CODE=\"{lottery_code}\"\n")
        
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

@router.post("/config-lottery")
async def config_lottery(payload: ConfigLotteryRequest):
    config.LOTTERY_ID = payload.lottery_id
    config.LOTTERY_CODE = payload.lottery_code
    
    try:
        update_env_file(payload.lottery_id, payload.lottery_code)
    except Exception as e:
        pass
        
    store.clear()
    if scraper.is_running:
        await scraper.stop()
        await scraper.start()
        
    return {
        "status": "success",
        "message": f"Da chuyen sang game: ID={config.LOTTERY_ID}, Code={config.LOTTERY_CODE}. Da xoa bo nho dem de nap lai lich su."
    }


@router.get("/socket/history")
async def get_socket_history(limit: int = Query(default=100, ge=1, le=500)):
    logs = store.get_connection_logs(limit=limit)
    return {
        "status": "success",
        "data": logs
    }


