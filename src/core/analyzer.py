import pandas as pd
import numpy as np
from typing import Dict, Any, List
import time
import logging
from src.config import config
from src.database.store import store
from src.core.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

class ProbabilityAnalyzer:
    @staticmethod
    def _analyze_streak_transitions(series: pd.Series) -> tuple[dict, int, Any]:
        streak_stats = {}
        if len(series) == 0:
            return streak_stats, 0, None
        current_state = series.iloc[0]
        current_len = 1
        for val in series.iloc[1:]:
            if val == current_state:
                if current_len not in streak_stats:
                    streak_stats[current_len] = {"continue": 0, "switch": 0}
                streak_stats[current_len]["continue"] += 1
                current_len += 1
            else:
                if current_len not in streak_stats:
                    streak_stats[current_len] = {"continue": 0, "switch": 0}
                streak_stats[current_len]["switch"] += 1
                current_state = val
                current_len = 1
        active_state = series.iloc[-1]
        active_len = 0
        for val in series.iloc[::-1]:
            if val == active_state:
                active_len += 1
            else:
                break
        return streak_stats, active_len, active_state

    @staticmethod
    def _get_max_streak(series: pd.Series) -> int:
        if len(series) == 0:
            return 0
        max_len = 1
        curr_len = 1
        for i in range(1, len(series)):
            if series.iloc[i] == series.iloc[i-1]:
                curr_len += 1
                max_len = max(max_len, curr_len)
            else:
                curr_len = 1
        return max_len

    @staticmethod
    def analyze(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return {
                "total_records": 0,
                "probabilities": {},
                "streaks": {},
                "prediction_for_next_issue": "Không có",
                "prediction_streak_based": "Không có"
            }

        df = pd.DataFrame(history)
        total_records = len(df)

        # ===== THAM SỐ CHUNG =====
        N_sliding = max(12, min(22, int(total_records * 0.16)))
        # === FIX: Tăng ar_window lên 15-30 để có nhiều mẫu hơn ===
        ar_window = max(15, min(30, int(total_records * 0.25)))

        N_parity = max(10, min(20, int(len(history) * 0.15)))
        N_size = max(12, min(25, int(len(history) * 0.18)))

        recent_history_parity = history[:N_parity]
        recent_history_size = history[:N_size]

        # ---- Tính AR cơ bản ----
        M = min(ar_window, len(history))
        parity_alternations = 0
        size_alternations = 0
        for i in range(M - 1):
            if history[i].get("is_le") != history[i+1].get("is_le"):
                parity_alternations += 1
            if history[i].get("is_tai") != history[i+1].get("is_tai"):
                size_alternations += 1
        ar_parity = parity_alternations / (M - 1) if M > 1 else 0.5
        ar_size = size_alternations / (M - 1) if M > 1 else 0.5

        def get_percentile(data, p):
            if not data:
                return 0.5
            s = sorted(data)
            k = (len(s) - 1) * (p / 100)
            f = int(k)
            c = f + 1 if f < len(s) - 1 else f
            if f == c:
                return s[f]
            return s[f] * (c - k) + s[c] * (k - f)

        # ---- Danh sách AR trượt ----
        ar_parity_list = []
        ar_size_list = []
        num_windows = max(1, len(history) - ar_window)
        for start_idx in range(num_windows):
            window = history[start_idx: start_idx + ar_window]
            if len(window) > 1:
                alt_p = sum(1 for k in range(len(window)-1) if window[k].get("is_le") != window[k+1].get("is_le"))
                alt_s = sum(1 for k in range(len(window)-1) if window[k].get("is_tai") != window[k+1].get("is_tai"))
                ar_parity_list.append(alt_p / (len(window)-1))
                ar_size_list.append(alt_s / (len(window)-1))

        # === FIX: Hàm EMA để làm trơn AR ===
        def ema(values, alpha=0.3):
            if not values:
                return 0.5
            ema_val = values[0]
            for v in values[1:]:
                ema_val = alpha * v + (1 - alpha) * ema_val
            return ema_val

        # === FIX: Hàm xác nhận AR (2/3 kỳ gần nhất vượt ngưỡng) ===
        def is_ar_confirmed(ar_list, threshold, window=3):
            if len(ar_list) < window:
                return ar_list[-1] >= threshold if ar_list else False
            recent = ar_list[-window:]
            count = sum(1 for v in recent if v >= threshold)
            return count >= 2

        # ===== NGƯỠNG PING‑PONG (cập nhật hệ số) =====
        # Parity: giảm hệ số từ 0.7 -> 0.6
        if len(ar_parity_list) >= 3:
            ar_mean_p = sum(ar_parity_list) / len(ar_parity_list)
            ar_std_p = np.std(ar_parity_list) if len(ar_parity_list) > 1 else 0.0
            ar_threshold_parity = ar_mean_p + 0.6 * ar_std_p
        else:
            ar_threshold_parity = 0.58
        ar_threshold_parity = max(0.48, min(0.82, ar_threshold_parity))  # nới giới hạn

        # Size: giảm hệ số từ 0.55 -> 0.5
        if len(ar_size_list) >= 3:
            ar_mean_s = sum(ar_size_list) / len(ar_size_list)
            ar_std_s = np.std(ar_size_list) if len(ar_size_list) > 1 else 0.0
            ar_threshold_size = ar_mean_s + 0.5 * ar_std_s
        else:
            ar_threshold_size = 0.54
        ar_threshold_size = max(0.44, min(0.78, ar_threshold_size))  # nới giới hạn

        # ---- Xác suất trượt ban đầu ----
        recent_records = history[:N_sliding]
        recent_le_count = sum(1 for r in recent_records if r.get("is_le"))
        recent_tai_count = sum(1 for r in recent_records if r.get("is_tai"))
        prob_le_sliding = recent_le_count / N_sliding if N_sliding > 0 else 0.5
        prob_chan_sliding = 1.0 - prob_le_sliding
        prob_tai_sliding = recent_tai_count / N_sliding if N_sliding > 0 else 0.5
        prob_xiu_sliding = 1.0 - prob_tai_sliding

        # ---- Thống kê cơ bản ----
        le_count = df["is_le"].sum()
        chan_count = total_records - le_count
        tai_count = df["is_tai"].sum()
        xiu_count = total_records - tai_count

        prob_le = float(le_count / total_records) if total_records > 0 else 0.5
        prob_chan = float(chan_count / total_records) if total_records > 0 else 0.5
        prob_tai = float(tai_count / total_records) if total_records > 0 else 0.5
        prob_xiu = float(xiu_count / total_records) if total_records > 0 else 0.5

        # ---- Chuỗi streak ----
        series_le = df["is_le"].iloc[::-1].reset_index(drop=True)
        series_tai = df["is_tai"].iloc[::-1].reset_index(drop=True)

        le_streak_stats, active_le_len, active_le_state = ProbabilityAnalyzer._analyze_streak_transitions(series_le)
        tai_streak_stats, active_tai_len, active_tai_state = ProbabilityAnalyzer._analyze_streak_transitions(series_tai)

        CONFIDENCE_THRESHOLD = 0.90
        MIN_SAMPLES = 3

        # ---- Streak transition cho Parity ----
        le_stats = le_streak_stats.get(active_le_len, {"continue": 0, "switch": 0})
        total_le_transitions = le_stats["continue"] + le_stats["switch"]
        pred_streak_le_switch = "Không có"
        pred_streak_le_continue = "Không có"
        is_high_conf_le = False
        if total_le_transitions >= MIN_SAMPLES:
            pred_streak_le_switch = le_stats["switch"] / total_le_transitions
            pred_streak_le_continue = 1 - pred_streak_le_switch
            if pred_streak_le_switch >= CONFIDENCE_THRESHOLD or pred_streak_le_continue >= CONFIDENCE_THRESHOLD:
                is_high_conf_le = True

        prob_next_le = 0.5
        prob_next_chan = 0.5
        predicted_parity = "Không có"
        if is_high_conf_le:
            if active_le_state:
                prob_next_chan = pred_streak_le_switch
                prob_next_le = 1 - pred_streak_le_switch
            else:
                prob_next_le = pred_streak_le_switch
                prob_next_chan = 1 - pred_streak_le_switch
            predicted_parity = "Le" if prob_next_le >= prob_next_chan else "Chan"

        # ---- Streak transition cho Size ----
        tai_stats = tai_streak_stats.get(active_tai_len, {"continue": 0, "switch": 0})
        total_tai_transitions = tai_stats["continue"] + tai_stats["switch"]
        pred_streak_tai_switch = "Không có"
        pred_streak_tai_continue = "Không có"
        is_high_conf_tai = False
        if total_tai_transitions >= MIN_SAMPLES:
            pred_streak_tai_switch = tai_stats["switch"] / total_tai_transitions
            pred_streak_tai_continue = 1 - pred_streak_tai_switch
            if pred_streak_tai_switch >= CONFIDENCE_THRESHOLD or pred_streak_tai_continue >= CONFIDENCE_THRESHOLD:
                is_high_conf_tai = True

        prob_next_tai = 0.5
        prob_next_xiu = 0.5
        predicted_size = "Không có"
        if is_high_conf_tai:
            if active_tai_state:
                prob_next_xiu = pred_streak_tai_switch
                prob_next_tai = 1 - pred_streak_tai_switch
            else:
                prob_next_tai = pred_streak_tai_switch
                prob_next_xiu = 1 - pred_streak_tai_switch
            predicted_size = "Tai" if prob_next_tai >= prob_next_xiu else "Xiu"

        # ---- Dự đoán Markov (bậc 2) ----
        pred_le = prob_le_sliding
        pred_tai = prob_tai_sliding
        if total_records > 15:
            states_le = {
                "L_L": {"L": 0, "C": 0},
                "L_C": {"L": 0, "C": 0},
                "C_L": {"L": 0, "C": 0},
                "C_C": {"L": 0, "C": 0}
            }
            for i in range(len(df) - 2):
                curr = "L" if df.iloc[i]["is_le"] else "C"
                prev = "L" if df.iloc[i+1]["is_le"] else "C"
                prev2 = "L" if df.iloc[i+2]["is_le"] else "C"
                states_le[f"{prev2}_{prev}"][curr] += 1
            last_state = "L" if df.iloc[0]["is_le"] else "C"
            last_prev = "L" if df.iloc[1]["is_le"] else "C"
            current_state_le = f"{last_prev}_{last_state}"
            total_from_state_le = states_le[current_state_le]["L"] + states_le[current_state_le]["C"]
            if total_from_state_le > 0:
                pred_le = states_le[current_state_le]["L"] / total_from_state_le

            states_tai = {
                "T_T": {"T": 0, "X": 0},
                "T_X": {"T": 0, "X": 0},
                "X_T": {"T": 0, "X": 0},
                "X_X": {"T": 0, "X": 0}
            }
            for i in range(len(df) - 2):
                curr = "T" if df.iloc[i]["is_tai"] else "X"
                prev = "T" if df.iloc[i+1]["is_tai"] else "X"
                prev2 = "T" if df.iloc[i+2]["is_tai"] else "X"
                states_tai[f"{prev2}_{prev}"][curr] += 1
            last_tai = "T" if df.iloc[0]["is_tai"] else "X"
            last_prev_tai = "T" if df.iloc[1]["is_tai"] else "X"
            current_state_tai = f"{last_prev_tai}_{last_tai}"
            total_from_state_tai = states_tai[current_state_tai]["T"] + states_tai[current_state_tai]["X"]
            if total_from_state_tai > 0:
                pred_tai = states_tai[current_state_tai]["T"] / total_from_state_tai

        # ---- Max streak trong lịch sử ----
        historical_le = series_le.iloc[:-active_le_len] if active_le_len > 0 else series_le
        historical_tai = series_tai.iloc[:-active_tai_len] if active_tai_len > 0 else series_tai
        max_le_streak = ProbabilityAnalyzer._get_max_streak(historical_le)
        max_tai_streak = ProbabilityAnalyzer._get_max_streak(historical_tai)

        # --- KHỞI TẠO GIÁ TRỊ MẶC ĐỊNH ---
        parity_decision = "BỎ QUA"
        parity_confidence = 50
        parity_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."
        size_decision = "BỎ QUA"
        size_confidence = 50
        size_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."

        stats_context = {
            "streaks": {
                "le_streak": {"state": "Le" if active_le_state else "Chan", "count": active_le_len, "max_history": max_le_streak, "transition_history": le_streak_stats},
                "tai_streak": {"state": "Tai" if active_tai_state else "Xiu", "count": active_tai_len, "max_history": max_tai_streak, "transition_history": tai_streak_stats}
            },
            "markov": {"pred_le": pred_le, "pred_tai": pred_tai}
        }

        # ======================================================================
        # ========== HEURISTICS ==========
        # ======================================================================

        def get_dynamic_confirmation(history, direction, ar_value):
            if ar_value > 0.70:
                window, threshold = 5, 4
            elif ar_value < 0.45:
                window, threshold = 10, 5
            else:
                window, threshold = 5, 3
            window = max(5, min(10, window))
            threshold = max(3, min(6, threshold))

            recent = history[:window]
            if direction == "tai":
                count = sum(1 for r in recent if r.get("is_tai"))
            elif direction == "xiu":
                count = sum(1 for r in recent if not r.get("is_tai"))
            elif direction == "le":
                count = sum(1 for r in recent if r.get("is_le"))
            elif direction == "chan":
                count = sum(1 for r in recent if not r.get("is_le"))
            else:
                return True
            return count >= threshold

        # ===== SATURATION =====
        K_z = min(100, len(history))
        sliding_probs_le = []
        sliding_probs_tai = []
        for idx in range(K_z):
            window_p = history[idx: idx + N_sliding]
            if len(window_p) > 0:
                le_w = sum(1 for r in window_p if r.get("is_le")) / len(window_p)
                sliding_probs_le.append(le_w)
            window_s = history[idx: idx + N_sliding]
            if len(window_s) > 0:
                tai_w = sum(1 for r in window_s if r.get("is_tai")) / len(window_s)
                sliding_probs_tai.append(tai_w)

        mean_le = sum(sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.5
        std_le = max(0.05, np.std(sliding_probs_le) if sliding_probs_le else 0.05)
        mean_tai = sum(sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.5
        std_tai = max(0.05, np.std(sliding_probs_tai) if sliding_probs_tai else 0.05)

        T_sat_le = max(0.50, min(0.75, get_percentile(sliding_probs_le, 60)))
        T_sat_chan = max(0.50, min(0.75, get_percentile([1.0 - x for x in sliding_probs_le], 60)))
        T_sat_tai = max(0.43, min(0.72, get_percentile(sliding_probs_tai, 50)))
        T_sat_xiu = max(0.43, min(0.72, get_percentile([1.0 - x for x in sliding_probs_tai], 50)))

        # ===== COOLING-OFF & WIN STREAK =====
        try:
            pred_hist = store.get_prediction_history(limit=10)
        except Exception as e:
            logger.warning(f"[Cooling] Could not fetch: {e}")
            pred_hist = []

        parity_loss_streak = 0
        for p in pred_hist:
            if p.get("status_parity") == "lose":
                parity_loss_streak += 1
            elif p.get("status_parity") in ("win", "ignored"):
                break
        total_parity = sum(1 for p in pred_hist if p.get("status_parity") in ("win", "lose"))
        is_parity_cooling = parity_loss_streak >= 3
        is_parity_cooling_3 = parity_loss_streak >= 3
        is_parity_cooling_2 = parity_loss_streak >= 2

        size_loss_streak = 0
        for p in pred_hist:
            if p.get("status_size") == "lose":
                size_loss_streak += 1
            elif p.get("status_size") in ("win", "ignored"):
                break
        total_size = sum(1 for p in pred_hist if p.get("status_size") in ("win", "lose"))
        is_size_cooling = size_loss_streak >= 3
        is_size_cooling_3 = size_loss_streak >= 3
        is_size_cooling_2 = size_loss_streak >= 2

        parity_win_streak = 0
        for p in pred_hist:
            if p.get("status_parity") == "win":
                parity_win_streak += 1
            elif p.get("status_parity") in ("lose", "ignored"):
                break
        is_parity_win_streak_pause = parity_win_streak >= 3

        size_win_streak = 0
        for p in pred_hist:
            if p.get("status_size") == "win":
                size_win_streak += 1
            elif p.get("status_size") in ("lose", "ignored"):
                break
        is_size_win_streak_pause = size_win_streak >= 3

        # ===== NGƯỠNG MUA ĐỘNG =====
        buy_threshold_parity = max(0.48, min(0.60, mean_le + 0.35 * std_le))
        buy_threshold_size = max(0.44, min(0.63, mean_tai + 0.25 * std_tai))

        # ============================================================
        # ======== XỬ LÝ PARITY ========
        # ============================================================
        recent_le_count_par = sum(1 for r in recent_history_parity if r.get("is_le"))
        recent_chan_count = N_parity - recent_le_count_par
        prob_le_sliding_par = recent_le_count_par / N_parity if N_parity > 0 else 0.5
        prob_chan_sliding_par = recent_chan_count / N_parity if N_parity > 0 else 0.5

        sliding_pred = "None"
        markov_pred = "None"

        # === FIX: Dùng EMA và xác nhận đa kỳ ===
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
            if prob_le_sliding_par >= buy_threshold_parity and ar_smooth_parity < ar_threshold_parity and prob_le_sliding_par >= 0.60:
                parity_decision = "MUA LẺ"
                parity_confidence = int(prob_le_sliding_par * 100)
                parity_rationale = f"Xác suất Lẻ {prob_le_sliding_par*100:.1f}% ≥{buy_threshold_parity*100:.1f}%, AR trung bình, ưu tiên cao."
            elif prob_chan_sliding_par >= buy_threshold_parity and ar_smooth_parity < ar_threshold_parity and prob_chan_sliding_par >= 0.60:
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
                        if prob_to_check >= 0.60:
                            parity_decision = "MUA LẺ" if sliding_pred == "Le" else "MUA CHẴN"
                            parity_confidence = min(int((0.6 * (prob_le_sliding_par if sliding_pred == "Le" else prob_chan_sliding_par) + 0.4 * (pred_le if sliding_pred == "Le" else 1.0 - pred_le)) * 100 * 1.05), 70)
                            parity_rationale = f"Consensus: {sliding_pred} (≥60%)"
                        else:
                            parity_rationale = "Xác suất < 60%, bỏ qua"
                    else:
                        parity_rationale = "Bão hòa, bỏ qua"
                else:
                    parity_rationale = "Không đồng thuận, bỏ qua"

        # ---- Bộ lọc recent trend (Parity) ----
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

        # Cross-market filter
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

        # Bệt filter 7 kỳ
        if parity_decision == "BỎ QUA" and not is_parity_cooling_3 and len(history) >= 7:
            if all(r.get("is_le") for r in history[:7]):
                parity_decision = "MUA CHẴN"
                parity_confidence = 60
                parity_rationale = "Bệt Lẻ 7 kỳ - đảo chiều"
            elif all(not r.get("is_le") for r in history[:7]):
                parity_decision = "MUA LẺ"
                parity_confidence = 60
                parity_rationale = "Bệt Chẵn 7 kỳ - đảo chiều"

        # Win rate filter
        try:
            stats_recent = store.get_prediction_stats_recent(limit=15)
            parity_wr = stats_recent.get("parity", {}).get("win_rate", 0.5)
            if stats_recent.get("parity", {}).get("total", 0) >= 5 and parity_wr < 0.50 and parity_decision != "BỎ QUA":
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Bỏ qua Parity do win rate 15 kỳ {parity_wr*100:.1f}% < 50%."
        except Exception as e:
            logger.debug(f"Could not fetch parity win rate: {e}")

        # ============================================================
        # ======== XỬ LÝ SIZE ========
        # ============================================================
        recent_tai_count_sz = sum(1 for r in recent_history_size if r.get("is_tai"))
        recent_xiu_count = N_size - recent_tai_count_sz
        prob_tai_sliding_sz = recent_tai_count_sz / N_size if N_size > 0 else 0.5
        prob_xiu_sliding_sz = recent_xiu_count / N_size if N_size > 0 else 0.5

        sliding_pred_size = "None"
        markov_pred_size = "None"

        # === FIX: Dùng EMA và xác nhận đa kỳ cho Size ===
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

        # ---- Bộ lọc recent trend (Size) ----
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

        # Cross-market filter
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

        # Bệt filter 7 kỳ
        if size_decision == "BỎ QUA" and not is_size_cooling_3 and len(history) >= 7:
            if all(r.get("is_tai") for r in history[:7]):
                size_decision = "MUA XỈU"
                size_confidence = 60
                size_rationale = "Bệt Tài 7 kỳ - đảo chiều"
            elif all(not r.get("is_tai") for r in history[:7]):
                size_decision = "MUA TÀI"
                size_confidence = 60
                size_rationale = "Bệt Xỉu 7 kỳ - đảo chiều"

        # Win rate filter
        try:
            stats_recent = store.get_prediction_stats_recent(limit=15)
            size_wr = stats_recent.get("size", {}).get("win_rate", 0.5)
            if stats_recent.get("size", {}).get("total", 0) >= 5 and size_wr < 0.50 and size_decision != "BỎ QUA":
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Bỏ qua Size do win rate 15 kỳ {size_wr*100:.1f}% < 50%."
        except Exception as e:
            logger.debug(f"Could not fetch size win rate: {e}")

        # ===== CONFIRMATION ĐỘNG =====
        if parity_decision != "BỎ QUA" and "Ping-Pong" not in parity_rationale and "Răng cưa" not in parity_rationale:
            direction = "le" if parity_decision == "MUA LẺ" else "chan"
            if not get_dynamic_confirmation(history, direction, ar_smooth_parity):
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Xu hướng {direction} chưa được xác nhận (AR={ar_smooth_parity:.2f})."

        if size_decision != "BỎ QUA" and "Ping-Pong" not in size_rationale and "Răng cưa" not in size_rationale:
            direction = "tai" if size_decision == "MUA TÀI" else "xiu"
            if not get_dynamic_confirmation(history, direction, ar_smooth_size):
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Xu hướng {direction} chưa được xác nhận (AR={ar_smooth_size:.2f})."

        # ============================================================
        # ========== MA-50 LONG-TERM TREND FILTER (CẬP NHẬT) ==========
        # ============================================================
        if len(history) >= 20:
            K_ma = min(50, len(history))
            ma50_le_ratio = sum(1 for r in history[:K_ma] if r.get("is_le")) / K_ma
            ma50_tai_ratio = sum(1 for r in history[:K_ma] if r.get("is_tai")) / K_ma

            # ---- Hàm áp dụng cho từng quyết định ----
            def apply_ma_filter(decision, confidence, rationale, ratio, side):
                """
                side: "Le" hoặc "Tai" (dùng để xác định xu hướng)
                ratio: tỷ lệ của side đó (ma50_le_ratio hoặc ma50_tai_ratio)
                """
                if decision == "BỎ QUA":
                    return decision, confidence, rationale

                # Xác định side của quyết định
                if "MUA LẺ" in decision:
                    dec_side = "Le"
                elif "MUA CHẴN" in decision:
                    dec_side = "Chan"
                elif "MUA TÀI" in decision:
                    dec_side = "Tai"
                elif "MUA XỈU" in decision:
                    dec_side = "Xiu"
                else:
                    return decision, confidence, rationale

                # Đối với mỗi side, ta cần kiểm tra tỷ lệ của chính side đó và side ngược lại
                # Nếu side là Le thì side_opposite = Chan, ratio_opposite = 1 - ratio
                # Nhưng ta chỉ có ma50_le_ratio và ma50_tai_ratio, không có trực tiếp Chan hay Xiu.
                # Nhưng vì chỉ có 2 cửa, tỷ lệ Chan = 1 - Le, Xiu = 1 - Tai.
                if dec_side == "Le":
                    ma_side = "Le"
                    ma_side_ratio = ratio  # ratio là ma50_le_ratio
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Chan":
                    ma_side = "Le"
                    ma_side_ratio = ratio  # vẫn dùng ratio của Le, nhưng quyết định là Chan
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Tai":
                    ma_side = "Tai"
                    ma_side_ratio = ratio  # ratio là ma50_tai_ratio
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Xiu":
                    ma_side = "Tai"
                    ma_side_ratio = ratio
                    opp_side_ratio = 1 - ratio
                else:
                    return decision, confidence, rationale

                # Nếu quyết định cùng side với MA-50 và tỷ lệ của side đó >= 55%
                if ((dec_side == "Le" and ma_side == "Le") or (dec_side == "Tai" and ma_side == "Tai")) and ma_side_ratio >= 0.55:
                    confidence = min(70, confidence + 5)
                    rationale += f" [MA-50 cùng xu hướng {ma_side} ({ma_side_ratio*100:.1f}%)]"
                # Nếu quyết định ngược side với MA-50 và tỷ lệ của side đối diện >= 55% (tức MA-50 nghiêng về phía đối diện)
                elif ((dec_side == "Chan" and ma_side == "Le") or (dec_side == "Xiu" and ma_side == "Tai")) and opp_side_ratio >= 0.55:
                    confidence -= 10
                    if confidence < 55:
                        decision = "BỎ QUA"
                        confidence = 50
                        rationale = f"MA-50 ngược xu hướng ({opp_side_ratio*100:.1f}% {ma_side}), bỏ qua."
                    else:
                        rationale += f" [MA-50 ngược xu hướng ({opp_side_ratio*100:.1f}% {ma_side})]"
                # Nếu cùng side nhưng tỷ lệ < 55% hoặc ngược side nhưng tỷ lệ đối diện <55%, không làm gì
                return decision, confidence, rationale

            # Áp dụng cho Parity
            parity_decision, parity_confidence, parity_rationale = apply_ma_filter(
                parity_decision, parity_confidence, parity_rationale, ma50_le_ratio, "Le"
            )

            # Áp dụng cho Size (side là Tai)
            size_decision, size_confidence, size_rationale = apply_ma_filter(
                size_decision, size_confidence, size_rationale, ma50_tai_ratio, "Tai"
            )

        # ============================================================
        # ========== GEMINI ==========
        # ============================================================
        gemini_success = False
        gemini_pred = {}
        current_time = time.time()
        time_since_last_call = current_time - GeminiClient._last_call_time

        min_interval = 120 + (GeminiClient._consecutive_failures * 30)
        min_interval = min(min_interval, 300)

        if getattr(config, "GEMINI_API_KEY", "") and total_records >= 10:
            latest_issue = str(df.iloc[0].get("issue") or "")
            lottery_id = getattr(config, "LOTTERY_ID", "default")
            cache_key = f"{lottery_id}_{latest_issue}" if latest_issue else None

            cached = GeminiClient._gemini_cache.get(cache_key) if cache_key else None
            if cached and (current_time - cached["timestamp"]) < GeminiClient._cache_ttl:
                gemini_pred = cached["data"]
                gemini_success = True
                GeminiClient._consecutive_failures = 0
                logger.info(f"[Gemini] Using cached prediction for {cache_key}")
            elif time_since_last_call < min_interval:
                logger.debug(f"[Gemini] Rate limit ({min_interval}s), skipping")
            else:
                try:
                    GeminiClient._last_call_time = current_time
                    gemini_pred = GeminiClient.call_with_retry(df, stats_context)
                    if isinstance(gemini_pred, dict) and "parity" in gemini_pred and "size" in gemini_pred:
                        gemini_success = True
                        GeminiClient._consecutive_failures = 0
                        if cache_key:
                            if len(GeminiClient._gemini_cache) > 5:
                                GeminiClient._gemini_cache.clear()
                            GeminiClient._gemini_cache[cache_key] = {
                                "data": gemini_pred,
                                "timestamp": current_time
                            }
                            logger.info(f"[Gemini] Cached prediction for {cache_key}")
                    else:
                        logger.warning("[Gemini] Invalid response format")
                        GeminiClient._consecutive_failures += 1
                except Exception as e:
                    logger.error(f"[Gemini] API call failed: {e}")
                    GeminiClient._consecutive_failures += 1

        # ======== KẾT HỢP GEMINI + HEURISTICS ========
        engine_used_parity = "Heuristics"
        engine_used_size = "Heuristics"

        heuristics_combined_parity = (sliding_pred != "None" and markov_pred != "None" and sliding_pred == markov_pred)
        heuristics_combined_size = (sliding_pred_size != "None" and markov_pred_size != "None" and sliding_pred_size == markov_pred_size)

        if gemini_success:
            # PARITY
            g_decision = gemini_pred["parity"].get("decision", "BỎ QUA")
            g_conf = int(gemini_pred["parity"].get("confidence", 50))
            h_decision = parity_decision
            h_conf = parity_confidence

            if g_decision == h_decision:
                parity_decision = g_decision
                parity_confidence = min(70, max(g_conf, h_conf) + 5)
                parity_rationale = f"Đồng thuận (Gemini+Heuristics): {g_decision}"
                engine_used_parity = "Combined"
            else:
                if abs(g_conf - h_conf) >= 10:
                    if g_conf > h_conf:
                        parity_decision = g_decision
                        parity_confidence = g_conf
                        parity_rationale = "Chọn Gemini (chênh lệch >10%)"
                        engine_used_parity = "Gemini"
                    else:
                        parity_decision = h_decision
                        parity_confidence = h_conf
                        parity_rationale = "Chọn Heuristics (chênh lệch >10%)"
                        engine_used_parity = "Heuristics"
                else:
                    parity_decision = "BỎ QUA"
                    parity_confidence = 50
                    parity_rationale = "Mâu thuẫn, bỏ qua để bảo toàn"
                    engine_used_parity = "Conflict"

            # SIZE
            g_decision = gemini_pred["size"].get("decision", "BỎ QUA")
            g_conf = int(gemini_pred["size"].get("confidence", 50))
            h_decision = size_decision
            h_conf = size_confidence

            if g_decision == h_decision:
                size_decision = g_decision
                size_confidence = min(70, max(g_conf, h_conf) + 5)
                size_rationale = f"Đồng thuận (Gemini+Heuristics): {g_decision}"
                engine_used_size = "Combined"
            else:
                if abs(g_conf - h_conf) >= 10:
                    if g_conf > h_conf:
                        size_decision = g_decision
                        size_confidence = g_conf
                        size_rationale = "Chọn Gemini (chênh lệch >10%)"
                        engine_used_size = "Gemini"
                    else:
                        size_decision = h_decision
                        size_confidence = h_conf
                        size_rationale = "Chọn Heuristics (chênh lệch >10%)"
                        engine_used_size = "Heuristics"
                else:
                    size_decision = "BỎ QUA"
                    size_confidence = 50
                    size_rationale = "Mâu thuẫn, bỏ qua để bảo toàn"
                    engine_used_size = "Conflict"
        else:
            if heuristics_combined_parity and parity_decision != "BỎ QUA":
                engine_used_parity = "Combined"
                parity_rationale = f"Đồng thuận (Heuristics): {parity_decision}"
            if heuristics_combined_size and size_decision != "BỎ QUA":
                engine_used_size = "Combined"
                size_rationale = f"Đồng thuận (Heuristics): {size_decision}"

        # ======== STREAK SAFETY TRAP ========
        T_streak_parity = max(4, max_le_streak + 2)
        T_streak_size = max(4, max_tai_streak + 2)

        if parity_decision != "BỎ QUA" and active_le_len >= T_streak_parity:
            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = f"Bệt {active_le_len} vượt trần {T_streak_parity} (max_history {max_le_streak} + 2)"

        if size_decision != "BỎ QUA" and active_tai_len >= T_streak_size:
            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = f"Bệt {active_tai_len} vượt trần {T_streak_size} (max_history {max_tai_streak} + 2)"

        parity_confidence = min(parity_confidence, 70)
        size_confidence = min(size_confidence, 70)

        return {
            "total_records": total_records,
            "probabilities": {
                "le": round(prob_le, 4),
                "chan": round(prob_chan, 4),
                "tai": round(prob_tai, 4),
                "xiu": round(prob_xiu, 4)
            },
            "streaks": {
                "le_streak": {"state": "Le" if active_le_state else "Chan", "count": active_le_len, "max_history": max_le_streak},
                "tai_streak": {"state": "Tai" if active_tai_state else "Xiu", "count": active_tai_len, "max_history": max_tai_streak}
            },
            "prediction_for_next_issue": {
                "le_probability": round(pred_le, 4),
                "chan_probability": round(1 - pred_le, 4),
                "predicted_parity": "Le" if pred_le >= 0.5 else "Chan",
                "tai_probability": round(pred_tai, 4),
                "xiu_probability": round(1 - pred_tai, 4),
                "predicted_size": "Tai" if pred_tai >= 0.5 else "Xiu"
            },
            "prediction_streak_based": {
                "parity": {
                    "current_streak_state": "Le" if active_le_state else "Chan",
                    "current_streak_count": active_le_len,
                    "historical_samples_found": total_le_transitions,
                    "probability_switch": round(pred_streak_le_switch, 4) if isinstance(pred_streak_le_switch, float) else "Không có",
                    "probability_continue": round(pred_streak_le_continue, 4) if isinstance(pred_streak_le_continue, float) else "Không có",
                    "is_high_confidence": is_high_conf_le,
                    "predicted_outcome": predicted_parity
                },
                "size": {
                    "current_streak_state": "Tai" if active_tai_state else "Xiu",
                    "current_streak_count": active_tai_len,
                    "historical_samples_found": total_tai_transitions,
                    "probability_switch": round(pred_streak_tai_switch, 4) if isinstance(pred_streak_tai_switch, float) else "Không có",
                    "probability_continue": round(pred_streak_tai_continue, 4) if isinstance(pred_streak_tai_continue, float) else "Không có",
                    "is_high_confidence": is_high_conf_tai,
                    "predicted_outcome": predicted_size
                }
            },
            "ai_recommendation": {
                "parity": {"decision": parity_decision, "confidence": parity_confidence, "rationale": parity_rationale},
                "size": {"decision": size_decision, "confidence": size_confidence, "rationale": size_rationale},
                "engine": "Gemini AI" if gemini_success else "Heuristics (3-Layer)"
            },
            "engine_used": {
                "parity": engine_used_parity,
                "size": engine_used_size
            }
        }