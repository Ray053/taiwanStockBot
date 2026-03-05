from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.stock import Stock
from app.models.kline import DailyKline
from app.models.institutional import InstitutionalInvestors
from app.models.margin import MarginTrading
from app.schemas.stock import (
    KlineResponse,
    InstitutionalResponse,
    MarginResponse,
    StockDetailResponse,
    StockResponse,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_stock_or_404(stock_id: str, db: Session) -> Stock:
    stock = db.query(Stock).filter(Stock.stock_id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {stock_id} not found")
    return stock


@router.get("/{stock_id}/kline", response_model=list[KlineResponse])
def get_kline(
    stock_id: str,
    days: int = Query(default=60, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get K-line data with technical indicators."""
    _get_stock_or_404(stock_id, db)
    since = date.today() - timedelta(days=days)
    records = (
        db.query(DailyKline)
        .filter(
            DailyKline.stock_id == stock_id,
            DailyKline.trade_date >= since,
        )
        .order_by(DailyKline.trade_date.desc())
        .all()
    )
    return [KlineResponse.model_validate(r) for r in records]


@router.get("/{stock_id}/institutional", response_model=list[InstitutionalResponse])
def get_institutional(
    stock_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get three major institutional investors buy/sell data."""
    _get_stock_or_404(stock_id, db)
    since = date.today() - timedelta(days=days)
    records = (
        db.query(InstitutionalInvestors)
        .filter(
            InstitutionalInvestors.stock_id == stock_id,
            InstitutionalInvestors.trade_date >= since,
        )
        .order_by(InstitutionalInvestors.trade_date.desc())
        .all()
    )
    return [InstitutionalResponse.model_validate(r) for r in records]


@router.get("/{stock_id}/margin", response_model=list[MarginResponse])
def get_margin(
    stock_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get margin trading (融資融券) data."""
    _get_stock_or_404(stock_id, db)
    since = date.today() - timedelta(days=days)
    records = (
        db.query(MarginTrading)
        .filter(
            MarginTrading.stock_id == stock_id,
            MarginTrading.trade_date >= since,
        )
        .order_by(MarginTrading.trade_date.desc())
        .all()
    )
    return [MarginResponse.model_validate(r) for r in records]


@router.get("/{stock_id}/detail", response_model=StockDetailResponse)
def get_stock_detail(
    stock_id: str,
    db: Session = Depends(get_db),
):
    """Get full snapshot for a stock."""
    stock = _get_stock_or_404(stock_id, db)

    latest_kline = (
        db.query(DailyKline)
        .filter(DailyKline.stock_id == stock_id)
        .order_by(DailyKline.trade_date.desc())
        .first()
    )
    latest_inst = (
        db.query(InstitutionalInvestors)
        .filter(InstitutionalInvestors.stock_id == stock_id)
        .order_by(InstitutionalInvestors.trade_date.desc())
        .first()
    )
    latest_margin = (
        db.query(MarginTrading)
        .filter(MarginTrading.stock_id == stock_id)
        .order_by(MarginTrading.trade_date.desc())
        .first()
    )

    return StockDetailResponse(
        stock=StockResponse.model_validate(stock),
        latest_kline=KlineResponse.model_validate(latest_kline) if latest_kline else None,
        latest_institutional=InstitutionalResponse.model_validate(latest_inst) if latest_inst else None,
        latest_margin=MarginResponse.model_validate(latest_margin) if latest_margin else None,
    )
