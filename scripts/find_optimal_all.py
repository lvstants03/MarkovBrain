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

def simulate_parity(dataset, N_parity, markov_thresh, sliding_mult, Z_pct, ar_pct):
    total_bets = 0
    wins = 0
    resolved_history = []
    
    for idx in range(40, len(dataset)):
        sub_history = list(reversed(dataset[:idx]))
        actual_next = dataset[idx]
        
        # 1. AR threshold
        ar_parity_list = []
        for start_idx in range(min(30, max(1, len(sub_history) - 30))):
            window = sub_history[start_idx : start_idx + 30]
            if len(window) > 1:
                alt_p = sum(1 for k in range(len(window)-1) if window[k]["is_le"] != window[k+1]["is_le"])
                ar_parity_list.append(alt_p / (len(window)-1))
        ar_threshold_parity = max(0.5, get_percentile(ar_parity_list, ar_pct))
        
        # Current alternations
        sub_M = min(30, len(sub_history))
        alt_parity = 0
        for i in range(sub_M - 1):
            if sub_history[i]["is_le"] != sub_history[i+1]["is_le"]:
                alt_parity += 1
        ar_parity = alt_parity / (sub_M - 1) if sub_M > 1 else 0.5
        
        # 2. Sliding window stats
        recent_p = sub_history[:N_parity]
        le_cnt = sum(1 for r in recent_p if r["is_le"])
        prob_le_sliding = le_cnt / N_parity if N_parity > 0 else 0.5
        prob_chan_sliding = 1.0 - prob_le_sliding
        
        # Sliding probabilities history for saturation percentile
        sub_K = min(100, len(sub_history))
        sliding_probs_le = []
        for k in range(sub_K):
            win_p = sub_history[k : k + N_parity]
            if len(win_p) > 0:
                sliding_probs_le.append(sum(1 for r in win_p if r["is_le"]) / len(win_p))
                
        mean_le = sum(sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.5
        var_le = sum((x - mean_le)**2 for x in sliding_probs_le) / len(sliding_probs_le) if sliding_probs_le else 0.01
        std_le = max(0.05, var_le ** 0.5)
        
        T_sat_le = get_percentile(sliding_probs_le, Z_pct)
        T_sat_chan = get_percentile([1.0 - x for x in sliding_probs_le], Z_pct)
        
        # 3. Cooling off check (broken on ignored/win)
        parity_loss_streak = 0
        for p in reversed(resolved_history):
            if p["status_parity"] == "lose":
                parity_loss_streak += 1
            elif p["status_parity"] == "win" or p["status_parity"] == "ignored":
                break
        is_parity_cooling = (parity_loss_streak >= 2)
        
        # 4. Markov Order 2
        pred_le = prob_le_sliding
        if len(sub_history) > 15:
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
                
        # 5. Prediction Decision
        decision_p = "BỎ QUA"
        if is_parity_cooling:
            decision_p = "BỎ QUA"
        elif ar_parity >= ar_threshold_parity:
            decision_p = "MUA LẺ" if not sub_history[0]["is_le"] else "MUA CHẴN"
        else:
            sliding_pred = "Le" if prob_le_sliding >= (mean_le + sliding_mult * std_le) else "Chan" if prob_chan_sliding >= ((1.0 - mean_le) + sliding_mult * std_le) else "None"
            markov_pred = "Le" if pred_le >= markov_thresh else "Chan" if (1.0 - pred_le) >= markov_thresh else "None"
            
            if sliding_pred != "None" and sliding_pred == markov_pred:
                is_saturated = (sliding_pred == "Le" and prob_le_sliding >= T_sat_le) or (sliding_pred == "Chan" and prob_chan_sliding >= T_sat_chan)
                if not is_saturated:
                    decision_p = "MUA LẺ" if sliding_pred == "Le" else "MUA CHẴN"
                    
        # 6. Evaluate
        stat_p = "ignored"
        if decision_p != "BỎ QUA":
            total_bets += 1
            is_win = (decision_p == "MUA LẺ") == actual_next["is_le"]
            if is_win:
                wins += 1
                stat_p = "win"
            else:
                stat_p = "lose"
        resolved_history.append({"status_parity": stat_p})
        
    wr = (wins / total_bets * 100) if total_bets > 0 else 0.0
    return total_bets, wins, wr

def search_all():
    dataset = load_dataset()
    if not dataset:
        print("No dataset loaded.")
        return
        
    print(f"Searching for optimal Parity parameters (with fixed cooling-off)...")
    best_wr = 0.0
    best_params = {}
    
    # Grid search for Parity
    for N_parity in [15, 20]:
        for markov_thresh in [0.51, 0.52, 0.53, 0.54]:
            for sliding_mult in [0.3, 0.4, 0.5]:
                for Z_pct in [80, 85]:
                    for ar_pct in [70, 75]:
                        bets, wins, wr = simulate_parity(dataset, N_parity, markov_thresh, sliding_mult, Z_pct, ar_pct)
                        if bets >= 5 and wr > best_wr:
                            best_wr = wr
                            best_params = {
                                "N_parity": N_parity,
                                "markov_thresh": markov_thresh,
                                "sliding_mult": sliding_mult,
                                "Z_pct": Z_pct,
                                "ar_pct": ar_pct,
                                "bets": bets,
                                "wins": wins
                            }
                                
    print("\nBest Parity Parameters (with fixed cooling-off):")
    for k, v in best_params.items():
        print(f"  - {k}: {v}")
    print(f"  - Best Win Rate: {best_wr:.1f}%")

if __name__ == "__main__":
    search_all()
