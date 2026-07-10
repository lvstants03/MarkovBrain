from src.database.store import DataStore
from src.core.analyzer import ProbabilityAnalyzer

def test_datastore_add_and_retrieve():
    store = DataStore(max_size=5)
    
    # Check initial state
    assert store.get_count() == 0
    assert len(store.get_history()) == 0
    
    # Add a valid record
    added = store.add_record("20260701001", [1, 2, 3, 4, 5])  # Total = 15
    assert added is True
    assert store.get_count() == 1
    
    # Retrieve and verify details
    history = store.get_history()
    assert len(history) == 1
    record = history[0]
    assert record["issue"] == "20260701001"
    assert record["numbers"] == [1, 2, 3, 4, 5]
    assert record["total"] == 15
    assert record["is_tai"] is False  # 15 <= 22
    assert record["is_le"] is True   # 15 % 2 != 0

    # Add duplicate record (should be ignored)
    added_dup = store.add_record("20260701001", [9, 9, 9, 9, 9])
    assert added_dup is False
    assert store.get_count() == 1

def test_datastore_max_size():
    store = DataStore(max_size=3)
    
    store.add_record("001", [1, 1, 1, 1, 1])
    store.add_record("002", [2, 2, 2, 2, 2])
    store.add_record("003", [3, 3, 3, 3, 3])
    assert store.get_count() == 3
    
    # Adding a 4th record should evict the oldest ("001")
    store.add_record("004", [4, 4, 4, 4, 4])
    assert store.get_count() == 3
    
    history = store.get_history()
    issues = [r["issue"] for r in history]
    assert "001" not in issues
    assert "004" in issues
    assert issues == ["004", "003", "002"]  # Newest first

def test_datastore_clear():
    store = DataStore()
    store.add_record("001", [1, 2, 3, 4, 5])
    assert store.get_count() == 1
    
    store.clear()
    assert store.get_count() == 0
    assert len(store.get_history()) == 0

def test_analyzer_empty_history():
    result = ProbabilityAnalyzer.analyze([])
    assert result["total_records"] == 0
    assert result["probabilities"] == {}
    assert result["streaks"] == {}

def test_analyzer_simple_calculations():
    # 5 records:
    # 1. total = 10 (xiu, chan) -> issue 001
    # 2. total = 25 (tai, le)  -> issue 002
    # 3. total = 30 (tai, chan) -> issue 003
    # 4. total = 15 (xiu, le)  -> issue 004
    # 5. total = 20 (xiu, chan) -> issue 005
    history = [
        {"issue": "005", "numbers": [4, 4, 4, 4, 4], "total": 20, "is_tai": False, "is_le": False}, # newest
        {"issue": "004", "numbers": [3, 3, 3, 3, 3], "total": 15, "is_tai": False, "is_le": True},
        {"issue": "003", "numbers": [6, 6, 6, 6, 6], "total": 30, "is_tai": True, "is_le": False},
        {"issue": "002", "numbers": [5, 5, 5, 5, 5], "total": 25, "is_tai": True, "is_le": True},
        {"issue": "001", "numbers": [2, 2, 2, 2, 2], "total": 10, "is_tai": False, "is_le": False}, # oldest
    ]
    
    result = ProbabilityAnalyzer.analyze(history)
    assert result["total_records"] == 5
    
    # 2 le, 3 chan -> le: 2/5 = 0.4, chan: 3/5 = 0.6
    # 2 tai, 3 xiu -> tai: 2/5 = 0.4, xiu: 3/5 = 0.6
    assert result["probabilities"]["le"] == 0.4
    assert result["probabilities"]["chan"] == 0.6
    assert result["probabilities"]["tai"] == 0.4
    assert result["probabilities"]["xiu"] == 0.6

    # Streaks (oldest first series for streak analysis, which means df.iloc[::-1])
    # df has 005 at index 0, 001 at index 4
    # series order: 001, 002, 003, 004, 005
    # le_series: False (001), True (002), False (003), True (004), False (005) -> active streak at end is False (Chan) count 1
    # tai_series: False (001), True (002), True (003), False (004), False (005) -> active streak at end is False (Xiu) count 2
    assert result["streaks"]["le_streak"]["state"] == "Chan"
    assert result["streaks"]["le_streak"]["count"] == 1
    assert result["streaks"]["tai_streak"]["state"] == "Xiu"
    assert result["streaks"]["tai_streak"]["count"] == 2

def test_predictions_and_ai():
    store = DataStore()
    store.clear()
    
    # 1. Test adding prediction
    pred_data = {
        "predicted_parity": "Le",
        "predicted_size": "Tai",
        "parity_confidence": 85,
        "size_confidence": 90
    }
    added = store.add_prediction("20260701001", pred_data)
    assert added is True
    
    # Try adding duplicate (should be False)
    added_dup = store.add_prediction("20260701001", pred_data)
    assert added_dup is False
    
    # 2. Verify prediction exists in history
    history = store.get_prediction_history()
    assert len(history) == 1
    assert history[0]["issue"] == "20260701001"
    assert history[0]["status_parity"] == "pending"
    assert history[0]["parity_confidence"] == 85
    assert history[0]["size_confidence"] == 90
    
    # 3. Resolve prediction by adding a record
    # sum = 25 (Tai, Le)
    store.add_record("20260701001", [5, 5, 5, 5, 5])
    
    history_resolved = store.get_prediction_history()
    assert history_resolved[0]["status_parity"] == "win"
    assert history_resolved[0]["status_size"] == "win"
    assert history_resolved[0]["actual_parity"] == "Le"
    assert history_resolved[0]["actual_size"] == "Tai"
    
    # Verify stats
    stats = store.get_prediction_stats()
    assert stats["parity"]["wins"] == 1
    assert stats["size"]["wins"] == 1
    assert stats["overall_win_rate"] == 1.0
    
    # 4. Test AI recommendation structure
    # With 5 records from test_analyzer_simple_calculations, check if the analyzer returns ai_recommendation
    history_records = [
        {"issue": "005", "numbers": [4, 4, 4, 4, 4], "total": 20, "is_tai": False, "is_le": False},
        {"issue": "004", "numbers": [3, 3, 3, 3, 3], "total": 15, "is_tai": False, "is_le": True},
        {"issue": "003", "numbers": [6, 6, 6, 6, 6], "total": 30, "is_tai": True, "is_le": False},
        {"issue": "002", "numbers": [5, 5, 5, 5, 5], "total": 25, "is_tai": True, "is_le": True},
        {"issue": "001", "numbers": [2, 2, 2, 2, 2], "total": 10, "is_tai": False, "is_le": False},
    ]
    result = ProbabilityAnalyzer.analyze(history_records)
    assert "ai_recommendation" in result
    assert "parity" in result["ai_recommendation"]
    assert "size" in result["ai_recommendation"]
    assert "decision" in result["ai_recommendation"]["parity"]
    assert "confidence" in result["ai_recommendation"]["parity"]
    assert "rationale" in result["ai_recommendation"]["parity"]

def test_analyzer_gemini_fallback():
    # If GEMINI_API_KEY is not set or invalid, analyzer should fallback to heuristics without crash
    from src.config import config
    original_key = getattr(config, "GEMINI_API_KEY", "")
    try:
        config.GEMINI_API_KEY = "" # Ensure it's empty
        history_records = [
            {"issue": f"{i:03d}", "numbers": [5, 5, 5, 5, 5], "total": 25, "is_tai": i % 2 == 0, "is_le": i % 2 == 0}
            for i in range(10)
        ]
        result = ProbabilityAnalyzer.analyze(history_records)
        assert "ai_recommendation" in result
        assert result["ai_recommendation"]["parity"]["decision"] in ["MUA CHẴN", "MUA LẺ", "BỎ QUA"]
        assert result["ai_recommendation"]["size"]["decision"] in ["MUA TÀI", "MUA XỈU", "BỎ QUA"]
    finally:
        config.GEMINI_API_KEY = original_key

def test_martingale_and_custom_balance():
    store = DataStore()
    store.clear()
    
    # Test setting custom demo balance and strategy
    store.update_demo_balance(500000.0)
    store.set_demo_bet_strategy("martingale_x3")
    store.set_demo_bet_amount(10000.0)
    
    balances = store.get_balances()
    assert balances["demo_balance"] == 500000.0
    assert balances["demo_bet_strategy"] == "martingale_x3"
    assert balances["demo_bet_amount"] == 10000.0
    
    # Verify initial loss streaks are 0
    loss_streaks = store.get_loss_streaks()
    assert loss_streaks["parity"] == 0
    assert loss_streaks["size"] == 0
    
    # Place first bet (should use base amount 10,000)
    store.place_demo_bet("20260701001", "parity", "MUA LẺ", 10000.0)
    
    # After placing bet, balance should decrease by 10,000
    balances = store.get_balances()
    assert balances["demo_balance"] == 490000.0
    
    # Resolve bet as a loss (numbers sum to even: sum = 20)
    # This should increase loss streak for parity to 1
    store.resolve_demo_bets("20260701001", [4, 4, 4, 4, 4])
    
    loss_streaks = store.get_loss_streaks()
    assert loss_streaks["parity"] == 1
    
    # Place second bet (should use 10,000 * 3^1 = 30,000)
    store.place_demo_bet("20260701002", "parity", "MUA LẺ", 10000.0)
    
    balances = store.get_balances()
    assert balances["demo_balance"] == 460000.0 # 490,000 - 30,000
    
    # Resolve bet as a win (numbers sum to odd: sum = 25)
    # This should reset loss streak for parity to 0
    store.resolve_demo_bets("20260701002", [5, 5, 5, 5, 5])
    
    loss_streaks = store.get_loss_streaks()
    assert loss_streaks["parity"] == 0
    
    # Win payout: 30,000 * 1.95 = 58,500
    # New balance should be 460,000 + 58,500 = 518,500
    balances = store.get_balances()
    assert balances["demo_balance"] == 518500.0


def test_clear_demo_bets():
    store = DataStore()
    store.use_redis = False
    
    # Setup some state
    store.update_demo_balance(500000.0)
    store.place_demo_bet("20260701001", "parity", "MUA LẺ", 10000.0)
    store.resolve_demo_bets("20260701001", [4, 4, 4, 4, 4]) # Loss -> streak = 1
    
    assert len(store.get_demo_bets()) > 0
    assert store.get_loss_streaks()["parity"] == 1
    assert store.get_balances()["demo_balance"] == 490000.0
    
    # Clear bets
    store.clear_demo_bets()
    
    # Bets should be cleared, streaks reset, but balance KEPT
    assert len(store.get_demo_bets()) == 0
    assert store.get_loss_streaks()["parity"] == 0
    assert store.get_balances()["demo_balance"] == 490000.0


def test_capital_collapse_logging():
    store = DataStore()
    store.clear()
    store.clear_capital_collapses()

    # Set custom demo balance and strategy to trigger overdraft
    store.update_demo_balance(10000.0)
    store.set_demo_bet_strategy("fixed")
    store.set_demo_bet_amount(50000.0)

    # Place bet should return "insufficient_balance" and trigger collapse log
    res = store.place_demo_bet("20260701001", "parity", "MUA LẺ", 50000.0)
    assert res == "insufficient_balance"

    # Verify collapse logged
    collapses = store.get_capital_collapses()
    assert len(collapses) == 1
    assert collapses[0]["issue"] == "20260701001"
    assert collapses[0]["amount_required"] == 50000.0
    assert collapses[0]["balance_current"] == 10000.0

    # Clear collapses
    store.clear_capital_collapses()
    assert len(store.get_capital_collapses()) == 0


def test_drawdown_pause_protection():
    store = DataStore()
    store.use_redis = False
    
    # 1. Reset/Set balance to 1,000,000. Peak should become 1,000,000.
    store.update_demo_balance(1000000.0)
    store.set_demo_bet_amount(300000.0)
    balances = store.get_balances()
    assert balances["demo_balance"] == 1000000.0
    assert balances["peak_demo_balance"] == 1000000.0
    
    # 2. Place a bet of 300,000 (which is 30% of capital)
    store.place_demo_bet("20260701001", "parity", "MUA LẺ", 300000.0)
    
    # 3. Resolve the bet as a loss (numbers sum to even: sum = 20)
    store.resolve_demo_bets("20260701001", [4, 4, 4, 4, 4])
    
    # Balance resolved is 700,000. Drawdown = 30% (>= 25%).
    # This should trigger the pause.
    daily_info = store.get_daily_loss_info()
    assert daily_info["parity_pause_until"] is not None
    assert daily_info["size_pause_until"] is not None
    import time
    assert daily_info["parity_pause_until"] - time.time() > 500  # should be around 600s
    assert daily_info["parity_pause_until"] - time.time() <= 600
    
    # Peak balance should still be 1,000,000 (since balance went down, not up)
    assert store.get_balances()["peak_demo_balance"] == 1000000.0
    
    # 4. Check that when pause expires, peak balance resets to current balance (700,000)
    import time
    store._parity_pause_until = time.time() - 10 # expired 10 seconds ago
    store._size_pause_until = time.time() - 10
    
    # Calling get_daily_loss_info should auto-reset peak and clear pause
    info = store.get_daily_loss_info()
    assert info["parity_pause_until"] is None
    assert info["size_pause_until"] is None
    assert store.get_balances()["peak_demo_balance"] == 700000.0


def test_ping_pong_overall_probability_override():
    from src.database.store import store
    store.clear()
    store.clear_demo_bets()
    
    # Construct a history of 35 alternating rounds
    history = []
    for i in range(35):
        val = (i % 2 == 0)
        history.append({
            "issue": f"20260701{i:03d}",
            "numbers": [1, 2, 3, 4, 5] if val else [2, 2, 2, 2, 2],
            "total": 15 if val else 10,
            "is_tai": True,
            "is_le": val
        })

    # Run analysis
    from src.core.analyzer import ProbabilityAnalyzer
    res = ProbabilityAnalyzer.analyze(history)
    
    # Standard ping-pong predicts: not history[0]["is_le"] = False (Chan) -> "MUA CHẴN".
    # BUT overall probability of Le (8/15) is higher than Chan (7/15).
    # Therefore, the override changes it to "MUA LẺ" and rationale contains "Hiệu chỉnh".
    
    assert res["ai_recommendation"]["parity"]["decision"] == "MUA LẺ"
    assert "Hiệu chỉnh theo xác suất tổng thể" in res["ai_recommendation"]["parity"]["rationale"]


def test_recent_win_rate_and_health_log():
    import os
    store = DataStore()
    store.clear()
    
    # 1. Add predictions to test get_prediction_stats_recent
    # We will add 20 predictions, 15 win, 5 lose
    for i in range(25):
        issue = f"20260702{i:03d}"
        is_win = (i >= 10)  # last 15 are wins
        
        # We need total_records_at_prediction > 10 to not be skipped
        pred_data = {
            "predicted_parity": "Le",
            "predicted_size": "Tai",
            "parity_confidence": 85,
            "size_confidence": 90,
            "total_records_at_prediction": 15
        }
        store.add_prediction(issue, pred_data)
        
        # Resolve prediction
        if is_win:
            store.resolve_prediction(issue, [5, 5, 5, 5, 5])  # sum = 25 (Tai, Le) -> Win
        else:
            store.resolve_prediction(issue, [2, 2, 2, 2, 2])  # sum = 10 (Xiu, Chan) -> Lose

    # Get recent stats (should evaluate the 15 most recent resolved items)
    stats_recent = store.get_prediction_stats_recent(15)
    # The 15 most recent should be all wins (since i from 10 to 24 are all wins)
    assert stats_recent["parity"]["total"] == 15
    assert stats_recent["parity"]["wins"] == 15
    assert stats_recent["parity"]["win_rate"] == 1.0

    # Test market stability
    assert store.is_market_stable() is True

    # Test market health log file creation
    log_file_path = os.path.join(os.getcwd(), "market_health_30.log")
    if os.path.exists(log_file_path):
        os.remove(log_file_path)

    store.write_market_health_log()
    assert os.path.exists(log_file_path) is True
    
    with open(log_file_path, "r", encoding="utf-8") as f:
        log_content = f.read()
    assert "Khối 30 kỳ gần nhất" in log_content

    # Clean up log
    if os.path.exists(log_file_path):
        os.remove(log_file_path)


def test_kelly_half_martingale_x3_calculation():
    from src.core.money_management import MoneyManager
    
    # 1. Test is_stable = False -> returns 0.0
    bet = MoneyManager.calculate_bet(
        strategy="kelly_half_martingale_x3",
        base_amount=10000.0,
        current_balance=1000000.0,
        loss_streak=0,
        daily_loss_count=0,
        pause_until=None,
        win_rate=0.60,
        is_stable=False
    )
    assert bet == 0.0

    # 2. Test WR >= 60% (Active Kelly) -> k_half = Kelly 1/2, max 10%
    # For WR=0.65, payout=0.95: Kelly = (0.65 * 1.95 - 1) / 0.95 = 0.281 -> Kelly 1/2 = 0.14 -> max 10% (0.10)
    # Bet should be 1,000,000 * 0.10 = 100,000
    bet_active = MoneyManager.calculate_bet(
        strategy="kelly_half_martingale_x3",
        base_amount=10000.0,
        current_balance=1000000.0,
        loss_streak=0,
        daily_loss_count=0,
        pause_until=None,
        win_rate=0.65,
        is_stable=True
    )
    assert bet_active == 100000.0

    # 3. Test WR < 50% (Conservative + Martingale Limited) -> 1.5% base + Martingale
    # For WR=0.48: base_bet = 1,000,000 * 0.015 = 15,000
    # streak = 0 -> 15,000
    bet_m0 = MoneyManager.calculate_bet(
        strategy="kelly_half_martingale_x3",
        base_amount=10000.0,
        current_balance=1000000.0,
        loss_streak=0,
        daily_loss_count=0,
        pause_until=None,
        win_rate=0.48,
        is_stable=True
    )
    assert bet_m0 == 15000.0

    # streak = 1 -> 15,000 * 3 = 45,000
    bet_m1 = MoneyManager.calculate_bet(
        strategy="kelly_half_martingale_x3",
        base_amount=10000.0,
        current_balance=1000000.0,
        loss_streak=1,
        daily_loss_count=0,
        pause_until=None,
        win_rate=0.48,
        is_stable=True
    )
    assert bet_m1 == 45000.0

    # streak = 4 -> limited to 3 -> 15,000 * 27 = 405,000
    bet_m4 = MoneyManager.calculate_bet(
        strategy="kelly_half_martingale_x3",
        base_amount=10000.0,
        current_balance=1000000.0,
        loss_streak=4,
        daily_loss_count=0,
        pause_until=None,
        win_rate=0.48,
        is_stable=True
    )
    assert bet_m4 == 405000.0








