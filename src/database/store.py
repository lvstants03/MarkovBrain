import threading
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._lock = threading.Lock()
        self._history: List[Dict[str, Any]] = []
        self._seen_issues = set()
        
        # Cau hinh Redis tu bien moi truong
        self.redis_client = None
        self.use_redis = False
        redis_host = os.getenv("REDIS_HOST", "")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_password = os.getenv("REDIS_PASSWORD", "")
        
        if redis_host:
            try:
                import redis
                import time
                
                # Vong lap retry de doi container Redis khoi dong hoan toan
                for attempt in range(5):
                    try:
                        self.redis_client = redis.Redis(
                            host=redis_host,
                            port=redis_port,
                            password=redis_password,
                            decode_responses=True,
                            socket_timeout=3
                        )
                        self.redis_client.ping()
                        self.use_redis = True
                        logger.info(f"Connected to Redis successfully at {redis_host}:{redis_port}")
                        break
                    except Exception as e:
                        if attempt < 4:
                            logger.warning(f"Redis is not ready yet (attempt {attempt+1}/5), retrying in 2s... Error: {e}")
                            time.sleep(2)
                        else:
                            raise e
            except Exception as e:
                logger.error(f"Failed to connect to Redis after 5 attempts, falling back to RAM store: {e}")

    def add_record(self, issue: str, numbers: List[int]) -> bool:
        # Them mot ky quay moi vao lich su. Tra ve True neu la ky moi, False neu bi trung
        if not issue or not numbers:
            return False
            
        if self.use_redis:
            try:
                # Kiem tra xem ky nay da ton tai chua
                record_json = self.redis_client.hget("lottery:records", issue)
                if record_json:
                    record = json.loads(record_json)
                    # Nang cap neu truoc day la ky tinh san (numbers rong)
                    if not record.get("numbers"):
                        total = sum(numbers)
                        record["numbers"] = numbers
                        record["total"] = total
                        record["is_tai"] = total > 22
                        record["is_le"] = total % 2 != 0
                        self.redis_client.hset("lottery:records", issue, json.dumps(record))
                        return True
                    return False
                
                total = sum(numbers)
                is_tai = total > 22
                is_le = total % 2 != 0
                
                record = {
                    "issue": issue,
                    "numbers": numbers,
                    "total": total,
                    "is_tai": is_tai,
                    "is_le": is_le
                }
                
                self.redis_client.hset("lottery:records", issue, json.dumps(record))
                self.redis_client.lpush("lottery:history_issues", issue)
                
                # Gioi han size cua list
                list_len = self.redis_client.llen("lottery:history_issues")
                if list_len > self.max_size:
                    removed_issue = self.redis_client.rpop("lottery:history_issues")
                    if removed_issue:
                        self.redis_client.hdel("lottery:records", removed_issue)
                return True
            except Exception as e:
                logger.error(f"Redis error in add_record: {e}")
                
        with self._lock:
            # Nang cap neu ky nay da ton tai truoc do duoi dang dummy (chua co numbers)
            for record in self._history:
                if record["issue"] == issue:
                    if not record["numbers"]:
                        total = sum(numbers)
                        record["numbers"] = numbers
                        record["total"] = total
                        record["is_tai"] = total > 22
                        record["is_le"] = total % 2 != 0
                        return True
                    return False

            if issue in self._seen_issues:
                return False
                
            total = sum(numbers)
            is_tai = total > 22
            is_le = total % 2 != 0
            
            record = {
                "issue": issue,
                "numbers": numbers,
                "total": total,
                "is_tai": is_tai,
                "is_le": is_le
            }
            
            self._history.insert(0, record)
            self._history.sort(key=lambda x: x["issue"], reverse=True)
            self._seen_issues.add(issue)
            
            if len(self._history) > self.max_size:
                removed = self._history.pop()
                self._seen_issues.discard(removed["issue"])
                
            return True

    def add_calculated_record(self, issue: str, is_tai: bool, is_le: bool) -> bool:
        # Them mot ky quay chi co ket qua Tai/Xiu, Chan/Le tinh san
        if not issue:
            return False
            
        if self.use_redis:
            try:
                if self.redis_client.hexists("lottery:records", issue):
                    return False
                    
                record = {
                    "issue": issue,
                    "numbers": [],
                    "total": 23 if is_tai else 22,
                    "is_tai": is_tai,
                    "is_le": is_le
                }
                
                self.redis_client.hset("lottery:records", issue, json.dumps(record))
                self.redis_client.lpush("lottery:history_issues", issue)
                
                list_len = self.redis_client.llen("lottery:history_issues")
                if list_len > self.max_size:
                    removed_issue = self.redis_client.rpop("lottery:history_issues")
                    if removed_issue:
                        self.redis_client.hdel("lottery:records", removed_issue)
                return True
            except Exception as e:
                logger.error(f"Redis error in add_calculated_record: {e}")
            
        with self._lock:
            if issue in self._seen_issues:
                return False
                
            record = {
                "issue": issue,
                "numbers": [],
                "total": 23 if is_tai else 22,
                "is_tai": is_tai,
                "is_le": is_le
            }
            
            self._history.insert(0, record)
            self._history.sort(key=lambda x: x["issue"], reverse=True)
            self._seen_issues.add(issue)
            
            if len(self._history) > self.max_size:
                removed = self._history.pop()
                self._seen_issues.discard(removed["issue"])
                
            return True

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                issues = self.redis_client.lrange("lottery:history_issues", 0, limit - 1)
                if not issues:
                    return []
                records_json = self.redis_client.hmget("lottery:records", issues)
                history = []
                for item in records_json:
                    if item:
                        history.append(json.loads(item))
                history.sort(key=lambda x: x["issue"], reverse=True)
                return history
            except Exception as e:
                logger.error(f"Redis error in get_history: {e}")
                
        with self._lock:
            return list(self._history[:limit])

    def get_count(self) -> int:
        if self.use_redis:
            try:
                return self.redis_client.llen("lottery:history_issues")
            except Exception as e:
                logger.error(f"Redis error in get_count: {e}")
        with self._lock:
            return len(self._history)

    def clear(self):
        if self.use_redis:
            try:
                self.redis_client.delete("lottery:records", "lottery:history_issues")
            except Exception as e:
                logger.error(f"Redis error in clear: {e}")
        with self._lock:
            self._history.clear()
            self._seen_issues.clear()

store = DataStore()
