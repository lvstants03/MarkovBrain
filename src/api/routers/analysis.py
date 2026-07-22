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
            "message": "Chưa có dữ liệu dự đoán để phân tích.",
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
            details["details"].append(f"Parity: Đoán {pred['predicted_parity']} ({pred['parity_confidence']}% xác suất) nhưng ra {pred['actual_parity']}")
        if pred.get("status_size") == "lose" and (pred.get("size_confidence") or 0) >= 68:
            is_weird = True
            details["details"].append(f"Size: Đoán {pred['predicted_size']} ({pred['size_confidence']}% xác suất) nhưng ra {pred['actual_size']}")
        
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
        
        status = "Ổn định" if win_rate >= 55.0 else "Hỗn loạn" if win_rate < 45.0 else "Bình thường"
        
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
            "Thời gian", "Kỳ cược", "Dự đoán Chẵn/Lẻ", "% Parity",
            "Dự đoán Tài/Xỉu", "% Size", "Kết quả thật", "Trạng thái"
        ])
        
        for p in predictions:
            raw_parity = p.get("predicted_parity", "Không có")
            parity_pred = "Lẻ" if raw_parity == "Le" else "Chẵn" if raw_parity == "Chan" else "Bỏ qua"
            parity_conf = f"{p.get('parity_confidence')}%" if (raw_parity != "Không có" and p.get('parity_confidence')) else "-"
            
            raw_size = p.get("predicted_size", "Không có")
            size_pred = "Tài" if raw_size == "Tai" else "Xỉu" if raw_size == "Xiu" else "Bỏ qua"
            size_conf = f"{p.get('size_confidence')}%" if (raw_size != "Không có" and p.get('size_confidence')) else "-"
            
            real_parity = p.get("actual_parity", "")
            real_size = p.get("actual_size", "")
            if real_parity or real_size:
                act_p = "Lẻ" if real_parity == "Le" else "Chẵn"
                act_s = "Tài" if real_size == "Tai" else "Xỉu"
                real_result = f"{act_s} / {act_p}"
            else:
                real_result = "-"
            
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

@router.get("/export/demo-bets")
async def export_demo_bets():
    bets = store.get_demo_bets(limit=10000)
    
    def generate():
        yield b'\xef\xbb\xbf'
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Thời gian", "Kỳ quay", "Hạng mục", "Cửa đặt", "Thuật toán",
            "Lượng cược", "Trạng thái", "Kết quả VND", "Số dư sau"
        ])
        
        for b in bets:
            market_txt = "Chẵn/Lẻ" if b.get("market_type") == "parity" else "Tài/Xỉu"
            status = b.get("status", "pending")
            status_txt = "Đang chờ" if status == "pending" else "THẮNG" if status == "win" else "THUA"
            
            if status == "win":
                result_vnd = f"+{b.get('win_amount', 0.0):,.0f}"
            elif status == "lose":
                result_vnd = f"-{b.get('amount', 0.0):,.0f}"
            else:
                result_vnd = "-"

            writer.writerow([
                b.get("time", ""),
                b.get("issue", ""),
                market_txt,
                b.get("prediction", ""),
                b.get("engine", "Heuristics"),
                f"{b.get('amount', 0.0):,.0f}",
                status_txt,
                result_vnd,
                f"{b.get('balance_after', 0.0):,.0f}"
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)
            
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nhat_ky_cuoc_gia_lap.csv"}
    )


@router.get("/market-health/analytics")
async def get_market_health_analytics():
    """
    Tra cuu va phan tich thong ke Suc Khoe Thi Truong tu CSDL.
    Xac dinh Khung Gio Vang va kiem tra dieu kien Auto-Pause (Win Rate 3 khoi < 48%).
    """
    try:
        from src.database.connection import db_session_scope
        from src.database.models.system import MarketHealthLog
        
        with db_session_scope() as session:
            logs = session.query(MarketHealthLog).order_by(MarketHealthLog.id.desc()).limit(30).all()
            
            if not logs:
                return {
                    "status": "success",
                    "message": "Chưa có đủ lịch sử MarketHealth trong CSDL.",
                    "data": {
                        "db_records_count": 0,
                        "recent_blocks": [],
                        "time_window_stats": {},
                        "golden_window": "Chưa xác định",
                        "requires_pause": False,
                        "recommendation": "Tiếp tục tích lũy dữ liệu quay."
                    }
                }
            
            records_data = []
            recent_win_rates = []
            for log in logs:
                records_data.append({
                    "id": log.id,
                    "issue_range": log.issue_range,
                    "total_bets": log.total_bets,
                    "win_count": log.win_count,
                    "win_rate_pct": log.win_rate_pct,
                    "status": log.status,
                    "created_at": log.created_at.strftime("%H:%M:%S %d/%m/%Y") if log.created_at else "-"
                })
                if len(recent_win_rates) < 3:
                    recent_win_rates.append(log.win_rate_pct)

            # Check Auto-Pause Guard (Average of recent 3 blocks < 48%)
            avg_recent_wr = sum(recent_win_rates) / len(recent_win_rates) if recent_win_rates else 50.0
            requires_pause = (avg_recent_wr < 48.0) and (len(recent_win_rates) >= 3)
            
            # Simple Time Window Distribution Mock/Grouping
            time_windows = {
                "Sáng (08:00 - 12:00)": [],
                "Trưa (12:00 - 14:00)": [],
                "Chiều (14:00 - 18:00)": [],
                "Tối (18:00 - 23:00)": []
            }
            
            for log in logs:
                if log.created_at:
                    hour = log.created_at.hour
                    if 8 <= hour < 12:
                        time_windows["Sáng (08:00 - 12:00)"].append(log.win_rate_pct)
                    elif 12 <= hour < 14:
                        time_windows["Trưa (12:00 - 14:00)"].append(log.win_rate_pct)
                    elif 14 <= hour < 18:
                        time_windows["Chiều (14:00 - 18:00)"].append(log.win_rate_pct)
                    else:
                        time_windows["Tối (18:00 - 23:00)"].append(log.win_rate_pct)
            
            window_averages = {}
            best_window = "Chiều (14:00 - 18:00)"
            highest_avg = 0.0
            
            for tw_name, wr_list in time_windows.items():
                if wr_list:
                    avg_wr = sum(wr_list) / len(wr_list)
                    window_averages[tw_name] = round(avg_wr, 1)
                    if avg_wr > highest_avg:
                        highest_avg = avg_wr
                        best_window = tw_name
                else:
                    window_averages[tw_name] = 50.0
            
            return {
                "status": "success",
                "data": {
                    "db_records_count": len(records_data),
                    "avg_recent_3_blocks_wr": round(avg_recent_wr, 1),
                    "requires_pause": requires_pause,
                    "golden_window": best_window if highest_avg >= 53.0 else "Chiều (14:00 - 18:00)",
                    "golden_window_wr": round(highest_avg, 1) if highest_avg > 0 else 55.0,
                    "time_window_stats": window_averages,
                    "recent_blocks": records_data[:10],
                    "recommendation": "TẠM NGỪNG CƯỢC: Thị trường đang hỗn loạn (Win Rate < 48%)" if requires_pause else f"Giao dịch tốt nhất vào khung giờ: {best_window}"
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi truy vấn MarketHealth Analytics: {e}")
