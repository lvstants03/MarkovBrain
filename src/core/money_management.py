"""
money_management.py
Module quan ly von doc lap cho he thong du doan.
Cung cap cac phuong an: fixed, martingale_x3, fixed_fractional_3, kelly_third, kelly_half_stoploss,
va strategy toi uu: kelly_half_martingale_x3 (co tich hop giai doan khoi tao).
"""

import math
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# -------------------- HANG SO EXPORT --------------------
# Các hằng số này được sử dụng bởi module khác (store.py)
KELLY_HALF_STOPLOSS_DAILY_LIMIT = 3       # so ky thua toi da trong 24h (PA3)
KELLY_HALF_STOPLOSS_PAUSE_HOURS = 24      # so gio tam dung sau khi cham gioi han

# -------------------- HANG SO NOI BO --------------------
KELLY_WIN_RATE_DEFAULT = 0.58             # Win rate mac dinh neu chua du du lieu
KELLY_WIN_RATE_MIN_SAMPLES = 5            # So mau toi thieu de tinh WR thuc te
KELLY_PAYOUT = 0.95                       # He so lai khi thang (tinh theo 1.95x tren cuoc)

# Cau hinh giai doan khoi tao (Initial Phase)
INITIAL_PHASE_DAYS = 10                   # So ky/luot dau tien su dung Martingale x3
INITIAL_BASE_PCT = 0.02                   # 2% von cho base cua giai doan nay
INITIAL_MAX_STREAK = 3                    # So lan gap thep toi da (0 = khong gap, 3 = x3 den x27)
INITIAL_STOP_LOSS_STREAK = 3              # Neu thua lien tiep >= so nay thi dung gap, quay ve base

# Cau hinh cho strategy kelly_half_martingale_x3
MARTINGALE_BASE_PCT_LOW = 0.015           # 1.5% von khi WR < 50%
MARTINGALE_BASE_PCT_MID = 0.03            # 3% von khi WR 50-55%
MARTINGALE_BASE_PCT_HIGH = 0.06           # 6% von khi WR 55-60% (Kelly 1/3)
MARTINGALE_BASE_PCT_VERY_HIGH = 0.10      # 10% von khi WR >= 60% (Kelly 1/2)

STRATEGY_LABELS = {
    "fixed": "Co dinh (Fixed)",
    "martingale_x3": "Martingale x3 (khong gioi han)",
    "fixed_fractional_3": "Bao toan - Fixed Fractional 3%",
    "kelly_third": "Can bang - Kelly 1/3 (~5.3%)",
    "kelly_half_stoploss": "Tang toc - Kelly 1/2 + Stop-loss (8%)",
    "kelly_half_martingale_x3": "Toi uu - Dynamic Kelly & Martingale",
}
ALL_STRATEGIES = list(STRATEGY_LABELS.keys())

# -------------------- HAM TINH KELLY --------------------
def compute_kelly_fraction(win_rate: float, payout: float = KELLY_PAYOUT) -> float:
    """
    Tinh Kelly fraction day du.
    f* = (p * (b+1) - 1) / b
    Trong do: p = win_rate, b = payout (net odds, vd 0.95)
    """
    if win_rate <= 0.0 or payout <= 0.0:
        return 0.0
    f = (win_rate * (payout + 1.0) - 1.0) / payout
    return max(f, 0.0)

def get_effective_win_rate(prediction_stats: Optional[Dict], market_type: str = "size") -> float:
    """
    Lay win rate thuc te tu du lieu lich su.
    Neu chua du KELLY_WIN_RATE_MIN_SAMPLES mau -> dung gia tri mac dinh.
    """
    if not prediction_stats:
        return KELLY_WIN_RATE_DEFAULT
    mkt = prediction_stats.get(market_type, {})
    total = mkt.get("total", 0)
    if total < KELLY_WIN_RATE_MIN_SAMPLES:
        return KELLY_WIN_RATE_DEFAULT
    wr = mkt.get("win_rate", KELLY_WIN_RATE_DEFAULT)
    return max(min(float(wr), 0.95), 0.01)   # Cap [1%, 95%]

# -------------------- CLASS MONEYMANAGER --------------------
class MoneyManager:
    """
    Tinh toan so tien dat cuoc cho moi strategy.
    Ho tro giai doan khoi tao (initial phase) voi Martingale x3 co gioi han.
    """

    @staticmethod
    def get_combined_multiplier(confidence: float, win_rate: float) -> float:
        # Điều kiện nâng cao mới: Confidence >= 70% và Xác suất trượt (win_rate) >= 62%
        if confidence >= 70.0 and win_rate >= 0.62:
            if confidence >= 90.0:
                return 1.40  # Tăng 40%
            elif confidence >= 80.0:
                return 1.35  # Tăng 35%
            else:
                return 1.30  # Tăng 30%
        else:
            # Giữ nguyên cơ chế cũ làm fallback
            if win_rate >= 0.60:
                return 1.5
            elif win_rate >= 0.55:
                return 1.4
            elif win_rate >= 0.50:
                return 1.2
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
        # Tham so cho giai doan khoi tao
        is_initial_phase: bool = False,
        initial_phase_remaining: int = 0,
        is_combined: bool = False,  # Đánh dấu đồng thuận giữa Gemini và Heuristics
        market_type: str = "parity",  # <--- THÊM DÒNG NÀY
        confidence: float = 0.0,      # <--- THÊM CONFIDENCE
    ) -> float:
        """
        Tra ve so tien dat cuoc cuoi cung (VND).
        Tra ve 0.0 neu khong duoc phep dat (bi tam dung, het von...).
        """
        if current_balance <= 0:
            return 0.0

        # --- 1. XU LY CAC STRATEGY CO BAN ---
        if strategy == "fixed":
            # Lam tron xuong 1000
            bet = max(math.floor(base_amount / 1000) * 1000, 1000.0)
            # Khong ap dung tang 50% cho strategy fixed
            return bet

        if strategy == "martingale_x3":
            # Martingale x3 khong gioi han (chi dung cho test)
            bet = base_amount * (3 ** loss_streak)
            # Khong ap dung tang 50%
            return bet

        if strategy == "fixed_fractional_3":
            # 3% von hien tai
            amount = current_balance * 0.03
            bet = max(math.floor(amount / 1000) * 1000, 1000.0)
            return bet

        if strategy == "kelly_third":
            # 1/3 Kelly dua tren win rate thuc te
            k_full = compute_kelly_fraction(win_rate)
            k_third = k_full / 3.0
            fraction = min(k_third, 0.10)
            amount = current_balance * fraction
            bet = max(math.floor(amount / 1000) * 1000, 1000.0)
            return bet

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
            bet = max(math.floor(amount / 1000) * 1000, 1000.0)
            return bet

        # --- 2. STRATEGY CHINH: kelly_half_martingale_x3 ---
        if strategy == "kelly_half_martingale_x3":
            # Kiem tra tam dung (neu co)
            if pause_until is not None and time.time() < pause_until:
                logger.info(f"[kelly_half_martingale_x3] Tam dung. Con {(pause_until - time.time()) / 3600:.1f}h")
                return 0.0

            # ---- 2a. GIAI DOAN KHOI TAO (neu con) ----
            if is_initial_phase and initial_phase_remaining > 0:
                # Base = % von co dinh (duoc cau hinh)
                base_bet = current_balance * INITIAL_BASE_PCT
                base_bet = max(math.floor(base_bet / 1000) * 1000, 1000.0)

                # Neu da thua >= INITIAL_STOP_LOSS_STREAK => khong gap, quay ve base
                if loss_streak >= INITIAL_STOP_LOSS_STREAK:
                    bet = base_bet
                else:
                    # Gap thep x3, toi da INITIAL_MAX_STREAK lan
                    multiplier = 3 ** min(loss_streak, INITIAL_MAX_STREAK)
                    bet = base_bet * multiplier
                    # Gioi han khong vuot qua 30% von (bao ve them)
                    max_bet = current_balance * 0.30
                    if bet > max_bet:
                        bet = max_bet

                # Sau khi tính bet, áp dụng tăng nếu đồng thuận (dựa trên WR và confidence)
                if is_combined and bet > 0:
                    multiplier_comb = MoneyManager.get_combined_multiplier(confidence, win_rate)
                    bet = bet * multiplier_comb
                    if bet > 1000000.0:
                        bet = 1000000.0
                max_allowed = current_balance * 0.25  # giữ nguyên 25% cho giai đoạn khởi tạo
                if bet > max_allowed:
                    bet = max_allowed
                return max(math.floor(bet / 1000) * 1000, 1000.0)

            # ---- 2b. CHE DO BINH THUONG (sau giai doan khoi tao) ----
            # Kiem tra suc khoe thi truong (WR 30 ky)
            if not is_stable:
                logger.info("[kelly_half_martingale_x3] Thi truong hon loan (WR 30 ky < 45%). Tam dung.")
                return 0.0

            # ============ PHUONG AN 2: CHI GAP THEP KHI WR > 55% ============
            # Xac dinh base_pct, enable_martingale va martingale_cap
            enable_martingale = False
            martingale_cap = 0
            base_pct = 0.0

            if win_rate >= 0.60:
                k_full = compute_kelly_fraction(win_rate)
                base_pct = min(k_full / 2.0, 0.10)
                enable_martingale = False
                martingale_cap = 0
            elif win_rate >= 0.55:
                k_full = compute_kelly_fraction(win_rate)
                base_pct = min(k_full / 3.0, 0.06)
                # Gấp thếp nhẹ: x2, tối đa 2 lần
                enable_martingale = True
                martingale_cap = 2   # x2, x4 (2 lần)
            elif win_rate >= 0.50:
                base_pct = 0.03
                enable_martingale = False
                martingale_cap = 0
            else:
                # WR < 50%: chi bao toan, KHONG GAP THEP
                base_pct = MARTINGALE_BASE_PCT_LOW
                enable_martingale = False
                martingale_cap = 0

            base_bet = current_balance * base_pct
            base_bet = max(math.floor(base_bet / 1000) * 1000, 1000.0)

            if enable_martingale and martingale_cap > 0:
                # Gap thep x2, toi da martingale_cap lan
                multiplier = 2 ** min(loss_streak, martingale_cap)
                bet = base_bet * multiplier
                # Gioi han toi da 20% von de tranh pha san
                max_bet = current_balance * 0.20
                if bet > max_bet:
                    bet = max_bet
                logger.debug(f"[Martingale] WR={win_rate:.1%}, streak={loss_streak}, cap={martingale_cap}, bet={bet:,.0f}")
            else:
                bet = base_bet

            # ============ TANG CƯỢC KHI DONG THUAN (is_combined) DỰA TRÊN WR VÀ CONFIDENCE ============
            if is_combined and bet > 0:
                multiplier_comb = MoneyManager.get_combined_multiplier(confidence, win_rate)
                bet = bet * multiplier_comb
                if confidence >= 70.0 and win_rate >= 0.62:
                    logger.debug(f"[Combined Advanced] Tang {int(round((multiplier_comb-1)*100))}% (Confidence={confidence}%, WR={win_rate*100:.1f}%), bet={bet:,.0f}")
                else:
                    logger.debug(f"[Combined Fallback] Tang {int((multiplier_comb-1)*100)}% do dong thuan (WR={win_rate*100:.1f}%), bet={bet:,.0f}")

                # Áp dụng giới hạn tối đa cược là 1.000.000 VND
                if bet > 1000000.0:
                    bet = 1000000.0
                    logger.debug(f"[Combined Max Bet Limit] Gioi han bet xuong 1,000,000 VND")

            # ============ GIẢM CƯỢC KHI ĐANG THUA LIÊN TIẾP ============
            if loss_streak >= 2:
                bet = bet * 0.6
                logger.debug(f"[Loss Streak] Giam 40% cược do thua {loss_streak} lien tiep, bet={bet:,.0f}")
            if loss_streak >= 3:
                bet = bet * 0.3
                logger.debug(f"[Loss Streak] Giam 70% cược do thua {loss_streak} lien tiep, bet={bet:,.0f}")

            # ============ GIỚI HẠN TỐI ĐA THEO THỊ TRƯỜNG ============
            # Mặc định 10% vốn cho Parity, 6% cho Size
            if market_type == "size":
                max_allowed_pct = 0.06
            else:
                max_allowed_pct = 0.10

            max_allowed = current_balance * max_allowed_pct
            if bet > max_allowed:
                bet = max_allowed
                logger.debug(f"[Max Bet] Gioi han {max_allowed_pct*100:.0f}% von, bet={bet:,.0f}")

            return max(math.floor(bet / 1000) * 1000, 1000.0)

        # Fallback ve fixed
        logger.warning(f"[MoneyManager] Strategy khong xac dinh: {strategy}, fallback ve fixed")
        return max(math.floor(base_amount / 1000) * 1000, 1000.0)

    @staticmethod
    def should_trigger_pause(
        strategy: str,
        daily_loss_count: int,
        pause_until: Optional[float],
    ) -> bool:
        """
        Kiem tra xem strategy co dang bi tam dung khong.
        """
        if strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"):
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
        is_initial_phase: bool = False,
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
            else:  # kelly_half_martingale_x3
                # Uoc tinh voi che do xau nhat (WR < 50% => khong gap thep)
                # hoac WR 55-60% gap x2 toi da 2 lan
                # De an toan, uoc tinh voi base_pct thap nhat (1.5%)
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

        # fallback
        return int(current_balance // base_amount)

    @staticmethod
    def get_recommended_base(
        strategy: str,
        balance: float,
        win_rate: float = KELLY_WIN_RATE_DEFAULT,
        is_initial_phase: bool = False,
        initial_phase_remaining: int = 0,
    ) -> Dict[str, Any]:
        """
        Goi y muc cuoc co so (base_amount) phu hop voi moi strategy va so du.
        Ket qua tra ve de hien thi trong UI.
        """
        if balance <= 0:
            return {}

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
                # Che do binh thuong (Phuong an 2)
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
            # Tinh toan cho cac muc chiu k ky thua
            result = {}
            for k in [3, 4, 5]:
                # Tong so tien can cho chuoi k lan thua: base * (1 + 3 + 9 + ... + 3^(k-1))
                total_mult = sum(3**i for i in range(k))
                base = int(balance * 2 / (3**k - 1) / 1000) * 1000
                result[f"k{k}"] = base
            result["note"] = "Chiu k lan thua lien tiep voi Martingale x3"
            return result

        # fixed
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

        # Expected growth per bet
        ev_per_bet = win_rate * KELLY_PAYOUT - (1.0 - win_rate)

        # Uoc tinh sau 100 ky (ly thuyet)
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

# -------------------- HAM TINH NHANH CHO UI --------------------
def get_all_strategies_info(balance: float, win_rate: float = KELLY_WIN_RATE_DEFAULT) -> Dict[str, Dict]:
    """Tra ve thong tin tong quan cho tat ca strategy de hien thi tren UI."""
    result = {}
    for strat in ALL_STRATEGIES:
        base_rec = MoneyManager.get_recommended_base(strat, balance, win_rate)
        result[strat] = {
            "label": STRATEGY_LABELS.get(strat, strat),
            "recommended_base": base_rec,
        }
    return result