import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from src.database.store import store
from src.core.analyzer.helpers import (
    ema, is_ar_confirmed, get_percentile, get_dynamic_confirmation
)

logger = logging.getLogger(__name__)

class ParityAnalyzer:
    @staticmethod
    def analyze(history: List[Dict[str, Any]], cfg_p: dict, N_parity: int, ar_parity_list: List[float], 
                ar_threshold_parity: float, mean_le: float, std_le: float, T_sat_le: float, T_sat_chan: float, 
                is_parity_cooling: bool, parity_loss_streak: int, is_parity_win_streak_pause: bool, 
                parity_win_streak: int, buy_threshold_parity: float, pred_le: float) -> tuple:
        
        parity_decision = "BỎ QUA"
        parity_confidence = 50
        parity_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."
        engine_used_parity = "Heuristics"

        recent_history_parity = history[:N_parity]
        actual_n_par = len(recent_history_parity)
        recent_le_count_par = sum(1 for r in recent_history_parity if r.get("is_le"))
        recent_chan_count = actual_n_par - recent_le_count_par
        prob_le_sliding_par = recent_le_count_par / actual_n_par if actual_n_par > 0 else 0.5
        prob_chan_sliding_par = recent_chan_count / actual_n_par if actual_n_par > 0 else 0.5

        sliding_pred = "None"
        markov_pred = "None"

        ar_smooth_parity = ema(ar_parity_list)
        ar_confirmed_parity = is_ar_confirmed(ar_parity_list, ar_threshold_parity)

        if is_parity_cooling:
            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = f"Cooling-off sau {parity_loss_streak} thua"
        elif is_parity_win_streak_pause:
            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = f"Chốt lời sau {parity_win_streak} thắng"
        elif ar_smooth_parity >= ar_threshold_parity and ar_confirmed_parity:
            if len(history) >= 2:
                last_is_le = history[0].get("is_le")
                prev_is_le = history[1].get("is_le")
                if last_is_le != prev_is_le:
                    predicted_is_le = not last_is_le
                    base_rationale = f"Ping-Pong AR {ar_smooth_parity*100:.1f}% (ngưỡng {ar_threshold_parity*100:.1f}%)"
                    base_confidence = int(ar_smooth_parity * 100)
                else:
                    predicted_is_le = last_is_le
                    base_rationale = "Răng cưa gãy, đánh thuận"
                    base_confidence = int(ar_smooth_parity * 90)
            else:
                last_is_le = history[0].get("is_le") if history else True
                predicted_is_le = not last_is_le
                base_rationale = f"Ping-Pong AR {ar_smooth_parity*100:.1f}% (ngưỡng {ar_threshold_parity*100:.1f}%)"
                base_confidence = int(ar_smooth_parity * 100)
            
            if predicted_is_le and prob_le_sliding_par < prob_chan_sliding_par:
                predicted_is_le = False
                parity_rationale = f"{base_rationale}: mua Chẵn (hiệu chỉnh theo XS)"
            elif not predicted_is_le and prob_chan_sliding_par < prob_le_sliding_par:
                predicted_is_le = True
                parity_rationale = f"{base_rationale}: mua Lẻ (hiệu chỉnh theo XS)"
            else:
                parity_rationale = f"{base_rationale}: mua {'Lẻ' if predicted_is_le else 'Chẵn'}"
            parity_decision = "MUA LẺ" if predicted_is_le else "MUA CHẴN"
            parity_confidence = min(base_confidence, 70)
        else:
            reversal_th = cfg_p.get("reversal_threshold", 0.85)
            min_prob = cfg_p.get("min_probability_threshold", 0.60)
            if prob_le_sliding_par >= reversal_th:
                parity_decision = "MUA CHẴN"
                parity_confidence = 65
                parity_rationale = f"Đảo chiều: Xác suất Lẻ cực đoan {prob_le_sliding_par*100:.1f}% ≥{reversal_th*100:.0f}%."
            elif prob_chan_sliding_par >= reversal_th:
                parity_decision = "MUA LẺ"
                parity_confidence = 65
                parity_rationale = f"Đảo chiều: Xác suất Chẵn cực đoan {prob_chan_sliding_par*100:.1f}% ≥{reversal_th*100:.0f}%."
            elif prob_le_sliding_par >= buy_threshold_parity and ar_smooth_parity < ar_threshold_parity and prob_le_sliding_par >= min_prob:
                parity_decision = "MUA LẺ"
                parity_confidence = int(prob_le_sliding_par * 100)
                parity_rationale = f"Xác suất Lẻ {prob_le_sliding_par*100:.1f}% ≥{buy_threshold_parity*100:.1f}%, AR trung bình, ưu tiên cao."
            elif prob_chan_sliding_par >= buy_threshold_parity and ar_smooth_parity < ar_threshold_parity and prob_chan_sliding_par >= min_prob:
                parity_decision = "MUA CHẴN"
                parity_confidence = int(prob_chan_sliding_par * 100)
                parity_rationale = f"Xác suất Chẵn {prob_chan_sliding_par*100:.1f}% ≥{buy_threshold_parity*100:.1f}%, AR trung bình, ưu tiên cao."
            else:
                sliding_pred = "Le" if prob_le_sliding_par >= (mean_le + 0.3*std_le) else "Chan" if prob_chan_sliding_par >= ((1.0 - mean_le) + 0.3*std_le) else "None"
                markov_pred = "Le" if pred_le >= 0.51 else "Chan" if (1.0 - pred_le) >= 0.51 else "None"
                if sliding_pred != "None" and markov_pred != "None" and sliding_pred == markov_pred:
                    is_sat = (sliding_pred == "Le" and prob_le_sliding_par >= T_sat_le) or (sliding_pred == "Chan" and prob_chan_sliding_par >= T_sat_chan)
                    if not is_sat:
                        prob_to_check = prob_le_sliding_par if sliding_pred == "Le" else prob_chan_sliding_par
                        if prob_to_check >= min_prob:
                            parity_decision = "MUA LẺ" if sliding_pred == "Le" else "MUA CHẴN"
                            parity_confidence = min(int((0.6 * (prob_le_sliding_par if sliding_pred == "Le" else prob_chan_sliding_par) + 0.4 * (pred_le if sliding_pred == "Le" else 1.0 - pred_le)) * 100 * 1.05), 70)
                            parity_rationale = f"Consensus: {sliding_pred} (≥{min_prob*100:.0f}%)"
                        else:
                            parity_rationale = f"Xác suất < {min_prob*100:.0f}%, bỏ qua"
                    else:
                        parity_rationale = "Bão hòa, bỏ qua"
                else:
                    parity_rationale = "Không đồng thuận, bỏ qua"

        if parity_decision == "MUA LẺ" and len(history) >= 3:
            if all(not r.get("is_le") for r in history[:3]):
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = "Bỏ qua do 3 kỳ gần nhất đều Chẵn."
        elif parity_decision == "MUA CHẴN" and len(history) >= 3:
            if all(r.get("is_le") for r in history[:3]):
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = "Bỏ qua do 3 kỳ gần nhất đều Lẻ."

        if parity_decision == "MUA LẺ" and len(history) >= 6 and all(not r.get("is_tai") for r in history[:6]):
            parity_confidence -= 15
            if parity_confidence < 55:
                parity_decision = "BỎ QUA"
                parity_rationale = "Tương quan xấu (bệt Xỉu 6 kỳ)"
        elif parity_decision == "MUA CHẴN" and len(history) >= 6 and all(r.get("is_tai") for r in history[:6]):
            parity_confidence -= 15
            if parity_confidence < 55:
                parity_decision = "BỎ QUA"
                parity_rationale = "Tương quan xấu (bệt Tài 6 kỳ)"

        if parity_decision == "BỎ QUA" and parity_loss_streak < 3 and len(history) >= 7:
            if all(r.get("is_le") for r in history[:7]):
                parity_decision = "MUA CHẴN"
                parity_confidence = 60
                parity_rationale = "Bệt Lẻ 7 kỳ - đảo chiều"
            elif all(not r.get("is_le") for r in history[:7]):
                parity_decision = "MUA LẺ"
                parity_confidence = 60
                parity_rationale = "Bệt Chẵn 7 kỳ - đảo chiều"

        try:
            stats_recent = store.get_prediction_stats_recent(limit=cfg_p["win_rate_filter_window"])
            parity_wr = stats_recent.get("parity", {}).get("win_rate", 0.5)
            if stats_recent.get("parity", {}).get("total", 0) >= cfg_p["win_rate_filter_min_total"] and parity_wr < cfg_p["win_rate_filter_threshold"] and parity_decision != "BỎ QUA":
                recent_preds = store.get_prediction_history(limit=3)
                consecutive_ignored = sum(1 for p in recent_preds if p.get("status_parity") == "ignored")
                if consecutive_ignored < 3:
                    parity_decision = "BỎ QUA"
                    parity_confidence = 50
                    parity_rationale = f"Bỏ qua Parity do win rate {cfg_p['win_rate_filter_window']} kỳ {parity_wr*100:.1f}% < {cfg_p['win_rate_filter_threshold']*100:.0f}%."
                else:
                    logger.info(f"[Parity] Đã bỏ qua {consecutive_ignored} kỳ liên tiếp do win_rate thấp, cho phép thử lại để phục hồi.")
        except Exception as e:
            logger.debug(f"Could not fetch parity win rate: {e}")

        if parity_decision != "BỎ QUA" and "Ping-Pong" not in parity_rationale and "Răng cưa" not in parity_rationale:
            direction = "le" if parity_decision == "MUA LẺ" else "chan"
            if not get_dynamic_confirmation(history, direction, ar_smooth_parity):
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Xu hướng {direction} chưa được xác nhận (AR={ar_smooth_parity:.2f})."

        return parity_decision, parity_confidence, parity_rationale, engine_used_parity, sliding_pred, markov_pred
