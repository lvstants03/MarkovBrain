import os
import sys
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_dataset():
    paths = [
        r"C:\Users\lyvan\.gemini\antigravity-ide\brain\5f8dd960-f4ce-45be-9e96-cf7ce8740eff\scratch\out_48.json",
        r"C:\Users\lyvan\.gemini\antigravity-ide\brain\5f8dd960-f4ce-45be-9e96-cf7ce8740eff\scratch\all_lotteries.json",
        "out_48.json",
        "all_lotteries.json"
    ]
    
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if isinstance(data, dict) and "data" in data and "statisticsInfo" in data["data"]:
                    stats_info = data["data"]["statisticsInfo"]
                    if "total_sum" in stats_info and "statisticDataList" in stats_info["total_sum"]:
                        datalist = stats_info["total_sum"]["statisticDataList"]
                        odd_even_list = datalist.get("oddEven", [])
                        big_small_list = datalist.get("bigSmall", [])
                        
                        draws_map = {}
                        for item in odd_even_list:
                            issue = item["issue"]
                            draws_map[issue] = {
                                "issue": issue,
                                "is_le": item["result"] == "odd"
                            }
                        for item in big_small_list:
                            issue = item["issue"]
                            if issue in draws_map:
                                draws_map[issue]["is_tai"] = item["result"] == "big"
                                
                        formatted = list(draws_map.values())
                        formatted.sort(key=lambda x: x["issue"])
                        print(f"Loaded {len(formatted)} valid draw records from statisticsInfo in {p}")
                        return formatted
            except Exception as e:
                print(f"Failed to load from {p}: {e}")
                
    # Fallback to store
    from src.config import config
    config.LOTTERY_CODE = "mb75g"
    from src.database.store import store
    history = store.get_history(limit=500)
    if history:
        history = list(reversed(history))
        print(f"Fallback: Loaded {len(history)} records from active database store.")
        return history
        
    print("Error: No dataset found for backtesting.")
    return []

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

def run_backtest():
    dataset = load_dataset()
    if not dataset:
        return
        
    print(f"Starting Walk-Forward Backtesting of upgraded rules over {len(dataset)} rounds...")
    
    # Heuristics settings
    N_parity = 20
    N_size = 20
    M = 30
    Z_pct = 85
    AR_pct_p = 75
    AR_pct_s = 70
    
    total_bets_p = 0
    wins_p = 0
    total_bets_s = 0
    wins_s = 0
    
    resolved_history = [] # list of {"status_parity": "win"/"lose", "status_size": "win"/"lose"}
    
    for idx in range(40, len(dataset)):
        sub_history = list(reversed(dataset[:idx]))
        actual_next = dataset[idx]
        
        # 1. AR threshold
        ar_parity_list = []
        ar_size_list = []
        for start_idx in range(min(30, max(1, len(sub_history) - 30))):
            window = sub_history[start_idx : start_idx + 30]
            if len(window) > 1:
                alt_p = sum(1 for k in range(len(window)-1) if window[k]["is_le"] != window[k+1]["is_le"])
                alt_s = sum(1 for k in range(len(window)-1) if window[k]["is_tai"] != window[k+1]["is_tai"])
                ar_parity_list.append(alt_p / (len(window)-1))
                ar_size_list.append(alt_s / (len(window)-1))
        ar_threshold_parity = max(0.5, get_percentile(ar_parity_list, AR_pct_p))
        ar_threshold_size = max(0.5, get_percentile(ar_size_list, AR_pct_s))
        
        # Current alternations
        sub_M = min(M, len(sub_history))
        alt_parity = 0
        alt_size = 0
        for i in range(sub_M - 1):
            if sub_history[i]["is_le"] != sub_history[i+1]["is_le"]:
                alt_parity += 1
            if sub_history[i]["is_tai"] != sub_history[i+1]["is_tai"]:
                alt_size += 1
        ar_parity = alt_parity / (sub_M - 1) if sub_M > 1 else 0.5
        ar_size = alt_size / (sub_M - 1) if sub_M > 1 else 0.5
        
        # 2. Sliding window stats
        recent_p = sub_history[:N_parity]
        le_cnt = sum(1 for r in recent_p if r["is_le"])
        prob_le_sliding = le_cnt / N_parity if N_parity > 0 else 0.5
        prob_chan_sliding = 1.0 - prob_le_sliding
        
        recent_s = sub_history[:N_size]
        tai_cnt = sum(1 for r in recent_s if r["is_tai"])
        prob_tai_sliding = tai_cnt / N_size if N_size > 0 else 0.5
        prob_xiu_sliding = 1.0 - prob_tai_sliding
        
        # Sliding probabilities history for saturation percentile
        sub_K = min(100, len(sub_history))
        sliding_probs_le = []
        sliding_probs_tai = []
        for k in range(sub_K):
            win_p = sub_history[k : k + N_parity]
            if len(win_p) > 0:
                sliding_probs_le.append(sum(1 for r in win_p if r["is_le"]) / len(win_p))
            win_s = sub_history[k : k + N_size]
            if len(win_s) > 0:
                sliding_probs_tai.append(sum(1 for r in win_s if r["is_tai"]) / len(win_s))
                
        mean_le = sum(sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.5
        var_le = sum((x - mean_le)**2 for x in sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.01
        std_le = max(0.05, var_le ** 0.5)
        
        mean_tai = sum(sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.5
        var_tai = sum((x - mean_tai)**2 for x in sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.01
        std_tai = max(0.05, var_tai ** 0.5)
        
        T_sat_le = get_percentile(sliding_probs_le, Z_pct)
        T_sat_chan = get_percentile([1.0 - x for x in sliding_probs_le], Z_pct)
        T_sat_tai = get_percentile(sliding_probs_tai, Z_pct)
        T_sat_xiu = get_percentile([1.0 - x for x in sliding_probs_tai], Z_pct)
        
        # 3. Cooling off check & Win-streak check
        parity_loss_streak = 0
        for p in reversed(resolved_history):
            if p["status_parity"] == "lose":
                parity_loss_streak += 1
            elif p["status_parity"] == "win" or p["status_parity"] == "ignored":
                break
        is_parity_cooling = (parity_loss_streak >= 2)
        
        parity_win_streak = 0
        for p in reversed(resolved_history):
            if p["status_parity"] == "win":
                parity_win_streak += 1
            elif p["status_parity"] == "lose" or p["status_parity"] == "ignored":
                break
        is_parity_win_streak_pause = (parity_win_streak >= 3)
        
        size_loss_streak = 0
        for p in reversed(resolved_history):
            if p["status_size"] == "lose":
                size_loss_streak += 1
            elif p["status_size"] == "win" or p["status_size"] == "ignored":
                break
        is_size_cooling = (size_loss_streak >= 2)

        size_win_streak = 0
        for p in reversed(resolved_history):
            if p["status_size"] == "win":
                size_win_streak += 1
            elif p["status_size"] == "lose" or p["status_size"] == "ignored":
                break
        is_size_win_streak_pause = (size_win_streak >= 3)

        # 3.1. Calculate Active Streak and Historical Max Streaks (excluding active)
        active_le_val = sub_history[0]["is_le"]
        active_le_len = 0
        for r in sub_history:
            if r["is_le"] == active_le_val:
                active_le_len += 1
            else:
                break
                
        hist_p_series = sub_history[active_le_len:]
        max_le_streak = 0
        curr_len = 0
        for i in range(len(hist_p_series)):
            if i == 0 or hist_p_series[i]["is_le"] == hist_p_series[i-1]["is_le"]:
                curr_len += 1
                max_le_streak = max(max_le_streak, curr_len)
            else:
                curr_len = 1
                
        active_tai_val = sub_history[0]["is_tai"]
        active_tai_len = 0
        for r in sub_history:
            if r["is_tai"] == active_tai_val:
                active_tai_len += 1
            else:
                break
                
        hist_s_series = sub_history[active_tai_len:]
        max_tai_streak = 0
        curr_len = 0
        for i in range(len(hist_s_series)):
            if i == 0 or hist_s_series[i]["is_tai"] == hist_s_series[i-1]["is_tai"]:
                curr_len += 1
                max_tai_streak = max(max_tai_streak, curr_len)
            else:
                curr_len = 1
                
        T_streak_parity = max(4, max_le_streak)
        T_streak_size = max(4, max_tai_streak)
        
        # 4. Markov Order 2
        pred_le = prob_le_sliding
        pred_tai = prob_tai_sliding
        if len(sub_history) > 15:
            # Parity Markov
            states_le = {
                "L_L": {"L": 0, "C": 0}, "L_C": {"L": 0, "C": 0},
                "C_L": {"L": 0, "C": 0}, "C_C": {"L": 0, "C": 0}
            }
            for i in range(len(sub_history) - 2):
                curr = "L" if sub_history[i]["is_le"] else "C"
                prev = "L" if sub_history[i+1]["is_le"] else "C"
                prev2 = "L" if sub_history[i+2]["is_le"] else "C"
                states_le[f"{prev2}_{prev}"][curr] += 1
            last_state = "L" if sub_history[0]["is_le"] else "C"
            last_prev = "L" if sub_history[1]["is_le"] else "C"
            state_key = f"{last_prev}_{last_state}"
            tot = states_le[state_key]["L"] + states_le[state_key]["C"]
            if tot > 0:
                pred_le = states_le[state_key]["L"] / tot
                
            # Size Markov
            states_tai = {
                "T_T": {"T": 0, "X": 0}, "T_X": {"T": 0, "X": 0},
                "X_T": {"T": 0, "X": 0}, "X_X": {"T": 0, "X": 0}
            }
            for i in range(len(sub_history) - 2):
                curr = "T" if sub_history[i]["is_tai"] else "X"
                prev = "T" if sub_history[i+1]["is_tai"] else "X"
                prev2 = "T" if sub_history[i+2]["is_tai"] else "X"
                states_tai[f"{prev2}_{prev}"][curr] += 1
            last_tai = "T" if sub_history[0]["is_tai"] else "X"
            last_prev_tai = "T" if sub_history[1]["is_tai"] else "X"
            state_key_tai = f"{last_prev_tai}_{last_tai}"
            tot_tai = states_tai[state_key_tai]["T"] + states_tai[state_key_tai]["X"]
            if tot_tai > 0:
                pred_tai = states_tai[state_key_tai]["T"] / tot_tai
                
        # 5. Prediction Decisions
        # Parity
        decision_p = "BỎ QUA"
        if is_parity_cooling:
            decision_p = "BỎ QUA"
        elif is_parity_win_streak_pause:
            decision_p = "BỎ QUA"
        elif ar_parity >= ar_threshold_parity:
            if len(sub_history) >= 2:
                if sub_history[0]["is_le"] != sub_history[1]["is_le"]:
                    decision_p = "MUA LẺ" if not sub_history[0]["is_le"] else "MUA CHẴN"
                else:
                    decision_p = "MUA LẺ" if sub_history[0]["is_le"] else "MUA CHẴN"
            else:
                decision_p = "MUA LẺ" if not sub_history[0]["is_le"] else "MUA CHẴN"
        else:
            sliding_pred = "Le" if prob_le_sliding >= (mean_le + 0.3 * std_le) else "Chan" if prob_chan_sliding >= ((1.0 - mean_le) + 0.3 * std_le) else "None"
            markov_pred = "Le" if pred_le >= 0.51 else "Chan" if (1.0 - pred_le) >= 0.51 else "None"
            if sliding_pred != "None" and sliding_pred == markov_pred:
                is_saturated = (sliding_pred == "Le" and prob_le_sliding >= T_sat_le) or (sliding_pred == "Chan" and prob_chan_sliding >= T_sat_chan)
                if not is_saturated:
                    decision_p = "MUA LẺ" if sliding_pred == "Le" else "MUA CHẴN"
                    
        # Apply Parity Streak Safety Trap
        if decision_p != "BỎ QUA" and active_le_len >= T_streak_parity:
            decision_p = "BỎ QUA"
                    
        # Size
        decision_s = "BỎ QUA"
        if is_size_cooling:
            decision_s = "BỎ QUA"
        elif is_size_win_streak_pause:
            decision_s = "BỎ QUA"
        elif ar_size >= ar_threshold_size:
            if len(sub_history) >= 2:
                if sub_history[0]["is_tai"] != sub_history[1]["is_tai"]:
                    decision_s = "MUA TÀI" if not sub_history[0]["is_tai"] else "MUA XỈU"
                else:
                    decision_s = "MUA TÀI" if sub_history[0]["is_tai"] else "MUA XỈU"
            else:
                decision_s = "MUA TÀI" if not sub_history[0]["is_tai"] else "MUA XỈU"
        else:
            sliding_pred_size = "Tai" if prob_tai_sliding >= (mean_tai + 0.3 * std_tai) else "Xiu" if prob_xiu_sliding >= ((1.0 - mean_tai) + 0.3 * std_tai) else "None"
            markov_pred_size = "Tai" if pred_tai >= 0.51 else "Xiu" if (1.0 - pred_tai) >= 0.51 else "None"
            if sliding_pred_size != "None" and sliding_pred_size == markov_pred_size:
                is_saturated_size = (sliding_pred_size == "Tai" and prob_tai_sliding >= T_sat_tai) or (sliding_pred_size == "Xiu" and prob_xiu_sliding >= T_sat_xiu)
                if not is_saturated_size:
                    decision_s = "MUA TÀI" if sliding_pred_size == "Tai" else "MUA XỈU"
                    
        # Main Trend Filter for Size
        if decision_s == "BỎ QUA" and not is_size_cooling and len(sub_history) >= 6:
            if all(r["is_tai"] for r in sub_history[:6]):
                decision_s = "MUA XỈU"
            elif all(not r["is_tai"] for r in sub_history[:6]):
                decision_s = "MUA TÀI"

        # Apply Size Streak Safety Trap
        if decision_s != "BỎ QUA" and active_tai_len >= T_streak_size:
            decision_s = "BỎ QUA"
                
        # 6. Evaluate
        stat_p = "ignored"
        stat_s = "ignored"
        
        if decision_p != "BỎ QUA":
            total_bets_p += 1
            is_win = (decision_p == "MUA LẺ") == actual_next["is_le"]
            if is_win:
                wins_p += 1
                stat_p = "win"
            else:
                stat_p = "lose"
                
        if decision_s != "BỎ QUA":
            total_bets_s += 1
            is_win_s = (decision_s == "MUA TÀI") == actual_next["is_tai"]
            if is_win_s:
                wins_s += 1
                stat_s = "win"
            else:
                stat_s = "lose"
                
        resolved_history.append({"status_parity": stat_p, "status_size": stat_s})
            
    wr_p = (wins_p / total_bets_p * 100) if total_bets_p > 0 else 0.0
    wr_s = (wins_s / total_bets_s * 100) if total_bets_s > 0 else 0.0
    print("\n==============================================")
    print("BACKTEST RESULTS FOR UPGRADED PARITY ALGORITHM:")
    print(f"  - Total Bets: {total_bets_p}")
    print(f"  - Wins: {wins_p}")
    print(f"  - Win Rate: {wr_p:.1f}%")
    print("\nBACKTEST RESULTS FOR UPGRADED SIZE ALGORITHM:")
    print(f"  - Total Bets: {total_bets_s}")
    print(f"  - Wins: {wins_s}")
    print(f"  - Win Rate: {wr_s:.1f}%")
    print("==============================================")

if __name__ == "__main__":
    run_backtest()
