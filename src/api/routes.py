from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from src.database.store import store
from src.core.analyzer import ProbabilityAnalyzer
from src.core.scraper import scraper

router = APIRouter(prefix="/api")

class MockDrawRequest(BaseModel):
    issue: str = Field(..., description="Ma ky quay, vi du: 20260628001")
    numbers: List[int] = Field(..., description="Danh sach 5 chu so tu 0 den 9", min_items=5, max_items=5)

@router.get("/history")
async def get_history(limit: int = Query(default=100, ge=1, le=1000)):
    # Lay danh sach lich su cac ky quay so
    await scraper.fetch_latest_info()
    history = store.get_history(limit=limit)
    return {
        "status": "success",
        "count": len(history),
        "total_in_store": store.get_count(),
        "data": history
    }

@router.get("/statistics")
async def get_statistics(limit: int = Query(default=500, ge=1, le=10000)):
    # Lay ket qua phan tich thong ke xac suat Chan/Le, Tai/Xiu
    await scraper.fetch_latest_info()
    history = store.get_history(limit=limit)
    stats = ProbabilityAnalyzer.analyze(history)
    return {
        "status": "success",
        "limit_analyzed": limit,
        "data": stats
    }

@router.post("/mock-draw")
async def mock_draw(payload: MockDrawRequest):
    # Endpoint ho tro day du lieu gia lap de test thong ke xac suat
    for num in payload.numbers:
        if num < 0 or num > 9:
            raise HTTPException(status_code=400, detail="Moi chu so phai nam trong khoang tu 0 den 9")
            
    added = store.add_record(payload.issue, payload.numbers)
    if not added:
        return {
            "status": "ignored",
            "message": f"Ky quay {payload.issue} da ton tai trong store"
        }
        
    return {
        "status": "success",
        "message": f"Da them ky quay gia lap {payload.issue} thanh cong"
    }

@router.post("/clear")
async def clear_store():
    # Xoa toan bo lich su trong store
    store.clear()
    return {
        "status": "success",
        "message": "Da xoa toan bo du lieu trong store"
    }

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

@router.post("/config-token")
async def config_token(payload: ConfigTokenRequest):
    # Trich xuat phan URL co so, giu nguyen cac tham so khac nhu x-device neu muon
    # Hoac tu dong ghep vao URL chuan cua game
    new_url = f"wss://vip.ee8833.me/ws/?token={payload.token}&x-device=pc"
    await scraper.update_url(new_url)
    return {
        "status": "success",
        "message": f"Da cap nhat token moi va tai khoi dong ket noi WebSocket. Token: {payload.token}"
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

@router.post("/import-history")
async def import_history(payload: dict):
    # Endpoint ho tro import nhanh lich su tu ket qua copy tren Network cua trinh duyet
    draw_list = []
    
    # Kiem tra cac cau truc JSON co the co
    if "data" in payload and isinstance(payload["data"], dict) and "list" in payload["data"]:
        draw_list = payload["data"]["list"]
    elif "list" in payload and isinstance(payload["list"], list):
        draw_list = payload["list"]
    elif isinstance(payload, list):
        draw_list = payload
        
    imported_count = 0
    for item in draw_list:
        if not isinstance(item, dict):
            continue
        issue = str(item.get("issue") or "")
        digits = item.get("open_numbers_formatted") or []
        numbers = [int(x) for x in digits if str(x).isdigit()]
        if issue and len(numbers) == 5:
            added = store.add_record(issue, numbers)
            if added:
                imported_count += 1
                
    return {
        "status": "success",
        "imported_records": imported_count,
        "total_in_store": store.get_count()
    }
