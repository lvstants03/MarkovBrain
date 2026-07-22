import os
import json
import logging
from datetime import datetime
from src.config import config
from src.database.connection import init_db, get_db_session
from src.database.models import (
    User, Lottery, AnalyzerConfig, SystemParameter, UserBalance, Bet
)

logger = logging.getLogger(__name__)

def _run_alter_migrations(engine):
    """Chay ALTER TABLE de bo sung cac cot con thieu vao analyzer_configs.
    Dung AUTOCOMMIT de tranh PostgreSQL abort toan bo transaction khi cot da ton tai.
    """
    from sqlalchemy import text
    new_columns = [
        ("ar_threshold_multiplier",      "FLOAT DEFAULT 0.85"),
        ("n_recent_min",                 "INTEGER DEFAULT 6"),
        ("n_recent_max",                 "INTEGER DEFAULT 14"),
        ("n_recent_ratio",               "FLOAT DEFAULT 0.12"),
        ("streak_confidence_threshold",  "FLOAT DEFAULT 0.90"),
        ("streak_min_samples",           "INTEGER DEFAULT 3"),
        ("streak_safety_trap_multiplier","FLOAT DEFAULT 1.5"),
        ("streak_safety_trap_min",       "INTEGER DEFAULT 4"),
        ("saturation_percentile",        "FLOAT DEFAULT 68.0"),
        ("saturation_limit_min",         "FLOAT DEFAULT 0.52"),
        ("saturation_limit_max",         "FLOAT DEFAULT 0.78"),
        ("cooling_off_loss_limit",       "INTEGER DEFAULT 2"),
        ("win_streak_pause_limit",       "INTEGER DEFAULT 2"),
        ("buy_threshold_multiplier",     "FLOAT DEFAULT 0.45"),
        ("ma50_window",                  "INTEGER DEFAULT 30"),
        ("win_rate_filter_window",       "INTEGER DEFAULT 10"),
        ("win_rate_filter_min_total",    "INTEGER DEFAULT 4"),
        ("win_rate_filter_threshold",    "FLOAT DEFAULT 0.52"),
        ("volatility_penalty",           "FLOAT DEFAULT 1.2"),
        ("preset_name",                  "VARCHAR(50) DEFAULT 'default'"),
        ("is_active",                    "BOOLEAN DEFAULT TRUE"),
    ]
    # Moi cot dung mot connection rieng biet voi AUTOCOMMIT
    # de tranh PostgreSQL loi "current transaction is aborted"
    for col_name, col_def in new_columns:
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(
                    f"ALTER TABLE analyzer_configs ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
                ))
            logger.info(f"Migration: ensured column analyzer_configs.{col_name}")
        except Exception as ex:
            logger.debug(f"Migration skip {col_name}: {ex}")

    # Migration unique constraint: Drop uk_analyzer_config_lottery_market cu, add uk_analyzer_config_preset (3 cot)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(
                "ALTER TABLE analyzer_configs DROP CONSTRAINT IF EXISTS uk_analyzer_config_lottery_market"
            ))
            # Dam bao index/constraint uk_analyzer_config_preset ton tai voi 3 cot
            conn.execute(text(
                "ALTER TABLE analyzer_configs ADD CONSTRAINT uk_analyzer_config_preset UNIQUE (lottery_code, market_type, preset_name)"
            ))
        logger.info("Migration: updated unique constraint on analyzer_configs to include preset_name")
    except Exception as ex:
        logger.debug(f"Migration constraint update skip or already present: {ex}")


def seed_default_data():
    """Nap bo tham so chuan mac dinh vao analyzer_configs va system_parameters"""
    init_db()

    # Chay ALTER TABLE truoc de dam bao schema day du
    try:
        from src.database.connection import engine
        _run_alter_migrations(engine)
    except Exception as e:
        logger.warning(f"Migration warning: {e}")

    with get_db_session() as session:
        # 1. Dam bao default user
        user = session.query(User).filter_by(username="default_user").first()
        if not user:
            user = User(username="default_user", email="admin@local.com")
            session.add(user)
            session.flush()

        # 2. Dam bao default lottery
        lottery = session.query(Lottery).filter_by(code=config.LOTTERY_CODE).first()
        if not lottery:
            lottery = Lottery(
                code=config.LOTTERY_CODE,
                name="Mien Bac 5 Phut",
                external_id=config.LOTTERY_ID
            )
            session.add(lottery)
            session.flush()

        # 3. Seed analyzer_configs (Parity & Size) — day du 33 tham so
        full_params = {
            "n_sliding_min": 12,
            "n_sliding_max": 20,
            "n_sliding_ratio": 0.20,
            "ar_window_min": 10,
            "ar_window_max": 30,
            "ar_window_ratio": 0.25,
            "ar_threshold_multiplier": 0.85,
            "ar_threshold_min": 0.70,
            "ar_threshold_max": 0.88,
            "n_recent_min": 6,
            "n_recent_max": 14,
            "n_recent_ratio": 0.12,
            "streak_confidence_threshold": 0.90,
            "streak_min_samples": 3,
            "streak_safety_trap_multiplier": 1.5,
            "streak_safety_trap_min": 4,
            "saturation_percentile": 68.0,
            "saturation_limit_min": 0.52,
            "saturation_limit_max": 0.78,
            "cooling_off_loss_limit": 2,
            "win_streak_pause_limit": 2,
            "buy_threshold_multiplier": 0.45,
            "buy_threshold_min": 0.55,
            "buy_threshold_max": 0.82,
            "min_probability_threshold": 0.55,
            "ma50_window": 30,
            "ma50_filter_active": False,
            "win_rate_filter_window": 10,
            "win_rate_filter_min_total": 4,
            "win_rate_filter_threshold": 0.52,
            "reversal_threshold": 0.85,
            "volatility_penalty": 1.2,
        }

        for market in ["parity", "size"]:
            cfg = session.query(AnalyzerConfig).filter_by(
                lottery_code=config.LOTTERY_CODE,
                market_type=market,
                preset_name="default"
            ).first()

            if not cfg:
                cfg = AnalyzerConfig(
                    lottery_code=config.LOTTERY_CODE,
                    market_type=market,
                    preset_name="default"
                )
                session.add(cfg)

            for field, value in full_params.items():
                setattr(cfg, field, value)

            cfg.is_active = True
            logger.info(f"Seeded/Updated analyzer_config [{market}] with {len(full_params)} params")

        # 4. Seed system_parameters
        params = [
            ("dkm_enabled", "true", "Kich hoat dkm_adaptive_pro"),
            ("dkm_kelly_fraction", "0.25", "Ty le Kelly co so"),
            ("dkm_max_martingale_multiplier", "2.0", "He so nhan gap doi toi da"),
            ("dkm_max_martingale_steps", "3", "So buoc gap thep toi da"),
            ("dkm_daily_loss_limit_percent", "5.0", "Gioi han dung lo ngay (%)"),
            ("dkm_min_balance", "500000", "Muc so du toi thieu de cuoc (VND)"),
        ]
        for key, val, desc in params:
            param = session.query(SystemParameter).filter_by(param_key=key).first()
            if not param:
                session.add(SystemParameter(param_key=key, param_value=val, description=desc))
                logger.info(f"Seeded system_parameter: {key}")

def migrate_from_json():
    """Tự động di chuyển dữ liệu từ demo_store.json sang Database"""
    db_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(db_dir, "demo_store.json")
    if not os.path.exists(json_path):
        logger.info("No demo_store.json found to migrate.")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        with get_db_session() as session:
            user = session.query(User).filter_by(username="default_user").first()
            user_id = user.id if user else 1

            balance = session.query(UserBalance).filter_by(
                user_id=user_id,
                lottery_code=config.LOTTERY_CODE
            ).first()

            if not balance:
                balance = UserBalance(
                    user_id=user_id,
                    lottery_code=config.LOTTERY_CODE,
                    demo_balance=data.get("demo_balance", 10000000.0),
                    peak_demo_balance=data.get("peak_demo_balance", 10000000.0),
                    demo_bet_amount=data.get("demo_bet_amount", 100000.0),
                    demo_bet_strategy=data.get("demo_bet_strategy", "dkm_adaptive_pro"),
                    parity_loss_streak=data.get("parity_loss_streak", 0),
                    size_loss_streak=data.get("size_loss_streak", 0),
                    parity_daily_loss_count=data.get("parity_daily_loss_count", 0),
                    size_daily_loss_count=data.get("size_daily_loss_count", 0),
                    initial_phase_remaining=data.get("initial_phase_remaining", 10)
                )
                session.add(balance)
                logger.info("Migrated user balance from demo_store.json to Database.")
    except Exception as e:
        logger.error(f"Error migrating demo_store.json: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_default_data()
    migrate_from_json()
    print("Database seeding & migration completed successfully!")
