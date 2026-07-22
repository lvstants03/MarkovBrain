from sqlalchemy import Column, BigInteger, String, Float, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from src.database.models.base import Base

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue = Column(String(50), index=True, nullable=False)
    predicted_parity = Column(String(20), default="Không có")
    predicted_size = Column(String(20), default="Không có")
    parity_confidence = Column(Float, nullable=True)
    size_confidence = Column(Float, nullable=True)
    engine_used_parity = Column(String(50), default="Heuristics")
    engine_used_size = Column(String(50), default="Heuristics")
    parity_rationale = Column(Text, default="")
    size_rationale = Column(Text, default="")
    actual_parity = Column(String(20), nullable=True)
    actual_size = Column(String(20), nullable=True)
    status_parity = Column(String(20), default="pending")
    status_size = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    lottery = relationship("Lottery", back_populates="predictions")

    __table_args__ = (
        UniqueConstraint("lottery_code", "issue", name="uk_predictions_lottery_issue"),
    )


class AIAuditLog(Base):
    __tablename__ = "ai_audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    lottery_code = Column(String(50), ForeignKey("lotteries.code", ondelete="CASCADE"), nullable=False)
    issue = Column(String(50), index=True, nullable=False)
    model_name = Column(String(50), default="gemini-2.5-flash", nullable=False)
    prompt_payload = Column(Text, nullable=False)
    response_raw = Column(Text, nullable=True)
    latency_seconds = Column(Float, default=0.0)
    is_success = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
