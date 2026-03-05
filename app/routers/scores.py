from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_score import DailyScore
from app.models.stock import Stock
from app.schemas.score import ScoreResponse

router = APIRouter(prefix="/scores", tags=["scores"])


def _enrich_score(score: DailyScore, db: Session) -> ScoreResponse:
    stock = db.query(Stock).filter(Stock.stock_id == score.stock_id).first()
    return ScoreResponse(
        stock_id=score.stock_id,
        stock_name=stock.stock_name if stock else None,
        sector=stock.sector if stock else None,
        score_date=score.score_date,
        total_score=float(score.total_score) if score.total_score is not None else None,
        tech_score=float(score.tech_score) if score.tech_score is not None else None,
        inst_score=float(score.inst_score) if score.inst_score is not None else None,
        margin_score=float(score.margin_score) if score.margin_score is not None else None,
        macro_score=float(score.macro_score) if score.macro_score is not None else None,
        rank=score.rank,
        breakdown=score.breakdown,
    )


@router.get("/today", response_model=list[ScoreResponse])
def get_today_scores(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get today's top N stock scores."""
    today = date.today()
    scores = (
        db.query(DailyScore)
        .filter(DailyScore.score_date == today)
        .order_by(DailyScore.rank)
        .limit(limit)
        .all()
    )
    # Fallback: try yesterday if today has no data
    if not scores:
        yesterday = today - timedelta(days=1)
        scores = (
            db.query(DailyScore)
            .filter(DailyScore.score_date == yesterday)
            .order_by(DailyScore.rank)
            .limit(limit)
            .all()
        )
    return [_enrich_score(s, db) for s in scores]


@router.get("/stock/{stock_id}", response_model=list[ScoreResponse])
def get_stock_score_history(
    stock_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get historical scores for a specific stock."""
    since = date.today() - timedelta(days=days)
    scores = (
        db.query(DailyScore)
        .filter(
            DailyScore.stock_id == stock_id,
            DailyScore.score_date >= since,
        )
        .order_by(DailyScore.score_date.desc())
        .all()
    )
    return [_enrich_score(s, db) for s in scores]


@router.get("/{score_date}", response_model=list[ScoreResponse])
def get_scores_by_date(
    score_date: date,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get scores for a specific date (YYYY-MM-DD)."""
    scores = (
        db.query(DailyScore)
        .filter(DailyScore.score_date == score_date)
        .order_by(DailyScore.rank)
        .limit(limit)
        .all()
    )
    return [_enrich_score(s, db) for s in scores]
