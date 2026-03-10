"""Scheduled task functions."""
import logging
import time
from datetime import date, timedelta

from sqlalchemy import text

from app.database import SessionLocal
from app.services import finmind_client, polymarket_client, scoring_engine
from app.services.signal_engine import enrich_kline_df
from app.services.notifier import send_top_scores_notification

import pandas as pd

logger = logging.getLogger(__name__)

# Top ~100 TWSE stocks by market cap — only these will be set is_active=TRUE
# Covers semiconductors, financials, shipping, electronics, telecom, retail
TOP_ACTIVE_STOCKS = {
    # Semiconductors / IC Design
    "2330", "2454", "2303", "3711", "2408", "3034", "6415", "2344", "2337",
    "3044", "3037", "2379", "2458", "6770", "3533", "6669",
    # Electronics / ODM / OEM
    "2317", "2382", "2357", "4938", "2324", "2353", "2356", "2376", "2383",
    "2301", "2308", "2385", "2395", "2409", "2474", "2492", "3481", "2439",
    "2451", "4958", "2360",
    # Financials
    "2882", "2881", "2886", "2891", "2884", "5880", "2885", "2892", "2883",
    "2887", "2890", "2801", "2880", "2888", "5876", "5871",
    # Shipping / Transport
    "2603", "2609", "2615", "2618", "2610",
    # Telecom
    "2412", "3045", "4904",
    # Petrochemicals / Materials
    "1301", "1303", "1326", "6505", "2002", "1101", "1102",
    # Retail / Food / Consumer
    "1216", "2912", "2207",
    # Other Tech / Industrial
    "3008", "2049", "1590", "2327", "2345", "2371", "2392", "2404",
    "2543", "2597", "5234", "6274", "6278",
}

# Fallback stock list if DB is empty
DEFAULT_STOCK_IDS = sorted(TOP_ACTIVE_STOCKS)[:15]

# Rate limit: seconds between each stock API call (avoid being blocked)
RATE_LIMIT_DELAY = 0.5


def sync_stocks():
    """Weekly — Fetch all TWSE listed stocks from FinMind and upsert into stocks table.

    Only stocks in TOP_ACTIVE_STOCKS are set is_active=TRUE to stay within
    the free-tier FinMind API quota (~600 req/day). All others are stored
    but inactive so users can opt-in manually.
    """
    logger.info("Task: sync_stocks started")
    db = SessionLocal()
    try:
        records = finmind_client.fetch_stock_info()
        if not records:
            logger.warning("Task: sync_stocks — no data returned from FinMind")
            return

        total, activated = 0, 0
        for r in records:
            stock_id = r.get("stock_id") or r.get("StockID")
            stock_name = r.get("stock_name") or r.get("CompanyName") or ""
            industry = r.get("industry_category") or r.get("IndustryCategory") or ""

            if not stock_id or not str(stock_id).isdigit() or not (4 <= len(str(stock_id)) <= 6):
                continue

            is_active = str(stock_id) in TOP_ACTIVE_STOCKS

            db.execute(
                text("""
                    INSERT INTO stocks (stock_id, stock_name, sector, market, is_active)
                    VALUES (:stock_id, :stock_name, :sector, 'TWSE', :is_active)
                    ON CONFLICT (stock_id)
                    DO UPDATE SET
                        stock_name = EXCLUDED.stock_name,
                        sector     = EXCLUDED.sector,
                        is_active  = EXCLUDED.is_active
                """),
                {"stock_id": stock_id, "stock_name": stock_name, "sector": industry, "is_active": is_active},
            )
            total += 1
            if is_active:
                activated += 1

        db.commit()
        logger.info(f"Task: sync_stocks done. Upserted {total} stocks, {activated} active.")
    except Exception as e:
        logger.error(f"Task: sync_stocks error: {e}")
        db.rollback()
    finally:
        db.close()


def fetch_polymarket():
    """06:00 — Fetch Polymarket macro snapshot and save to DB."""
    logger.info("Task: fetch_polymarket started")
    db = SessionLocal()
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
                    fed_cut_prob        = EXCLUDED.fed_cut_prob,
                    nvidia_beat_prob    = EXCLUDED.nvidia_beat_prob,
                    taiwan_strait_prob  = EXCLUDED.taiwan_strait_prob,
                    china_gdp_miss_prob = EXCLUDED.china_gdp_miss_prob,
                    oil_above_90_prob   = EXCLUDED.oil_above_90_prob,
                    created_at          = NOW()
            """),
            {"snapshot_date": today, **data},
        )
        db.commit()
        logger.info(f"Task: fetch_polymarket done. Data: {data}")
    except Exception as e:
        logger.error(f"Task: fetch_polymarket error: {e}")
        db.rollback()
    finally:
        db.close()


def fetch_institutional():
    """08:30 — Fetch institutional investors data from FinMind."""
    logger.info("Task: fetch_institutional started")
    db = SessionLocal()
    try:
        today = date.today()
        start = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        stocks = _get_active_stock_ids(db)
        for stock_id in stocks:
            try:
                records = finmind_client.fetch_institutional_investors(stock_id, start, end)
                for r in records:
                    _upsert_institutional(db, stock_id, r)
                db.commit()
            except Exception as e:
                logger.error(f"fetch_institutional error for {stock_id}: {e}")
                db.rollback()
            time.sleep(RATE_LIMIT_DELAY)

        logger.info("Task: fetch_institutional done")
    finally:
        db.close()


def compute_signals():
    """09:05 — Fetch K-line data, compute signals, update DB."""
    logger.info("Task: compute_signals started")
    db = SessionLocal()
    try:
        today = date.today()
        start = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        stocks = _get_active_stock_ids(db)
        for stock_id in stocks:
            try:
                records = finmind_client.fetch_stock_price(stock_id, start, end)
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
                    _upsert_kline(db, stock_id, row)
                db.commit()
            except Exception as e:
                logger.error(f"compute_signals error for {stock_id}: {e}")
                db.rollback()
            time.sleep(RATE_LIMIT_DELAY)

        logger.info("Task: compute_signals done")
    finally:
        db.close()


def run_scoring():
    """14:05 — Run multi-factor scoring for all active stocks."""
    logger.info("Task: run_scoring started")
    db = SessionLocal()
    try:
        results = scoring_engine.run_scoring(db)
        logger.info(f"Task: run_scoring done. Top 3: {[r['stock_id'] for r in results[:3]]}")
        return results
    except Exception as e:
        logger.error(f"Task: run_scoring error: {e}")
        return []
    finally:
        db.close()


def send_notification():
    """14:30 — Send notification with top scores."""
    logger.info("Task: send_notification started")
    db = SessionLocal()
    try:
        today = date.today()
        from app.models.daily_score import DailyScore
        from app.models.stock import Stock

        scores = (
            db.query(DailyScore, Stock)
            .join(Stock, DailyScore.stock_id == Stock.stock_id)
            .filter(DailyScore.score_date == today)
            .order_by(DailyScore.rank)
            .limit(10)
            .all()
        )

        top_scores = []
        for score, stock in scores:
            top_scores.append({
                "rank": score.rank,
                "stock_id": score.stock_id,
                "stock_name": stock.stock_name,
                "total_score": float(score.total_score) if score.total_score else 0,
                "breakdown": score.breakdown or {},
            })

        if top_scores:
            send_top_scores_notification(top_scores)
        logger.info("Task: send_notification done")
    except Exception as e:
        logger.error(f"Task: send_notification error: {e}")
    finally:
        db.close()


def fetch_us_afterhours():
    """23:00 — Placeholder for US afterhours data (yfinance)."""
    logger.info("Task: fetch_us_afterhours started (placeholder)")
    # Future: use yfinance to update US macro signals
    logger.info("Task: fetch_us_afterhours done")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_active_stock_ids(db) -> list[str]:
    from app.models.stock import Stock
    stocks = db.query(Stock.stock_id).filter(Stock.is_active == True).all()  # noqa: E712
    return [s.stock_id for s in stocks] if stocks else DEFAULT_STOCK_IDS


def _upsert_kline(db, stock_id: str, row) -> None:
    def safe(val):
        if pd.isna(val):
            return None
        return val

    db.execute(
        text("""
            INSERT INTO daily_kline
                (stock_id, trade_date, open, high, low, close, volume,
                 ma5, ma20, ma60, rsi14, macd, macd_signal)
            VALUES
                (:stock_id, :trade_date, :open, :high, :low, :close, :volume,
                 :ma5, :ma20, :ma60, :rsi14, :macd, :macd_signal)
            ON CONFLICT (stock_id, trade_date)
            DO UPDATE SET
                open        = EXCLUDED.open,
                high        = EXCLUDED.high,
                low         = EXCLUDED.low,
                close       = EXCLUDED.close,
                volume      = EXCLUDED.volume,
                ma5         = EXCLUDED.ma5,
                ma20        = EXCLUDED.ma20,
                ma60        = EXCLUDED.ma60,
                rsi14       = EXCLUDED.rsi14,
                macd        = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal
        """),
        {
            "stock_id": stock_id,
            "trade_date": row["trade_date"],
            "open": safe(row.get("open")),
            "high": safe(row.get("high")),
            "low": safe(row.get("low")),
            "close": safe(row.get("close")),
            "volume": int(safe(row.get("volume")) or 0),
            "ma5": safe(row.get("ma5")),
            "ma20": safe(row.get("ma20")),
            "ma60": safe(row.get("ma60")),
            "rsi14": safe(row.get("rsi14")),
            "macd": safe(row.get("macd")),
            "macd_signal": safe(row.get("macd_signal")),
        },
    )


def _upsert_institutional(db, stock_id: str, row: dict) -> None:
    """Parse and upsert institutional investors row from FinMind."""
    name = row.get("name", "")
    buy = int(row.get("buy", 0) or 0)
    sell = int(row.get("sell", 0) or 0)
    net = buy - sell
    trade_date = row.get("date") or row.get("trade_date")

    col_map = {
        "外資": "foreign_net",
        "投信": "trust_net",
        "自營商": "dealer_net",
    }
    col = col_map.get(name)
    if not col:
        return

    # First ensure row exists
    db.execute(
        text("""
            INSERT INTO institutional_investors (stock_id, trade_date)
            VALUES (:stock_id, :trade_date)
            ON CONFLICT (stock_id, trade_date) DO NOTHING
        """),
        {"stock_id": stock_id, "trade_date": trade_date},
    )

    db.execute(
        text(f"""
            UPDATE institutional_investors
            SET {col} = :{col}
            WHERE stock_id = :stock_id AND trade_date = :trade_date
        """),
        {col: net, "stock_id": stock_id, "trade_date": trade_date},
    )

    # Update total_net
    db.execute(
        text("""
            UPDATE institutional_investors
            SET total_net = COALESCE(foreign_net, 0) + COALESCE(trust_net, 0) + COALESCE(dealer_net, 0)
            WHERE stock_id = :stock_id AND trade_date = :trade_date
        """),
        {"stock_id": stock_id, "trade_date": trade_date},
    )
