import pandas as pd
import numpy as np
from typing import Dict, Any, List

class ProbabilityAnalyzer:
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

        # 3. Dự đoán xác suất kỳ tiếp theo bằng xích Markov (Markov Chain - Cấp 1) lam tham khao
        pred_le = 0.5
        pred_tai = 0.5
        
        if total_records > 10:
            transitions_le = {"L_L": 0, "L_C": 0, "C_L": 0, "C_C": 0}
            for i in range(len(df) - 1):
                curr = "L" if df.iloc[i]["is_le"] else "C"
                prev = "L" if df.iloc[i+1]["is_le"] else "C"
                transitions_le[f"{prev}_{curr}"] += 1
                
            last_state = "L" if df.iloc[0]["is_le"] else "C"
            if last_state == "L":
                total_from_l = transitions_le["L_L"] + transitions_le["L_C"]
                if total_from_l > 0:
                    pred_le = transitions_le["L_L"] / total_from_l
            else:
                total_from_c = transitions_le["C_L"] + transitions_le["C_C"]
                if total_from_c > 0:
                    pred_le = transitions_le["C_L"] / total_from_c
                    
            transitions_tai = {"T_T": 0, "T_X": 0, "X_T": 0, "X_X": 0}
            for i in range(len(df) - 1):
                curr = "T" if df.iloc[i]["is_tai"] else "X"
                prev = "T" if df.iloc[i+1]["is_tai"] else "X"
                transitions_tai[f"{prev}_{curr}"] += 1
                
            last_tai_state = "T" if df.iloc[0]["is_tai"] else "X"
            if last_tai_state == "T":
                total_from_t = transitions_tai["T_T"] + transitions_tai["T_X"]
                if total_from_t > 0:
                    pred_tai = transitions_tai["T_T"] / total_from_t
            else:
                total_from_x = transitions_tai["X_T"] + transitions_tai["X_X"]
                if total_from_x > 0:
                    pred_tai = transitions_tai["X_T"] / total_from_x
 
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
                    "count": active_le_len
                },
                "tai_streak": {
                    "state": "Tai" if active_tai_state else "Xiu",
                    "count": active_tai_len
                }
            },
            "prediction_for_next_issue": {
                "le_probability": round(pred_le, 4) if total_records > 10 else "Không có",
                "chan_probability": round(1 - pred_le, 4) if total_records > 10 else "Không có",
                "predicted_parity": ("Le" if pred_le >= 0.5 else "Chan") if total_records > 10 else "Không có",
                "tai_probability": round(pred_tai, 4) if total_records > 10 else "Không có",
                "xiu_probability": round(1 - pred_tai, 4) if total_records > 10 else "Không có",
                "predicted_size": ("Tai" if pred_tai >= 0.5 else "Xiu") if total_records > 10 else "Không có"
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
            }
        }
