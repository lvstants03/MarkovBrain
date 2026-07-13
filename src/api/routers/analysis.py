import io
import csv
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from src.database.store import store

router = APIRouter()

@router.get("/market-analysis")
async def get_market_analysis(limit: int = Query(default=100, ge=30, le=1000)):
    predictions = store.get_prediction_history(limit=limit)
    if not predictions:
        return {
            "status": "success",
            "message": "Ch?a c? d? li?u d? ?o?n ?? ph?n t?ch.",
            "data": {
                "weird_breaks": [],
                "blocks_30": [],
                "golden_hours": []
            }
        }
    
    weird_breaks = []
    for pred in predictions:
        is_weird = False
        details = {
            "issue": pred["issue"],
            "time": pred.get("time", "-"),
            "details": []
        }
        if pred.get("status_parity") == "lose" and (pred.get("parity_confidence") or 0) >= 68:
            is_weird = True
            details["details"].append(f"Parity: ?o?n {pred['predicted_parity']} ({pred['parity_confidence']}% x?c su?t) nh?ng ra {pred['actual_parity']}")
        if pred.get("status_size") == "lose" and (pred.get("size_confidence") or 0) >= 68:
            is_weird = True
            details["details"].append(f"Size: ?o?n {pred['predicted_size']} ({pred['size_confidence']}% x?c su?t) nh?ng ra {pred['actual_size']}")
        
        if is_weird:
            weird_breaks.append(details)
            
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
        
        status = "?n ??nh" if win_rate >= 55.0 else "H?n lo?n" if win_rate < 45.0 else "B?nh th??ng"
        
        blocks_analysis.append({
            "block_range": f"{start_issue} - {end_issue}",
            "time_range": f"{start_time} - {end_time}",
            "total_bets": total_bets,
            "win_rate": round(win_rate, 1),
            "status": status
        })
        
    hourly_stats = {}
    for p in predictions:
        time_str = p.get("time", "")
        if len(time_str) >= 5:
            try:
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
        yield b'\xef\xbb\xbf'
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["K? (Issue)", "Th?i gian", "S? k?t qu?", "T?ng ?i?m", "T?i / X?u", "Ch?n / L?"])
        
        for r in history:
            numbers_str = " ".join(map(str, r.get("numbers") or []))
            writer.writerow([
                r.get("issue", ""),
                r.get("time", ""),
                numbers_str,
                r.get("total", ""),
                "T?i" if r.get("is_tai") else "X?u",
                "L?" if r.get("is_le") else "Ch?n"
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
            "Th?i gian", "K? c??c", "D? ?o?n Ch?n/L?", "% Parity",
            "D? ?o?n T?i/X?u", "% Size", "K?t qu? th?t", "Tr?ng th?i"
        ])
        
        for p in predictions:
            raw_parity = p.get("predicted_parity", "Kh?ng c?")
            parity_pred = "L?" if raw_parity == "Le" else "Ch?n" if raw_parity == "Chan" else "B? qua"
            parity_conf = f"{p.get('parity_confidence')}%" if (raw_parity != "Kh?ng c?" and p.get('parity_confidence')) else "-"
            
            raw_size = p.get("predicted_size", "Kh?ng c?")
            size_pred = "T?i" if raw_size == "Tai" else "X?u" if raw_size == "Xiu" else "B? qua"
            size_conf = f"{p.get('size_confidence')}%" if (raw_size != "Kh?ng c?" and p.get('size_confidence')) else "-"
            
            real_parity = p.get("actual_parity", "")
            real_size = p.get("actual_size", "")
            if real_parity or real_size:
                act_p = "L?" if real_parity == "Le" else "Ch?n"
                act_s = "T?i" if real_size == "Tai" else "X?u"
                real_result = f"{act_s} / {act_p}"
            else:
                real_result = "-"
            
            status_parity = p.get("status_parity", "ignored")
            status_size = p.get("status_size", "ignored")
            
            if status_parity == "pending" or status_size == "pending":
                status_txt = "?ang ch?"
            elif status_parity == "ignored" and status_size == "ignored":
                status_txt = "B? qua"
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
                    status_txt = "TH?NG"
                elif win_count == 0:
                    status_txt = "THUA"
                else:
                    status_txt = "H?A (1W/1L)"
                
            writer.writerow([
                p.get("time", ""), p.get("issue", ""), parity_pred, parity_conf,
                size_pred, size_conf, real_result, status_txt
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)
            
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lich_su_du_doan.csv"}
    )
