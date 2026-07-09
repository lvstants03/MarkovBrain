import pandas as pd
import numpy as np
from typing import Dict, Any, List
import requests
import json
import time
from src.config import config

class ProbabilityAnalyzer:
    _gemini_cache = {}
    _last_call_time = 0

    @staticmethod
    def _analyze_streak_transitions(series: pd.Series) -> tuple[dict, int, Any]:
        # series is from oldest to newest
        streak_stats = {} # length -> {"continue": 0, "switch": 0}
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
                
        # Active streak at the end (newest)
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
    def _call_gemini_api(df: pd.DataFrame, stats_context: dict) -> dict:
        """
        Calls Gemini 2.5 Flash API with the last 100 draws and statistics.
        Returns a dictionary representing predictions, or raises Exception if failed.
        """
        api_key = getattr(config, "GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in config.")

        # Take last 100 draws
        history_subset = df.head(100)
        draws_list = []
        for idx, row in history_subset.iterrows():
            draws_list.append({
                "issue": str(row.get("issue")),
                "numbers": list(row.get("numbers") or []),
                "total": int(row.get("total")),
                "parity": "Le" if row.get("is_le") else "Chan",
                "size": "Tai" if row.get("is_tai") else "Xiu"
            })

        # Reverse so that Gemini sees chronological order (oldest to newest)
        draws_list.reverse()

        prompt = f"""
Bạn là chuyên gia phân tích chuỗi số và dự đoán xác suất xổ số chuyên nghiệp.
Nhiệm vụ của bạn là phân tích dữ liệu lịch sử các kỳ quay số gần nhất và đưa ra khuyến nghị thông minh (Dự đoán kỳ quay tiếp theo) cho 2 thị trường: Chẵn/Lẻ (Parity) và Tài/Xỉu (Size).

Dữ liệu lịch sử 100 kỳ gần nhất (từ cũ đến mới nhất):
{json.dumps(draws_list, ensure_ascii=False, indent=2)}

Bối cảnh thống kê hiện tại của hệ thống:
- Chuỗi bệt hiện tại:
  + Chẵn/Lẻ: {json.dumps(stats_context.get('streaks', {}).get('le_streak', {}), ensure_ascii=False)}
  + Tài/Xỉu: {json.dumps(stats_context.get('streaks', {}).get('tai_streak', {}), ensure_ascii=False)}
- Dự đoán xác suất Markov kỳ tiếp theo:
  + Parity (Lẻ): {stats_context.get('markov', {}).get('pred_le', 0.5) * 100:.1f}% | (Chẵn): {(1 - stats_context.get('markov', {}).get('pred_le', 0.5)) * 100:.1f}%
  + Size (Tài): {stats_context.get('markov', {}).get('pred_tai', 0.5) * 100:.1f}% | (Xỉu): {(1 - stats_context.get('markov', {}).get('pred_tai', 0.5)) * 100:.1f}%

HÃY ĐƯA RA DỰ ĐOÁN KỲ QUAY TIẾP THEO (Issue tiếp theo).
Quy tắc:
1. Bạn có thể dự đoán: "MUA LẺ", "MUA CHẴN", hoặc "BỎ QUA" cho Parity.
2. Bạn có thể dự đoán: "MUA TÀI", "MUA XỈU", hoặc "BỎ QUA" cho Size.
3. Chỉ khuyến nghị MUA khi bạn phát hiện tín hiệu xu hướng lặp lại phi tuyến tính cực kỳ rõ ràng, hoặc dây bệt quá dài chuẩn bị bẻ cầu. Ngược lại hãy khuyến nghị "BỎ QUA" (mặc định nếu không chắc chắn).
4. Độ tin cậy (confidence) phải là số nguyên từ 0 đến 100. Nếu quyết định là "BỎ QUA", confidence nên ở mức 50%.
5. Rationale (lý giải): Giải thích bằng tiếng Việt thật ngắn gọn (tối đa 2 dòng) lý do vì sao dự đoán như vậy.

Bạn BẮT BUỘC phải trả về kết quả dưới dạng JSON object tuân thủ schema sau:
{{
  "parity": {{
    "decision": "MUA LẺ | MUA CHẴN | BỎ QUA",
    "confidence": 50,
    "rationale": "Lý giải ngắn gọn..."
  }},
  "size": {{
    "decision": "MUA TÀI | MUA XỈU | BỎ QUA",
    "confidence": 50,
    "rationale": "Lý giải ngắn gọn..."
  }}
}}
"""
        gemini_model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
        gemini_version = getattr(config, "GEMINI_API_VERSION", "v1beta")
        url = f"https://generativelanguage.googleapis.com/{gemini_version}/models/{gemini_model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        res_data = response.json()
        text_content = res_data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text_content)

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
        
        # Calculate sliding window probabilities (last 15 records) for initialization
        N_sliding = min(15, total_records)
        recent_records = history[:N_sliding]
        recent_le_count = sum(1 for r in recent_records if r.get("is_le"))
        recent_tai_count = sum(1 for r in recent_records if r.get("is_tai"))
        
        prob_le_sliding = recent_le_count / N_sliding if N_sliding > 0 else 0.5
        prob_chan_sliding = 1.0 - prob_le_sliding
        prob_tai_sliding = recent_tai_count / N_sliding if N_sliding > 0 else 0.5
        prob_xiu_sliding = 1.0 - prob_tai_sliding
        
        # 1. Tinh xac suat phan tram xuat hien
        le_count = df["is_le"].sum()
        chan_count = total_records - le_count
        tai_count = df["is_tai"].sum()
        xiu_count = total_records - tai_count
        
        prob_le = float(le_count / total_records)
        prob_chan = float(chan_count / total_records)
        prob_tai = float(tai_count / total_records)
        prob_xiu = float(xiu_count / total_records)
        
        # 2. Tinh chuoi cau bet (streaks) hien tai va tỷ lệ chuyen doi
        # Reverse to oldest first for streak analysis
        series_le = df["is_le"].iloc[::-1].reset_index(drop=True)
        series_tai = df["is_tai"].iloc[::-1].reset_index(drop=True)
        
        le_streak_stats, active_le_len, active_le_state = ProbabilityAnalyzer._analyze_streak_transitions(series_le)
        tai_streak_stats, active_tai_len, active_tai_state = ProbabilityAnalyzer._analyze_streak_transitions(series_tai)

        # Config bot loc giam nhieu (tin cay >= 90%)
        CONFIDENCE_THRESHOLD = 0.90
        MIN_SAMPLES = 3 # Can it nhat 3 mau lich su cung do dai de tin tuong
        
        # Tinh xác suat gãy bệt cho Le/Chan
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
            if active_le_state: # Hien tai la Le
                prob_next_chan = pred_streak_le_switch
                prob_next_le = 1 - pred_streak_le_switch
            else: # Hien tai la Chan
                prob_next_le = pred_streak_le_switch
                prob_next_chan = 1 - pred_streak_le_switch
            predicted_parity = "Le" if prob_next_le >= prob_next_chan else "Chan"

        # Tinh xác suat gãy bệt cho Tai/Xiu
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
            if active_tai_state: # Hien tai la Tai
                prob_next_xiu = pred_streak_tai_switch
                prob_next_tai = 1 - pred_streak_tai_switch
            else: # Hien tai la Xiu
                prob_next_tai = pred_streak_tai_switch
                prob_next_xiu = 1 - pred_streak_tai_switch
            predicted_size = "Tai" if prob_next_tai >= prob_next_xiu else "Xiu"

        # 3. Dự đoán xác suất kỳ tiếp theo bằng xích Markov Cấp 2 (Markov Chain Order 2)
        pred_le = prob_le_sliding
        pred_tai = prob_tai_sliding
        
        if total_records > 15:
            # --- Parity Markov Order 2 ---
            states_le = {
                "L_L": {"L": 0, "C": 0},
                "L_C": {"L": 0, "C": 0},
                "C_L": {"L": 0, "C": 0},
                "C_C": {"L": 0, "C": 0}
            }
            # df is ordered newest first. so index i is newer than i+1
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
                
            # --- Size Markov Order 2 ---
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
 
        # Calculate max streaks (excluding active streak to get true historical max ceiling)
        historical_le = series_le.iloc[:-active_le_len] if active_le_len > 0 else series_le
        historical_tai = series_tai.iloc[:-active_tai_len] if active_tai_len > 0 else series_tai
        max_le_streak = ProbabilityAnalyzer._get_max_streak(historical_le)
        max_tai_streak = ProbabilityAnalyzer._get_max_streak(historical_tai)

        # AI Recommendation calculations
        parity_decision = "BỎ QUA"
        parity_confidence = 50
        parity_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."
        
        size_decision = "BỎ QUA"
        size_confidence = 50
        size_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."

        # 1. Prepare statistics context for Gemini
        stats_context = {
            "streaks": {
                "le_streak": {
                    "state": "Le" if active_le_state else "Chan",
                    "count": active_le_len,
                    "max_history": max_le_streak,
                    "transition_history": le_streak_stats
                },
                "tai_streak": {
                    "state": "Tai" if active_tai_state else "Xiu",
                    "count": active_tai_len,
                    "max_history": max_tai_streak,
                    "transition_history": tai_streak_stats
                }
            },
            "markov": {
                "pred_le": pred_le,
                "pred_tai": pred_tai
            }
        }

        # 2. Try to call Gemini API
        gemini_success = False
        gemini_pred = {}
        
        current_time = time.time()
        time_since_last_call = current_time - ProbabilityAnalyzer._last_call_time
        
        if getattr(config, "GEMINI_API_KEY", "") and total_records >= 10:
            # Calculate cache key
            latest_issue = str(df.iloc[0].get("issue") or "")
            cache_key = f"{config.LOTTERY_ID}_{latest_issue}" if latest_issue else None

            if cache_key and cache_key in ProbabilityAnalyzer._gemini_cache:
                gemini_pred = ProbabilityAnalyzer._gemini_cache[cache_key]
                gemini_success = True
            elif time_since_last_call < 20:
                # Rate limit call to Gemini API, fallback to heuristics to prevent 429
                pass
            else:
                try:
                    # Update timestamp BEFORE calling to prevent concurrent stampedes
                    ProbabilityAnalyzer._last_call_time = current_time
                    gemini_pred = ProbabilityAnalyzer._call_gemini_api(df, stats_context)
                    if isinstance(gemini_pred, dict) and "parity" in gemini_pred and "size" in gemini_pred:
                        gemini_success = True
                        if cache_key:
                            # Keep cache size small, e.g. max 5 items to avoid leaking memory
                            if len(ProbabilityAnalyzer._gemini_cache) > 5:
                                ProbabilityAnalyzer._gemini_cache.clear()
                            ProbabilityAnalyzer._gemini_cache[cache_key] = gemini_pred
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to call Gemini API: {e}. Falling back to heuristics.")

        if gemini_success:
            parity_decision = gemini_pred["parity"].get("decision", "BỎ QUA")
            parity_confidence = int(gemini_pred["parity"].get("confidence", 50))
            parity_rationale = gemini_pred["parity"].get("rationale", "Dự đoán bởi Gemini AI.")
            
            size_decision = gemini_pred["size"].get("decision", "BỎ QUA")
            size_confidence = int(gemini_pred["size"].get("confidence", 50))
            size_rationale = gemini_pred["size"].get("rationale", "Dự đoán bởi Gemini AI.")
        else:
            # Upgraded dynamic mathematical heuristics based on BẢN GÓP Ý TỔNG THỂ
            N_parity = min(15, len(history))
            recent_history_parity = history[:N_parity]
            N_size = min(20, len(history))
            recent_history_size = history[:N_size]
            
            # 1. Calculate Alternating Rate (AR) for Parity and Size over the last 30 rounds
            M = min(30, len(history))
            parity_alternations = 0
            size_alternations = 0
            for i in range(M - 1):
                if history[i].get("is_le") != history[i+1].get("is_le"):
                    parity_alternations += 1
                if history[i].get("is_tai") != history[i+1].get("is_tai"):
                    size_alternations += 1
            ar_parity = parity_alternations / (M - 1) if M > 1 else 0.5
            ar_size = size_alternations / (M - 1) if M > 1 else 0.5

            # Pure Python percentile function
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

            # Calculate AR list for the last 30 periods (each period has 30 rounds) to get 75% percentile threshold
            ar_parity_list = []
            ar_size_list = []
            for start_idx in range(min(30, max(1, len(history) - 30))):
                window = history[start_idx : start_idx + 30]
                if len(window) > 1:
                    alt_p = sum(1 for k in range(len(window)-1) if window[k].get("is_le") != window[k+1].get("is_le"))
                    alt_s = sum(1 for k in range(len(window)-1) if window[k].get("is_tai") != window[k+1].get("is_tai"))
                    ar_parity_list.append(alt_p / (len(window)-1))
                    ar_size_list.append(alt_s / (len(window)-1))
            
            ar_threshold_parity = max(0.5, get_percentile(ar_parity_list, 75))
            ar_threshold_size = max(0.5, get_percentile(ar_size_list, 70))

            # Calculate mean and standard deviation of sliding window probabilities over the last 100 rounds
            K_z = min(100, len(history))
            sliding_probs_le = []
            sliding_probs_tai = []
            for idx in range(K_z):
                # Parity sliding window is 15
                window_p = history[idx : idx + 15]
                if len(window_p) > 0:
                    le_w = sum(1 for r in window_p if r.get("is_le")) / len(window_p)
                    sliding_probs_le.append(le_w)
                # Size sliding window is 20
                window_s = history[idx : idx + 20]
                if len(window_s) > 0:
                    tai_w = sum(1 for r in window_s if r.get("is_tai")) / len(window_s)
                    sliding_probs_tai.append(tai_w)
            
            mean_le = sum(sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.5
            var_le = sum((x - mean_le) ** 2 for x in sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.01
            std_le = max(0.05, var_le ** 0.5)
            
            mean_tai = sum(sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.5
            var_tai = sum((x - mean_tai) ** 2 for x in sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.01
            std_tai = max(0.05, var_tai ** 0.5)
            
            # Saturation thresholds using percentile 85% instead of Z-score
            T_sat_le = get_percentile(sliding_probs_le, 85)
            T_sat_chan = get_percentile([1.0 - x for x in sliding_probs_le], 85)
            T_sat_tai = get_percentile(sliding_probs_tai, 85)
            T_sat_xiu = get_percentile([1.0 - x for x in sliding_probs_tai], 85)

            # 2. Cooling-off mechanism from database prediction history
            from src.database.store import store
            pred_hist = store.get_prediction_history(limit=5)
            
            parity_loss_streak = 0
            for p in pred_hist:
                status_p = p.get("status_parity")
                if status_p == "lose":
                    parity_loss_streak += 1
                elif status_p == "win" or status_p == "ignored":
                    break
            is_parity_cooling = (parity_loss_streak >= 2)
            
            parity_win_streak = 0
            for p in pred_hist:
                status_p = p.get("status_parity")
                if status_p == "win":
                    parity_win_streak += 1
                elif status_p == "lose" or status_p == "ignored":
                    break
            is_parity_win_streak_pause = (parity_win_streak >= 3)
            
            size_loss_streak = 0
            for p in pred_hist:
                status_s = p.get("status_size")
                if status_s == "lose":
                    size_loss_streak += 1
                elif status_s == "win" or status_s == "ignored":
                    break
            is_size_cooling = (size_loss_streak >= 2)

            size_win_streak = 0
            for p in pred_hist:
                status_s = p.get("status_size")
                if status_s == "win":
                    size_win_streak += 1
                elif status_s == "lose" or status_s == "ignored":
                    break
            is_size_win_streak_pause = (size_win_streak >= 3)

            # ----------------------------------------------------
            # 1. PARITY (Chẵn/Lẻ) Prediction
            # ----------------------------------------------------
            recent_le_count = sum(1 for r in recent_history_parity if r.get("is_le"))
            recent_chan_count = N_parity - recent_le_count
            prob_le_sliding = recent_le_count / N_parity if N_parity > 0 else 0.5
            prob_chan_sliding = recent_chan_count / N_parity if N_parity > 0 else 0.5

            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."

            if is_parity_cooling:
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Không cược - Kích hoạt chế độ nghỉ bảo vệ (Cooling-off) sau {parity_loss_streak} kỳ thua liên tiếp."
            elif is_parity_win_streak_pause:
                parity_decision = "BỎ QUA"
                parity_confidence = 50
                parity_rationale = f"Không cược - Chốt lời ngắn hạn sau chuỗi {parity_win_streak} kỳ thắng liên tiếp để bảo toàn lợi nhuận."
            elif ar_parity >= ar_threshold_parity:
                # ----------------------------------------------------
                # PING-PONG SNIPER (ar >= ar_threshold_parity)
                # ----------------------------------------------------
                if len(history) >= 2:
                    last_is_le = history[0].get("is_le")
                    prev_is_le = history[1].get("is_le")
                    
                    if last_is_le != prev_is_le:
                        # Răng cưa nguyên vẹn -> cược đảo chiều
                        predicted_is_le = not last_is_le
                        base_rationale = f"Phát hiện thị trường răng cưa (Alternating Rate: {ar_parity*100:.1f}%). Đánh đảo chiều"
                        base_confidence = int(ar_parity * 100)
                    else:
                        # Răng cưa đã bị bẻ -> cược thuận xu hướng mới
                        predicted_is_le = last_is_le
                        base_rationale = f"Răng cưa gãy (kỳ trước ra trùng). Đánh thuận xu hướng mới"
                        base_confidence = int(ar_parity * 90)
                else:
                    last_is_le = history[0].get("is_le") if len(history) > 0 else True
                    predicted_is_le = not last_is_le
                    base_rationale = f"Phát hiện thị trường răng cưa (Alternating Rate: {ar_parity*100:.1f}%). Đánh đảo chiều"
                    base_confidence = int(ar_parity * 100)
                
                # Check overall probability to override
                if predicted_is_le and prob_le_sliding < prob_chan_sliding:
                    predicted_is_le = False
                    parity_rationale = f"{base_rationale}: mua Chẵn (Hiệu chỉnh theo xác suất tổng thể: Chẵn {prob_chan_sliding*100:.1f}% > Lẻ {prob_le_sliding*100:.1f}%)."
                elif not predicted_is_le and prob_chan_sliding < prob_le_sliding:
                    predicted_is_le = True
                    parity_rationale = f"{base_rationale}: mua Lẻ (Hiệu chỉnh theo xác suất tổng thể: Lẻ {prob_le_sliding*100:.1f}% > Chẵn {prob_chan_sliding*100:.1f}%)."
                else:
                    parity_rationale = f"{base_rationale}: mua {'Lẻ' if predicted_is_le else 'Chẵn'}."
                
                parity_decision = "MUA LẺ" if predicted_is_le else "MUA CHẴN"
                parity_confidence = base_confidence
            else:
                # ----------------------------------------------------
                # TRENDING CONSENSUS SNIPER (ar < ar_threshold_parity)
                # ----------------------------------------------------
                # Sliding predictions using mean + 0.3*std (optimized)
                sliding_pred = "Le" if prob_le_sliding >= (mean_le + 0.3 * std_le) else "Chan" if prob_chan_sliding >= ((1.0 - mean_le) + 0.3 * std_le) else "None"
                # Markov predictions using 0.51 threshold (optimized)
                markov_pred = "Le" if pred_le >= 0.51 else "Chan" if (1.0 - pred_le) >= 0.51 else "None"
                
                # Consensus check
                if sliding_pred != "None" and markov_pred != "None" and sliding_pred == markov_pred:
                    # Bỏ điều kiện last == prev (2-step confirmation) để tránh chậm lệnh
                    is_saturated = (sliding_pred == "Le" and prob_le_sliding >= T_sat_le) or (sliding_pred == "Chan" and prob_chan_sliding >= T_sat_chan)
                    if not is_saturated:
                        parity_decision = "MUA LẺ" if sliding_pred == "Le" else "MUA CHẴN"
                        # Dynamic Weighting Consensus: boost confidence by 1.05x (reduced from 1.15x)
                        parity_confidence = int((0.6 * (prob_le_sliding if sliding_pred == "Le" else prob_chan_sliding) + 0.4 * (pred_le if sliding_pred == "Le" else 1.0 - pred_le)) * 100 * 1.05)
                        parity_rationale = f"Đồng thuận xu hướng {'Lẻ' if sliding_pred == 'Le' else 'Chẵn'}. Xác suất tổng hợp: {parity_confidence}%."
                    else:
                        parity_rationale = f"Không cược - Phát hiện bẫy {'Lẻ' if sliding_pred == 'Le' else 'Chẵn'} đạt đỉnh (Xác suất trượt: {(prob_le_sliding if sliding_pred == 'Le' else prob_chan_sliding)*100:.1f}%, Ngưỡng bão hòa 85%: {T_sat_le*100:.1f}%)."
                else:
                    parity_rationale = "Không cược - Chỉ báo xu hướng và Markov không đồng thuận."

            # Layer 4: Softened Cross-Market Correlation Risk Filter
            if parity_decision == "MUA LẺ" and len(history) >= 5:
                if all(not r.get("is_tai") for r in history[:5]):
                    parity_confidence -= 15
                    parity_rationale += " (Cảnh báo tương quan: bệt Xỉu 5 kỳ. Giảm 15% tự tin)."
                    if parity_confidence < 55:
                        parity_decision = "BỎ QUA"
                        parity_rationale = "Không cược - Tránh rủi ro tương quan chéo (Tự tin rớt dưới 55%)."
            elif parity_decision == "MUA CHẴN" and len(history) >= 5:
                if all(r.get("is_tai") for r in history[:5]):
                    parity_confidence -= 15
                    parity_rationale += " (Cảnh báo tương quan: bệt Tài 5 kỳ. Giảm 15% tự tin)."
                    if parity_confidence < 55:
                        parity_decision = "BỎ QUA"
                        parity_rationale = "Không cược - Tránh rủi ro tương quan chéo (Tự tin rớt dưới 55%)."

            # ----------------------------------------------------
            # 2. SIZE (Tài/Xỉu) Prediction
            # ----------------------------------------------------
            recent_tai_count = sum(1 for r in recent_history_size if r.get("is_tai"))
            recent_xiu_count = N_size - recent_tai_count
            prob_tai_sliding = recent_tai_count / N_size if N_size > 0 else 0.5
            prob_xiu_sliding = recent_xiu_count / N_size if N_size > 0 else 0.5

            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = "Tín hiệu thị trường lưỡng lự, chuỗi bệt ngắn hoặc xác suất cân bằng."

            if is_size_cooling:
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Không cược - Kích hoạt chế độ nghỉ bảo vệ (Cooling-off) sau {size_loss_streak} kỳ thua liên tiếp."
            elif is_size_win_streak_pause:
                size_decision = "BỎ QUA"
                size_confidence = 50
                size_rationale = f"Không cược - Chốt lời ngắn hạn sau chuỗi {size_win_streak} kỳ thắng liên tiếp để bảo toàn lợi nhuận."
            elif ar_size >= ar_threshold_size:
                # ----------------------------------------------------
                # PING-PONG SNIPER (ar >= ar_threshold_size)
                # ----------------------------------------------------
                if len(history) >= 2:
                    last_is_tai = history[0].get("is_tai")
                    prev_is_tai = history[1].get("is_tai")
                    
                    if last_is_tai != prev_is_tai:
                        # Răng cưa nguyên vẹn -> cược đảo chiều
                        predicted_is_tai = not last_is_tai
                        base_rationale = f"Phát hiện thị trường răng cưa (Alternating Rate: {ar_size*100:.1f}%). Đánh đảo chiều"
                        base_confidence = int(ar_size * 100)
                    else:
                        # Răng cưa đã bị bẻ -> cược thuận xu hướng mới
                        predicted_is_tai = last_is_tai
                        base_rationale = f"Răng cưa gãy (kỳ trước ra trùng). Đánh thuận xu hướng mới"
                        base_confidence = int(ar_size * 90)
                else:
                    last_is_tai = history[0].get("is_tai") if len(history) > 0 else True
                    predicted_is_tai = not last_is_tai
                    base_rationale = f"Phát hiện thị trường răng cưa (Alternating Rate: {ar_size*100:.1f}%). Đánh đảo chiều"
                    base_confidence = int(ar_size * 100)
                
                # Check overall probability to override
                if predicted_is_tai and prob_tai_sliding < prob_xiu_sliding:
                    predicted_is_tai = False
                    size_rationale = f"{base_rationale}: mua Xỉu (Hiệu chỉnh theo xác suất tổng thể: Xỉu {prob_xiu_sliding*100:.1f}% > Tài {prob_tai_sliding*100:.1f}%)."
                elif not predicted_is_tai and prob_xiu_sliding < prob_tai_sliding:
                    predicted_is_tai = True
                    size_rationale = f"{base_rationale}: mua Tài (Hiệu chỉnh theo xác suất tổng thể: Tài {prob_tai_sliding*100:.1f}% > Xỉu {prob_xiu_sliding*100:.1f}%)."
                else:
                    size_rationale = f"{base_rationale}: mua {'Tài' if predicted_is_tai else 'Xỉu'}."
                
                size_decision = "MUA TÀI" if predicted_is_tai else "MUA XỈU"
                size_confidence = base_confidence
            else:
                # ----------------------------------------------------
                # TRENDING CONSENSUS SNIPER (ar < ar_threshold_size)
                # ----------------------------------------------------
                # Sliding predictions using mean + 0.3*std (optimized)
                sliding_pred_size = "Tai" if prob_tai_sliding >= (mean_tai + 0.3 * std_tai) else "Xiu" if prob_xiu_sliding >= ((1.0 - mean_tai) + 0.3 * std_tai) else "None"
                # Markov predictions using 0.51 threshold (optimized)
                markov_pred_size = "Tai" if pred_tai >= 0.51 else "Xiu" if (1.0 - pred_tai) >= 0.51 else "None"
                
                # Consensus check
                if sliding_pred_size != "None" and markov_pred_size != "None" and sliding_pred_size == markov_pred_size:
                    is_saturated_size = (sliding_pred_size == "Tai" and prob_tai_sliding >= T_sat_tai) or (sliding_pred_size == "Xiu" and prob_xiu_sliding >= T_sat_xiu)
                    if not is_saturated_size:
                        size_decision = "MUA TÀI" if sliding_pred_size == "Tai" else "MUA XỈU"
                        # Dynamic Weighting Consensus: boost confidence by 1.05x (reduced from 1.15x)
                        size_confidence = int((0.6 * (prob_tai_sliding if sliding_pred_size == "Tai" else prob_xiu_sliding) + 0.4 * (pred_tai if sliding_pred_size == "Tai" else 1.0 - pred_tai)) * 100 * 1.05)
                        size_rationale = f"Đồng thuận xu hướng {'Tài' if sliding_pred_size == 'Tai' else 'Xỉu'}. Xác suất tổng hợp: {size_confidence}%."
                    else:
                        size_rationale = f"Không cược - Phát hiện bẫy {'Tài' if sliding_pred_size == 'Tai' else 'Xỉu'} đạt đỉnh (Xác suất trượt: {(prob_tai_sliding if sliding_pred_size == 'Tai' else prob_xiu_sliding)*100:.1f}%, Ngưỡng bão hòa 85%: {T_sat_tai*100:.1f}%)."
                else:
                    size_rationale = "Không cược - Chỉ báo xu hướng và Markov không đồng thuận."

            # Layer 4: Softened Cross-Market Correlation Risk Filter
            if size_decision == "MUA TÀI" and len(history) >= 5:
                if all(not r.get("is_le") for r in history[:5]):
                    size_confidence -= 15
                    size_rationale += " (Cảnh báo tương quan: bệt Chẵn 5 kỳ. Giảm 15% tự tin)."
                    if size_confidence < 55:
                        size_decision = "BỎ QUA"
                        size_rationale = "Không cược - Tránh rủi ro tương quan chéo (Tự tin rớt dưới 55%)."
            elif size_decision == "MUA XỈU" and len(history) >= 5:
                if all(r.get("is_le") for r in history[:5]):
                    size_confidence -= 15
                    size_rationale += " (Cảnh báo tương quan: bệt Lẻ 5 kỳ. Giảm 15% tự tin)."
                    if size_confidence < 55:
                        size_decision = "BỎ QUA"
                        size_rationale = "Không cược - Tránh rủi ro tương quan chéo (Tự tin rớt dưới 55%)."

            # 3. Main Trend Filter (Đảo chiều bệt trung lập):
            if size_decision == "BỎ QUA" and not is_size_cooling and len(history) >= 6:
                if all(r.get("is_tai") for r in history[:6]):
                    size_decision = "MUA XỈU"
                    size_confidence = 60
                    size_rationale = "Bộ lọc xu hướng: Đảo chiều sớm do bệt Tài liên tiếp 6 kỳ."
                elif all(not r.get("is_tai") for r in history[:6]):
                    size_decision = "MUA TÀI"
                    size_confidence = 60
                    size_rationale = "Bộ lọc xu hướng: Đảo chiều sớm do bệt Xỉu liên tiếp 6 kỳ."

        # Adaptive Streak Safety Trap (Block betting when streaks reach historical max levels)
        T_streak_parity = max(4, max_le_streak)
        T_streak_size = max(4, max_tai_streak)

        if parity_decision != "BỎ QUA" and active_le_len >= T_streak_parity:
            parity_decision = "BỎ QUA"
            parity_confidence = 50
            parity_rationale = f"Không cược - Chuỗi bệt hiện tại ({active_le_len} kỳ) đã chạm/vượt trần lịch sử dữ liệu mẫu ({T_streak_parity} kỳ), rủi ro đảo chiều đạt đỉnh."

        if size_decision != "BỎ QUA" and active_tai_len >= T_streak_size:
            size_decision = "BỎ QUA"
            size_confidence = 50
            size_rationale = f"Không cược - Chuỗi bệt hiện tại ({active_tai_len} kỳ) đã chạm/vượt trần lịch sử dữ liệu mẫu ({T_streak_size} kỳ), rủi ro đảo chiều đạt đỉnh."

        # 3.2. Giới hạn tự tin tối đa cho cả 2 thị trường ở mức 70% để tránh overconfidence
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
                "le_streak": {
                    "state": "Le" if active_le_state else "Chan",
                    "count": active_le_len,
                    "max_history": max_le_streak
                },
                "tai_streak": {
                    "state": "Tai" if active_tai_state else "Xiu",
                    "count": active_tai_len,
                    "max_history": max_tai_streak
                }
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
                "parity": {
                    "decision": parity_decision,
                    "confidence": parity_confidence,
                    "rationale": parity_rationale
                },
                "size": {
                    "decision": size_decision,
                    "confidence": size_confidence,
                    "rationale": size_rationale
                },
                "engine": "Gemini AI" if gemini_success else "Heuristics (3-Layer)"
            }
        }
