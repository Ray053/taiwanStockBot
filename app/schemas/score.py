from datetime import date, datetime
from typing import Optional, Any
from pydantic import BaseModel


class ScoreResponse(BaseModel):
    stock_id: str
    stock_name: Optional[str] = None
    sector: Optional[str] = None
    score_date: date
    total_score: Optional[float] = None
    tech_score: Optional[float] = None
    inst_score: Optional[float] = None
    margin_score: Optional[float] = None
    macro_score: Optional[float] = None
    rank: Optional[int] = None
    breakdown: Optional[Any] = None

    model_config = {"from_attributes": True}
