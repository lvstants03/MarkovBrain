"""
management.py - Module quản lý vốn DKM Pro Engine và Kelly Strategy.
"""

import math
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

KELLY_HALF_STOPLOSS_DAILY_LIMIT = 3
KELLY_HALF_STOPLOSS_PAUSE_HOURS = 24

KELLY_WIN_RATE_DEFAULT = 0.58
KELLY_WIN_RATE_MIN_SAMPLES = 5
KELLY_PAYOUT = 0.95

INITIAL_PHASE_DAYS = 10
INITIAL_BASE_PCT = 0.02
INITIAL_MAX_STREAK = 3
INITIAL_STOP_LOSS_STREAK = 3

MARTINGALE_BASE_PCT_LOW = 0.015
MARTINGALE_BASE_PCT_MID = 0.03
MARTINGALE_BASE_PCT_HIGH = 0.06
MARTINGALE_BASE_PCT_VERY_HIGH = 0.10

STRATEGY_LABELS = {
    "martingale_x3": "Gap thep x3 (Martingale)",
    "kelly_half_martingale_x3": "Toi uu - Dynamic Kelly & Martingale",
    "dkm_adaptive_pro": "Chuyen Nghiep - Adaptive DKM Pro Engine",
}
ALL_STRATEGIES = list(STRATEGY_LABELS.keys())

def check_time_slot_weight() -> float:
    now_str = time.strftime("%H:%M")
    if "19:30" <= now_str <= "21:00":
        return 0.0
    if ("10:00" <= now_str <= "12:00") or ("15:00" <= now_str <= "16:00"):
        return 1.0
    return 0.5

def compute_kelly_fraction(win_rate: float, payout: float = KELLY_PAYOUT) -> float:
    if win_rate <= 0.0 or payout <= 0.0:
        return 0.0
    f = (win_rate * (payout + 1.0) - 1.0) / payout
    return max(f, 0.0)

def get_effective_win_rate(prediction_stats: Optional[Dict], market_type: str = "size") -> float:
    if not prediction_stats:
        return KELLY_WIN_RATE_DEFAULT
    mkt = prediction_stats.get(market_type, {})
    total = mkt.get("total", 0)
    if total < KELLY_WIN_RATE_MIN_SAMPLES:
        return KELLY_WIN_RATE_DEFAULT
    wr = mkt.get("win_rate", KELLY_WIN_RATE_DEFAULT)
    return max(min(float(wr), 0.95), 0.01)

class MoneyManager:
    @staticmethod
    def get_combined_multiplier(confidence: float, win_rate: float) -> float:
        if confidence >= 70.0 and win_rate >= 0.62:
            if confidence >= 90.0:
                return 1.40
            elif confidence >= 80.0:
                return 1.35
            else:
                return 1.30
        else:
            return 1.0

    @staticmethod
    def calculate_bet(
        strategy: str,
        base_amount: float,
        current_balance: float,
        loss_streak: int,
        daily_loss_count: int,
        pause_until: Optional[float],
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
        is_stable: bool = True,
        is_initial_phase: bool = False,
        initial_phase_remaining: int = 0,
        is_combined: bool = False,
        market_type: str = "parity",
        confidence: float = 0.0,
    ) -> float:
        if current_balance <= 0:
            return 0.0

        if strategy == "dkm_adaptive_pro":
            from src.config import config
            min_bal = getattr(config, "DKM_MIN_BALANCE", 500000.0)
            if current_balance < min_bal:
                logger.debug(f"[dkm_adaptive_pro] So du {current_balance:,.0f} < muc toi thieu {min_bal:,.0f}. Bo qua.")
                return 0.0

            # TODO: Bat lai khi co du du lieu Bao Cao Suc Khoe Thi Truong (>=30 ky ~1 thang)
            # time_weight = check_time_slot_weight()
            # if time_weight <= 0.0:
            #     logger.debug("[dkm_adaptive_pro] Khung gio den (19:30-21:00). Bo qua cuoc.")
            #     return 0.0
            time_weight = 1.0  # Tam thoi luon cho cuoc, chua dua vao gio

            if win_rate < 0.50 and loss_streak >= 1:
                logger.debug(f"[dkm_adaptive_pro] WR {win_rate*100:.1f}% < 50% va thua {loss_streak} ky. Ngat cuoc de bao ve von.")
                return 0.0
            elif win_rate < 0.60 and loss_streak >= 2:
                logger.debug(f"[dkm_adaptive_pro] WR {win_rate*100:.1f}% < 60% va thua {loss_streak} ky. Cooling-off 1-2 ky.")
                return 0.0

            p = (confidence / 100.0) if confidence > 0 else win_rate
            f0 = compute_kelly_fraction(p, KELLY_PAYOUT)
            if f0 <= 0:
                f0 = 0.015

            max_steps = getattr(config, "DKM_MAX_MARTINGALE_STEPS", 3)
            if loss_streak >= max_steps:
                martingale_boost = 1.0
            else:
                martingale_boost = 1.0 + min(loss_streak * 0.5, 1.0)

            dkm_fraction = getattr(config, "DKM_KELLY_FRACTION", 0.25)
            final_fraction = min(f0 * dkm_fraction * time_weight * martingale_boost, 0.15)
            amount = current_balance * final_fraction
            return max(math.floor(amount / 1000) * 1000, 1000.0)

        if strategy == "martingale_x3":
            bet = base_amount * (3 ** loss_streak)
            return bet

        if strategy == "kelly_half_martingale_x3":
            if pause_until is not None and time.time() < pause_until:
                logger.debug(f"[kelly_half_martingale_x3] Tam dung. Con {(pause_until - time.time()) / 3600:.1f}h")
                return 0.0

            if is_initial_phase and initial_phase_remaining > 0:
                base_bet = current_balance * INITIAL_BASE_PCT
                base_bet = max(math.floor(base_bet / 1000) * 1000, 1000.0)

                if loss_streak >= INITIAL_STOP_LOSS_STREAK:
                    bet = base_bet
                else:
                    multiplier = 3 ** min(loss_streak, INITIAL_MAX_STREAK)
                    bet = base_bet * multiplier
                    max_bet = current_balance * 0.30
                    if bet > max_bet:
                        bet = max_bet

                if is_combined and bet > 0:
                    multiplier_comb = MoneyManager.get_combined_multiplier(confidence, win_rate)
                    bet = bet * multiplier_comb
                    if bet > 1000000.0:
                        bet = 1000000.0
                max_allowed = current_balance * 0.25
                if bet > max_allowed:
                    bet = max_allowed
                return max(math.floor(bet / 1000) * 1000, 1000.0)

            if not is_stable:
                logger.info("[kelly_half_martingale_x3] Thi truong hon loan (WR 30 ky < 45%). Tam dung.")
                return 0.0

            enable_martingale = False
            martingale_cap = 0
            base_pct = 0.0

            if win_rate >= 0.70:
                k_full = compute_kelly_fraction(win_rate)
                base_pct = min(k_full / 3.0, 0.05)
                enable_martingale = True
                martingale_cap = 3
            elif win_rate >= 0.60:
                k_full = compute_kelly_fraction(win_rate)
                base_pct = min(k_full / 2.0, 0.10)
                enable_martingale = False
                martingale_cap = 0
            elif win_rate >= 0.55:
                k_full = compute_kelly_fraction(win_rate)
                base_pct = min(k_full / 3.0, 0.06)
                enable_martingale = True
                martingale_cap = 2
            elif win_rate >= 0.50:
                base_pct = 0.03
                enable_martingale = False
                martingale_cap = 0
            else:
                base_pct = MARTINGALE_BASE_PCT_LOW
                enable_martingale = False
                martingale_cap = 0

            base_bet = current_balance * base_pct
            base_bet = max(math.floor(base_bet / 1000) * 1000, 1000.0)

            if enable_martingale and martingale_cap > 0:
                multiplier = 2 ** min(loss_streak, martingale_cap)
                bet = base_bet * multiplier
                max_bet = current_balance * 0.20
                if bet > max_bet:
                    bet = max_bet
                logger.debug(f"[Martingale] WR={win_rate:.1%}, streak={loss_streak}, cap={martingale_cap}, bet={bet:,.0f}")
            else:
                bet = base_bet

            if is_combined and bet > 0:
                multiplier_comb = MoneyManager.get_combined_multiplier(confidence, win_rate)
                bet = bet * multiplier_comb
                if confidence >= 70.0 and win_rate >= 0.62:
                    logger.debug(f"[Combined Advanced] Tang {int(round((multiplier_comb-1)*100))}% (Confidence={confidence}%, WR={win_rate*100:.1f}%), bet={bet:,.0f}")
                else:
                    logger.debug(f"[Combined Fallback] Tang {int((multiplier_comb-1)*100)}% do dong thuan (WR={win_rate*100:.1f}%), bet={bet:,.0f}")

                if bet > 1000000.0:
                    bet = 1000000.0
                    logger.debug(f"[Combined Max Bet Limit] Gioi han bet xuong 1,000,000 VND")

            if loss_streak >= 3:
                bet = bet * 0.3
                logger.debug(f"[Loss Streak] Giam 70% cược do thua {loss_streak} lien tiep, bet={bet:,.0f}")
            elif loss_streak >= 2:
                bet = bet * 0.6
                logger.debug(f"[Loss Streak] Giam 40% cược do thua {loss_streak} lien tiep, bet={bet:,.0f}")

            if market_type == "size":
                max_allowed_pct = 0.06
            else:
                max_allowed_pct = 0.10

            max_allowed = current_balance * max_allowed_pct
            if bet > max_allowed:
                bet = max_allowed
                logger.debug(f"[Max Bet] Gioi han {max_allowed_pct*100:.0f}% von, bet={bet:,.0f}")

            return max(math.floor(bet / 1000) * 1000, 1000.0)

        logger.warning(f"[MoneyManager] Strategy khong xac dinh: {strategy}, fallback ve fixed")
        return max(math.floor(base_amount / 1000) * 1000, 1000.0)

    @staticmethod
    def should_trigger_pause(
        strategy: str,
        daily_loss_count: int,
        pause_until: Optional[float],
    ) -> bool:
        if strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"):
            return False
        if pause_until is not None and time.time() < pause_until:
            return True
        return False

    @staticmethod
    def new_pause_until() -> float:
        return time.time() + KELLY_HALF_STOPLOSS_PAUSE_HOURS * 3600

    @staticmethod
    def get_max_streak_tolerated(
        strategy: str,
        current_balance: float,
        base_amount: float,
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
        is_initial_phase: bool = False,
    ) -> int:
        if current_balance <= 0 or base_amount <= 0:
            return 0

        if strategy == "fixed":
            return int(current_balance // base_amount)

        if strategy == "martingale_x3":
            ratio = (2.0 * current_balance) / base_amount + 1.0
            if ratio > 0:
                return int(math.floor(math.log(ratio, 3.0)))
            return 0

        if strategy in ("fixed_fractional_3", "kelly_third", "kelly_half_stoploss", "kelly_half_martingale_x3"):
            if strategy == "fixed_fractional_3":
                loss_rate = 0.03
            elif strategy == "kelly_third":
                k = compute_kelly_fraction(win_rate) / 3.0
                loss_rate = min(k, 0.10)
            elif strategy == "kelly_half_stoploss":
                k = compute_kelly_fraction(win_rate) / 2.0
                loss_rate = min(k, 0.12)
            else:
                loss_rate = 0.015
                bal = current_balance
                count = 0
                while bal >= 1000 and count < 100:
                    bet = bal * loss_rate
                    bet = max(math.floor(bet / 1000) * 1000, 1000.0)
                    if bet > bal:
                        break
                    bal -= bet
                    count += 1
                return count

            if loss_rate <= 0 or current_balance <= 1000:
                return 9999
            n = math.log(1000.0 / current_balance) / math.log(1.0 - loss_rate)
            return max(int(math.floor(n)), 0)

        return int(current_balance // base_amount)

    @staticmethod
    def get_recommended_base(
        strategy: str,
        balance: float,
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
        is_initial_phase: bool = False,
        initial_phase_remaining: int = 0,
    ) -> Dict[str, Any]:
        if strategy == "dkm_adaptive_pro":
            k_full = compute_kelly_fraction(win_rate)
            safe = int(balance * min(k_full * 0.25, 0.08) / 1000) * 1000
            return {"recommended": max(safe, 10000), "note": f"DKM Pro: Kelly dong 25% ({win_rate*100:.1f}% WR) + Gap x2 + Cooling-off 2 chieu"}

        if strategy == "fixed_fractional_3":
            safe = int(balance * 0.03 / 1000) * 1000
            return {"recommended": safe, "note": "3% von hien tai (co dinh theo % - base_amount it anh huong)"}

        if strategy == "kelly_third":
            k_full = compute_kelly_fraction(win_rate)
            k_third = min(k_full / 3.0, 0.10)
            safe = int(balance * k_third / 1000) * 1000
            return {"recommended": safe, "note": f"1/3 Kelly ({k_third*100:.1f}% von) dua tren WR {win_rate*100:.1f}%"}

        if strategy == "kelly_half_stoploss":
            k_full = compute_kelly_fraction(win_rate)
            k_half = min(k_full / 2.0, 0.12)
            safe = int(balance * k_half / 1000) * 1000
            return {"recommended": safe, "note": f"1/2 Kelly ({k_half*100:.1f}% von) + Stop-loss {KELLY_HALF_STOPLOSS_DAILY_LIMIT} thua/24h"}

        if strategy == "kelly_half_martingale_x3":
            if is_initial_phase and initial_phase_remaining > 0:
                safe = int(balance * INITIAL_BASE_PCT / 1000) * 1000
                note = f"Khoi tao: {INITIAL_BASE_PCT*100:.1f}% von, gap x3 (toi da {INITIAL_MAX_STREAK} lan), con {initial_phase_remaining} ky"
                return {"recommended": safe, "note": note}
            else:
                if win_rate >= 0.60:
                    k_full = compute_kelly_fraction(win_rate)
                    k_half = min(k_full / 2.0, 0.10)
                    safe = int(balance * k_half / 1000) * 1000
                    note = f"Active Kelly ({k_half*100:.1f}% von) dua tren WR trượt {win_rate*100:.1f}% >= 60%"
                elif win_rate >= 0.55:
                    k_full = compute_kelly_fraction(win_rate)
                    k_third = min(k_full / 3.0, 0.06)
                    safe = int(balance * k_third / 1000) * 1000
                    note = f"Moderate Kelly ({k_third*100:.1f}% von) + Gap x2 (toi da 2 lan) dua tren WR trượt {win_rate*100:.1f}%"
                elif win_rate >= 0.50:
                    safe = int(balance * 0.03 / 1000) * 1000
                    note = f"Passive Kelly (3.0% von) dua tren WR trượt {win_rate*100:.1f}%"
                else:
                    safe = int(balance * MARTINGALE_BASE_PCT_LOW / 1000) * 1000
                    note = f"Bao toan ({MARTINGALE_BASE_PCT_LOW*100:.1f}% von, KHONG GAP) dua tren WR trượt {win_rate*100:.1f}% < 50%"
                return {"recommended": safe, "note": note}

        if strategy == "martingale_x3":
            result = {}
            for k in [3, 4, 5]:
                base = int(balance * 2 / (3**k - 1) / 1000) * 1000
                result[f"k{k}"] = base
            result["note"] = "Chiu k lan thua lien tiep voi Martingale x3"
            return result

        safe = int(balance * 0.01 / 1000) * 1000
        return {"recommended": safe, "note": "Goi y 1% von cho strategy Fixed"}

    @staticmethod
    def get_risk_info(
        strategy: str,
        current_balance: float,
        base_amount: float,
        win_rate: float,
        loss_streak: int,
        daily_loss_count: int,
        pause_until: Optional[float],
        is_stable: bool = True,
        is_initial_phase: bool = False,
        initial_phase_remaining: int = 0,
        is_combined: bool = False,
        market_type: str = "parity",
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        next_bet = MoneyManager.calculate_bet(
            strategy=strategy,
            base_amount=base_amount,
            current_balance=current_balance,
            loss_streak=loss_streak,
            daily_loss_count=daily_loss_count,
            pause_until=pause_until,
            win_rate=win_rate,
            is_stable=is_stable,
            is_initial_phase=is_initial_phase,
            initial_phase_remaining=initial_phase_remaining,
            is_combined=is_combined,
            market_type=market_type,
            confidence=confidence,
        )

        pct_of_balance = (next_bet / current_balance * 100) if current_balance > 0 else 0.0
        max_streak = MoneyManager.get_max_streak_tolerated(
            strategy, current_balance, base_amount, win_rate, is_initial_phase
        )

        is_paused = MoneyManager.should_trigger_pause(strategy, daily_loss_count, pause_until)
        pause_remaining_hours = 0.0
        if pause_until and time.time() < pause_until:
            pause_remaining_hours = round((pause_until - time.time()) / 3600, 2)

        ev_per_bet = win_rate * KELLY_PAYOUT - (1.0 - win_rate)

        expected_balance_100 = current_balance
        if next_bet > 0 and current_balance > 0:
            win_factor = 1.0 + (next_bet * KELLY_PAYOUT / current_balance)
            lose_factor = 1.0 - (next_bet / current_balance)
            w_rounds = round(win_rate * 100)
            l_rounds = 100 - w_rounds
            try:
                expected_balance_100 = current_balance * (win_factor ** w_rounds) * (lose_factor ** l_rounds)
            except Exception:
                expected_balance_100 = current_balance

        return {
            "strategy": strategy,
            "strategy_label": STRATEGY_LABELS.get(strategy, strategy),
            "next_bet": next_bet,
            "pct_of_balance": round(pct_of_balance, 2),
            "max_streak_tolerated": max_streak,
            "is_paused": is_paused,
            "pause_remaining_hours": pause_remaining_hours,
            "daily_loss_count": daily_loss_count,
            "daily_loss_limit": KELLY_HALF_STOPLOSS_DAILY_LIMIT if strategy == "kelly_half_stoploss" else None,
            "win_rate_used": round(win_rate, 4),
            "ev_per_bet": round(ev_per_bet, 4),
            "expected_balance_after_100": round(expected_balance_100, 0),
            "expected_growth_pct_100": round((expected_balance_100 / current_balance - 1.0) * 100, 1) if current_balance > 0 else 0.0,
            "loss_streak": loss_streak,
            "is_initial_phase": is_initial_phase,
            "initial_phase_remaining": initial_phase_remaining,
        }

def get_all_strategies_info(balance: float, win_rate: float = KELLY_WIN_RATE_DEFAULT) -> Dict[str, Dict]:
    result = {}
    for strat in ALL_STRATEGIES:
        base_rec = MoneyManager.get_recommended_base(strat, balance, win_rate)
        result[strat] = {
            "label": STRATEGY_LABELS.get(strat, strat),
            "recommended_base": base_rec,
        }
    return result
