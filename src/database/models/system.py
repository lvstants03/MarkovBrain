from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Float, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database.models.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    balances = relationship("UserBalance", back_populates="user", cascade="all, delete-orphan")
    bets = relationship("Bet", back_populates="user", cascade="all, delete-orphan")
    commands = relationship("ScriptCommand", back_populates="user", cascade="all, delete-orphan")


class MarketHealthLog(Base):
    __tablename__ = "market_health_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue_range = Column(String(100), nullable=False)
    total_bets = Column(Integer, nullable=False)
    win_count = Column(Integer, nullable=False)
    win_rate_pct = Column(Float, nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemConnectionLog(Base):
    __tablename__ = "system_connection_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    lottery = relationship("Lottery", back_populates="connection_logs")


class AnalyzerConfig(Base):
    __tablename__ = "analyzer_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    market_type = Column(String(20), nullable=False)
    # --- Sliding window ---
    n_sliding_min = Column(Integer, default=12, nullable=False)
    n_sliding_max = Column(Integer, default=20, nullable=False)
    n_sliding_ratio = Column(Float, default=0.20, nullable=False)
    # --- AR window ---
    ar_window_min = Column(Integer, default=10, nullable=False)
    ar_window_max = Column(Integer, default=30, nullable=False)
    ar_window_ratio = Column(Float, default=0.25, nullable=False)
    ar_threshold_multiplier = Column(Float, default=0.85, nullable=False)
    ar_threshold_min = Column(Float, default=0.70, nullable=False)
    ar_threshold_max = Column(Float, default=0.88, nullable=False)
    # --- Recent window ---
    n_recent_min = Column(Integer, default=6, nullable=False)
    n_recent_max = Column(Integer, default=14, nullable=False)
    n_recent_ratio = Column(Float, default=0.12, nullable=False)
    # --- Streak ---
    streak_confidence_threshold = Column(Float, default=0.90, nullable=False)
    streak_min_samples = Column(Integer, default=3, nullable=False)
    streak_safety_trap_multiplier = Column(Float, default=1.5, nullable=False)
    streak_safety_trap_min = Column(Integer, default=4, nullable=False)
    # --- Saturation ---
    saturation_percentile = Column(Float, default=68.0, nullable=False)
    saturation_limit_min = Column(Float, default=0.52, nullable=False)
    saturation_limit_max = Column(Float, default=0.78, nullable=False)
    # --- Cooling off / pause ---
    cooling_off_loss_limit = Column(Integer, default=2, nullable=False)
    win_streak_pause_limit = Column(Integer, default=2, nullable=False)
    # --- Buy threshold ---
    buy_threshold_multiplier = Column(Float, default=0.45, nullable=False)
    buy_threshold_min = Column(Float, default=0.55, nullable=False)
    buy_threshold_max = Column(Float, default=0.82, nullable=False)
    min_probability_threshold = Column(Float, default=0.55, nullable=False)
    # --- MA50 ---
    ma50_window = Column(Integer, default=30, nullable=False)
    ma50_filter_active = Column(Boolean, default=False, nullable=False)
    # --- Win rate filter ---
    win_rate_filter_window = Column(Integer, default=10, nullable=False)
    win_rate_filter_min_total = Column(Integer, default=4, nullable=False)
    win_rate_filter_threshold = Column(Float, default=0.52, nullable=False)
    # --- Reversal / Volatility ---
    reversal_threshold = Column(Float, default=0.85, nullable=False)
    volatility_penalty = Column(Float, default=1.2, nullable=False)
    # --- Preset meta ---
    preset_name = Column(String(50), default="default", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lottery = relationship("Lottery", back_populates="analyzer_configs")

    __table_args__ = (
        UniqueConstraint("lottery_code", "market_type", "preset_name", name="uk_analyzer_config_preset"),
    )


class SystemParameter(Base):
    __tablename__ = "system_parameters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    param_key = Column(String(100), unique=True, nullable=False)
    param_value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScriptCommand(Base):
    __tablename__ = "script_commands"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False)
    command = Column(String(50), nullable=False)
    is_consumed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    consumed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="commands")
