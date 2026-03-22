from sqlalchemy import Column, Integer, Date, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class MacroSnapshot(Base):
    __tablename__ = "macro_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False, unique=True)
    fed_cut_prob = Column(Numeric(5, 4))
    nvidia_beat_prob = Column(Numeric(5, 4))
    taiwan_strait_prob = Column(Numeric(5, 4))
    china_gdp_miss_prob = Column(Numeric(5, 4))
    oil_above_90_prob = Column(Numeric(5, 4))
    # Market signals (fetched via yfinance at 06:00 after overnight close)
    txf_night_change = Column(Numeric(6, 4))   # Taiwan night session proxy (EWT ETF % change)
    sox_change = Column(Numeric(6, 4))          # Philadelphia Semiconductor Index % change
    nasdaq_change = Column(Numeric(6, 4))       # NASDAQ Composite % change
    sp500_change = Column(Numeric(6, 4))        # S&P 500 % change
    created_at = Column(DateTime, server_default=func.now())
