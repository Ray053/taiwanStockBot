from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    stock_id = Column(String(10), primary_key=True)
    stock_name = Column(String(50), nullable=False)
    sector = Column(String(30), nullable=True)
    market = Column(String(10), default="TWSE")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
