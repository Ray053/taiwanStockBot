"""Multi-factor weighted scoring engine."""
import logging
from datetime import date, timedelta
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
    Technical scoring (max 100) — swing-trade optimised.

    Score breakdown:
    - MA5 > MA20 > MA60 bull alignment      : +30
    - RSI (direction-aware):
        from oversold (<40 recently) → ≥50  : +25  ← wave just starting
        healthy 50–70 (no from-low context) : +15
        overbought > 80                     : -20 penalty
    - MACD golden cross today               : +20
    - Volume surge (> 20d avg × 1.5)        : +15
    - KD low golden cross (K<30 → K>D)      : +10
    - KD high dead cross  (K>70 → K<D)      : -10 penalty

    Max reachable = 30 + 25 + 20 + 15 + 10 = 100
    """
    score = 0.0
    reasons = []

    if signals.get("bull_alignment"):
        score += 30
        reasons.append("✅ 均線多頭排列")

    rsi = signals.get("rsi14")
    if rsi is not None:
        if rsi > 80:
            score -= 20
            reasons.append(f"❌ RSI 超買警示 ({rsi:.1f})，追高風險")
        elif signals.get("rsi_from_low") and 50 <= rsi <= 70:
            score += 25
            reasons.append(f"✅ RSI 從低檔反彈啟動 ({rsi:.1f})")
        elif 50 <= rsi <= 70:
            score += 15
            reasons.append(f"✅ RSI 強勢健康 ({rsi:.1f})")

    if signals.get("golden_cross"):
        score += 20
        reasons.append("✅ MACD 金叉")

    if signals.get("volume_surge"):
        score += 15
        reasons.append("✅ 量能放大")

    if signals.get("kd_golden_cross_low"):
        score += 10
        kd_k = signals.get("kd_k")
        kd_d = signals.get("kd_d")
        label = f"K={kd_k:.1f}, D={kd_d:.1f}" if kd_k is not None and kd_d is not None else ""
        reasons.append(f"✅ KD 低檔金叉（波段起點）{label}")

    if signals.get("kd_dead_cross_high"):
        score -= 10
        kd_k = signals.get("kd_k")
        label = f"K={kd_k:.1f}" if kd_k is not None else ""
        reasons.append(f"❌ KD 高檔死叉（避免追高）{label}")

    return max(0.0, min(100.0, score)), reasons


def score_institutional(
    foreign_net: Optional[int],
    trust_net: Optional[int],
    dealer_net: Optional[int],
    foreign_consec: int = 0,
    trust_consec: int = 0,
) -> tuple[float, list[str]]:
    """
    Institutional scoring (max 100).

    Base (single-day buy):
    - Foreign buy  : +40
    - Trust buy    : +40
    - Dealer buy   : +20

    Consecutive-day bonus (added on top of base if buying today):
    - Foreign 3–4 consecutive days : +8
    - Foreign 5+ consecutive days  : +15
    - Trust  3–4 consecutive days  : +5
    - Trust  5+ consecutive days   : +10

    Capped at 100.
    """
    score = 0.0
    reasons = []

    if foreign_net is not None and foreign_net > 0:
        score += 40
        if foreign_consec >= 5:
            score += 15
            reasons.append(f"✅ 外資連續 {foreign_consec} 日買超 +{foreign_net:,} 張（主力建倉）")
        elif foreign_consec >= 3:
            score += 8
            reasons.append(f"✅ 外資連續 {foreign_consec} 日買超 +{foreign_net:,} 張")
        else:
            reasons.append(f"✅ 外資買超 +{foreign_net:,} 張")

    if trust_net is not None and trust_net > 0:
        score += 40
        if trust_consec >= 5:
            score += 10
            reasons.append(f"✅ 投信連續 {trust_consec} 日買超 +{trust_net:,} 張（持續佈局）")
        elif trust_consec >= 3:
            score += 5
            reasons.append(f"✅ 投信連續 {trust_consec} 日買超 +{trust_net:,} 張")
        else:
            reasons.append(f"✅ 投信買超 +{trust_net:,} 張")

    if dealer_net is not None and dealer_net > 0:
        score += 20
        reasons.append(f"✅ 自營商買超 +{dealer_net:,} 張")

    return min(100.0, score), reasons


def score_margin(
    margin_change: Optional[int],
    short_change: Optional[int],
) -> tuple[float, list[str]]:
    """
    Margin trading scoring (max 100).
    - No data: 50 (neutral, no reason shown)
    - Both decrease: 100
    - One decreases: 60
    - Both increase: 20
    """
    # No data at all → neutral, don't penalize
    if margin_change is None and short_change is None:
        return 50.0, []

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


def _apply_night_session(change: float) -> tuple[float, str]:
    """Tiered scoring for Taiwan night session proxy (EWT ETF % change)."""
    if change > 0.01:
        return +5.0, f"✅ 夜盤上漲 ({change:+.1%})"
    elif change < -0.02:
        return -15.0, f"❌ 夜盤重挫 ({change:+.1%})"
    elif change < -0.01:
        return -8.0, f"⚠️ 夜盤下跌 ({change:+.1%})"
    return 0.0, ""


def _apply_sox(change: float, sector: str) -> tuple[float, str]:
    """SOX affects 半導體 sector."""
    if sector != "半導體":
        return 0.0, ""
    if change > 0.02:
        return +10.0, f"✅ 費半大漲 ({change:+.1%})"
    elif change < -0.02:
        return -15.0, f"❌ 費半重挫 ({change:+.1%})"
    return 0.0, ""


def _apply_nasdaq(change: float, sector: str) -> tuple[float, str]:
    """NASDAQ affects 電子 sector."""
    if sector != "電子":
        return 0.0, ""
    if change > 0.015:
        return +8.0, f"✅ 那指大漲 ({change:+.1%})"
    elif change < -0.015:
        return -10.0, f"❌ 那指重挫 ({change:+.1%})"
    return 0.0, ""


def _apply_sp500(change: float) -> tuple[float, str]:
    """S&P 500 is a market-wide signal affecting all sectors."""
    if change > 0.01:
        return +5.0, f"✅ 標普上漲 ({change:+.1%})"
    elif change < -0.01:
        return -8.0, f"❌ 標普下跌 ({change:+.1%})"
    return 0.0, ""


def score_macro(sector: Optional[str], snapshot: Optional[MacroSnapshot]) -> tuple[float, list[str]]:
    """
    Macro scoring based on Polymarket probabilities + US/night market signals.
    Base score: 50, then apply rules based on sector.
    """
    base = 50.0
    reasons = []

    if snapshot is None:
        return base, []  # No macro data — use neutral 50, no reason shown

    sector_str = sector or ""

    # ── Polymarket probability rules ──────────────────────────────────────────
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

    # ── US market & night session signals ─────────────────────────────────────
    night = getattr(snapshot, "txf_night_change", None)
    if night is not None:
        delta, reason = _apply_night_session(float(night))
        if reason:
            base += delta
            reasons.append(reason)

    sox = getattr(snapshot, "sox_change", None)
    if sox is not None:
        delta, reason = _apply_sox(float(sox), sector_str)
        if reason:
            base += delta
            reasons.append(reason)

    nasdaq = getattr(snapshot, "nasdaq_change", None)
    if nasdaq is not None:
        delta, reason = _apply_nasdaq(float(nasdaq), sector_str)
        if reason:
            base += delta
            reasons.append(reason)

    sp500 = getattr(snapshot, "sp500_change", None)
    if sp500 is not None:
        delta, reason = _apply_sp500(float(sp500))
        if reason:
            base += delta
            reasons.append(reason)

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


def _count_consecutive_buying(records: list, field: str) -> int:
    """
    Count the number of consecutive days (most recent first) where `field` > 0.
    `records` should be ordered by trade_date descending.
    """
    count = 0
    for rec in records:
        val = getattr(rec, field, None)
        if val is not None and int(val) > 0:
            count += 1
        else:
            break
    return count


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

    # Batch-fetch yesterday's scores for momentum calculation
    prev_date = score_date - timedelta(days=1)
    prev_scores: dict[str, float] = {}
    for ps in db.query(DailyScore).filter(DailyScore.score_date == prev_date).all():
        prev_scores[ps.stock_id] = float(ps.total_score)

    results = []

    for stock in stocks:
        try:
            result = _score_single_stock(
                db, stock, score_date, macro,
                prev_total_score=prev_scores.get(stock.stock_id),
            )
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
    prev_total_score: Optional[float] = None,
) -> Optional[dict]:
    # Fetch recent K-line data (last 180 days for indicator warmup)
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
    else:
        # KD is never pre-stored — always compute from raw OHLC
        from app.services.signal_engine import compute_kd
        import numpy as np
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)
        kd_k, kd_d = compute_kd(high, low, close)
        df["kd_k"] = kd_k.round(2)
        df["kd_d"] = kd_d.round(2)

    signals = get_latest_signals(df)

    # Fetch last 5 days of institutional data (for consecutive-buying count)
    inst_records = (
        db.query(InstitutionalInvestors)
        .filter(
            InstitutionalInvestors.stock_id == stock.stock_id,
            InstitutionalInvestors.trade_date <= score_date,
        )
        .order_by(InstitutionalInvestors.trade_date.desc())
        .limit(5)
        .all()
    )

    inst = inst_records[0] if inst_records else None

    foreign_consec = _count_consecutive_buying(inst_records, "foreign_net")
    trust_consec = _count_consecutive_buying(inst_records, "trust_net")

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
        foreign_consec=foreign_consec,
        trust_consec=trust_consec,
    )

    margin_score, margin_reasons = score_margin(
        margin_change=int(margin.margin_change) if margin and margin.margin_change is not None else None,
        short_change=int(margin.short_change) if margin and margin.short_change is not None else None,
    )

    macro_score, macro_reasons = score_macro(stock.sector, macro)

    total = compute_total_score(tech_score, inst_score, margin_score, macro_score)

    # ── Score momentum bonus (swing-trade: reward rising signals) ────────────
    momentum_reasons: list[str] = []
    if prev_total_score is not None:
        score_diff = total - prev_total_score
        if score_diff >= 10:
            total = min(100.0, round(total + 3.0, 2))
            momentum_reasons.append(f"✅ 評分上升動能 (昨 {prev_total_score:.1f} → 今 {total:.1f})")
        elif score_diff >= 5:
            total = min(100.0, round(total + 1.5, 2))
            momentum_reasons.append(f"✅ 評分小幅上升 (+{score_diff:.1f})")
        elif score_diff <= -10:
            total = max(0.0, round(total - 3.0, 2))
            momentum_reasons.append(f"⚠️ 評分明顯下滑 ({score_diff:.1f})")
        elif score_diff <= -5:
            total = max(0.0, round(total - 1.5, 2))
            momentum_reasons.append(f"⚠️ 評分小幅下滑 ({score_diff:.1f})")

    all_reasons = tech_reasons + inst_reasons + margin_reasons + macro_reasons + momentum_reasons

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
                 :margin_score, :macro_score, :rank, CAST(:breakdown AS jsonb))
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
