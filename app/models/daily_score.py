from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base


class DailyScore(Base):
    __tablename__ = "daily_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_date = Column(Date, nullable=False)
    stock_id = Column(String(10), ForeignKey("stocks.stock_id"), nullable=False)
    total_score = Column(Numeric(6, 2))
    tech_score = Column(Numeric(6, 2))
    inst_score = Column(Numeric(6, 2))
    margin_score = Column(Numeric(6, 2))
    macro_score = Column(Numeric(6, 2))
    rank = Column(Integer)
    breakdown = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("score_date", "stock_id", name="uq_score_date_stock"),
        Index("idx_scores_date", "score_date", "total_score"),
    )
