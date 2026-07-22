import time
import logging
from typing import Dict, Any
from src.config import config

logger = logging.getLogger(__name__)

# Fallback values khi DB chua co du lieu
_PARITY_DEFAULTS = {
    "n_sliding_min": 12, "n_sliding_max": 20, "n_sliding_ratio": 0.20,
    "ar_window_min": 10, "ar_window_max": 30, "ar_window_ratio": 0.25,
    "ar_threshold_multiplier": 0.85, "ar_threshold_min": 0.70, "ar_threshold_max": 0.88,
    "n_recent_min": 6, "n_recent_max": 14, "n_recent_ratio": 0.12,
    "streak_confidence_threshold": 0.90, "streak_min_samples": 3,
    "streak_safety_trap_multiplier": 1.5, "streak_safety_trap_min": 4,
    "saturation_percentile": 68.0, "saturation_limit_min": 0.52, "saturation_limit_max": 0.78,
    "cooling_off_loss_limit": 2, "win_streak_pause_limit": 2,
    "buy_threshold_multiplier": 0.45, "buy_threshold_min": 0.55, "buy_threshold_max": 0.82,
    "min_probability_threshold": 0.55, "ma50_window": 30, "ma50_filter_active": False,
    "win_rate_filter_window": 10, "win_rate_filter_min_total": 4, "win_rate_filter_threshold": 0.52,
    "reversal_threshold": 0.85, "volatility_penalty": 1.2,
}

_SIZE_DEFAULTS = {
    "n_sliding_min": 12, "n_sliding_max": 20, "n_sliding_ratio": 0.20,
    "ar_window_min": 10, "ar_window_max": 30, "ar_window_ratio": 0.25,
    "ar_threshold_multiplier": 0.85, "ar_threshold_min": 0.70, "ar_threshold_max": 0.88,
    "n_recent_min": 6, "n_recent_max": 14, "n_recent_ratio": 0.12,
    "streak_confidence_threshold": 0.90, "streak_min_samples": 3,
    "streak_safety_trap_multiplier": 1.5, "streak_safety_trap_min": 4,
    "saturation_percentile": 68.0, "saturation_limit_min": 0.52, "saturation_limit_max": 0.78,
    "cooling_off_loss_limit": 2, "win_streak_pause_limit": 2,
    "buy_threshold_multiplier": 0.45, "buy_threshold_min": 0.55, "buy_threshold_max": 0.82,
    "min_probability_threshold": 0.55, "ma50_window": 30, "ma50_filter_active": False,
    "win_rate_filter_window": 10, "win_rate_filter_min_total": 4, "win_rate_filter_threshold": 0.52,
    "reversal_threshold": 0.85, "volatility_penalty": 1.2,
}

_DEFAULTS_BY_MARKET = {
    "parity": _PARITY_DEFAULTS,
    "size": _SIZE_DEFAULTS,
}

# In-memory cache: { "parity": {"data": {...}, "ts": float}, "size": {...} }
_config_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 60  # seconds


class ConfigMixin:
    def get_analyzer_config(self, market_type: str) -> Dict[str, Any]:
        """
        Nap bo tham so phan tich tu DB (analyzer_configs).
        - Uu tien: preset is_active=True, sap xep updated_at DESC.
        - Cache in-memory 60s de tranh query moi lan analyze.
        - Fallback ve gia tri mac dinh neu DB khong co du lieu.
        """
        now = time.time()
        cached = _config_cache.get(market_type)
        if cached and (now - cached["ts"]) < _CACHE_TTL:
            return cached["data"]

        defaults = _DEFAULTS_BY_MARKET.get(market_type, _PARITY_DEFAULTS)
        result = defaults.copy()

        try:
            from src.database.connection import get_db_session
            from src.database.models.system import AnalyzerConfig

            with get_db_session() as session:
                cfg_obj = (
                    session.query(AnalyzerConfig)
                    .filter_by(
                        lottery_code=config.LOTTERY_CODE,
                        market_type=market_type,
                        is_active=True,
                    )
                    .order_by(AnalyzerConfig.updated_at.desc())
                    .first()
                )
                if cfg_obj:
                    db_dict = {
                        col.name: getattr(cfg_obj, col.name)
                        for col in cfg_obj.__table__.columns
                        if col.name in defaults
                    }
                    result.update(db_dict)
                    logger.info(
                        f"[ConfigMixin] Loaded analyzer_config [{market_type}] "
                        f"preset='{cfg_obj.preset_name}' from DB"
                    )
                else:
                    logger.warning(
                        f"[ConfigMixin] No active analyzer_config for [{market_type}], "
                        f"using defaults"
                    )
        except Exception as ex:
            logger.warning(f"[ConfigMixin] DB read failed for [{market_type}]: {ex}, using defaults")

        _config_cache[market_type] = {"data": result, "ts": now}
        return result

    def invalidate_analyzer_config_cache(self):
        """Xoa cache khi nguoi dung cap nhat tham so qua UI."""
        _config_cache.clear()
        logger.info("[ConfigMixin] Analyzer config cache invalidated")

    def calculate_optimal_retention_limit(self) -> int:
        """
        Thuat toan tu dong tinh toan so ky luu giu toi uu de Win Rate dat muc cao nhat:
        MaxWindow = max(n_sliding_max, ar_window_max, win_rate_filter_window * 2, ma50_window, n_recent_max, 100)
        OptimalLimit = max(int(MaxWindow * 3.0), 300)
        """
        try:
            parity_cfg = self.get_analyzer_config("parity")
            size_cfg = self.get_analyzer_config("size")

            p_sliding = parity_cfg.get("n_sliding_max", 20)
            s_sliding = size_cfg.get("n_sliding_max", 20)
            p_ar = parity_cfg.get("ar_window_max", 30)
            s_ar = size_cfg.get("ar_window_max", 30)
            p_wr = parity_cfg.get("win_rate_filter_window", 10) * 2
            s_wr = size_cfg.get("win_rate_filter_window", 10) * 2
            p_ma = parity_cfg.get("ma50_window", 30)
            s_ma = size_cfg.get("ma50_window", 30)
            p_rec = parity_cfg.get("n_recent_max", 14)
            s_rec = size_cfg.get("n_recent_max", 14)

            max_win = max(p_sliding, s_sliding, p_ar, s_ar, p_wr, s_wr, p_ma, s_ma, p_rec, s_rec, 100)
            optimal_limit = max(int(max_win * 3.0), 300)
            return optimal_limit
        except Exception as ex:
            logger.warning(f"[ConfigMixin] Dynamic retention limit calculation failed: {ex}, fallback 500")
            return 500

