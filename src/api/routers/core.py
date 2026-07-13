from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.database.store import store
from src.core.analyzer import ProbabilityAnalyzer
from src.core.scraper import scraper
from src.config import config

router = APIRouter()

class MockDrawRequest(BaseModel):
    issue: str = Field(..., description="Ma ky quay, vi du: 20260628001")
    numbers: List[int] = Field(..., description="Danh sach 5 chu so tu 0 den 9", min_items=5, max_items=5)

@router.get("/history")
async def get_history(limit: int = Query(default=100, ge=1, le=1000)):
    # Lay danh sach lich su cac ky quay so
    history = store.get_history(limit=limit)
    return {
        "status": "success",
        "count": len(history),
        "total_in_store": store.get_count(),
        "data": history
    }


def get_next_issue_code(last_issue: str) -> str:
    if not last_issue:
        return ""
    try:
        return str(int(last_issue) + 1)
    except Exception:
        return last_issue

@router.get("/statistics")
async def get_statistics(limit: int = Query(default=500, ge=1, le=10000)):
    # Lay ket qua phan tich thong ke xac suat Chan/Le, Tai/Xiu
    history = store.get_history(limit=limit)
    stats = ProbabilityAnalyzer.analyze(history)
    
    # Predict next issue and save to store for win rate tracking
    if history:
        last_issue = history[0]["issue"]
        next_issue = get_next_issue_code(last_issue)
        
        # Override with scraper's active issue if available and newer
        scraper_curr = getattr(scraper, "current_issue", "")
        if scraper_curr and scraper_curr > last_issue:
            next_issue = scraper_curr
            
        existing_pred = store.get_prediction(next_issue) if next_issue else None
        
        if existing_pred:
            # Override stats with existing saved prediction to avoid UI mismatch
            p_pred = existing_pred.get("predicted_parity", "Không có")
            s_pred = existing_pred.get("predicted_size", "Không có")
            
            stats["ai_recommendation"] = {
                "engine": existing_pred.get("engine", "Saved Prediction"),
                "parity": {
                    "decision": "MUA LẺ" if p_pred == "Le" else "MUA CHẴN" if p_pred == "Chan" else "BỎ QUA",
                    "confidence": existing_pred.get("parity_confidence") or 50,
                    "rationale": existing_pred.get("parity_rationale") or "Dự đoán đã được ghi nhận trong cơ sở dữ liệu."
                },
                "size": {
                    "decision": "MUA TÀI" if s_pred == "Tai" else "MUA XỈU" if s_pred == "Xiu" else "BỎ QUA",
                    "confidence": existing_pred.get("size_confidence") or 50,
                    "rationale": existing_pred.get("size_rationale") or "Dự đoán đã được ghi nhận trong cơ sở dữ liệu."
                }
            }
        else:
            ai_parity = stats.get("ai_recommendation", {}).get("parity", {}).get("decision", "BỎ QUA")
            ai_size = stats.get("ai_recommendation", {}).get("size", {}).get("decision", "BỎ QUA")
            
            predicted_parity = "Le" if ai_parity == "MUA LẺ" else "Chan" if ai_parity == "MUA CHẴN" else "Không có"
            predicted_size = "Tai" if ai_size == "MUA TÀI" else "Xiu" if ai_size == "MUA XỈU" else "Không có"
            
            parity_conf = stats.get("ai_recommendation", {}).get("parity", {}).get("confidence", 50)
            size_conf = stats.get("ai_recommendation", {}).get("size", {}).get("confidence", 50)
            
            # Always save the prediction to history (even if BỎ QUA) to reset streaks correctly and show on UI
            store.add_prediction(next_issue, {
                "predicted_parity": predicted_parity,
                "predicted_size": predicted_size,
                "parity_confidence": parity_conf if predicted_parity != "Không có" else None,
                "size_confidence": size_conf if predicted_size != "Không có" else None,
                "total_records_at_prediction": stats.get("total_records", 0),
                "engine": stats.get("ai_recommendation", {}).get("engine", "Heuristics (3-Layer)"),
                "parity_rationale": stats.get("ai_recommendation", {}).get("parity", {}).get("rationale", ""),
                "size_rationale": stats.get("ai_recommendation", {}).get("size", {}).get("rationale", "")
            })
            
    prediction_stats = store.get_prediction_stats()
    
    return {
        "status": "success",
        "limit_analyzed": limit,
        "prediction_stats": prediction_stats,
        "ws_status": scraper.connection_status,
        "lottery_id": config.LOTTERY_ID,
        "lottery_code": config.LOTTERY_CODE,
        "data": stats
    }

@router.get("/predictions")
async def get_predictions(limit: int = Query(default=100, ge=1, le=1000)):
    history = store.get_prediction_history(limit=limit)
    stats = store.get_prediction_stats()
    return {
        "status": "success",
        "count": len(history),
        "stats": stats,
        "data": history
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


