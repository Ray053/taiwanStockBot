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
    created_at = Column(DateTime, server_default=func.now())
