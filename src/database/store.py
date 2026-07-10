import threading
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from src.config import config
from src.core.money_management import MoneyManager, KELLY_HALF_STOPLOSS_DAILY_LIMIT

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._lock = threading.RLock()
        self._history: List[Dict[str, Any]] = []
        self._seen_issues = set()
        self._predictions: Dict[str, Dict[str, Any]] = {}
        
        # Khoi tao so du va dat cuoc gia lap
        self._real_balance = 0.0
        self._demo_balance = 10000000.0
        self._peak_demo_balance = 10000000.0
        self._demo_bet_amount = 100000.0
        self._demo_bets = {} # issue -> List of bets
        self._http_cf_auth_token = ""
        self._http_cookie = ""
        self._demo_bet_strategy = "fixed"
        self._parity_loss_streak = 0
        self._size_loss_streak = 0
        self._script_command = "none"
        self._capital_collapses = []
        # Daily loss tracking cho PA3 kelly_half_stoploss
        self._parity_daily_loss_count = 0
        self._size_daily_loss_count = 0
        self._parity_pause_until: Optional[float] = None   # timestamp het tam dung
        self._size_pause_until: Optional[float] = None
        
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
                
        if not self.use_redis:
            self._load_local_store()

    def _save_local_store(self):
        if self.use_redis:
            return
        try:
            db_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(db_dir, "demo_store.json")
            data = {
                "demo_balance": self._demo_balance,
                "peak_demo_balance": self._peak_demo_balance,
                "demo_bet_amount": self._demo_bet_amount,
                "demo_bet_strategy": self._demo_bet_strategy,
                "parity_loss_streak": self._parity_loss_streak,
                "size_loss_streak": self._size_loss_streak,
                "demo_bets": self._demo_bets,
                "capital_collapses": self._capital_collapses,
                "parity_daily_loss_count": self._parity_daily_loss_count,
                "size_daily_loss_count": self._size_daily_loss_count,
                "parity_pause_until": self._parity_pause_until,
                "size_pause_until": self._size_pause_until,
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local demo store: {e}")

    def _load_local_store(self):
        if self.use_redis:
            return
        try:
            db_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(db_dir, "demo_store.json")
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._demo_balance = data.get("demo_balance", 10000000.0)
                    self._peak_demo_balance = data.get("peak_demo_balance", self._demo_balance)
                    self._demo_bet_amount = data.get("demo_bet_amount", 100000.0)
                    self._demo_bet_strategy = data.get("demo_bet_strategy", "fixed")
                    self._parity_loss_streak = data.get("parity_loss_streak", 0)
                    self._size_loss_streak = data.get("size_loss_streak", 0)
                    self._demo_bets = data.get("demo_bets", {})
                    self._capital_collapses = data.get("capital_collapses", [])
                    self._parity_daily_loss_count = data.get("parity_daily_loss_count", 0)
                    self._size_daily_loss_count = data.get("size_daily_loss_count", 0)
                    self._parity_pause_until = data.get("parity_pause_until", None)
                    self._size_pause_until = data.get("size_pause_until", None)
                logger.info(f"Loaded local demo store configuration successfully: balance={self._demo_balance}, strategy={self._demo_bet_strategy}")
        except Exception as e:
            logger.error(f"Error loading local demo store: {e}")

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

    @property
    def key_real_balance(self):
        return f"lottery:{config.LOTTERY_CODE}:real_balance"

    @property
    def key_demo_balance(self):
        return f"lottery:{config.LOTTERY_CODE}:demo_balance"

    @property
    def key_peak_demo_balance(self):
        return f"lottery:{config.LOTTERY_CODE}:peak_demo_balance"

    @property
    def key_demo_bet_amount(self):
        return f"lottery:{config.LOTTERY_CODE}:demo_bet_amount"

    @property
    def key_demo_bets(self):
        return f"lottery:{config.LOTTERY_CODE}:demo_bets"

    @property
    def key_demo_bets_list(self):
        return f"lottery:{config.LOTTERY_CODE}:demo_bets_list"

    @property
    def key_capital_collapses(self):
        return f"lottery:{config.LOTTERY_CODE}:capital_collapses"

    @property
    def key_http_cf_auth_token(self):
        return f"lottery:{config.LOTTERY_CODE}:http_cf_auth_token"

    @property
    def key_http_cookie(self):
        return f"lottery:{config.LOTTERY_CODE}:http_cookie"

    @property
    def key_demo_bet_strategy(self):
        return f"lottery:{config.LOTTERY_CODE}:demo_bet_strategy"

    @property
    def key_parity_loss_streak(self):
        return f"lottery:{config.LOTTERY_CODE}:parity_loss_streak"

    @property
    def key_size_loss_streak(self):
        return f"lottery:{config.LOTTERY_CODE}:size_loss_streak"

    @property
    def key_parity_daily_loss_count(self):
        return f"lottery:{config.LOTTERY_CODE}:parity_daily_loss_count"

    @property
    def key_size_daily_loss_count(self):
        return f"lottery:{config.LOTTERY_CODE}:size_daily_loss_count"

    @property
    def key_parity_pause_until(self):
        return f"lottery:{config.LOTTERY_CODE}:parity_pause_until"

    @property
    def key_size_pause_until(self):
        return f"lottery:{config.LOTTERY_CODE}:size_pause_until"

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
                        # Cho phép cả kỳ quay đầy đủ số (len=5) và kỳ nạp thống kê tính sẵn (len=0)
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
                    self.key_records, 
                    self.key_history_issues, 
                    self.key_predictions, 
                    self.key_prediction_issues,
                    self.key_parity_loss_streak,
                    self.key_size_loss_streak
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
            self._save_local_store()

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
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "engine": prediction_data.get("engine", "Heuristics (3-Layer)"),
            "parity_rationale": prediction_data.get("parity_rationale", ""),
            "size_rationale": prediction_data.get("size_rationale", "")
        }
        
        added = False
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
                    added = True
            except Exception as e:
                logger.error(f"Redis error in add_prediction: {e}")
                
        else:
            with self._lock:
                if not hasattr(self, "_predictions"):
                    self._predictions = {}
                if issue not in self._predictions:
                    self._predictions[issue] = record
                    if len(self._predictions) > 1000:
                        oldest_key = min(self._predictions.keys(), key=lambda k: self._predictions[k]["timestamp"])
                        self._predictions.pop(oldest_key, None)
                    added = True
                    
        if added:
            # Tu dong dat cuoc gia lap neu khong phai "Khong co"
            bet_amt = self.get_balances()["demo_bet_amount"]
            pred_p = record.get("predicted_parity")
            if pred_p and pred_p != "Không có":
                dec_p = "MUA LẺ" if pred_p == "Le" else "MUA CHẴN"
                result_p = self.place_demo_bet(issue, "parity", dec_p, bet_amt)
                if result_p == "insufficient_balance":
                    logger.warning(f"[DEMO] Skipped parity bet for {issue}: insufficient balance.")
                
            pred_s = record.get("predicted_size")
            if pred_s and pred_s != "Không có":
                dec_s = "MUA TÀI" if pred_s == "Tai" else "MUA XỈU"
                result_s = self.place_demo_bet(issue, "size", dec_s, bet_amt)
                if result_s == "insufficient_balance":
                    logger.warning(f"[DEMO] Skipped size bet for {issue}: insufficient balance.")
                    
        return added

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
                
        else:
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
                        
        if updated:
            self.resolve_demo_bets(issue, numbers)
            try:
                self.write_market_health_log()
            except Exception as e:
                logger.error(f"Error writing market health log: {e}")
            
        return updated


    def get_prediction(self, issue: str) -> Optional[Dict[str, Any]]:
        if self.use_redis:
            try:
                record_json = self.redis_client.hget(self.key_predictions, issue)
                if record_json:
                    return json.loads(record_json)
                return None
            except Exception as e:
                logger.error(f"Redis error in get_prediction: {e}")
                return None
        with self._lock:
            if hasattr(self, "_predictions") and issue in self._predictions:
                return self._predictions[issue]
            return None

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

    def get_prediction_stats_recent(self, limit: int = 15) -> dict:
        history = self.get_prediction_history(limit=1000)
        
        # Parity
        parity_wins = 0
        parity_losses = 0
        parity_total = 0
        for item in history:
            if item.get("total_records_at_prediction", 11) <= 10:
                continue
            sp = item.get("status_parity")
            if sp in ("win", "lose"):
                if sp == "win":
                    parity_wins += 1
                else:
                    parity_losses += 1
                parity_total += 1
                if parity_total >= limit:
                    break
                    
        # Size
        size_wins = 0
        size_losses = 0
        size_total = 0
        for item in history:
            if item.get("total_records_at_prediction", 11) <= 10:
                continue
            ss = item.get("status_size")
            if ss in ("win", "lose"):
                if ss == "win":
                    size_wins += 1
                else:
                    size_losses += 1
                size_total += 1
                if size_total >= limit:
                    break
                    
        win_rate_parity = round(parity_wins / parity_total, 4) if parity_total > 0 else 0.0
        win_rate_size = round(size_wins / size_total, 4) if size_total > 0 else 0.0
        
        return {
            "parity": {
                "wins": parity_wins,
                "losses": parity_losses,
                "total": parity_total,
                "win_rate": win_rate_parity
            },
            "size": {
                "wins": size_wins,
                "losses": size_losses,
                "total": size_total,
                "win_rate": win_rate_size
            }
        }

    def is_market_stable(self) -> bool:
        history = self.get_prediction_history(limit=1000)
        resolved_items = []
        for item in history:
            if item.get("total_records_at_prediction", 11) <= 10:
                continue
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose") or ss in ("win", "lose"):
                resolved_items.append(item)
            if len(resolved_items) >= 30:
                break
                
        if len(resolved_items) < 30:
            return True
            
        total_bets = 0
        wins = 0
        for item in resolved_items:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose"):
                total_bets += 1
                if sp == "win":
                    wins += 1
            if ss in ("win", "lose"):
                total_bets += 1
                if ss == "win":
                    wins += 1
                    
        win_rate_pct = (wins / total_bets * 100) if total_bets > 0 else 0.0
        return win_rate_pct >= 53.0

    def write_market_health_log(self) -> None:
        history = self.get_prediction_history(limit=1000)
        resolved_items = []
        for item in history:
            if item.get("total_records_at_prediction", 11) <= 10:
                continue
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose") or ss in ("win", "lose"):
                resolved_items.append(item)
            if len(resolved_items) >= 30:
                break
                
        log_file_path = os.path.join(os.getcwd(), "market_health_30.log")
        
        if len(resolved_items) < 30:
            header = (
                "Khối 30 kỳ gần nhất: -\n"
                "Hiệu suất thắng: -\n"
                "Phạm Vi Kỳ\tThời Gian\tSố Lượt Cược\tTỷ Lệ Thắng\tTrạng Thái\n"
            )
            content = header + "Chưa có đủ 30 kỳ để phân tích. Để quan sát ghi nhận lại những thời điểm hỗn loạn mà hệ thống chúng ta hay gặp phải.\n"
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return
            
        end_issue = resolved_items[0]["issue"]
        start_issue = resolved_items[-1]["issue"]
        issue_range = f"{start_issue}-{end_issue}"
        
        total_bets = 0
        wins = 0
        for item in resolved_items:
            sp = item.get("status_parity")
            ss = item.get("status_size")
            if sp in ("win", "lose"):
                total_bets += 1
                if sp == "win":
                    wins += 1
            if ss in ("win", "lose"):
                total_bets += 1
                if ss == "win":
                    wins += 1
                    
        win_rate_pct = (wins / total_bets * 100) if total_bets > 0 else 0.0
        status = "Ổn định" if win_rate_pct >= 53.0 else "Hỗn loạn"
        
        existing_rows = []
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines:
                    parts = line.strip().split("\t")
                    if len(parts) >= 5 and parts[0] != "Phạm Vi Kỳ":
                        existing_rows.append(line.strip())
            except Exception:
                pass
                
        current_time_str = time.strftime("%H:%M:%S %d/%m/%Y")
        new_row = f"{issue_range}\t{current_time_str}\t{total_bets}\t{win_rate_pct:.1f}%\t{status}"
        
        if not any(row.startswith(issue_range) for row in existing_rows):
            existing_rows.append(new_row)
            
        header = (
            f"Khối 30 kỳ gần nhất: {start_issue} - {end_issue}\n"
            f"Hiệu suất thắng: {wins}/{total_bets} ({win_rate_pct:.1f}%)\n"
            "Phạm Vi Kỳ\tThời Gian\tSố Lượt Cược\tTỷ Lệ Thắng\tTrạng Thái\n"
        )
        
        table_content = "\n".join(existing_rows[-100:]) + "\n"
        
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(header + table_content)

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

    def get_balances(self) -> Dict[str, Any]:
        if self.use_redis:
            try:
                real = self.redis_client.get(self.key_real_balance)
                demo = self.redis_client.get(self.key_demo_balance)
                peak = self.redis_client.get(self.key_peak_demo_balance)
                bet_amt = self.redis_client.get(self.key_demo_bet_amount)
                strategy = self.redis_client.get(self.key_demo_bet_strategy)
                
                # Support decoding bytes response from Redis
                strategy_str = "fixed"
                if strategy:
                    try:
                        strategy_str = strategy.decode('utf-8')
                    except AttributeError:
                        strategy_str = str(strategy)
                
                return {
                    "real_balance": float(real) if real else 0.0,
                    "demo_balance": float(demo) if demo else 10000000.0,
                    "peak_demo_balance": float(peak) if peak else 10000000.0,
                    "demo_bet_amount": float(bet_amt) if bet_amt else 100000.0,
                    "demo_bet_strategy": strategy_str
                }
            except Exception as e:
                logger.error(f"Redis error in get_balances: {e}")
                
        with self._lock:
            return {
                "real_balance": self._real_balance,
                "demo_balance": self._demo_balance,
                "peak_demo_balance": self._peak_demo_balance,
                "demo_bet_amount": self._demo_bet_amount,
                "demo_bet_strategy": self._demo_bet_strategy
            }

    def update_demo_balance(self, balance: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_balance, balance)
                self.redis_client.set(self.key_peak_demo_balance, balance)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_demo_balance: {e}")
        with self._lock:
            self._demo_balance = balance
            self._peak_demo_balance = balance
            self._save_local_store()
        return True

    def set_demo_bet_strategy(self, strategy: str):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_bet_strategy, strategy)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_demo_bet_strategy: {e}")
        with self._lock:
            self._demo_bet_strategy = strategy
            self._save_local_store()
        return True

    def get_loss_streaks(self) -> Dict[str, int]:
        if self.use_redis:
            try:
                p_streak = self.redis_client.get(self.key_parity_loss_streak)
                s_streak = self.redis_client.get(self.key_size_loss_streak)
                return {
                    "parity": int(p_streak) if p_streak else 0,
                    "size": int(s_streak) if s_streak else 0
                }
            except Exception as e:
                logger.error(f"Redis error in get_loss_streaks: {e}")
                
        with self._lock:
            return {
                "parity": self._parity_loss_streak,
                "size": self._size_loss_streak
            }

    def update_loss_streak(self, market_type: str, is_win: bool):
        if self.use_redis:
            try:
                streak_key = self.key_parity_loss_streak if market_type == "parity" else self.key_size_loss_streak
                daily_key = self.key_parity_daily_loss_count if market_type == "parity" else self.key_size_daily_loss_count
                if is_win:
                    self.redis_client.set(streak_key, 0)
                else:
                    self.redis_client.incr(streak_key)
                    self.redis_client.incr(daily_key)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_loss_streak: {e}")
                
        with self._lock:
            if market_type == "parity":
                if is_win:
                    self._parity_loss_streak = 0
                else:
                    self._parity_loss_streak += 1
                    self._parity_daily_loss_count += 1
            else:
                if is_win:
                    self._size_loss_streak = 0
                else:
                    self._size_loss_streak += 1
                    self._size_daily_loss_count += 1
            self._save_local_store()
        return True

    def update_real_balance(self, balance: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_real_balance, balance)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_real_balance: {e}")
                
        with self._lock:
            self._real_balance = balance
        return True

    def reset_demo_balance(self):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_balance, 10000000.0)
                self.redis_client.set(self.key_peak_demo_balance, 10000000.0)
                self.redis_client.delete(
                    self.key_demo_bets, self.key_demo_bets_list, self.key_capital_collapses,
                    self.key_parity_daily_loss_count, self.key_size_daily_loss_count,
                    self.key_parity_pause_until, self.key_size_pause_until
                )
                self.redis_client.set(self.key_parity_loss_streak, 0)
                self.redis_client.set(self.key_size_loss_streak, 0)
                return True
            except Exception as e:
                logger.error(f"Redis error in reset_demo_balance: {e}")
                
        with self._lock:
            self._demo_balance = 10000000.0
            self._peak_demo_balance = 10000000.0
            self._demo_bets.clear()
            self._capital_collapses.clear()
            self._parity_loss_streak = 0
            self._size_loss_streak = 0
            self._parity_daily_loss_count = 0
            self._size_daily_loss_count = 0
            self._parity_pause_until = None
            self._size_pause_until = None
            self._save_local_store()
        return True

    def clear_demo_bets(self):
        if self.use_redis:
            try:
                demo_bal = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                self.redis_client.set(self.key_peak_demo_balance, demo_bal)
                self.redis_client.delete(
                    self.key_demo_bets, self.key_demo_bets_list, self.key_capital_collapses,
                    self.key_parity_daily_loss_count, self.key_size_daily_loss_count,
                    self.key_parity_pause_until, self.key_size_pause_until
                )
                self.redis_client.set(self.key_parity_loss_streak, 0)
                self.redis_client.set(self.key_size_loss_streak, 0)
                return True
            except Exception as e:
                logger.error(f"Redis error in clear_demo_bets: {e}")
                
        with self._lock:
            self._peak_demo_balance = self._demo_balance
            self._demo_bets.clear()
            self._capital_collapses.clear()
            self._parity_loss_streak = 0
            self._size_loss_streak = 0
            self._parity_daily_loss_count = 0
            self._size_daily_loss_count = 0
            self._parity_pause_until = None
            self._size_pause_until = None
            self._save_local_store()
        return True

    def set_demo_bet_amount(self, amount: float):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_demo_bet_amount, amount)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_demo_bet_amount: {e}")
                
        with self._lock:
            self._demo_bet_amount = amount
            self._save_local_store()
        return True

    def get_demo_bets(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                issues = self.redis_client.lrange(self.key_demo_bets_list, 0, limit - 1)
                if not issues:
                    return []
                bets_json = self.redis_client.hmget(self.key_demo_bets, issues)
                all_bets = []
                for x in bets_json:
                    if x:
                        all_bets.extend(json.loads(x))
                all_bets.sort(key=lambda x: x["issue"], reverse=True)
                return all_bets[:limit]
            except Exception as e:
                logger.error(f"Redis error in get_demo_bets: {e}")
                
        with self._lock:
            flat_bets = []
            for issue, bets in self._demo_bets.items():
                flat_bets.extend(bets)
            flat_bets.sort(key=lambda x: x["issue"], reverse=True)
            return flat_bets[:limit]

    def get_daily_loss_info(self) -> Dict[str, Any]:
        """Lay thong tin daily loss count va pause_until cho ca 2 thi truong."""
        now = time.time()
        if self.use_redis:
            try:
                p_daily = self.redis_client.get(self.key_parity_daily_loss_count)
                s_daily = self.redis_client.get(self.key_size_daily_loss_count)
                p_pause = self.redis_client.get(self.key_parity_pause_until)
                s_pause = self.redis_client.get(self.key_size_pause_until)
                
                p_daily_val = int(p_daily) if p_daily else 0
                s_daily_val = int(s_daily) if s_daily else 0
                p_pause_val = float(p_pause) if p_pause else None
                s_pause_val = float(s_pause) if s_pause else None
                
                p_expired = p_pause_val is not None and now >= p_pause_val
                s_expired = s_pause_val is not None and now >= s_pause_val
                
                if p_expired or s_expired:
                    current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                    self.redis_client.set(self.key_peak_demo_balance, current_demo)
                    
                if p_expired:
                    self.redis_client.set(self.key_parity_daily_loss_count, 0)
                    self.redis_client.delete(self.key_parity_pause_until)
                    p_daily_val = 0
                    p_pause_val = None
                    
                if s_expired:
                    self.redis_client.set(self.key_size_daily_loss_count, 0)
                    self.redis_client.delete(self.key_size_pause_until)
                    s_daily_val = 0
                    s_pause_val = None
                    
                return {
                    "parity_daily_loss_count": p_daily_val,
                    "size_daily_loss_count": s_daily_val,
                    "parity_pause_until": p_pause_val,
                    "size_pause_until": s_pause_val,
                }
            except Exception as e:
                logger.error(f"Redis error in get_daily_loss_info: {e}")
                
        with self._lock:
            p_expired = self._parity_pause_until is not None and now >= self._parity_pause_until
            s_expired = self._size_pause_until is not None and now >= self._size_pause_until
            
            if p_expired or s_expired:
                self._peak_demo_balance = self._demo_balance
                
            if p_expired:
                self._parity_daily_loss_count = 0
                self._parity_pause_until = None
                
            if s_expired:
                self._size_daily_loss_count = 0
                self._size_pause_until = None
                
            if p_expired or s_expired:
                self._save_local_store()
                
            return {
                "parity_daily_loss_count": self._parity_daily_loss_count,
                "size_daily_loss_count": self._size_daily_loss_count,
                "parity_pause_until": self._parity_pause_until,
                "size_pause_until": self._size_pause_until,
            }

    def place_demo_bet(self, issue: str, market_type: str, prediction: str, amount: float):
        if not issue or not prediction or prediction in ("Khong co", "BO QUA", "Kh\u00f4ng c\u00f3", "B\u1ecf QUA"):
            return False

        balances = self.get_balances()
        base_amount = balances["demo_bet_amount"]
        strategy = balances["demo_bet_strategy"]
        current_balance = balances["demo_balance"]

        loss_streaks = self.get_loss_streaks()
        streak = loss_streaks.get(market_type, 0)

        daily_info = self.get_daily_loss_info()
        daily_loss_count = daily_info.get(f"{market_type}_daily_loss_count", 0)
        pause_until = daily_info.get(f"{market_type}_pause_until", None)

        # Determine if market is stable (for the 30-period check)
        is_stable = self.is_market_stable()

        # Lay win rate thuc te tu 15 ky gan nhat cho cac chien thuat Kelly
        prediction_stats_recent = self.get_prediction_stats_recent(15)
        win_rate = __import__("src.core.money_management", fromlist=["get_effective_win_rate"]).get_effective_win_rate(
            prediction_stats_recent, market_type
        )

        final_amount = MoneyManager.calculate_bet(
            strategy=strategy,
            base_amount=base_amount,
            current_balance=current_balance,
            loss_streak=streak,
            daily_loss_count=daily_loss_count,
            pause_until=pause_until,
            win_rate=win_rate,
            is_stable=is_stable,
        )

        # PA3: bo qua ky nay do dang bi tam dung
        if final_amount == 0.0:
            logger.info(f"[place_demo_bet] Ky {issue} ({market_type}): bi tam dung hoac het gioi han ngay. Bo qua.")
            return "paused"

        # --- OVERDRAFT GUARD: skip bet if balance is insufficient ---
        current_balance = balances["demo_balance"]
        if final_amount > current_balance:
            logger.warning(
                f"[OVERDRAFT] Skipping {market_type} bet for issue {issue}: "
                f"required {final_amount} > balance {current_balance}"
            )
            self.log_capital_collapse(
                issue=issue,
                market_type=market_type,
                loss_streak=streak,
                amount_required=final_amount,
                balance_current=current_balance,
                base_amount=base_amount,
                strategy=strategy
            )
            return "insufficient_balance"
            
        bet = {
            "issue": issue,
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "market_type": market_type,
            "prediction": prediction,
            "amount": final_amount,
            "status": "pending",
            "win_amount": 0.0,
            "balance_after": 0.0
        }
        
        if self.use_redis:
            try:
                current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                # Double-check under Redis read
                if final_amount > current_demo:
                    logger.warning(f"[OVERDRAFT][Redis] Skipping bet for {issue}, insufficient balance.")
                    self.log_capital_collapse(
                        issue=issue,
                        market_type=market_type,
                        loss_streak=streak,
                        amount_required=final_amount,
                        balance_current=current_demo,
                        base_amount=base_amount,
                        strategy=strategy
                    )
                    return "insufficient_balance"
                new_demo = current_demo - final_amount
                self.redis_client.set(self.key_demo_balance, new_demo)
                
                existing_json = self.redis_client.hget(self.key_demo_bets, issue)
                existing_bets = json.loads(existing_json) if existing_json else []
                bet["balance_after"] = new_demo
                existing_bets.append(bet)
                
                self.redis_client.hset(self.key_demo_bets, issue, json.dumps(existing_bets))
                if not existing_json:
                    self.redis_client.lpush(self.key_demo_bets_list, issue)
                return True
            except Exception as e:
                logger.error(f"Redis error in place_demo_bet: {e}")
                
        with self._lock:
            self._demo_balance = self._demo_balance - final_amount
            bet["balance_after"] = self._demo_balance
            if issue not in self._demo_bets:
                self._demo_bets[issue] = []
            self._demo_bets[issue].append(bet)
            self._save_local_store()
        return True

    def resolve_demo_bets(self, issue: str, numbers: List[int]):
        if not issue or not numbers or len(numbers) != 5:
            return False
            
        total = sum(numbers)
        actual_parity = "MUA LẺ" if total % 2 != 0 else "MUA CHẴN"
        actual_size = "MUA TÀI" if total > 22 else "MUA XỈU"
        
        updated = False
        if self.use_redis:
            try:
                existing_json = self.redis_client.hget(self.key_demo_bets, issue)
                if existing_json:
                    existing_bets = json.loads(existing_json)
                    current_demo = float(self.redis_client.get(self.key_demo_balance) or 10000000.0)
                    peak_demo = float(self.redis_client.get(self.key_peak_demo_balance) or current_demo)
                    
                    for bet in existing_bets:
                        if bet.get("status") == "pending":
                            actual = actual_parity if bet["market_type"] == "parity" else actual_size
                            is_win = (bet["prediction"] == actual)
                            if is_win:
                                bet["status"] = "win"
                                bet["win_amount"] = bet["amount"] * 1.95
                                current_demo += bet["win_amount"]
                            else:
                                bet["status"] = "lose"
                                bet["win_amount"] = 0.0
                                
                            self.update_loss_streak(bet["market_type"], is_win)
                            bet["balance_after"] = current_demo
                            updated = True
                            
                    if updated:
                        # Update peak
                        if current_demo > peak_demo:
                            peak_demo = current_demo
                            self.redis_client.set(self.key_peak_demo_balance, peak_demo)
                            
                        # Check 25% drawdown
                        if current_demo <= peak_demo * 0.75:
                            pause_ts = time.time() + 10 * 60
                            self.redis_client.set(self.key_parity_pause_until, pause_ts)
                            self.redis_client.set(self.key_size_pause_until, pause_ts)
                            logger.warning(f"[DRAWDOWN] Demo balance {current_demo} dropped by 25% or more from peak {peak_demo}. Pausing both markets for 10m.")
                            
                        self.redis_client.set(self.key_demo_balance, current_demo)
                        self.redis_client.hset(self.key_demo_bets, issue, json.dumps(existing_bets))
                return updated
            except Exception as e:
                logger.error(f"Redis error in resolve_demo_bets: {e}")
                
        with self._lock:
            if issue in self._demo_bets:
                for bet in self._demo_bets[issue]:
                    if bet.get("status") == "pending":
                        actual = actual_parity if bet["market_type"] == "parity" else actual_size
                        is_win = (bet["prediction"] == actual)
                        if is_win:
                            bet["status"] = "win"
                            bet["win_amount"] = bet["amount"] * 1.95
                            self._demo_balance += bet["win_amount"]
                        else:
                            bet["status"] = "lose"
                            bet["win_amount"] = 0.0
                            
                        self.update_loss_streak(bet["market_type"], is_win)
                        bet["balance_after"] = self._demo_balance
                        updated = True
                if updated:
                    # Update peak
                    if self._demo_balance > self._peak_demo_balance:
                        self._peak_demo_balance = self._demo_balance
                        
                    # Check 25% drawdown
                    if self._demo_balance <= self._peak_demo_balance * 0.75:
                        pause_ts = time.time() + 10 * 60
                        self._parity_pause_until = pause_ts
                        self._size_pause_until = pause_ts
                        logger.warning(f"[DRAWDOWN] Demo balance {self._demo_balance} dropped by 25% or more from peak {self._peak_demo_balance}. Pausing both markets for 10m.")
                        
                    self._save_local_store()
        return updated

    def update_http_headers(self, cf_auth_token: str, cookie: Optional[str] = None):
        if self.use_redis:
            try:
                self.redis_client.set(self.key_http_cf_auth_token, cf_auth_token)
                if cookie:
                    self.redis_client.set(self.key_http_cookie, cookie)
                return True
            except Exception as e:
                logger.error(f"Redis error in update_http_headers: {e}")
                
        with self._lock:
            self._http_cf_auth_token = cf_auth_token
            if cookie:
                self._http_cookie = cookie
        return True

    def get_http_headers(self) -> Dict[str, str]:
        if self.use_redis:
            try:
                cf_auth = self.redis_client.get(self.key_http_cf_auth_token)
                cookie = self.redis_client.get(self.key_http_cookie)
                return {
                    "cf_auth_token": cf_auth or "",
                    "cookie": cookie or ""
                }
            except Exception as e:
                logger.error(f"Redis error in get_http_headers: {e}")
                
        with self._lock:
            return {
                "cf_auth_token": self._http_cf_auth_token,
                "cookie": self._http_cookie
            }

    def set_script_command(self, cmd: str):
        if self.use_redis:
            try:
                self.redis_client.set(f"lottery:{config.LOTTERY_CODE}:script_command", cmd)
                return True
            except Exception as e:
                logger.error(f"Redis error in set_script_command: {e}")
        with self._lock:
            self._script_command = cmd
        return True

    def get_script_command(self) -> str:
        if self.use_redis:
            try:
                key = f"lottery:{config.LOTTERY_CODE}:script_command"
                cmd = self.redis_client.get(key)
                if cmd:
                    cmd_str = cmd.decode('utf-8') if hasattr(cmd, 'decode') else str(cmd)
                    self.redis_client.set(key, "none")
                    return cmd_str
                return "none"
            except Exception as e:
                logger.error(f"Redis error in get_script_command: {e}")
        with self._lock:
            cmd = self._script_command
            self._script_command = "none"
            return cmd

    def log_capital_collapse(self, issue: str, market_type: str, loss_streak: int, amount_required: float, balance_current: float, base_amount: float, strategy: str):
        collapse = {
            "timestamp": time.time(),
            "time": time.strftime("%H:%M:%S %d/%m/%Y"),
            "issue": issue,
            "market_type": market_type,
            "loss_streak": loss_streak,
            "amount_required": amount_required,
            "balance_current": balance_current,
            "base_amount": base_amount,
            "strategy": strategy
        }
        if self.use_redis:
            try:
                self.redis_client.lpush(self.key_capital_collapses, json.dumps(collapse))
                self.redis_client.ltrim(self.key_capital_collapses, 0, 49)
                return True
            except Exception as e:
                logger.error(f"Redis error in log_capital_collapse: {e}")
        with self._lock:
            self._capital_collapses.insert(0, collapse)
            self._capital_collapses = self._capital_collapses[:50]
            self._save_local_store()
        return True

    def get_capital_collapses(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self.use_redis:
            try:
                collapses = self.redis_client.lrange(self.key_capital_collapses, 0, limit - 1)
                return [json.loads(c) for c in collapses if c]
            except Exception as e:
                logger.error(f"Redis error in get_capital_collapses: {e}")
                return []
        with self._lock:
            return self._capital_collapses[:limit]

    def clear_capital_collapses(self):
        if self.use_redis:
            try:
                self.redis_client.delete(self.key_capital_collapses)
                return True
            except Exception as e:
                logger.error(f"Redis error in clear_capital_collapses: {e}")
        with self._lock:
            self._capital_collapses.clear()
            self._save_local_store()
        return True

store = DataStore()
