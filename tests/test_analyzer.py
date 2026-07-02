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
