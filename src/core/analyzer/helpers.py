import os
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


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

def ema(values, alpha=0.3):
    if not values:
        return 0.5
    ema_val = values[0]
    for v in values[1:]:
        ema_val = alpha * v + (1 - alpha) * ema_val
    return ema_val

def is_ar_confirmed(ar_list, threshold, window=3):
    if len(ar_list) < window:
        return ar_list[-1] >= threshold if ar_list else False
    recent = ar_list[-window:]
    count = sum(1 for v in recent if v >= threshold)
    return count >= 2

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
