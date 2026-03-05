from sqlalchemy import Column, Integer, String, Date, BigInteger, ForeignKey, UniqueConstraint
from app.database import Base


class MarginTrading(Base):
    __tablename__ = "margin_trading"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), ForeignKey("stocks.stock_id"), nullable=False)
    trade_date = Column(Date, nullable=False)
    margin_balance = Column(BigInteger)
    margin_change = Column(BigInteger)
    short_balance = Column(BigInteger)
    short_change = Column(BigInteger)

    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_margin_stock_date"),
    )
