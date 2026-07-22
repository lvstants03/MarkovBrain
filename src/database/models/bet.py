from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Numeric, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database.models.base import Base

class Bet(Base):
    __tablename__ = "bets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue = Column(String(50), index=True, nullable=False)
    is_demo = Column(Boolean, default=True, nullable=False)
    market_type = Column(String(20), nullable=False)
    prediction = Column(String(20), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    strategy = Column(String(50), default="dkm_adaptive_pro", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    win_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    balance_after = Column(Numeric(15, 2), default=0.00, nullable=False)
    placed_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="bets")
    lottery = relationship("Lottery", back_populates="bets")


class UserBalance(Base):
    __tablename__ = "user_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), default=1, nullable=False)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    real_balance = Column(Numeric(15, 2), default=0.00, nullable=False)
    demo_balance = Column(Numeric(15, 2), default=10000000.00, nullable=False)
    peak_demo_balance = Column(Numeric(15, 2), default=10000000.00, nullable=False)
    demo_bet_amount = Column(Numeric(15, 2), default=100000.00, nullable=False)
    demo_bet_strategy = Column(String(50), default="dkm_adaptive_pro", nullable=False)
    parity_loss_streak = Column(Integer, default=0, nullable=False)
    size_loss_streak = Column(Integer, default=0, nullable=False)
    parity_daily_loss_count = Column(Integer, default=0, nullable=False)
    size_daily_loss_count = Column(Integer, default=0, nullable=False)
    parity_pause_until = Column(DateTime, nullable=True)
    size_pause_until = Column(DateTime, nullable=True)
    initial_phase_remaining = Column(Integer, default=10, nullable=False)
    cf_auth_token = Column(Text, default="", nullable=True)
    cookie = Column(Text, default="", nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="balances")
    lottery = relationship("Lottery", back_populates="balances")

    __table_args__ = (
        UniqueConstraint("user_id", "lottery_code", name="uk_user_balances_user_lottery"),
    )


class CapitalCollapse(Base):
    __tablename__ = "capital_collapses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue = Column(String(50), nullable=False)
    market_type = Column(String(20), nullable=False)
    loss_streak = Column(Integer, nullable=False)
    amount_required = Column(Numeric(15, 2), nullable=False)
    balance_current = Column(Numeric(15, 2), nullable=False)
    strategy = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
