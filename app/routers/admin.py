import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services import scoring_engine, polymarket_client
from app.models.macro_snapshot import MacroSnapshot
from app.scheduler.tasks import sync_stocks, compute_signals
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


@router.post("/compute-signals")
def trigger_compute_signals(
    stock_ids: list[str] = Body(default=None),
    _: str = Depends(verify_api_key),
):
    """Manually trigger K-line fetch and signal computation.
    Pass stock_ids to limit scope (e.g. ['2330','2317']). Omit for all active stocks."""
    import threading
    def run():
        if stock_ids:
            from app.scheduler.tasks import SessionLocal, finmind_client, enrich_kline_df, _upsert_kline, RATE_LIMIT_DELAY
            import time
            from datetime import date, timedelta
            import pandas as pd
            today = date.today()
            start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
            end = today.strftime("%Y-%m-%d")
            db = SessionLocal()
            try:
                for sid in stock_ids:
                    try:
                        records = finmind_client.fetch_stock_price(sid, start, end)
                        if not records:
                            continue
                        df = pd.DataFrame(records)
                        df = df.rename(columns={
                            "date": "trade_date",
                            "Trading_Volume": "volume",
                            "max": "high",
                            "min": "low",
                        })
                        df = enrich_kline_df(df)
                        for _, row in df.iterrows():
                            _upsert_kline(db, sid, row)
                        db.commit()
                    except Exception as e:
                        logger.error(f"compute-signals error for {sid}: {e}")
                        db.rollback()
                    time.sleep(RATE_LIMIT_DELAY)
            finally:
                db.close()
        else:
            compute_signals()
    threading.Thread(target=run, daemon=True).start()
    scope = stock_ids if stock_ids else "all active stocks"
    return {"status": "ok", "message": f"compute_signals started in background for {scope}"}


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
