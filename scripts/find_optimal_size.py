import os
import sys
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_dataset():
    p = r"C:\Users\lyvan\.gemini\antigravity-ide\brain\5f8dd960-f4ce-45be-9e96-cf7ce8740eff\scratch\out_48.json"
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "data" in data and "statisticsInfo" in data["data"]:
            datalist = data["data"]["statisticsInfo"]["total_sum"]["statisticDataList"]
            odd_even = datalist.get("oddEven", [])
            big_small = datalist.get("bigSmall", [])
            draws_map = {}
            for item in odd_even:
                draws_map[item["issue"]] = {"issue": item["issue"], "is_le": item["result"] == "odd"}
            for item in big_small:
                if item["issue"] in draws_map:
                    draws_map[item["issue"]]["is_tai"] = item["result"] == "big"
            formatted = list(draws_map.values())
            formatted.sort(key=lambda x: x["issue"])
            return formatted
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

def simulate(dataset, N_size, markov_thresh, sliding_mult, Z_pct, ar_pct, trend_len):
    total_bets = 0
    wins = 0
    resolved_history = []
    
    for idx in range(40, len(dataset)):
        sub_history = list(reversed(dataset[:idx]))
        actual_next = dataset[idx]
        
        # 1. AR threshold
        ar_size_list = []
        for start_idx in range(min(30, max(1, len(sub_history) - 30))):
            window = sub_history[start_idx : start_idx + 30]
            if len(window) > 1:
                alt_s = sum(1 for k in range(len(window)-1) if window[k]["is_tai"] != window[k+1]["is_tai"])
                ar_size_list.append(alt_s / (len(window)-1))
        ar_threshold_size = max(0.5, get_percentile(ar_size_list, ar_pct))
        
        # Current alternations
        sub_M = min(30, len(sub_history))
        alt_size = 0
        for i in range(sub_M - 1):
            if sub_history[i]["is_tai"] != sub_history[i+1]["is_tai"]:
                alt_size += 1
        ar_size = alt_size / (sub_M - 1) if sub_M > 1 else 0.5
        
        # 2. Sliding window stats
        recent_s = sub_history[:N_size]
        tai_cnt = sum(1 for r in recent_s if r["is_tai"])
        prob_tai_sliding = tai_cnt / N_size if N_size > 0 else 0.5
        prob_xiu_sliding = 1.0 - prob_tai_sliding
        
        # Sliding probabilities history for saturation percentile
        sub_K = min(100, len(sub_history))
        sliding_probs_tai = []
        for k in range(sub_K):
            win_s = sub_history[k : k + N_size]
            if len(win_s) > 0:
                sliding_probs_tai.append(sum(1 for r in win_s if r["is_tai"]) / len(win_s))
                
        mean_tai = sum(sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.5
        var_tai = sum((x - mean_tai)**2 for x in sliding_probs_tai) / len(sliding_probs_tai) if sliding_probs_tai else 0.01
        std_tai = max(0.05, var_tai ** 0.5)
        
        T_sat_tai = get_percentile(sliding_probs_tai, Z_pct)
        T_sat_xiu = get_percentile([1.0 - x for x in sliding_probs_tai], Z_pct)
        
        # 3. Cooling off check (broken on ignored/win)
        size_loss_streak = 0
        for p in reversed(resolved_history):
            if p["status_size"] == "lose":
                size_loss_streak += 1
            elif p["status_size"] == "win" or p["status_size"] == "ignored":
                break
        is_size_cooling = (size_loss_streak >= 2)
        
        # 4. Markov Order 2
        pred_tai = prob_tai_sliding
        if len(sub_history) > 15:
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
                
        # 5. Prediction Decision
        decision_s = "BỎ QUA"
        if is_size_cooling:
            decision_s = "BỎ QUA"
        elif ar_size >= ar_threshold_size:
            decision_s = "MUA TÀI" if not sub_history[0]["is_tai"] else "MUA XỈU"
        else:
            sliding_pred_size = "Tai" if prob_tai_sliding >= (mean_tai + sliding_mult * std_tai) else "Xiu" if prob_xiu_sliding >= ((1.0 - mean_tai) + sliding_mult * std_tai) else "None"
            markov_pred_size = "Tai" if pred_tai >= markov_thresh else "Xiu" if (1.0 - pred_tai) >= markov_thresh else "None"
            
            if sliding_pred_size != "None" and sliding_pred_size == markov_pred_size:
                is_saturated_size = (sliding_pred_size == "Tai" and prob_tai_sliding >= T_sat_tai) or (sliding_pred_size == "Xiu" and prob_xiu_sliding >= T_sat_xiu)
                if not is_saturated_size:
                    decision_s = "MUA TÀI" if sliding_pred_size == "Tai" else "MUA XỈU"
                    
        # Main Trend Filter for Size
        if decision_s == "BỎ QUA" and not is_size_cooling and len(sub_history) >= trend_len:
            if all(r["is_tai"] for r in sub_history[:trend_len]):
                decision_s = "MUA XỈU"
            elif all(not r["is_tai"] for r in sub_history[:trend_len]):
                decision_s = "MUA TÀI"
                
        # 6. Evaluate
        stat_s = "ignored"
        if decision_s != "BỎ QUA":
            total_bets += 1
            is_win_s = (decision_s == "MUA TÀI") == actual_next["is_tai"]
            if is_win_s:
                wins += 1
                stat_s = "win"
            else:
                stat_s = "lose"
        resolved_history.append({"status_size": stat_s})
        
    wr = (wins / total_bets * 100) if total_bets > 0 else 0.0
    return total_bets, wins, wr

def search_all():
    dataset = load_dataset()
    if not dataset:
        print("No dataset loaded.")
        return
        
    print(f"Searching for optimal Size parameters on {len(dataset)} rounds...")
    best_wr = 0.0
    best_params = {}
    
    # Grid search
    for N_size in [15, 20]:
        for markov_thresh in [0.51, 0.52, 0.53, 0.54]:
            for sliding_mult in [0.3, 0.4, 0.5]:
                for Z_pct in [80, 85]:
                    for ar_pct in [70, 75]:
                        for trend_len in [5, 6]:
                            bets, wins, wr = simulate(dataset, N_size, markov_thresh, sliding_mult, Z_pct, ar_pct, trend_len)
                            # We want at least 2 bets to be statistically meaningful on this small 100-round set
                            if bets >= 2 and wr > best_wr:
                                best_wr = wr
                                best_params = {
                                    "N_size": N_size,
                                    "markov_thresh": markov_thresh,
                                    "sliding_mult": sliding_mult,
                                    "Z_pct": Z_pct,
                                    "ar_pct": ar_pct,
                                    "trend_len": trend_len,
                                    "bets": bets,
                                    "wins": wins
                                }
                                
    print("\nBest Size Parameters:")
    for k, v in best_params.items():
        print(f"  - {k}: {v}")
    print(f"  - Best Win Rate: {best_wr:.1f}%")

if __name__ == "__main__":
    search_all()
