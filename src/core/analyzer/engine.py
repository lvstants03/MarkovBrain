import logging
import time
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from src.config import config
from src.core.ai.gemini import GeminiClient
from src.database.store import store
from src.core.analyzer.helpers import (
    _analyze_streak_transitions, _get_max_streak,
    ema, is_ar_confirmed, get_percentile, get_dynamic_confirmation
)
from src.core.analyzer.parity import ParityAnalyzer
from src.core.analyzer.size import SizeAnalyzer

logger = logging.getLogger(__name__)

class ProbabilityAnalyzer:
    @staticmethod
    def _analyze_streak_transitions(series: pd.Series) -> tuple[dict, int, Any]:
        return _analyze_streak_transitions(series)

    @staticmethod
    def _get_max_streak(series: pd.Series) -> int:
        return _get_max_streak(series)

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

        # ===== NẠP CẤU HÌNH DÂN CHƠI =====
        parity_defaults = {
            "n_sliding_min": 12,
            "n_sliding_max": 22,
            "n_sliding_ratio": 0.16,
            "ar_window_min": 15,
            "ar_window_max": 30,
            "ar_window_ratio": 0.25,
            "n_recent_min": 10,
            "n_recent_max": 20,
            "n_recent_ratio": 0.15,
            "ar_threshold_multiplier": 0.6,
            "ar_threshold_min": 0.48,
            "ar_threshold_max": 0.82,
            "streak_confidence_threshold": 0.90,
            "streak_min_samples": 3,
            "saturation_percentile": 60.0,
            "saturation_limit_min": 0.50,
            "saturation_limit_max": 0.75,
            "cooling_off_loss_limit": 3,
            "win_streak_pause_limit": 3,
            "buy_threshold_multiplier": 0.35,
            "buy_threshold_min": 0.48,
            "buy_threshold_max": 0.60,
            "ma50_window": 50,
            "ma50_filter_active": True,
            "win_rate_filter_window": 15,
            "win_rate_filter_min_total": 5,
            "win_rate_filter_threshold": 0.50,
            "streak_safety_trap_multiplier": 2,
            "streak_safety_trap_min": 4,
            "min_probability_threshold": 0.60
        }
        
        size_defaults = {
            "n_sliding_min": 12,
            "n_sliding_max": 22,
            "n_sliding_ratio": 0.16,
            "ar_window_min": 15,
            "ar_window_max": 30,
            "ar_window_ratio": 0.25,
            "n_recent_min": 12,
            "n_recent_max": 25,
            "n_recent_ratio": 0.18,
            "ar_threshold_multiplier": 0.5,
            "ar_threshold_min": 0.44,
            "ar_threshold_max": 0.78,
            "streak_confidence_threshold": 0.90,
            "streak_min_samples": 3,
            "saturation_percentile": 50.0,
            "saturation_limit_min": 0.43,
            "saturation_limit_max": 0.72,
            "cooling_off_loss_limit": 3,
            "win_streak_pause_limit": 3,
            "buy_threshold_multiplier": 0.25,
            "buy_threshold_min": 0.44,
            "buy_threshold_max": 0.63,
            "ma50_window": 50,
            "ma50_filter_active": True,
            "win_rate_filter_window": 15,
            "win_rate_filter_min_total": 5,
            "win_rate_filter_threshold": 0.50,
            "streak_safety_trap_multiplier": 2,
            "streak_safety_trap_min": 4,
            "min_probability_threshold": 0.60
        }

        # Nap tham so tu DB (fallback ve parity_defaults/size_defaults neu DB rong)
        cfg_p = store.get_analyzer_config("parity")
        cfg_s = store.get_analyzer_config("size")

        N_sliding_p = max(cfg_p["n_sliding_min"], min(cfg_p["n_sliding_max"], int(total_records * cfg_p["n_sliding_ratio"])))
        N_sliding_s = max(cfg_s["n_sliding_min"], min(cfg_s["n_sliding_max"], int(total_records * cfg_s["n_sliding_ratio"])))

        ar_window_p = max(cfg_p["ar_window_min"], min(cfg_p["ar_window_max"], int(total_records * cfg_p["ar_window_ratio"])))
        ar_window_s = max(cfg_s["ar_window_min"], min(cfg_s["ar_window_max"], int(total_records * cfg_s["ar_window_ratio"])))

        N_parity = max(cfg_p["n_recent_min"], min(cfg_p["n_recent_max"], int(len(history) * cfg_p["n_recent_ratio"])))
        N_size = max(cfg_s["n_recent_min"], min(cfg_s["n_recent_max"], int(len(history) * cfg_s["n_recent_ratio"])))

        # ---- Tính AR cơ bản ----
        M_parity = min(ar_window_p, len(history))
        M_size = min(ar_window_s, len(history))
        parity_alternations = 0
        size_alternations = 0
        for i in range(M_parity - 1):
            if history[i].get("is_le") != history[i+1].get("is_le"):
                parity_alternations += 1
        for i in range(M_size - 1):
            if history[i].get("is_tai") != history[i+1].get("is_tai"):
                size_alternations += 1
        ar_parity = parity_alternations / (M_parity - 1) if M_parity > 1 else 0.5
        ar_size = size_alternations / (M_size - 1) if M_size > 1 else 0.5

        # ---- Danh sách AR trượt ----
        ar_parity_list = []
        ar_size_list = []
        num_windows_p = max(1, len(history) - ar_window_p)
        for start_idx in range(num_windows_p):
            window = history[start_idx: start_idx + ar_window_p]
            if len(window) > 1:
                alt_p = sum(1 for k in range(len(window)-1) if window[k].get("is_le") != window[k+1].get("is_le"))
                ar_parity_list.append(alt_p / (len(window)-1))
        
        num_windows_s = max(1, len(history) - ar_window_s)
        for start_idx in range(num_windows_s):
            window = history[start_idx: start_idx + ar_window_s]
            if len(window) > 1:
                alt_s = sum(1 for k in range(len(window)-1) if window[k].get("is_tai") != window[k+1].get("is_tai"))
                ar_size_list.append(alt_s / (len(window)-1))

        # ===== NGƯỠNG PING‑PONG =====
        if len(ar_parity_list) >= 3:
            ar_mean_p = sum(ar_parity_list) / len(ar_parity_list)
            ar_std_p = np.std(ar_parity_list) if len(ar_parity_list) > 1 else 0.0
            ar_threshold_parity = ar_mean_p + cfg_p["ar_threshold_multiplier"] * ar_std_p
        else:
            ar_threshold_parity = 0.58
        ar_threshold_parity = max(cfg_p["ar_threshold_min"], min(cfg_p["ar_threshold_max"], ar_threshold_parity))

        if len(ar_size_list) >= 3:
            ar_mean_s = sum(ar_size_list) / len(ar_size_list)
            ar_std_s = np.std(ar_size_list) if len(ar_size_list) > 1 else 0.0
            ar_threshold_size = ar_mean_s + cfg_s["ar_threshold_multiplier"] * ar_std_s
        else:
            ar_threshold_size = 0.54
        ar_threshold_size = max(cfg_s["ar_threshold_min"], min(cfg_s["ar_threshold_max"], ar_threshold_size))

        # ---- Xác suất trượt ban đầu ----
        recent_le_count = sum(1 for r in history[:N_sliding_p] if r.get("is_le"))
        recent_tai_count = sum(1 for r in history[:N_sliding_s] if r.get("is_tai"))
        prob_le_sliding = recent_le_count / N_sliding_p if N_sliding_p > 0 else 0.5
        prob_chan_sliding = 1.0 - prob_le_sliding
        prob_tai_sliding = recent_tai_count / N_sliding_s if N_sliding_s > 0 else 0.5
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

        le_streak_stats, active_le_len, active_le_state = _analyze_streak_transitions(series_le)
        tai_streak_stats, active_tai_len, active_tai_state = _analyze_streak_transitions(series_tai)

        max_le_streak = _get_max_streak(series_le)
        max_tai_streak = _get_max_streak(series_tai)

        CONFIDENCE_THRESHOLD_P = cfg_p["streak_confidence_threshold"]
        MIN_SAMPLES_P = cfg_p["streak_min_samples"]
        CONFIDENCE_THRESHOLD_S = cfg_s["streak_confidence_threshold"]
        MIN_SAMPLES_S = cfg_s["streak_min_samples"]

        # ---- Streak transition cho Parity ----
        le_stats = le_streak_stats.get(active_le_len, {"continue": 0, "switch": 0})
        total_le_transitions = le_stats["continue"] + le_stats["switch"]
        pred_streak_le_switch = "Không có"
        pred_streak_le_continue = "Không có"
        is_high_conf_le = False
        if total_le_transitions >= MIN_SAMPLES_P:
            pred_streak_le_switch = le_stats["switch"] / total_le_transitions
            pred_streak_le_continue = 1 - pred_streak_le_switch
            if pred_streak_le_switch >= CONFIDENCE_THRESHOLD_P or pred_streak_le_continue >= CONFIDENCE_THRESHOLD_P:
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
        if total_tai_transitions >= MIN_SAMPLES_S:
            pred_streak_tai_switch = tai_stats["switch"] / total_tai_transitions
            pred_streak_tai_continue = 1 - pred_streak_tai_switch
            if pred_streak_tai_switch >= CONFIDENCE_THRESHOLD_S or pred_streak_tai_continue >= CONFIDENCE_THRESHOLD_S:
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
            prev_state = "L" if df.iloc[1]["is_le"] else "C"
            transition_key = f"{prev_state}_{last_state}"
            stats = states_le[transition_key]
            total_transitions = stats["L"] + stats["C"]
            if total_transitions >= 2:
                pred_le = stats["L"] / total_transitions

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
            last_state_t = "T" if df.iloc[0]["is_tai"] else "X"
            prev_state_t = "T" if df.iloc[1]["is_tai"] else "X"
            transition_key_t = f"{prev_state_t}_{last_state_t}"
            stats_t = states_tai[transition_key_t]
            total_transitions_t = stats_t["T"] + stats_t["X"]
            if total_transitions_t >= 2:
                pred_tai = stats_t["T"] / total_transitions_t

        # ===== SATURATION =====
        K_z = min(100, len(history))
        sliding_probs_le = []
        sliding_probs_tai = []
        for idx in range(K_z):
            window_p = history[idx: idx + N_sliding_p]
            if len(window_p) > 0:
                le_w = sum(1 for r in window_p if r.get("is_le")) / len(window_p)
                sliding_probs_le.append(le_w)
            window_s = history[idx: idx + N_sliding_s]
            if len(window_s) > 0:
                tai_w = sum(1 for r in window_s if r.get("is_tai")) / len(window_s)
                sliding_probs_tai.append(tai_w)

        mean_le = sum(sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.5
        std_le = max(0.05, np.std(sliding_probs_le) if sliding_probs_le else 0.05)
        mean_tai = sum(sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.5
        std_tai = max(0.05, np.std(sliding_probs_tai) if sliding_probs_tai else 0.05)

        T_sat_le = max(cfg_p["saturation_limit_min"], min(cfg_p["saturation_limit_max"], get_percentile(sliding_probs_le, cfg_p["saturation_percentile"])))
        T_sat_chan = max(cfg_p["saturation_limit_min"], min(cfg_p["saturation_limit_max"], get_percentile([1.0 - x for x in sliding_probs_le], cfg_p["saturation_percentile"])))
        T_sat_tai = max(cfg_s["saturation_limit_min"], min(cfg_s["saturation_limit_max"], get_percentile(sliding_probs_tai, cfg_s["saturation_percentile"])))
        T_sat_xiu = max(cfg_s["saturation_limit_min"], min(cfg_s["saturation_limit_max"], get_percentile([1.0 - x for x in sliding_probs_tai], cfg_s["saturation_percentile"])))

        # ===== COOLING-OFF & WIN STREAK =====
        try:
            pred_hist_30 = store.get_prediction_history(limit=30)
        except Exception as e:
            logger.warning(f"[Cooling] Could not fetch: {e}")
            pred_hist_30 = []

        pred_hist = pred_hist_30[:10]

        total_p_bets = sum(1 for p in pred_hist_30 if p.get("status_parity") in ("win", "lose"))
        wins_p = sum(1 for p in pred_hist_30 if p.get("status_parity") == "win")
        wr_30_parity = (wins_p / total_p_bets) if total_p_bets > 0 else 0.50

        total_s_bets = sum(1 for p in pred_hist_30 if p.get("status_size") in ("win", "lose"))
        wins_s = sum(1 for p in pred_hist_30 if p.get("status_size") == "win")
        wr_30_size = (wins_s / total_s_bets) if total_s_bets > 0 else 0.50

        parity_loss_streak = 0
        for p in pred_hist:
            if p.get("status_parity") == "lose":
                parity_loss_streak += 1
            elif p.get("status_parity") in ("win", "ignored"):
                break
        
        cooling_limit_p = cfg_p.get("cooling_off_loss_limit", 2)
        if wr_30_parity < 0.50:
            cooling_limit_p = 3
        is_parity_cooling = parity_loss_streak >= cooling_limit_p

        size_loss_streak = 0
        for p in pred_hist:
            if p.get("status_size") == "lose":
                size_loss_streak += 1
            elif p.get("status_size") in ("win", "ignored"):
                break
        
        cooling_limit_s = cfg_s.get("cooling_off_loss_limit", 2)
        if wr_30_size < 0.50:
            cooling_limit_s = 3
        is_size_cooling = size_loss_streak >= cooling_limit_s

        parity_win_streak = 0
        for p in pred_hist:
            if p.get("status_parity") == "win":
                parity_win_streak += 1
            elif p.get("status_parity") in ("lose", "ignored"):
                break
        is_parity_win_streak_pause = parity_win_streak >= cfg_p["win_streak_pause_limit"]

        size_win_streak = 0
        for p in pred_hist:
            if p.get("status_size") == "win":
                size_win_streak += 1
            elif p.get("status_size") in ("lose", "ignored"):
                break
        is_size_win_streak_pause = size_win_streak >= cfg_s["win_streak_pause_limit"]

        buy_threshold_parity = max(cfg_p["buy_threshold_min"], min(cfg_p["buy_threshold_max"], mean_le + cfg_p["buy_threshold_multiplier"] * std_le))
        buy_threshold_size = max(cfg_s["buy_threshold_min"], min(cfg_s["buy_threshold_max"], mean_tai + cfg_s["buy_threshold_multiplier"] * std_tai))

        (parity_decision, parity_confidence, parity_rationale, 
         engine_used_parity, sliding_pred, markov_pred) = ParityAnalyzer.analyze(
            history, cfg_p, N_parity, ar_parity_list, ar_threshold_parity,
            mean_le, std_le, T_sat_le, T_sat_chan,
            is_parity_cooling, parity_loss_streak, is_parity_win_streak_pause, parity_win_streak,
            buy_threshold_parity, pred_le
        )

        (size_decision, size_confidence, size_rationale, 
         engine_used_size, sliding_pred_size, markov_pred_size) = SizeAnalyzer.analyze(
            history, cfg_s, N_size, ar_size_list, ar_threshold_size,
            mean_tai, std_tai, T_sat_tai, T_sat_xiu,
            is_size_cooling, size_loss_streak, is_size_win_streak_pause, size_win_streak,
            buy_threshold_size, pred_tai
        )

        if len(history) >= 20:
            K_ma_p = min(cfg_p["ma50_window"], len(history))
            K_ma_s = min(cfg_s["ma50_window"], len(history))
            ma50_le_ratio = sum(1 for r in history[:K_ma_p] if r.get("is_le")) / K_ma_p
            ma50_tai_ratio = sum(1 for r in history[:K_ma_s] if r.get("is_tai")) / K_ma_s
 
            def apply_ma_filter(decision, confidence, rationale, ratio, side):
                if decision == "BỎ QUA":
                    return decision, confidence, rationale
 
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
 
                if dec_side == "Le":
                    ma_side = "Le"
                    ma_side_ratio = ratio
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Chan":
                    ma_side = "Le"
                    ma_side_ratio = ratio
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Tai":
                    ma_side = "Tai"
                    ma_side_ratio = ratio
                    opp_side_ratio = 1 - ratio
                elif dec_side == "Xiu":
                    ma_side = "Tai"
                    ma_side_ratio = ratio
                    opp_side_ratio = 1 - ratio
                else:
                    return decision, confidence, rationale
 
                if ((dec_side == "Le" and ma_side == "Le") or (dec_side == "Tai" and ma_side == "Tai")) and ma_side_ratio >= 0.55:
                    confidence = min(70, confidence + 5)
                    rationale += f" [MA-50 cùng xu hướng {ma_side} ({ma_side_ratio*100:.1f}%)]"
                elif ((dec_side == "Chan" and ma_side == "Le") or (dec_side == "Xiu" and ma_side == "Tai")) and opp_side_ratio >= 0.55:
                    confidence -= 10
                    if confidence < 55:
                        decision = "BỎ QUA"
                        confidence = 50
                        rationale = f"MA-50 ngược xu hướng ({opp_side_ratio*100:.1f}% {ma_side}), bỏ qua."
                    else:
                        rationale += f" [MA-50 ngược xu hướng ({opp_side_ratio*100:.1f}% {ma_side})]"
                return decision, confidence, rationale
 
            if cfg_p["ma50_filter_active"]:
                parity_decision, parity_confidence, parity_rationale = apply_ma_filter(
                    parity_decision, parity_confidence, parity_rationale, ma50_le_ratio, "Le"
                )
 
            if cfg_s["ma50_filter_active"]:
                size_decision, size_confidence, size_rationale = apply_ma_filter(
                    size_decision, size_confidence, size_rationale, ma50_tai_ratio, "Tai"
                )

        gemini_success = False
        gemini_pred = {}
        current_time = time.time()
        time_since_last_call = current_time - GeminiClient._last_call_time
        min_interval = getattr(config, "GEMINI_MIN_INTERVAL", 10)

        stats_context = {
            "total_records": total_records,
            "prob_le": prob_le, "prob_chan": prob_chan,
            "prob_tai": prob_tai, "prob_xiu": prob_xiu,
            "active_le_len": active_le_len, "active_le_state": active_le_state,
            "active_tai_len": active_tai_len, "active_tai_state": active_tai_state,
            "max_le_streak": max_le_streak, "max_tai_streak": max_tai_streak,
            "ar_smooth_parity": float(np.mean(ar_parity_list)) if ar_parity_list else ar_parity,
            "ar_threshold_parity": ar_threshold_parity,
            "ar_smooth_size": float(np.mean(ar_size_list)) if ar_size_list else ar_size,
            "ar_threshold_size": ar_threshold_size,
            "prob_le_sliding": prob_le_sliding,
            "prob_chan_sliding": prob_chan_sliding,
            "prob_tai_sliding": prob_tai_sliding,
            "prob_xiu_sliding": prob_xiu_sliding,
            "T_sat_le": T_sat_le, "T_sat_chan": T_sat_chan,
            "T_sat_tai": T_sat_tai, "T_sat_xiu": T_sat_xiu,
            "buy_threshold_parity": buy_threshold_parity,
            "buy_threshold_size": buy_threshold_size,
            "markov": {
                "pred_le": pred_le,
                "pred_tai": pred_tai
            }
        }

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

        heuristics_combined_parity = (sliding_pred != "None" and markov_pred != "None" and sliding_pred == markov_pred)
        heuristics_combined_size = (sliding_pred_size != "None" and markov_pred_size != "None" and sliding_pred_size == markov_pred_size)

        if gemini_success:
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

        T_streak_parity = max(cfg_p["streak_safety_trap_min"], max_le_streak + cfg_p["streak_safety_trap_multiplier"])
        T_streak_size = max(cfg_s["streak_safety_trap_min"], max_tai_streak + cfg_s["streak_safety_trap_multiplier"])

        if parity_decision != "BỎ QUA" and active_le_len >= T_streak_parity:
            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = f"Bệt {active_le_len} vượt trần {T_streak_parity} (max_history {max_le_streak} + {cfg_p['streak_safety_trap_multiplier']})"

        if size_decision != "BỎ QUA" and active_tai_len >= T_streak_size:
            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = f"Bệt {active_tai_len} vượt trần {T_streak_size} (max_history {max_tai_streak} + {cfg_s['streak_safety_trap_multiplier']})"

        # ===== AP DUNG VOLATILITY PENALTY =====
        # Khi thi truong bien dong cao (std > 0.12), giam confidence theo he so penalty
        vol_penalty_p = float(cfg_p.get("volatility_penalty", 1.2))
        vol_penalty_s = float(cfg_s.get("volatility_penalty", 1.2))
        if std_le > 0.12 and parity_decision != "BỎ QUA" and vol_penalty_p > 1.0:
            penalized = int(parity_confidence / vol_penalty_p)
            if penalized < 55:
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Bien dong cao (std={std_le:.3f}), sau penalty confidence={penalized} < 55, bo qua."
            else:
                parity_confidence = penalized
                parity_rationale += f" [vol_penalty={vol_penalty_p}]"
        if std_tai > 0.12 and size_decision != "BỎ QUA" and vol_penalty_s > 1.0:
            penalized = int(size_confidence / vol_penalty_s)
            if penalized < 55:
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Bien dong cao (std={std_tai:.3f}), sau penalty confidence={penalized} < 55, bo qua."
            else:
                size_confidence = penalized
                size_rationale += f" [vol_penalty={vol_penalty_s}]"

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
