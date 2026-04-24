"""Screening API — AiDEAR-style multi-category stock screening results."""
import logging
import traceback
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_score import DailyScore
from app.models.stock import Stock
from app.services.screening_engine import categorize_stocks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screening", tags=["screening"])


def _build_scored_stocks(rows: list) -> list[dict]:
    result = []
    for s, st in rows:
        bd = s.breakdown or {}
        result.append({
            "stock_id": s.stock_id,
            "stock_name": st.stock_name,
            "sector": st.sector,
            "total_score": float(s.total_score) if s.total_score else 0,
            "tech_score": float(s.tech_score) if s.tech_score else 0,
            "inst_score": float(s.inst_score) if s.inst_score else 0,
            "margin_score": float(s.margin_score) if s.margin_score else 0,
            "macro_score": float(s.macro_score) if s.macro_score else 0,
            "rank": s.rank,
            "breakdown": bd,
            "signals": bd.get("signals") or {},
            "foreign_net": bd.get("foreign_net"),
            "trust_net": bd.get("trust_net"),
            "foreign_consec": bd.get("foreign_consec") or 0,
            "trust_consec": bd.get("trust_consec") or 0,
        })
    return result


@router.get("/today")
def get_today_screening(db: Session = Depends(get_db)):
    """
    Return today's stocks grouped into named screening categories.
    Falls back to yesterday if today has no data.
    """
    try:
        today = date.today()
        rows = (
            db.query(DailyScore, Stock)
            .join(Stock, DailyScore.stock_id == Stock.stock_id)
            .filter(DailyScore.score_date == today)
            .all()
        )
        score_date = today
        if not rows:
            yesterday = today - timedelta(days=1)
            rows = (
                db.query(DailyScore, Stock)
                .join(Stock, DailyScore.stock_id == Stock.stock_id)
                .filter(DailyScore.score_date == yesterday)
                .all()
            )
            score_date = yesterday

        if not rows:
            return {"score_date": str(today), "categories": {}, "total_stocks": 0}

        scored_stocks = _build_scored_stocks(rows)
        categories = categorize_stocks(scored_stocks)

        return {
            "score_date": str(score_date),
            "categories": categories,
            "total_stocks": len(scored_stocks),
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"screening/today error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{stock_id}")
def get_stock_screening_history(
    stock_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Return historical daily scores and which categories a stock appeared in."""
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(DailyScore, Stock)
        .join(Stock, DailyScore.stock_id == Stock.stock_id)
        .filter(
            DailyScore.stock_id == stock_id,
            DailyScore.score_date >= since,
        )
        .order_by(DailyScore.score_date.desc())
        .all()
    )

    if not rows:
        return {"stock_id": stock_id, "history": [], "categories": []}

    st = rows[0][1]
    history = []
    for s, _ in rows:
        bd = s.breakdown or {}
        history.append({
            "score_date": str(s.score_date),
            "rank": s.rank,
            "total_score": float(s.total_score) if s.total_score else 0,
            "tech_score": float(s.tech_score) if s.tech_score else 0,
            "inst_score": float(s.inst_score) if s.inst_score else 0,
            "margin_score": float(s.margin_score) if s.margin_score else 0,
            "macro_score": float(s.macro_score) if s.macro_score else 0,
            "reasons": bd.get("reasons", []),
            "signals": bd.get("signals") or {},
            "foreign_net": bd.get("foreign_net"),
            "trust_net": bd.get("trust_net"),
        })

    # Determine which categories today's score qualifies for
    latest_row = [rows[0]]
    scored = _build_scored_stocks(latest_row)
    categories = categorize_stocks(scored)
    cat_names = [
        {"key": k, "name": v["name"], "emoji": v["emoji"]}
        for k, v in categories.items()
        if v["stocks"]
    ]

    return {
        "stock_id": stock_id,
        "stock_name": st.stock_name,
        "sector": st.sector,
        "history": history,
        "categories": cat_names,
    }
