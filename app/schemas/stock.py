from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class StockBase(BaseModel):
    stock_id: str
    stock_name: str
    sector: Optional[str] = None
    market: str = "TWSE"
    is_active: bool = True


class StockResponse(StockBase):
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KlineResponse(BaseModel):
    stock_id: str
    trade_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None

    model_config = {"from_attributes": True}


class InstitutionalResponse(BaseModel):
    stock_id: str
    trade_date: date
    foreign_net: Optional[int] = None
    trust_net: Optional[int] = None
    dealer_net: Optional[int] = None
    total_net: Optional[int] = None

    model_config = {"from_attributes": True}


class MarginResponse(BaseModel):
    stock_id: str
    trade_date: date
    margin_balance: Optional[int] = None
    margin_change: Optional[int] = None
    short_balance: Optional[int] = None
    short_change: Optional[int] = None

    model_config = {"from_attributes": True}


class StockDetailResponse(BaseModel):
    stock: StockResponse
    latest_kline: Optional[KlineResponse] = None
    latest_institutional: Optional[InstitutionalResponse] = None
    latest_margin: Optional[MarginResponse] = None
