"""Multi-factor weighted scoring engine."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.models.daily_score import DailyScore
from app.models.stock import Stock
from app.models.kline import DailyKline
from app.models.institutional import InstitutionalInvestors
from app.models.margin import MarginTrading
from app.models.macro_snapshot import MacroSnapshot
from app.services.signal_engine import enrich_kline_df, get_latest_signals

import pandas as pd

logger = logging.getLogger(__name__)

# Macro rules: (prob_field, threshold, sectors, delta, direction)
# direction: 'above' means trigger if prob > threshold
MACRO_RULES = [
    ("fed_cut_prob", 0.65, {"金融", "營建"}, +20, "above"),
    ("nvidia_beat_prob", 0.60, {"半導體", "電子"}, +20, "above"),
    ("taiwan_strait_prob", 0.25, {"半導體", "電子"}, -30, "above"),
    ("china_gdp_miss_prob", 0.50, {"傳產", "化工"}, -15, "above"),
    ("oil_above_90_prob", 0.55, {"航運", "塑化"}, +10, "above"),
]


def score_technical(signals: dict) -> tuple[float, list[str]]:
    """
    Technical scoring (max 100).
    - MA bull alignment: +40
    - RSI 50~70: +25
    - MACD golden cross today: +20
    - Volume > 20d avg * 1.5: +15
    """
    score = 0.0
    reasons = []

    if signals.get("bull_alignment"):
        score += 40
        reasons.append("✅ 均線多頭排列")

    rsi = signals.get("rsi14")
    if rsi is not None and 50 <= rsi <= 70:
        score += 25
        reasons.append(f"✅ RSI 強勢健康 ({rsi:.1f})")

    if signals.get("golden_cross"):
        score += 20
        reasons.append("✅ MACD 金叉")

    if signals.get("volume_surge"):
        score += 15
        reasons.append("✅ 量能放大")

    return score, reasons


def score_institutional(
    foreign_net: Optional[int],
    trust_net: Optional[int],
    dealer_net: Optional[int],
) -> tuple[float, list[str]]:
    """
    Institutional scoring (max 100).
    - Foreign buy: +40
    - Trust buy: +40
    - Dealer buy: +20
    """
    score = 0.0
    reasons = []

    if foreign_net is not None and foreign_net > 0:
        score += 40
        reasons.append(f"✅ 外資買超 +{foreign_net:,} 張")

    if trust_net is not None and trust_net > 0:
        score += 40
        reasons.append(f"✅ 投信買超 +{trust_net:,} 張")

    if dealer_net is not None and dealer_net > 0:
        score += 20
        reasons.append(f"✅ 自營商買超 +{dealer_net:,} 張")

    return score, reasons


def score_margin(
    margin_change: Optional[int],
    short_change: Optional[int],
) -> tuple[float, list[str]]:
    """
    Margin trading scoring (max 100).
    - Both decrease: 100
    - One decreases: 60
    - Both increase: 20
    """
    reasons = []

    margin_dec = margin_change is not None and margin_change < 0
    short_dec = short_change is not None and short_change < 0

    if margin_dec and short_dec:
        reasons.append("✅ 融資融券均減少，籌碼最乾淨")
        return 100.0, reasons
    elif margin_dec or short_dec:
        reasons.append("⚠️ 融資或融券其一減少")
        return 60.0, reasons
    else:
        reasons.append("❌ 融資融券均增加")
        return 20.0, reasons


def score_macro(sector: Optional[str], snapshot: Optional[MacroSnapshot]) -> tuple[float, list[str]]:
    """
    Macro scoring based on Polymarket probabilities.
    Base score: 50, then apply rules based on sector.
    """
    base = 50.0
    reasons = []

    if snapshot is None:
        return base, ["⚠️ 無宏觀快照資料"]

    sector_str = sector or ""

    for field, threshold, applicable_sectors, delta, direction in MACRO_RULES:
        prob = getattr(snapshot, field, None)
        if prob is None:
            continue
        prob_f = float(prob)
        triggered = prob_f > threshold if direction == "above" else prob_f < threshold

        if triggered and sector_str in applicable_sectors:
            base += delta
            sign = "+" if delta > 0 else ""
            label_map = {
                "fed_cut_prob": "Fed 降息預期高",
                "nvidia_beat_prob": "NVIDIA 財報超預期機率高",
                "taiwan_strait_prob": "台海風險上升",
                "china_gdp_miss_prob": "中國 GDP 不及預期",
                "oil_above_90_prob": "油價高漲",
            }
            label = label_map.get(field, field)
            icon = "✅" if delta > 0 else "❌"
            reasons.append(f"{icon} {label} ({prob_f:.0%}) → {sign}{delta} 分")

    score = max(0.0, min(100.0, base))
    return score, reasons


def compute_total_score(
    tech_score: float,
    inst_score: float,
    margin_score: float,
    macro_score: float,
) -> float:
    total = (
        tech_score * settings.weight_technical
        + inst_score * settings.weight_institutional
        + margin_score * settings.weight_margin
        + macro_score * settings.weight_macro
    )
    return round(total, 2)


def run_scoring(db: Session, score_date: Optional[date] = None) -> list[dict]:
    """
    Run full multi-factor scoring for all active stocks on score_date.
    Upserts results into daily_scores table.
    Returns list of score dicts.
    """
    if score_date is None:
        score_date = date.today()

    # Get latest macro snapshot
    macro = (
        db.query(MacroSnapshot)
        .order_by(MacroSnapshot.snapshot_date.desc())
        .first()
    )

    # Get all active stocks
    stocks = db.query(Stock).filter(Stock.is_active == True).all()  # noqa: E712
    if not stocks:
        logger.warning("No active stocks found for scoring.")
        return []

    results = []

    for stock in stocks:
        try:
            result = _score_single_stock(db, stock, score_date, macro)
            if result:
                results.append(result)
        except Exception as e:
            logger.error(f"Scoring error for {stock.stock_id}: {e}")

    # Rank by total_score descending
    results.sort(key=lambda x: x["total_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    # Upsert to DB
    for r in results:
        _upsert_score(db, r)

    db.commit()
    logger.info(f"Scoring complete for {score_date}: {len(results)} stocks scored.")
    return results


def _score_single_stock(
    db: Session,
    stock: Stock,
    score_date: date,
    macro: Optional[MacroSnapshot],
) -> Optional[dict]:
    # Fetch recent K-line data (last 120 days for indicator warmup)
    from datetime import timedelta
    start_date = score_date - timedelta(days=180)

    klines = (
        db.query(DailyKline)
        .filter(
            DailyKline.stock_id == stock.stock_id,
            DailyKline.trade_date >= start_date,
            DailyKline.trade_date <= score_date,
        )
        .order_by(DailyKline.trade_date)
        .all()
    )

    if not klines:
        return None

    # Convert to DataFrame
    df = pd.DataFrame([{
        "trade_date": k.trade_date,
        "open": float(k.open or 0),
        "high": float(k.high or 0),
        "low": float(k.low or 0),
        "close": float(k.close or 0),
        "volume": int(k.volume or 0),
        "ma5": float(k.ma5) if k.ma5 is not None else None,
        "ma20": float(k.ma20) if k.ma20 is not None else None,
        "ma60": float(k.ma60) if k.ma60 is not None else None,
        "rsi14": float(k.rsi14) if k.rsi14 is not None else None,
        "macd": float(k.macd) if k.macd is not None else None,
        "macd_signal": float(k.macd_signal) if k.macd_signal is not None else None,
    } for k in klines])

    # If indicators not pre-computed, compute them
    if df["ma5"].isna().all():
        df = enrich_kline_df(df)

    signals = get_latest_signals(df)

    # Fetch latest institutional data
    inst = (
        db.query(InstitutionalInvestors)
        .filter(
            InstitutionalInvestors.stock_id == stock.stock_id,
            InstitutionalInvestors.trade_date <= score_date,
        )
        .order_by(InstitutionalInvestors.trade_date.desc())
        .first()
    )

    # Fetch latest margin data
    margin = (
        db.query(MarginTrading)
        .filter(
            MarginTrading.stock_id == stock.stock_id,
            MarginTrading.trade_date <= score_date,
        )
        .order_by(MarginTrading.trade_date.desc())
        .first()
    )

    # Score each factor
    tech_score, tech_reasons = score_technical(signals)

    inst_score, inst_reasons = score_institutional(
        foreign_net=int(inst.foreign_net) if inst and inst.foreign_net is not None else None,
        trust_net=int(inst.trust_net) if inst and inst.trust_net is not None else None,
        dealer_net=int(inst.dealer_net) if inst and inst.dealer_net is not None else None,
    )

    margin_score, margin_reasons = score_margin(
        margin_change=int(margin.margin_change) if margin and margin.margin_change is not None else None,
        short_change=int(margin.short_change) if margin and margin.short_change is not None else None,
    )

    macro_score, macro_reasons = score_macro(stock.sector, macro)

    total = compute_total_score(tech_score, inst_score, margin_score, macro_score)

    all_reasons = tech_reasons + inst_reasons + margin_reasons + macro_reasons

    return {
        "score_date": score_date,
        "stock_id": stock.stock_id,
        "stock_name": stock.stock_name,
        "sector": stock.sector,
        "total_score": total,
        "tech_score": round(tech_score, 2),
        "inst_score": round(inst_score, 2),
        "margin_score": round(margin_score, 2),
        "macro_score": round(macro_score, 2),
        "rank": 0,
        "breakdown": {"reasons": all_reasons},
    }


def _upsert_score(db: Session, r: dict) -> None:
    db.execute(
        text("""
            INSERT INTO daily_scores
                (score_date, stock_id, total_score, tech_score, inst_score,
                 margin_score, macro_score, rank, breakdown)
            VALUES
                (:score_date, :stock_id, :total_score, :tech_score, :inst_score,
                 :margin_score, :macro_score, :rank, :breakdown::jsonb)
            ON CONFLICT (score_date, stock_id)
            DO UPDATE SET
                total_score = EXCLUDED.total_score,
                tech_score  = EXCLUDED.tech_score,
                inst_score  = EXCLUDED.inst_score,
                margin_score = EXCLUDED.margin_score,
                macro_score = EXCLUDED.macro_score,
                rank        = EXCLUDED.rank,
                breakdown   = EXCLUDED.breakdown,
                created_at  = NOW()
        """),
        {
            "score_date": r["score_date"],
            "stock_id": r["stock_id"],
            "total_score": r["total_score"],
            "tech_score": r["tech_score"],
            "inst_score": r["inst_score"],
            "margin_score": r["margin_score"],
            "macro_score": r["macro_score"],
            "rank": r["rank"],
            "breakdown": __import__("json").dumps(r["breakdown"], ensure_ascii=False),
        },
    )
