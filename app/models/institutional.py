from sqlalchemy import Column, Integer, String, Date, BigInteger, ForeignKey, UniqueConstraint, Index
from app.database import Base


class InstitutionalInvestors(Base):
    __tablename__ = "institutional_investors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), ForeignKey("stocks.stock_id"), nullable=False)
    trade_date = Column(Date, nullable=False)
    foreign_net = Column(BigInteger)
    trust_net = Column(BigInteger)
    dealer_net = Column(BigInteger)
    total_net = Column(BigInteger)

    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_inst_stock_date"),
        Index("idx_inst_stock", "stock_id", "trade_date"),
    )
