import json
import time
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class RecordsMixin:
    def add_record(self, issue: str, numbers: List[int]) -> bool:
        if not issue or not numbers:
            return False

        if self.use_redis:
            try:
                record_json = self.redis_client.hget(self.key_records, issue)
                if record_json:
                    record = json.loads(record_json)
                    if not record.get("numbers"):
                        total = sum(numbers)
                        record["numbers"] = numbers
                        record["total"] = total
                        record["is_tai"] = total > 22
                        record["is_le"] = total % 2 != 0
                        self.redis_client.hset(self.key_records, issue, json.dumps(record))
                        self.resolve_prediction(issue, numbers)
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
                    "is_le": is_le,
                    "time": time.strftime("%H:%M:%S %d/%m/%Y")
                }
                is_new = self.redis_client.hsetnx(self.key_records, issue, json.dumps(record))
                if is_new:
                    self.redis_client.lpush(self.key_history_issues, issue)
                    list_len = self.redis_client.llen(self.key_history_issues)
                    if list_len > self.max_size:
                        removed_issue = self.redis_client.rpop(self.key_history_issues)
                        if removed_issue:
                            self.redis_client.hdel(self.key_records, removed_issue)
                    self.resolve_prediction(issue, numbers)
                    return True
                return False
            except Exception as e:
                logger.error(f"Redis error in add_record: {e}")

        with self._lock:
            for record in self._history:
                if record["issue"] == issue:
                    if not record["numbers"]:
                        total = sum(numbers)
                        record["numbers"] = numbers
                        record["total"] = total
                        record["is_tai"] = total > 22
                        record["is_le"] = total % 2 != 0
                        self.resolve_prediction(issue, numbers)
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
                "is_le": is_le,
                "time": time.strftime("%H:%M:%S %d/%m/%Y")
            }
            self._history.insert(0, record)
            self._history.sort(key=lambda x: x["issue"], reverse=True)
            self._seen_issues.add(issue)
            if len(self._history) > self.max_size:
                removed = self._history.pop()
                self._seen_issues.discard(removed["issue"])
            self.resolve_prediction(issue, numbers)
            return True

    def add_calculated_record(self, issue: str, is_tai: bool, is_le: bool) -> bool:
        if not issue:
            return False

        if self.use_redis:
            try:
                if self.redis_client.hexists(self.key_records, issue):
                    return False
                record = {
                    "issue": issue,
                    "numbers": [],
                    "total": 23 if is_tai else 22,
                    "is_tai": is_tai,
                    "is_le": is_le,
                    "time": time.strftime("%H:%M:%S %d/%m/%Y")
                }
                self.redis_client.hset(self.key_records, issue, json.dumps(record))
                self.redis_client.lpush(self.key_history_issues, issue)
                list_len = self.redis_client.llen(self.key_history_issues)
                if list_len > self.max_size:
                    removed_issue = self.redis_client.rpop(self.key_history_issues)
                    if removed_issue:
                        self.redis_client.hdel(self.key_records, removed_issue)
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
                "is_le": is_le,
                "time": time.strftime("%H:%M:%S %d/%m/%Y")
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
                issues = self.redis_client.lrange(self.key_history_issues, 0, limit * 2)
                if not issues:
                    return []
                records_json = self.redis_client.hmget(self.key_records, issues)
                history = []
                for item in records_json:
                    if item:
                        rec = json.loads(item)
                        if len(rec.get("numbers", [])) in (0, 5):
                            history.append(rec)
                history.sort(key=lambda x: x["issue"], reverse=True)
                return history[:limit]
            except Exception as e:
                logger.error(f"Redis error in get_history: {e}")

        with self._lock:
            return [r for r in self._history if len(r.get("numbers", [])) in (0, 5)][:limit]

    def get_count(self) -> int:
        if self.use_redis:
            try:
                return self.redis_client.llen(self.key_history_issues)
            except Exception as e:
                logger.error(f"Redis error in get_count: {e}")
        with self._lock:
            return len(self._history)

    def clear(self):
        if self.use_redis:
            try:
                self.redis_client.delete(
                    self.key_records, self.key_history_issues,
                    self.key_predictions, self.key_prediction_issues,
                    self.key_parity_loss_streak, self.key_size_loss_streak
                )
            except Exception as e:
                logger.error(f"Redis error in clear: {e}")
        with self._lock:
            self._history.clear()
            self._seen_issues.clear()
            if hasattr(self, "_predictions"):
                self._predictions.clear()
            self._parity_loss_streak = 0
            self._size_loss_streak = 0
            self._initial_phase_remaining = 10
            self._save_local_store()


