from sqlalchemy import Column, Integer, String, Date, Numeric, BigInteger, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.database import Base


class DailyKline(Base):
    __tablename__ = "daily_kline"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), ForeignKey("stocks.stock_id"), nullable=False)
    trade_date = Column(Date, nullable=False)
    open = Column(Numeric(10, 2))
    high = Column(Numeric(10, 2))
    low = Column(Numeric(10, 2))
    close = Column(Numeric(10, 2))
    volume = Column(BigInteger)
    ma5 = Column(Numeric(10, 2))
    ma20 = Column(Numeric(10, 2))
    ma60 = Column(Numeric(10, 2))
    rsi14 = Column(Numeric(6, 2))
    macd = Column(Numeric(10, 4))
    macd_signal = Column(Numeric(10, 4))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_kline_stock_date"),
        Index("idx_kline_date", "trade_date"),
        Index("idx_kline_stock", "stock_id", "trade_date"),
    )
