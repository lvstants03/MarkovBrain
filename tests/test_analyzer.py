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


