from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import io
import csv
from src.database.store import store
from src.core.analyzer import ProbabilityAnalyzer
from src.core.scraper import scraper
from src.config import config

router = APIRouter(prefix="/api")

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

@router.get("/market-analysis")
async def get_market_analysis(limit: int = Query(default=100, ge=30, le=1000)):
    predictions = store.get_prediction_history(limit=limit)
    if not predictions:
        return {
            "status": "success",
            "message": "Chưa có dữ liệu dự đoán để phân tích.",
            "data": {
                "weird_breaks": [],
                "blocks_30": [],
                "golden_hours": []
            }
        }
    
    # 1. Phát hiện "Kỳ gãy lạ" (Weird Breaks): Predictions with confidence >= 68% (real confidence threshold) that lost
    weird_breaks = []
    for pred in predictions:
        is_weird = False
        details = {
            "issue": pred["issue"],
            "time": pred.get("time", "-"),
            "details": []
        }
        if pred.get("status_parity") == "lose" and pred.get("parity_confidence", 0) >= 68:
            is_weird = True
            details["details"].append(f"Parity: đoán {pred['predicted_parity']} ({pred['parity_confidence']}% xác suất) nhưng ra {pred['actual_parity']}")
        if pred.get("status_size") == "lose" and pred.get("size_confidence", 0) >= 68:
            is_weird = True
            details["details"].append(f"Size: đoán {pred['predicted_size']} ({pred['size_confidence']}% xác suất) nhưng ra {pred['actual_size']}")
        
        if is_weird:
            weird_breaks.append(details)
            
    # 2. Phân tích theo từng khối 30 kỳ (Sliding Block win rates)
    blocks_analysis = []
    ordered_preds = list(reversed(predictions))
    for i in range(len(ordered_preds) - 29):
        block = ordered_preds[i:i+30]
        wins = 0
        total_bets = 0
        for p in block:
            if p.get("status_parity") == "win":
                wins += 1
                total_bets += 1
            elif p.get("status_parity") == "lose":
                total_bets += 1
            if p.get("status_size") == "win":
                wins += 1
                total_bets += 1
            elif p.get("status_size") == "lose":
                total_bets += 1
        
        win_rate = (wins / total_bets * 100) if total_bets > 0 else 0.0
        start_issue = block[0]["issue"]
        end_issue = block[-1]["issue"]
        start_time = block[0].get("time", "-")
        end_time = block[-1].get("time", "-")
        
        status = "Ổn định" if win_rate >= 55.0 else "Hỗn loạn" if win_rate < 45.0 else "Bình thường"
        
        blocks_analysis.append({
            "block_range": f"{start_issue} - {end_issue}",
            "time_range": f"{start_time} - {end_time}",
            "total_bets": total_bets,
            "win_rate": round(win_rate, 1),
            "status": status
        })
        
    # 3. Phân tích khung giờ vàng (Best betting hours)
    hourly_stats = {}
    for p in predictions:
        time_str = p.get("time", "")
        # Expecting format: "HH:MM:SS DD/MM/YYYY"
        if len(time_str) >= 5:
            try:
                # Get the time part, then the hour
                hour = time_str.split(" ")[0].split(":")[0]
                if hour.isdigit():
                    if hour not in hourly_stats:
                        hourly_stats[hour] = {"wins": 0, "total": 0}
                    
                    if p.get("status_parity") == "win":
                        hourly_stats[hour]["wins"] += 1
                        hourly_stats[hour]["total"] += 1
                    elif p.get("status_parity") == "lose":
                        hourly_stats[hour]["total"] += 1
                        
                    if p.get("status_size") == "win":
                        hourly_stats[hour]["wins"] += 1
                        hourly_stats[hour]["total"] += 1
                    elif p.get("status_size") == "lose":
                        hourly_stats[hour]["total"] += 1
            except Exception:
                pass
                
    golden_hours = []
    for hr, stats in hourly_stats.items():
        if stats["total"] > 0:
            win_rate = (stats["wins"] / stats["total"]) * 100
            golden_hours.append({
                "hour": f"{hr}:00 - {hr}:59",
                "win_rate": round(win_rate, 1),
                "total_bets": stats["total"]
            })
    golden_hours.sort(key=lambda x: x["win_rate"], reverse=True)
    
    return {
        "status": "success",
        "data": {
            "weird_breaks": weird_breaks[:20],
            "blocks_30": list(reversed(blocks_analysis))[:10],
            "golden_hours": golden_hours
        }
    }


@router.get("/export/history")
async def export_history():
    history = store.get_history(limit=10000)
    
    def generate():
        # UTF-8 BOM for Excel
        yield b'\xef\xbb\xbf'
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Kỳ (Issue)", "Thời gian", "Số kết quả", "Tổng điểm", "Tài / Xỉu", "Chẵn / Lẻ"])
        
        for r in history:
            numbers_str = " ".join(map(str, r.get("numbers") or []))
            writer.writerow([
                r.get("issue", ""),
                r.get("time", ""),
                numbers_str,
                r.get("total", ""),
                "Tài" if r.get("is_tai") else "Xỉu",
                "Lẻ" if r.get("is_le") else "Chẵn"
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)
            
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lich_su_quay_so.csv"}
    )


@router.get("/export/predictions")
async def export_predictions():
    predictions = store.get_prediction_history(limit=10000)
    
    def generate():
        yield b'\xef\xbb\xbf'
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Thời gian",
            "Kỳ cược",
            "Dự đoán Chẵn/Lẻ",
            "% Parity",
            "Dự đoán Tài/Xỉu",
            "% Size",
            "Kết quả thật",
            "Trạng thái"
        ])
        
        for p in predictions:
            # Format Parity predict to Vietnamese
            raw_parity = p.get("predicted_parity", "Không có")
            parity_pred = "Lẻ" if raw_parity == "Le" else "Chẵn" if raw_parity == "Chan" else "Bỏ qua"
            parity_conf = f"{p.get('parity_confidence')}%" if (raw_parity != "Không có" and p.get('parity_confidence')) else "-"
            
            # Format Size predict to Vietnamese
            raw_size = p.get("predicted_size", "Không có")
            size_pred = "Tài" if raw_size == "Tai" else "Xỉu" if raw_size == "Xiu" else "Bỏ qua"
            size_conf = f"{p.get('size_confidence')}%" if (raw_size != "Không có" and p.get('size_confidence')) else "-"
            
            # Real result
            real_parity = p.get("actual_parity", "")
            real_size = p.get("actual_size", "")
            if real_parity or real_size:
                act_p = "Lẻ" if real_parity == "Le" else "Chẵn"
                act_s = "Tài" if real_size == "Tai" else "Xỉu"
                real_result = f"{act_s} / {act_p}"
            else:
                real_result = "-"
            
            # Resolve status exactly like UI
            status_parity = p.get("status_parity", "ignored")
            status_size = p.get("status_size", "ignored")
            
            if status_parity == "pending" or status_size == "pending":
                status_txt = "Đang chờ"
            elif status_parity == "ignored" and status_size == "ignored":
                status_txt = "Bỏ qua"
            else:
                win_count = 0
                loss_count = 0
                if status_parity == "win":
                    win_count += 1
                elif status_parity == "lose":
                    loss_count += 1
                if status_size == "win":
                    win_count += 1
                elif status_size == "lose":
                    loss_count += 1
                
                if loss_count == 0:
                    status_txt = "THẮNG"
                elif win_count == 0:
                    status_txt = "THUA"
                else:
                    status_txt = "HÒA (1W/1L)"
                
            writer.writerow([
                p.get("time", ""),
                p.get("issue", ""),
                parity_pred,
                parity_conf,
                size_pred,
                size_conf,
                real_result,
                status_txt
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)
            
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lich_su_du_doan.csv"}
    )


class DemoConfigUpdate(BaseModel):
    amount: Optional[float] = Field(None, ge=0.0, description="Muc tien dat cuoc moi lenh gia lap")
    strategy: Optional[str] = Field(None, description="Chien thuat dat cuoc (fixed, martingale_x3, fixed_fractional_3, kelly_third, kelly_half_stoploss)")
    demo_balance: Optional[float] = Field(None, ge=0.0, description="Tu dat so du gia lap moi")

@router.get("/balance")
async def get_balance_info():
    from src.core.money_management import MoneyManager, get_effective_win_rate, STRATEGY_LABELS
    balances = store.get_balances()
    bets = store.get_demo_bets(limit=50)

    demo_balance = balances.get("demo_balance", 0.0)
    base_bet = balances.get("demo_bet_amount", 100000.0)
    strategy = balances.get("demo_bet_strategy", "fixed")

    loss_streaks = store.get_loss_streaks()
    p_streak = loss_streaks.get("parity", 0)
    s_streak = loss_streaks.get("size", 0)

    daily_info = store.get_daily_loss_info()
    p_daily = daily_info.get("parity_daily_loss_count", 0)
    s_daily = daily_info.get("size_daily_loss_count", 0)
    p_pause = daily_info.get("parity_pause_until", None)
    s_pause = daily_info.get("size_pause_until", None)

    # Determine if market is stable
    is_stable = store.is_market_stable()

    # Win rate thuc te tu 15 ky gan nhat
    prediction_stats_recent = store.get_prediction_stats_recent(15)
    p_win_rate = get_effective_win_rate(prediction_stats_recent, "parity")
    s_win_rate = get_effective_win_rate(prediction_stats_recent, "size")

    # Tinh next bet dung MoneyManager
    p_bet = MoneyManager.calculate_bet(
        strategy=strategy, base_amount=base_bet, current_balance=demo_balance,
        loss_streak=p_streak, daily_loss_count=p_daily, pause_until=p_pause, win_rate=p_win_rate,
        is_stable=is_stable
    )
    s_bet = MoneyManager.calculate_bet(
        strategy=strategy, base_amount=base_bet, current_balance=demo_balance,
        loss_streak=s_streak, daily_loss_count=s_daily, pause_until=s_pause, win_rate=s_win_rate,
        is_stable=is_stable
    )

    max_streak = MoneyManager.get_max_streak_tolerated(strategy, demo_balance, base_bet, s_win_rate)

    is_bankrupt = demo_balance <= 0 or (p_bet <= 0 and s_bet <= 0 and strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"))
    if strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"):
        is_bankrupt = is_bankrupt or (p_bet > demo_balance and s_bet > demo_balance)

    collapses = store.get_capital_collapses(limit=50)

    # Risk info panel day du
    risk_info_parity = MoneyManager.get_risk_info(
        strategy=strategy, current_balance=demo_balance, base_amount=base_bet,
        win_rate=p_win_rate, loss_streak=p_streak, daily_loss_count=p_daily, pause_until=p_pause,
        is_stable=is_stable
    )
    risk_info_size = MoneyManager.get_risk_info(
        strategy=strategy, current_balance=demo_balance, base_amount=base_bet,
        win_rate=s_win_rate, loss_streak=s_streak, daily_loss_count=s_daily, pause_until=s_pause,
        is_stable=is_stable
    )

    return {
        "status": "success",
        "balances": balances,
        "max_loss_streak_tolerated": max_streak,
        "is_bankrupt": is_bankrupt,
        "next_bet_amounts": {
            "parity": p_bet,
            "size": s_bet,
            "parity_streak": p_streak,
            "size_streak": s_streak
        },
        "risk_info": {
            "parity": risk_info_parity,
            "size": risk_info_size,
        },
        "strategy_labels": STRATEGY_LABELS,
        "demo_bets": bets,
        "capital_collapses": collapses
    }

@router.post("/balance/reset")
async def reset_demo_balance():
    success = store.reset_demo_balance()
    return {
        "status": "success" if success else "error",
        "message": "Đã reset số dư giả lập về 10,000,000 VND và xóa lịch sử cược ảo."
    }

@router.post("/balance/clear-bets")
async def clear_demo_bets_endpoint():
    # 1. Clear predictions and draw records
    store.clear()
    
    # 2. Clear simulated bet logs & reset loss streaks (keeping demo balance)
    success = store.clear_demo_bets()
    
    # 3. Reload latest draw records from the scraper (async bootstrap/fetch)
    from src.core.scraper import scraper
    import asyncio
    asyncio.create_task(scraper.fetch_latest_info())
    
    return {
        "status": "success" if success else "error",
        "message": "Đã xóa sạch toàn bộ kỳ quay, lịch sử dự đoán, cược giả lập và đang tải về dữ liệu mới nhất."
    }

@router.post("/balance/config")
async def update_demo_config(config_data: DemoConfigUpdate):
    from src.core.money_management import MoneyManager, get_effective_win_rate, ALL_STRATEGIES
    success = True

    if config_data.amount is not None:
        success = success and store.set_demo_bet_amount(config_data.amount)
    if config_data.strategy is not None:
        if config_data.strategy not in ALL_STRATEGIES:
            return {
                "status": "error",
                "message": f"Strategy khong hop le. Cac gia tri cho phep: {ALL_STRATEGIES}",
                "recommended_bet": None
            }
        success = success and store.set_demo_bet_strategy(config_data.strategy)
    if config_data.demo_balance is not None:
        success = success and store.update_demo_balance(config_data.demo_balance)

    # Lay trang thai hien tai de tinh recommended_bet
    balances = store.get_balances()
    current_balance = balances.get("demo_balance", 0.0)
    current_strategy = balances.get("demo_bet_strategy", "fixed")
    prediction_stats_recent = store.get_prediction_stats_recent(15)
    win_rate = get_effective_win_rate(prediction_stats_recent, "size")

    recommended_bet = MoneyManager.get_recommended_base(
        strategy=current_strategy,
        balance=current_balance,
        win_rate=win_rate,
    ) if current_balance > 0 else None

    return {
        "status": "success" if success else "error",
        "message": "Da cap nhat cau hinh tai chinh gia lap thanh cong.",
        "recommended_bet": recommended_bet
    }

@router.post("/script/reload")
async def trigger_script_reload():
    store.set_script_command("reload")
    return {
        "status": "success",
        "message": "Đã gửi lệnh yêu cầu tải lại trang game. Tampermonkey sẽ thực hiện tải lại sau tối đa 2 giây."
    }

@router.get("/script/command")
async def get_script_command():
    cmd = store.get_script_command()
    return {
        "command": cmd
    }

