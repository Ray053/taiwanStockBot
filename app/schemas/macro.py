from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class MacroSnapshotResponse(BaseModel):
    id: int
    snapshot_date: date
    fed_cut_prob: Optional[float] = None
    nvidia_beat_prob: Optional[float] = None
    taiwan_strait_prob: Optional[float] = None
    china_gdp_miss_prob: Optional[float] = None
    oil_above_90_prob: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
