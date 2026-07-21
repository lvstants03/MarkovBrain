from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database.models.base import Base

class Lottery(Base):
    __tablename__ = "lotteries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    external_id = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("DrawRecord", back_populates="lottery", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="lottery", cascade="all, delete-orphan")
    bets = relationship("Bet", back_populates="lottery", cascade="all, delete-orphan")
    connection_logs = relationship("SystemConnectionLog", back_populates="lottery", cascade="all, delete-orphan")
    analyzer_configs = relationship("AnalyzerConfig", back_populates="lottery", cascade="all, delete-orphan")
    balances = relationship("UserBalance", back_populates="lottery", cascade="all, delete-orphan")


class DrawRecord(Base):
    __tablename__ = "draw_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue = Column(String(50), index=True, nullable=False)
    num_1 = Column(Integer, nullable=False)
    num_2 = Column(Integer, nullable=False)
    num_3 = Column(Integer, nullable=False)
    num_4 = Column(Integer, nullable=False)
    num_5 = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    is_tai = Column(Boolean, nullable=False)
    is_le = Column(Boolean, nullable=False)
    drawn_at = Column(DateTime, default=datetime.utcnow)

    lottery = relationship("Lottery", back_populates="records")

    __table_args__ = (
        UniqueConstraint("lottery_code", "issue", name="uk_draw_records_lottery_issue"),
        Index("idx_draw_records_lottery_issue", "lottery_code", "issue"),
    )
