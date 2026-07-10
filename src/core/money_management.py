"""
money_management.py
Module quan ly von doc lap cho he thong du doan.
Cung cap cac phuong an: fixed, martingale_x3, fixed_fractional_3, kelly_third, kelly_half_stoploss.
"""

import math
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Hang so ---
KELLY_WIN_RATE_DEFAULT = 0.58      # Win rate mac dinh neu chua du du lieu
KELLY_WIN_RATE_MIN_SAMPLES = 5   # So mau toi thieu de tinh WR thuc te
KELLY_PAYOUT = 0.95               # He so lai khi thang (tinh theo 1.95x tren cuoc)
KELLY_HALF_STOPLOSS_DAILY_LIMIT = 3  # Gioi han so ky thua/ngay (PA3)
KELLY_HALF_STOPLOSS_PAUSE_HOURS = 24 # So gio tam dung sau khi cham gioi han (PA3)

STRATEGY_LABELS = {
    "fixed": "Co dinh (Fixed)",
    "martingale_x3": "Martingale x3",
    "fixed_fractional_3": "Bao toan - Fixed Fractional 3%",
    "kelly_third": "Can bang - Kelly 1/3 (~5.3%)",
    "kelly_half_stoploss": "Tang toc - Kelly 1/2 + Stop-loss (8%)",
    "kelly_half_martingale_x3": "Tối ưu - Dynamic Kelly & Martingale",
}

ALL_STRATEGIES = list(STRATEGY_LABELS.keys())


def compute_kelly_fraction(win_rate: float, payout: float = KELLY_PAYOUT) -> float:
    """
    Tinh Kelly fraction day du.
    f* = (p * (b+1) - 1) / b
    Trong do: p = win_rate, b = payout (net odds, vd 0.95)
    """
    f = (win_rate * (payout + 1.0) - 1.0) / payout
    return max(f, 0.0)


def get_effective_win_rate(prediction_stats: Optional[dict], market_type: str = "size") -> float:
    """
    Lay win rate thuc te tu du lieu lich su.
    Neu chua du KELLY_WIN_RATE_MIN_SAMPLES mau -> dung gia tri mac dinh.

    Args:
        prediction_stats: dict tu store.get_prediction_stats(), co the None
        market_type: "parity" hoac "size"
    """
    if not prediction_stats:
        return KELLY_WIN_RATE_DEFAULT
    mkt = prediction_stats.get(market_type, {})
    total = mkt.get("total", 0)
    if total < KELLY_WIN_RATE_MIN_SAMPLES:
        return KELLY_WIN_RATE_DEFAULT
    wr = mkt.get("win_rate", KELLY_WIN_RATE_DEFAULT)
    return max(min(float(wr), 0.95), 0.01)   # Cap [1%, 95%]


class MoneyManager:
    """
    Tinh toan so tien dat cuoc cho moi strategy.
    Khong co trang thai (stateless) — moi call truyen du thong so vao.
    """

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
    ) -> float:
        """
        Tra ve so tien dat cuoc cuoi cung (VND).
        Tra ve 0.0 neu khong duoc phep dat (bi tam dung, het von...).

        Args:
            strategy: ten strategy
            base_amount: muc cuoc goc do nguoi dung cai dat
            current_balance: so du hien tai
            loss_streak: chuoi thua lien tiep hien tai (cho thi truong nay)
            daily_loss_count: so ky da thua trong 24h (cho thi truong nay, chi PA3)
            pause_until: timestamp het thoi gian tam dung (chi PA3), None = khong bi dung
            win_rate: win rate thuc te [0,1]
            is_stable: thi truong co dang on dinh khong (WR 30 ky >= 53%)
        """
        if current_balance <= 0:
            return 0.0

        if strategy == "fixed":
            return base_amount

        if strategy == "martingale_x3":
            return base_amount * (3 ** loss_streak)

        if strategy == "fixed_fractional_3":
            # 3% von hien tai, lam tron xuong 1000
            amount = current_balance * 0.03
            return max(math.floor(amount / 1000) * 1000, 1000.0)

        if strategy == "kelly_third":
            # 1/3 Kelly dua tren win rate thuc te
            k_full = compute_kelly_fraction(win_rate)
            k_third = k_full / 3.0
            # Clamp: toi da 10% von, toi thieu 1000 VND
            fraction = min(k_third, 0.10)
            amount = current_balance * fraction
            return max(math.floor(amount / 1000) * 1000, 1000.0)

        if strategy == "kelly_half_stoploss":
            # Kiem tra tam dung
            if pause_until is not None and time.time() < pause_until:
                logger.info(f"[kelly_half_stoploss] Dang tam dung. Con {(pause_until - time.time()) / 3600:.1f}h")
                return 0.0
            # 1/2 Kelly
            k_full = compute_kelly_fraction(win_rate)
            k_half = k_full / 2.0
            fraction = min(k_half, 0.12)
            amount = current_balance * fraction
            return max(math.floor(amount / 1000) * 1000, 1000.0)

        if strategy == "kelly_half_martingale_x3":
            # 1. Kiem tra suc khoe thi truong (30 ky)
            # Neu thi truong hon loan, tam dung dat cuoc (tra ve 0.0) de bao ve von
            if not is_stable:
                logger.info("[kelly_half_martingale_x3] Thi truong hon loan (WR 30 ky < 53%). Tam dung dat cuoc.")
                return 0.0
                
            # 2. Quyet dinh fraction dua tren Sliding Win Rate (15 ky)
            if win_rate >= 0.60:
                # Kelly chu dong: 1/2 Kelly, max 10%
                k_full = compute_kelly_fraction(win_rate)
                fraction = min(k_full / 2.0, 0.10)
            elif win_rate >= 0.55:
                # Kelly vua phai: 1/3 Kelly, max 6%
                k_full = compute_kelly_fraction(win_rate)
                fraction = min(k_full / 3.0, 0.06)
            elif win_rate >= 0.50:
                # Binh thuong: Phai bao toan, 3% von
                fraction = 0.03
            else:
                # Bao thu: 1.5% von + Gap thep x3, gioi han max streak = 3
                fraction = 0.015
                
            base_bet = current_balance * fraction
            base_bet = max(base_bet, 1000.0)
            
            # Giao thuc gap thep gioi han (chi ap dung cho phan vung WR < 50%)
            if win_rate < 0.50:
                multiplier = 3 ** min(loss_streak, 3)
                amount = base_bet * multiplier
            else:
                amount = base_bet
                
            return max(math.floor(amount / 1000) * 1000, 1000.0)

        # Fallback ve fixed
        logger.warning(f"[MoneyManager] Strategy khong xac dinh: {strategy}, fallback ve fixed")
        return base_amount

    @staticmethod
    def should_trigger_pause(
        strategy: str,
        daily_loss_count: int,
        pause_until: Optional[float],
    ) -> bool:
        """
        Kiem tra xem strategy co dang bi tam dung khong.
        """
        if strategy != "kelly_half_stoploss":
            return False
        if pause_until is not None and time.time() < pause_until:
            return True
        return False

    @staticmethod
    def new_pause_until() -> float:
        """Tinh timestamp het tam dung (hien tai + 24h)."""
        return time.time() + KELLY_HALF_STOPLOSS_PAUSE_HOURS * 3600

    @staticmethod
    def get_max_streak_tolerated(
        strategy: str,
        current_balance: float,
        base_amount: float,
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
    ) -> int:
        """
        Uoc tinh so ky thua toi da co the chiu truoc khi khong du tien cuoc.
        Chi mang tinh tham khao.
        """
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
                # Voi kelly_half_martingale_x3, tinh uoc tinh thua theo cac kieu phan bo WR
                # De an toan, ta gia lap chuoi thua lien tiep
                if current_balance <= 1000:
                    return 0
                bal = current_balance
                streak = 0
                losses = 0
                while bal >= 1000 and losses < 100:
                    frac = 0.015
                    if win_rate >= 0.60:
                        frac = min(compute_kelly_fraction(win_rate) / 2.0, 0.10)
                    elif win_rate >= 0.55:
                        frac = min(compute_kelly_fraction(win_rate) / 3.0, 0.06)
                    elif win_rate >= 0.50:
                        frac = 0.03
                    bet = bal * frac
                    bet = max(math.floor(bet / 1000) * 1000, 1000.0)
                    # neu < 50% co gap thep
                    if win_rate < 0.50:
                        mult = 3 ** min(streak, 3)
                        bet_final = bet * mult
                    else:
                        bet_final = bet
                    if bet_final > bal:
                        break
                    bal -= bet_final
                    losses += 1
                    streak += 1
                    if streak > 3:
                        streak = 0
                return losses

            if loss_rate <= 0:
                return 9999
            # (1 - loss_rate)^n * balance >= 1000
            # n <= log(1000/balance) / log(1 - loss_rate)
            if current_balance <= 1000:
                return 0
            n = math.log(1000.0 / current_balance) / math.log(1.0 - loss_rate)
            return max(int(math.floor(n)), 0)

        return int(current_balance // base_amount)

    @staticmethod
    def get_recommended_base(
        strategy: str,
        balance: float,
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
    ) -> dict:
        """
        Goi y muc cuoc co so (base_amount) phu hop voi moi strategy va so du.
        Ket qua tra ve de hien thi trong UI.
        """
        if balance <= 0:
            return {}

        if strategy == "fixed_fractional_3":
            safe = int(balance * 0.03 / 1000) * 1000
            return {
                "recommended": safe,
                "note": "3% von hien tai (co dinh theo % - base_amount it anh huong)"
            }

        if strategy == "kelly_third":
            k_full = compute_kelly_fraction(win_rate)
            k_third = min(k_full / 3.0, 0.10)
            safe = int(balance * k_third / 1000) * 1000
            return {
                "recommended": safe,
                "note": f"1/3 Kelly ({k_third*100:.1f}% von) dua tren WR {win_rate*100:.1f}%"
            }

        if strategy == "kelly_half_stoploss":
            k_full = compute_kelly_fraction(win_rate)
            k_half = min(k_full / 2.0, 0.12)
            safe = int(balance * k_half / 1000) * 1000
            return {
                "recommended": safe,
                "note": f"1/2 Kelly ({k_half*100:.1f}% von) + Stop-loss {KELLY_HALF_STOPLOSS_DAILY_LIMIT} thua/24h"
            }

        if strategy == "kelly_half_martingale_x3":
            k_full = compute_kelly_fraction(win_rate)
            if win_rate >= 0.60:
                k_half = min(k_full / 2.0, 0.10)
                safe = int(balance * k_half / 1000) * 1000
                note = f"Active Kelly ({k_half*100:.1f}% von) dua tren WR trượt {win_rate*100:.1f}% >= 60%"
            elif win_rate >= 0.55:
                k_third = min(k_full / 3.0, 0.06)
                safe = int(balance * k_third / 1000) * 1000
                note = f"Moderate Kelly ({k_third*100:.1f}% von) dua tren WR trượt {win_rate*100:.1f}%"
            elif win_rate >= 0.50:
                safe = int(balance * 0.03 / 1000) * 1000
                note = f"Passive Kelly (3.0% von) dua tren WR trượt {win_rate*100:.1f}%"
            else:
                safe = int(balance * 0.015 / 1000) * 1000
                note = f"Bao thu (1.5% von) + Gấp x3 (max 3x) dua tren WR trượt {win_rate*100:.1f}% < 50%"
            return {
                "recommended": safe,
                "note": note
            }

        if strategy == "martingale_x3":
            return {
                "k3": int(balance * 2 / (3**3 - 1)),
                "k4": int(balance * 2 / (3**4 - 1)),
                "k5": int(balance * 2 / (3**5 - 1)),
                "note": "Chiu k lan thua voi martingale x3"
            }

        # fixed
        return {
            "recommended": int(balance * 0.01 / 1000) * 1000,
            "note": "Goi y 1% von cho strategy Fixed"
        }

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
    ) -> dict:
        """
        Tra ve day du thong tin rui ro de hien thi trong Frontend panel.
        """
        next_bet = MoneyManager.calculate_bet(
            strategy=strategy,
            base_amount=base_amount,
            current_balance=current_balance,
            loss_streak=loss_streak,
            daily_loss_count=daily_loss_count,
            pause_until=pause_until,
            win_rate=win_rate,
            is_stable=is_stable,
        )

        pct_of_balance = (next_bet / current_balance * 100) if current_balance > 0 else 0.0
        max_streak = MoneyManager.get_max_streak_tolerated(
            strategy, current_balance, base_amount, win_rate
        )

        is_paused = MoneyManager.should_trigger_pause(strategy, daily_loss_count, pause_until)
        pause_remaining_hours = 0.0
        if pause_until and time.time() < pause_until:
            pause_remaining_hours = round((pause_until - time.time()) / 3600, 2)

        # Expected growth/loss per bet (EV)
        # EV = win_rate * payout - (1 - win_rate)
        ev_per_bet = win_rate * KELLY_PAYOUT - (1.0 - win_rate)

        # Uoc tinh sau 100 ky (ly thuyet)
        expected_balance_100 = current_balance
        if next_bet > 0 and current_balance > 0:
            win_factor = 1.0 + (next_bet * KELLY_PAYOUT / current_balance)
            lose_factor = 1.0 - (next_bet / current_balance)
            # (1+w)^58 * (1-l)^42 cho 100 ky voi WR=58%
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
            "daily_loss_limit": None,
            "win_rate_used": round(win_rate, 4),
            "ev_per_bet": round(ev_per_bet, 4),
            "expected_balance_after_100": round(expected_balance_100, 0),
            "expected_growth_pct_100": round((expected_balance_100 / current_balance - 1.0) * 100, 1) if current_balance > 0 else 0.0,
            "loss_streak": loss_streak,
        }
