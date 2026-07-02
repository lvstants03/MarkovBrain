import threading
from typing import List, Dict, Any, Optional

class DataStore:
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._lock = threading.Lock()
        self._history: List[Dict[str, Any]] = []
        self._seen_issues = set()

    def add_record(self, issue: str, numbers: List[int]) -> bool:
        # Them mot ky quay moi vao lich su. Tra ve True neu la ky moi, False neu bi trung
        if not issue or not numbers:
            return False
            
        with self._lock:
            if issue in self._seen_issues:
                return False
                
            total = sum(numbers)
            is_tai = total > 22 # Vi du: Tong 5 chu so lon hon 22 la Tai, nguoc lai la Xiu (hoac tuy cach thiet lap cua game)
            is_le = total % 2 != 0
            
            record = {
                "issue": issue,
                "numbers": numbers,
                "total": total,
                "is_tai": is_tai,
                "is_le": is_le
            }
            
            self._history.insert(0, record) # Ky moi nhat nam o dau
            self._seen_issues.add(issue)
            
            # Cat bot neu vuot qua kich thuoc toi da
            if len(self._history) > self.max_size:
                removed = self._history.pop()
                self._seen_issues.discard(removed["issue"])
                
            return True

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history[:limit])

    def get_count(self) -> int:
        with self._lock:
            return len(self._history)

    def clear(self):
        with self._lock:
            self._history.clear()
            self._seen_issues.clear()

store = DataStore()
