import threading
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from src.config import config

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._lock = threading.RLock()
        self._history: List[Dict[str, Any]] = []
        self._seen_issues = set()
        self._predictions: Dict[str, Dict[str, Any]] = {}
        
        # Cau hinh Redis tu bien moi truong
        self.redis_client = None
        self.use_redis = False
        redis_host = os.getenv("REDIS_HOST", "")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_password = os.getenv("REDIS_PASSWORD", "")
        
        if redis_host:
            try:
                import redis
                
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

    @property
    def key_records(self):
        return f"lottery:{config.LOTTERY_CODE}:records"

    @property
    def key_history_issues(self):
        return f"lottery:{config.LOTTERY_CODE}:history_issues"

    @property
    def key_predictions(self):
        return f"lottery:{config.LOTTERY_CODE}:predictions"

    @property
    def key_prediction_issues(self):
        return f"lottery:{config.LOTTERY_CODE}:prediction_issues"

    def add_record(self, issue: str, numbers: List[int]) -> bool:
        # Them mot ky quay moi vao lich su. Tra ve True neu la ky moi, False neu bi trung
        if not issue or not numbers:
            return False
            
        if self.use_redis:
            try:
                # Kiem tra xem ky nay da ton tai chua
                record_json = self.redis_client.hget(self.key_records, issue)
                if record_json:
                    record = json.loads(record_json)
                    # Nang cap neu truoc day la ky tinh san (numbers rong)
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
                
                self.redis_client.hset(self.key_records, issue, json.dumps(record))
                self.redis_client.lpush(self.key_history_issues, issue)
                
                # Gioi han size cua list
                list_len = self.redis_client.llen(self.key_history_issues)
                if list_len > self.max_size:
                    removed_issue = self.redis_client.rpop(self.key_history_issues)
                    if removed_issue:
                        self.redis_client.hdel(self.key_records, removed_issue)
                self.resolve_prediction(issue, numbers)
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
        # Them mot ky quay chi co ket qua Tai/Xiu, Chan/Le tinh san
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
                        if len(rec.get("numbers", [])) == 5:
                            history.append(rec)
                history.sort(key=lambda x: x["issue"], reverse=True)
                return history[:limit]
            except Exception as e:
                logger.error(f"Redis error in get_history: {e}")
                
        with self._lock:
            return [r for r in self._history if len(r.get("numbers", [])) == 5][:limit]

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
                self.redis_client.delete(self.key_records, self.key_history_issues, self.key_predictions, self.key_prediction_issues)
            except Exception as e:
                logger.error(f"Redis error in clear: {e}")
        with self._lock:
            self._history.clear()
            self._seen_issues.clear()
            if hasattr(self, "_predictions"):
                self._predictions.clear()

    def add_prediction(self, issue: str, prediction_data: dict) -> bool:
        if not issue:
            return False
            
        record = {
            "issue": issue,
            "predicted_parity": prediction_data.get("predicted_parity", "Không có"),
            "predicted_size": prediction_data.get("predicted_size", "Không có"),
            "parity_confidence": prediction_data.get("parity_confidence"),
            "size_confidence": prediction_data.get("size_confidence"),
            "actual_parity": None,
            "actual_size": None,
            "status_parity": "pending",
            "status_size": "pending",
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y")
        }
        
        if self.use_redis:
            try:
                existing = self.redis_client.hget(self.key_predictions, issue)
                if not existing:
                    self.redis_client.hset(self.key_predictions, issue, json.dumps(record))
                    self.redis_client.lpush(self.key_prediction_issues, issue)
                    if self.redis_client.llen(self.key_prediction_issues) > 1000:
                        removed = self.redis_client.rpop(self.key_prediction_issues)
                        if removed:
                            self.redis_client.hdel(self.key_predictions, removed)
                    return True
                return False
            except Exception as e:
                logger.error(f"Redis error in add_prediction: {e}")
                
        with self._lock:
            if not hasattr(self, "_predictions"):
                self._predictions = {}
            if issue not in self._predictions:
                self._predictions[issue] = record
                if len(self._predictions) > 1000:
                    oldest_key = min(self._predictions.keys(), key=lambda k: self._predictions[k]["timestamp"])
                    self._predictions.pop(oldest_key, None)
                return True
            return False

    def resolve_prediction(self, issue: str, numbers: List[int]) -> bool:
        if not issue or not numbers or len(numbers) != 5:
            return False
            
        total = sum(numbers)
        actual_parity = "Le" if total % 2 != 0 else "Chan"
        actual_size = "Tai" if total > 22 else "Xiu"
        
        updated = False
        if self.use_redis:
            try:
                record_json = self.redis_client.hget(self.key_predictions, issue)
                if record_json:
                    record = json.loads(record_json)
                    if record.get("status_parity") == "pending" or record.get("status_size") == "pending":
                        record["actual_parity"] = actual_parity
                        record["actual_size"] = actual_size
                        
                        pred_p = record.get("predicted_parity")
                        if pred_p and pred_p != "Không có":
                            record["status_parity"] = "win" if pred_p == actual_parity else "lose"
                        else:
                            record["status_parity"] = "ignored"
                            
                        pred_s = record.get("predicted_size")
                        if pred_s and pred_s != "Không có":
                            record["status_size"] = "win" if pred_s == actual_size else "lose"
                        else:
                            record["status_size"] = "ignored"
                            
                        self.redis_client.hset(self.key_predictions, issue, json.dumps(record))
                        updated = True
            except Exception as e:
                logger.error(f"Redis error in resolve_prediction: {e}")
                
        with self._lock:
            if hasattr(self, "_predictions") and issue in self._predictions:
                record = self._predictions[issue]
                if record.get("status_parity") == "pending" or record.get("status_size") == "pending":
                    record["actual_parity"] = actual_parity
                    record["actual_size"] = actual_size
                    
                    pred_p = record.get("predicted_parity")
                    if pred_p and pred_p != "Không có":
                        record["status_parity"] = "win" if pred_p == actual_parity else "lose"
                    else:
                        record["status_parity"] = "ignored"
                        
                    pred_s = record.get("predicted_size")
                    if pred_s and pred_s != "Không có":
                        record["status_size"] = "win" if pred_s == actual_size else "lose"
                    else:
                        record["status_size"] = "ignored"
                    updated = True
                    
        return updated

    def get_prediction_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                issues = self.redis_client.lrange(self.key_prediction_issues, 0, limit - 1)
                if not issues:
                    return []
                records_json = self.redis_client.hmget(self.key_predictions, issues)
                history = []
                for item in records_json:
                    if item:
                        history.append(json.loads(item))
                history.sort(key=lambda x: x["issue"], reverse=True)
                return history
            except Exception as e:
                logger.error(f"Redis error in get_prediction_history: {e}")
                
        with self._lock:
            if not hasattr(self, "_predictions"):
                return []
            preds = list(self._predictions.values())
            preds.sort(key=lambda x: x["issue"], reverse=True)
            return preds[:limit]

    def get_prediction_stats(self) -> dict:
        history = self.get_prediction_history(limit=1000)
        
        parity_wins = 0
        parity_losses = 0
        size_wins = 0
        size_losses = 0
        
        for item in history:
            # Exclude predictions made when there were 10 or fewer historical records (evaluate starting from 11th)
            if item.get("total_records_at_prediction", 11) <= 10:
                continue
                
            sp = item.get("status_parity")
            ss = item.get("status_size")
            
            if sp == "win":
                parity_wins += 1
            elif sp == "lose":
                parity_losses += 1
                
            if ss == "win":
                size_wins += 1
            elif ss == "lose":
                size_losses += 1
                
        total_parity = parity_wins + parity_losses
        total_size = size_wins + size_losses
        
        win_rate_parity = round(parity_wins / total_parity, 4) if total_parity > 0 else 0.0
        win_rate_size = round(size_wins / total_size, 4) if total_size > 0 else 0.0
        
        return {
            "parity": {
                "wins": parity_wins,
                "losses": parity_losses,
                "total": total_parity,
                "win_rate": win_rate_parity
            },
            "size": {
                "wins": size_wins,
                "losses": size_losses,
                "total": total_size,
                "win_rate": win_rate_size
            },
            "overall_win_rate": round((parity_wins + size_wins) / (total_parity + total_size), 4) if (total_parity + total_size) > 0 else 0.0
        }

    def log_connection_event(self, event: str, message: str) -> bool:
        log_entry = {
            "timestamp": time.time(),
            "event": event,
            "message": message,
            "lottery_code": config.LOTTERY_CODE
        }
        if self.use_redis:
            try:
                key = f"lottery:{config.LOTTERY_CODE}:socket_logs"
                self.redis_client.lpush(key, json.dumps(log_entry))
                self.redis_client.ltrim(key, 0, 499)
                return True
            except Exception as e:
                logger.error(f"Redis error in log_connection_event: {e}")
                
        with self._lock:
            if not hasattr(self, "_socket_logs"):
                self._socket_logs = []
            self._socket_logs.insert(0, log_entry)
            if len(self._socket_logs) > 500:
                self._socket_logs = self._socket_logs[:500]
        return True

    def get_connection_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                key = f"lottery:{config.LOTTERY_CODE}:socket_logs"
                logs_json = self.redis_client.lrange(key, 0, limit - 1)
                return [json.loads(x) for x in logs_json if x]
            except Exception as e:
                logger.error(f"Redis error in get_connection_logs: {e}")
                
        with self._lock:
            if not hasattr(self, "_socket_logs"):
                return []
            return self._socket_logs[:limit]

store = DataStore()
