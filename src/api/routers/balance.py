import time
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.database.store import store
from src.config import config

router = APIRouter()

class DemoConfigUpdate(BaseModel):
    amount: Optional[float] = Field(None, ge=0.0, description="Muc tien dat cuoc moi lenh gia lap")
    strategy: Optional[str] = Field(None, description="Chien thuat dat cuoc (fixed, martingale_x3, fixed_fractional_3, kelly_third, kelly_half_stoploss)")
    demo_balance: Optional[float] = Field(None, ge=0.0, description="Tu dat so du gia lap moi")

@router.get("/balance")
async def get_balance_info(page: int = Query(default=1, ge=1), limit: int = Query(default=10, ge=1, le=100)):
    from src.core.money import MoneyManager, get_effective_win_rate, STRATEGY_LABELS
    balances = store.get_balances()
    
    # Sử dụng hàm get_demo_bets_paginated để phân trang
    demo_bets_data = store.get_demo_bets_paginated(page=page, limit=limit)
    bets = demo_bets_data["bets"]
    total_bets = demo_bets_data["total"]

    demo_balance = balances.get("demo_balance", 0.0)
    base_bet = balances.get("demo_bet_amount", 100000.0)
    strategy = balances.get("demo_bet_strategy", "fixed")

    loss_streaks = store.get_loss_streaks()
    p_streak = loss_streaks.get("parity", 0)
    s_streak = loss_streaks.get("size", 0)

    daily_info = store.get_daily_loss_info()
    p_daily = daily_info.get("parity_daily_loss_count", 0)
    s_daily = daily_info.get("size_daily_loss_count", 0)
    p_pause = daily_info.get("parity_pause_until", None)
    s_pause = daily_info.get("size_pause_until", None)

    is_stable = store.is_market_stable()

    prediction_stats_recent = store.get_prediction_stats_recent(15)
    p_win_rate = get_effective_win_rate(prediction_stats_recent, "parity")
    s_win_rate = get_effective_win_rate(prediction_stats_recent, "size")

    # Lấy thông tin dự đoán mới nhất để đồng bộ tiền cược kì tới
    latest_preds = store.get_prediction_history(limit=1)
    is_combined_p = False
    is_combined_s = False
    p_confidence = 0.0
    s_confidence = 0.0
    if latest_preds:
        latest = latest_preds[0]
        is_combined_p = (latest.get("engine_used_parity") == "Combined")
        is_combined_s = (latest.get("engine_used_size") == "Combined")
        p_confidence = latest.get("parity_confidence") or 0.0
        s_confidence = latest.get("size_confidence") or 0.0

    p_bet = MoneyManager.calculate_bet(
        strategy=strategy, base_amount=base_bet, current_balance=demo_balance,
        loss_streak=p_streak, daily_loss_count=p_daily, pause_until=p_pause, win_rate=p_win_rate,
        is_stable=is_stable, is_combined=is_combined_p, market_type="parity", confidence=p_confidence
    )
    s_bet = MoneyManager.calculate_bet(
        strategy=strategy, base_amount=base_bet, current_balance=demo_balance,
        loss_streak=s_streak, daily_loss_count=s_daily, pause_until=s_pause, win_rate=s_win_rate,
        is_stable=is_stable, is_combined=is_combined_s, market_type="size", confidence=s_confidence
    )

    max_streak = MoneyManager.get_max_streak_tolerated(strategy, demo_balance, base_bet, s_win_rate)

    is_bankrupt = demo_balance <= 0 or (p_bet <= 0 and s_bet <= 0 and strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"))
    if strategy not in ("kelly_half_stoploss", "kelly_half_martingale_x3"):
        is_bankrupt = is_bankrupt or (p_bet > demo_balance and s_bet > demo_balance)

    collapses = store.get_capital_collapses(limit=50)
    summary_data = store.get_bet_summary()

    risk_info_parity = MoneyManager.get_risk_info(
        strategy=strategy, current_balance=demo_balance, base_amount=base_bet,
        win_rate=p_win_rate, loss_streak=p_streak, daily_loss_count=p_daily, pause_until=p_pause,
        is_stable=is_stable, is_combined=is_combined_p, market_type="parity", confidence=p_confidence
    )
    risk_info_size = MoneyManager.get_risk_info(
        strategy=strategy, current_balance=demo_balance, base_amount=base_bet,
        win_rate=s_win_rate, loss_streak=s_streak, daily_loss_count=s_daily, pause_until=s_pause,
        is_stable=is_stable, is_combined=is_combined_s, market_type="size", confidence=s_confidence
    )

    return {
        "status": "success",
        "balances": balances,
        "max_loss_streak_tolerated": max_streak,
        "is_bankrupt": is_bankrupt,
        "next_bet_amounts": {
            "parity": p_bet,
            "size": s_bet,
            "parity_streak": p_streak,
            "size_streak": s_streak
        },
        "risk_info": {
            "parity": risk_info_parity,
            "size": risk_info_size,
        },
        "strategy_labels": STRATEGY_LABELS,
        "demo_bets": bets,
        "total_bets": total_bets,
        "page": page,
        "limit": limit,
        "summary": summary_data["summary"],
        "capital_collapses": collapses
    }

@router.post("/balance/reset")
async def reset_demo_balance():
    success = store.reset_demo_balance()
    return {
        "status": "success" if success else "error",
        "message": "?? reset s? d? gi? l?p v? 10,000,000 VND v? x?a l?ch s? c??c ?o."
    }

@router.post("/balance/clear-bets")
async def clear_demo_bets_endpoint():
    store.clear()
    success = store.clear_demo_bets()
    
    from src.core.scraper import scraper
    import asyncio
    asyncio.create_task(scraper.fetch_latest_info())
    
    return {
        "status": "success" if success else "error",
        "message": "?? x?a s?ch to?n b? k? quay, l?ch s? d? ?o?n, c??c gi? l?p v? ?ang t?i v? d? li?u m?i nh?t."
    }

@router.post("/balance/config")
async def update_demo_config(config_data: DemoConfigUpdate):
    from src.core.money import MoneyManager, get_effective_win_rate, ALL_STRATEGIES
    success = True

    if config_data.amount is not None:
        success = success and store.set_demo_bet_amount(config_data.amount)
    if config_data.strategy is not None:
        if config_data.strategy not in ALL_STRATEGIES:
            return {
                "status": "error",
                "message": f"Strategy khong hop le. Cac gia tri cho phep: {ALL_STRATEGIES}",
                "recommended_bet": None
            }
        success = success and store.set_demo_bet_strategy(config_data.strategy)
    if config_data.demo_balance is not None:
        success = success and store.update_demo_balance(config_data.demo_balance)

    balances = store.get_balances()
    current_balance = balances.get("demo_balance", 0.0)
    current_strategy = balances.get("demo_bet_strategy", "fixed")
    prediction_stats_recent = store.get_prediction_stats_recent(15)
    win_rate = get_effective_win_rate(prediction_stats_recent, "size")

    recommended_bet = MoneyManager.get_recommended_base(
        strategy=current_strategy,
        balance=current_balance,
        win_rate=win_rate,
    ) if current_balance > 0 else None

    return {
        "status": "success" if success else "error",
        "message": "Da cap nhat cau hinh tai chinh gia lap thanh cong.",
        "recommended_bet": recommended_bet
    }

PERIOD_SECONDS = {
    "1h": 3600,
    "6h": 21600,
    "12h": 43200,
    "24h": 86400,
    "7d": 604800,
}

@router.get("/bet-log")
async def get_bet_log(
    period: Optional[str] = Query(default="24h", description="Khoang thoi gian: 1h, 6h, 12h, 24h, 7d hoac 'custom'"),
    start_time: Optional[float] = Query(default=None, description="Unix timestamp bat dau (chi dung khi period=custom)"),
    end_time: Optional[float] = Query(default=None, description="Unix timestamp ket thuc (chi dung khi period=custom)"),
):
    now = time.time()

    if period == "custom":
        since_ts = start_time
        until_ts = end_time if end_time else now
        if since_ts is None:
            raise HTTPException(status_code=400, detail="Phai cung cap start_time khi period=custom")
    elif period in PERIOD_SECONDS:
        since_ts = now - PERIOD_SECONDS[period]
        until_ts = now
    else:
        raise HTTPException(
            status_code=400,
            detail=f"period khong hop le. Cac gia tri cho phep: {list(PERIOD_SECONDS.keys())} hoac 'custom'"
        )

    summary = store.get_bet_summary(since_ts=since_ts, until_ts=until_ts)
    return {
        "status": "success",
        "period_label": period,
        **summary
    }
