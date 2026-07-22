import threading
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from src.config import config
from src.database.mixins.records_mixin import RecordsMixin
from src.database.mixins.predictions_mixin import PredictionsMixin
from src.database.mixins.bets_mixin import BetsMixin
from src.database.mixins.config_mixin import ConfigMixin

logger = logging.getLogger(__name__)


class DataStore(RecordsMixin, PredictionsMixin, BetsMixin, ConfigMixin):
    """
    Luu tru du lieu chinh: lich su quay so, du doan, cuoc gia lap, so du.
    Tach thanh cac Mixin de giu moi file duoi 750 dong:
      - RecordsMixin   : them/lay lich su quay so
      - PredictionsMixin: du doan, thong ke, market health
      - BetsMixin      : balance, demo bet, loss streak
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._lock = threading.RLock()
        self._history: List[Dict[str, Any]] = []
        self._seen_issues = set()
        self._predictions: Dict[str, Dict[str, Any]] = {}

        # Balances & demo
        self._real_balance = 0.0
        self._demo_balance = 10000000.0
        self._peak_demo_balance = 10000000.0
        self._demo_bet_amount = 100000.0
        self._demo_bets = {}
        self._http_cf_auth_token = ""
        self._http_cookie = ""
        self._demo_bet_strategy = "dkm_adaptive_pro"
        self._parity_loss_streak = 0
        self._size_loss_streak = 0
        self._script_command = "none"
        self._capital_collapses = []
        self._parity_daily_loss_count = 0
        self._size_daily_loss_count = 0
        self._parity_pause_until: Optional[float] = None
        self._size_pause_until: Optional[float] = None
        self._initial_phase_remaining = 10

        # Socket logs
        self._socket_logs = []

        # Redis
        self.redis_client = None
        self.use_redis = False
        redis_host = os.getenv("REDIS_HOST", "")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_password = os.getenv("REDIS_PASSWORD", "")

        if redis_host:
            try:
                import redis
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
                        logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
                        break
                    except Exception as e:
                        if attempt < 4:
                            logger.warning(f"Redis not ready (attempt {attempt+1}/5), retrying in 2s... {e}")
                            time.sleep(2)
                        else:
                            raise e
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")

        try:
            from src.database.db_migration import seed_default_data, migrate_from_json
            seed_default_data()
            migrate_from_json()
        except Exception as ex:
            logger.warning(f"DB Seeding skipped or deferred: {ex}")

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
                "initial_phase_remaining": self._initial_phase_remaining,
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
                    strat = data.get("demo_bet_strategy", "dkm_adaptive_pro")
                    from src.core.money import ALL_STRATEGIES
                    if strat not in ALL_STRATEGIES:
                        strat = "dkm_adaptive_pro"
                    self._demo_bet_strategy = strat
                    self._parity_loss_streak = data.get("parity_loss_streak", 0)
                    self._size_loss_streak = data.get("size_loss_streak", 0)
                    self._demo_bets = data.get("demo_bets", {})
                    self._capital_collapses = data.get("capital_collapses", [])
                    self._parity_daily_loss_count = data.get("parity_daily_loss_count", 0)
                    self._size_daily_loss_count = data.get("size_daily_loss_count", 0)
                    self._parity_pause_until = data.get("parity_pause_until", None)
                    self._size_pause_until = data.get("size_pause_until", None)
                    self._initial_phase_remaining = data.get("initial_phase_remaining", 10)
                logger.info(f"Loaded demo store: balance={self._demo_balance}, strategy={self._demo_bet_strategy}")
        except Exception as e:
            logger.error(f"Error loading local demo store: {e}")

    # ============================ PROPERTIES (Redis keys) ============================
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

    @property
    def key_initial_phase_remaining(self):
        return f"lottery:{config.LOTTERY_CODE}:initial_phase_remaining"

    # ============================ SOCKET LOGS ============================
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
                self._persist_connection_log_to_db(event, message)
                return True
            except Exception as e:
                logger.error(f"Redis error in log_connection_event: {e}")
        with self._lock:
            if not hasattr(self, "_socket_logs"):
                self._socket_logs = []
            self._socket_logs.insert(0, log_entry)
            if len(self._socket_logs) > 500:
                self._socket_logs = self._socket_logs[:500]
        self._persist_connection_log_to_db(event, message)
        return True

    def _persist_connection_log_to_db(self, event: str, message: str) -> None:
        """Ghi su kien ket noi WebSocket vao bang system_connection_logs trong CSDL."""
        try:
            from src.database.connection import get_db_session
            from src.database.models.system import SystemConnectionLog
            with get_db_session() as session:
                db_log = SystemConnectionLog(
                    lottery_code=config.LOTTERY_CODE,
                    event_type=event,
                    message=message,
                )
                session.add(db_log)
                logger.info(f"[DB] Saved connection_log: [{event}] {message[:60]}")
        except Exception as ex:
            logger.warning(f"[DB] connection_log persist warning: {ex}")


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

    def generate_and_save_prediction(self, next_issue: str) -> dict:
        if not next_issue:
            return {}
        existing = self.get_prediction(next_issue)
        if existing:
            return existing

        from src.core.analyzer import ProbabilityAnalyzer
        history = self.get_history(limit=500)
        stats = ProbabilityAnalyzer.analyze(history)

        ai_parity = stats.get("ai_recommendation", {}).get("parity", {}).get("decision", "BỎ QUA")
        ai_size = stats.get("ai_recommendation", {}).get("size", {}).get("decision", "BỎ QUA")

        predicted_parity = "Le" if ai_parity == "MUA LẺ" else "Chan" if ai_parity == "MUA CHẴN" else "Không có"
        predicted_size = "Tai" if ai_size == "MUA TÀI" else "Xiu" if ai_size == "MUA XỈU" else "Không có"

        parity_conf = stats.get("ai_recommendation", {}).get("parity", {}).get("confidence", 50)
        size_conf = stats.get("ai_recommendation", {}).get("size", {}).get("confidence", 50)

        pred_data = {
            "predicted_parity": predicted_parity,
            "predicted_size": predicted_size,
            "parity_confidence": parity_conf if predicted_parity != "Không có" else None,
            "size_confidence": size_conf if predicted_size != "Không có" else None,
            "total_records_at_prediction": stats.get("total_records", 0),
            "engine": stats.get("ai_recommendation", {}).get("engine", "Heuristics (3-Layer)"),
            "parity_rationale": stats.get("ai_recommendation", {}).get("parity", {}).get("rationale", ""),
            "size_rationale": stats.get("ai_recommendation", {}).get("size", {}).get("rationale", ""),
            "engine_used": stats.get("engine_used", {})
        }
        self.add_prediction(next_issue, pred_data)
        return pred_data


store = DataStore()
