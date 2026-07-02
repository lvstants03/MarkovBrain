import pandas as pd
import numpy as np
from typing import Dict, Any, List

class ProbabilityAnalyzer:
    @staticmethod
    def analyze(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return {
                "total_records": 0,
                "probabilities": {},
                "streaks": {},
                "prediction": {}
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
        
        # 2. Tinh chuoi cau bet (streaks) hien tai
        # Lay cac dong gan nhat de xet xem cau dang bet bao nhieu ky
        current_le_streak = 0
        current_tai_streak = 0
        
        # Xet tu ky moi nhat ve sau
        first_row = df.iloc[0]
        target_le = first_row["is_le"]
        for _, row in df.iterrows():
            if row["is_le"] == target_le:
                current_le_streak += 1
            else:
                break
                
        target_tai = first_row["is_tai"]
        for _, row in df.iterrows():
            if row["is_tai"] == target_tai:
                current_tai_streak += 1
            else:
                break
                
        # 3. Dự đoán xác suất kỳ tiếp theo bằng xích Markov (Markov Chain - Cấp 1)
        # Tinh xac suat chuyen doi trang thai tu ky truoc sang ky sau
        pred_le = 0.5
        pred_tai = 0.5
        
        if total_records > 10:
            # Chuyen doi cho Le/Chan
            # Dem so lan chuyen tu Le -> Le, Le -> Chan, Chan -> Le, Chan -> Chan
            transitions_le = {"L_L": 0, "L_C": 0, "C_L": 0, "C_C": 0}
            for i in range(len(df) - 1):
                curr = "L" if df.iloc[i]["is_le"] else "C"
                prev = "L" if df.iloc[i+1]["is_le"] else "C" # i+1 la ky truoc do trong list (vi list sap xep giam dan)
                transitions_le[f"{prev}_{curr}"] += 1
                
            # Lay trang thai cua ky cuoi cung (tuc la ky moi nhat hien tai)
            last_state = "L" if df.iloc[0]["is_le"] else "C"
            if last_state == "L":
                total_from_l = transitions_le["L_L"] + transitions_le["L_C"]
                if total_from_l > 0:
                    pred_le = transitions_le["L_L"] / total_from_l
            else:
                total_from_c = transitions_le["C_L"] + transitions_le["C_C"]
                if total_from_c > 0:
                    pred_le = transitions_le["C_L"] / total_from_c
                    
            # Tuong tu cho Tai/Xiu
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
                    "state": "Le" if target_le else "Chan",
                    "count": current_le_streak
                },
                "tai_streak": {
                    "state": "Tai" if target_tai else "Xiu",
                    "count": current_tai_streak
                }
            },
            "prediction_for_next_issue": {
                "le_probability": round(pred_le, 4),
                "chan_probability": round(1 - pred_le, 4),
                "predicted_parity": "Le" if pred_le >= 0.5 else "Chan",
                "tai_probability": round(pred_tai, 4),
                "xiu_probability": round(1 - pred_tai, 4),
                "predicted_size": "Tai" if pred_tai >= 0.5 else "Xiu"
            }
        }
