import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services import scoring_engine, polymarket_client
from app.models.macro_snapshot import MacroSnapshot
from app.scheduler.tasks import sync_stocks
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key


@router.post("/trigger-score")
def trigger_score(
    score_date: date = None,
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Manually trigger the scoring calculation and write results to DB."""
    try:
        results = scoring_engine.run_scoring(db, score_date=score_date)
        return {
            "status": "ok",
            "score_date": str(score_date or date.today()),
            "stocks_scored": len(results),
            "top3": [
                {"rank": r["rank"], "stock_id": r["stock_id"], "total_score": r["total_score"]}
                for r in results[:3]
            ],
        }
    except Exception as e:
        logger.error(f"trigger-score error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-stocks")
def trigger_sync_stocks(_: str = Depends(verify_api_key)):
    """Manually trigger syncing all TWSE stocks from FinMind into the stocks table."""
    try:
        sync_stocks()
        return {"status": "ok", "message": "Stock sync completed. Check logs for details."}
    except Exception as e:
        logger.error(f"sync-stocks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-polymarket")
def refresh_polymarket(
    db: Session = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Manually fetch and update Polymarket macro snapshot."""
    try:
        data = polymarket_client.fetch_macro_snapshot()
        today = date.today()

        db.execute(
            text("""
                INSERT INTO macro_snapshots
                    (snapshot_date, fed_cut_prob, nvidia_beat_prob, taiwan_strait_prob,
                     china_gdp_miss_prob, oil_above_90_prob)
                VALUES
                    (:snapshot_date, :fed_cut_prob, :nvidia_beat_prob, :taiwan_strait_prob,
                     :china_gdp_miss_prob, :oil_above_90_prob)
                ON CONFLICT (snapshot_date)
                DO UPDATE SET
                    fed_cut_prob       = EXCLUDED.fed_cut_prob,
                    nvidia_beat_prob   = EXCLUDED.nvidia_beat_prob,
                    taiwan_strait_prob = EXCLUDED.taiwan_strait_prob,
                    china_gdp_miss_prob = EXCLUDED.china_gdp_miss_prob,
                    oil_above_90_prob  = EXCLUDED.oil_above_90_prob,
                    created_at         = NOW()
            """),
            {"snapshot_date": today, **data},
        )
        db.commit()
        return {"status": "ok", "snapshot_date": str(today), "data": data}
    except Exception as e:
        logger.error(f"refresh-polymarket error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
