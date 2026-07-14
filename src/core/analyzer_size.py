import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from src.database.store import store
from src.core.analyzer_helpers import (
    ema, is_ar_confirmed, get_percentile, get_dynamic_confirmation
)

logger = logging.getLogger(__name__)

class SizeAnalyzer:
    @staticmethod
    def analyze(history: List[Dict[str, Any]], df: pd.DataFrame, total_records: int, cfg_s: dict, 
                ar_window_s: int, N_size: int, ar_size_list: List[float], ar_threshold_size: float, 
                ar_size: float, prob_tai_sliding: float, prob_xiu_sliding: float, 
                mean_tai: float, std_tai: float, T_sat_tai: float, T_sat_xiu: float, 
                is_size_cooling: bool, size_loss_streak: int, 
                is_size_win_streak_pause: bool, size_win_streak: int, 
                buy_threshold_size: float, active_tai_len: int, active_tai_state: bool, 
                tai_streak_stats: dict, total_tai_transitions: int, 
                pred_streak_tai_switch: Any, pred_streak_tai_continue: Any, 
                is_high_conf_tai: bool, predicted_size: str, pred_tai: float) -> tuple:
        
        size_decision = "BỎ QUA"
        size_confidence = 50
        size_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."
        engine_used_size = "Heuristics"

        recent_history_size = history[:N_size]
        recent_tai_count_sz = sum(1 for r in recent_history_size if r.get("is_tai"))
        recent_xiu_count = N_size - recent_tai_count_sz
        prob_tai_sliding_sz = recent_tai_count_sz / N_size if N_size > 0 else 0.5
        prob_xiu_sliding_sz = recent_xiu_count / N_size if N_size > 0 else 0.5

        sliding_pred_size = "None"
        markov_pred_size = "None"

        ar_smooth_size = ema(ar_size_list)
        ar_confirmed_size = is_ar_confirmed(ar_size_list, ar_threshold_size)

        if is_size_cooling:
            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = f"Cooling-off sau {size_loss_streak} thua"
        elif is_size_win_streak_pause:
            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = f"Chốt lời sau {size_win_streak} thắng"
        elif ar_smooth_size >= ar_threshold_size and ar_confirmed_size:
            if len(history) >= 2:
                last_is_tai = history[0].get("is_tai")
                prev_is_tai = history[1].get("is_tai")
                if last_is_tai != prev_is_tai:
                    predicted_is_tai = not last_is_tai
                    base_rationale = f"Ping-Pong AR {ar_smooth_size*100:.1f}% (ngưỡng {ar_threshold_size*100:.1f}%)"
                    base_confidence = int(ar_smooth_size * 100)
                else:
                    predicted_is_tai = last_is_tai
                    base_rationale = "Răng cưa gãy, đánh thuận"
                    base_confidence = int(ar_smooth_size * 90)
            else:
                last_is_tai = history[0].get("is_tai") if history else True
                predicted_is_tai = not last_is_tai
                base_rationale = f"Ping-Pong AR {ar_smooth_size*100:.1f}% (ngưỡng {ar_threshold_size*100:.1f}%)"
                base_confidence = int(ar_smooth_size * 100)
            
            if predicted_is_tai and prob_tai_sliding_sz < prob_xiu_sliding_sz:
                predicted_is_tai = False
                size_rationale = f"{base_rationale}: mua Xỉu (hiệu chỉnh theo XS)"
            elif not predicted_is_tai and prob_xiu_sliding_sz < prob_tai_sliding_sz:
                predicted_is_tai = True
                size_rationale = f"{base_rationale}: mua Tài (hiệu chỉnh theo XS)"
            else:
                size_rationale = f"{base_rationale}: mua {'Tài' if predicted_is_tai else 'Xỉu'}"
            size_decision = "MUA TÀI" if predicted_is_tai else "MUA XỈU"
            size_confidence = min(base_confidence, 70)
        else:
            if prob_tai_sliding_sz >= buy_threshold_size and ar_smooth_size < ar_threshold_size and prob_tai_sliding_sz >= 0.60:
                size_decision = "MUA TÀI"
                size_confidence = int(prob_tai_sliding_sz * 100)
                size_rationale = f"Xác suất Tài {prob_tai_sliding_sz*100:.1f}% ≥{buy_threshold_size*100:.1f}%, AR trung bình, ưu tiên cao."
            elif prob_xiu_sliding_sz >= buy_threshold_size and ar_smooth_size < ar_threshold_size and prob_xiu_sliding_sz >= 0.60:
                size_decision = "MUA XỈU"
                size_confidence = int(prob_xiu_sliding_sz * 100)
                size_rationale = f"Xác suất Xỉu {prob_xiu_sliding_sz*100:.1f}% ≥{buy_threshold_size*100:.1f}%, AR trung bình, ưu tiên cao."
            else:
                sliding_pred_size = "Tai" if prob_tai_sliding_sz >= (mean_tai + 0.3*std_tai) else "Xiu" if prob_xiu_sliding_sz >= ((1.0 - mean_tai) + 0.3*std_tai) else "None"
                markov_pred_size = "Tai" if pred_tai >= 0.51 else "Xiu" if (1.0 - pred_tai) >= 0.51 else "None"
                if sliding_pred_size != "None" and markov_pred_size != "None" and sliding_pred_size == markov_pred_size:
                    is_sat_size = (sliding_pred_size == "Tai" and prob_tai_sliding_sz >= T_sat_tai) or (sliding_pred_size == "Xiu" and prob_xiu_sliding_sz >= T_sat_xiu)
                    if not is_sat_size:
                        prob_to_check = prob_tai_sliding_sz if sliding_pred_size == "Tai" else prob_xiu_sliding_sz
                        if prob_to_check >= 0.60:
                            size_decision = "MUA TÀI" if sliding_pred_size == "Tai" else "MUA XỈU"
                            size_confidence = min(int((0.6 * (prob_tai_sliding_sz if sliding_pred_size == "Tai" else prob_xiu_sliding_sz) + 0.4 * (pred_tai if sliding_pred_size == "Tai" else 1.0 - pred_tai)) * 100 * 1.05), 70)
                            size_rationale = f"Consensus: {sliding_pred_size} (≥60%)"
                        else:
                            size_rationale = "Xác suất < 60%, bỏ qua"
                    else:
                        size_rationale = "Bão hòa, bỏ qua"
                else:
                    size_rationale = "Không đồng thuận, bỏ qua"

        if size_decision == "MUA TÀI" and len(history) >= 3:
            if all(not r.get("is_tai") for r in history[:3]):
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = "Bỏ qua do 3 kỳ gần nhất đều Xỉu."
        elif size_decision == "MUA XỈU" and len(history) >= 3:
            if all(r.get("is_tai") for r in history[:3]):
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = "Bỏ qua do 3 kỳ gần nhất đều Tài."

        if size_decision == "MUA TÀI" and len(history) >= 6 and all(not r.get("is_le") for r in history[:6]):
            size_confidence -= 15
            if size_confidence < 55:
                size_decision = "BỎ QUA"
                size_rationale = "Tương quan xấu (bệt Chẵn 6 kỳ)"
        elif size_decision == "MUA XỈU" and len(history) >= 6 and all(r.get("is_le") for r in history[:6]):
            size_confidence -= 15
            if size_confidence < 55:
                size_decision = "BỎ QUA"
                size_rationale = "Tương quan xấu (bệt Lẻ 6 kỳ)"

        if size_decision == "BỎ QUA" and size_loss_streak < 3 and len(history) >= 7:
            if all(r.get("is_tai") for r in history[:7]):
                size_decision = "MUA XỈU"
                size_confidence = 60
                size_rationale = "Bệt Tài 7 kỳ - đảo chiều"
            elif all(not r.get("is_tai") for r in history[:7]):
                size_decision = "MUA TÀI"
                size_confidence = 60
                size_rationale = "Bệt Xỉu 7 kỳ - đảo chiều"

        try:
            stats_recent = store.get_prediction_stats_recent(limit=cfg_s["win_rate_filter_window"])
            size_wr = stats_recent.get("size", {}).get("win_rate", 0.5)
            if stats_recent.get("size", {}).get("total", 0) >= cfg_s["win_rate_filter_min_total"] and size_wr < cfg_s["win_rate_filter_threshold"] and size_decision != "BỎ QUA":
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Bỏ qua Size do win rate {cfg_s['win_rate_filter_window']} kỳ {size_wr*100:.1f}% < {cfg_s['win_rate_filter_threshold']*100:.0f}%."
        except Exception as e:
            logger.debug(f"Could not fetch size win rate: {e}")

        if size_decision != "BỎ QUA" and "Ping-Pong" not in size_rationale and "Răng cưa" not in size_rationale:
            direction = "tai" if size_decision == "MUA TÀI" else "xiu"
            if not get_dynamic_confirmation(history, direction, ar_smooth_size):
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Xu hướng {direction} chưa được xác nhận (AR={ar_smooth_size:.2f})."

        return size_decision, size_confidence, size_rationale, engine_used_size, sliding_pred_size, markov_pred_size
