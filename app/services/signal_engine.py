"""Technical indicator computation: MA, RSI, MACD, Volume."""
import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def compute_ma(prices: pd.Series, window: int) -> pd.Series:
    """Compute simple moving average."""
    return prices.rolling(window=window, min_periods=window).mean()


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI (Relative Strength Index)."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    # When avg_loss is 0 (pure uptrend), RSI = 100
    rsi = pd.Series(index=prices.index, dtype=float)
    no_loss = avg_loss == 0
    has_loss = ~no_loss & avg_loss.notna() & avg_gain.notna()
    rsi[no_loss & avg_gain.notna()] = 100.0
    rsi[has_loss] = 100 - (100 / (1 + avg_gain[has_loss] / avg_loss[has_loss]))
    return rsi


def compute_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Compute MACD, Signal line, and Histogram.
    Returns (macd_line, signal_line, histogram).
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_volume_ma(volumes: pd.Series, window: int = 20) -> pd.Series:
    """Compute volume moving average."""
    return volumes.rolling(window=window, min_periods=1).mean()


def enrich_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a raw K-line DataFrame with columns [date/trade_date, close, volume, open, high, low],
    compute and append MA5, MA20, MA60, RSI14, MACD, MACD_signal columns.
    Returns enriched DataFrame.
    """
    if df.empty:
        return df

    df = df.copy()

    # Normalize date column
    if "date" in df.columns and "trade_date" not in df.columns:
        df = df.rename(columns={"date": "trade_date"})

    df = df.sort_values("trade_date").reset_index(drop=True)

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    df["ma5"] = compute_ma(close, 5).round(2)
    df["ma20"] = compute_ma(close, 20).round(2)
    df["ma60"] = compute_ma(close, 60).round(2)
    df["rsi14"] = compute_rsi(close, 14).round(2)

    macd_line, signal_line, _ = compute_macd(close)
    df["macd"] = macd_line.round(4)
    df["macd_signal"] = signal_line.round(4)

    df["vol_ma20"] = compute_volume_ma(volume, 20).round(0)

    return df


def check_golden_cross(df: pd.DataFrame) -> bool:
    """
    Check if MACD crossed above signal line today (golden cross).
    Requires at least 2 rows.
    """
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    prev_macd = prev.get("macd")
    prev_sig = prev.get("macd_signal")
    curr_macd = curr.get("macd")
    curr_sig = curr.get("macd_signal")
    if any(pd.isna(v) for v in [prev_macd, prev_sig, curr_macd, curr_sig]):
        return False
    return float(prev_macd) < float(prev_sig) and float(curr_macd) >= float(curr_sig)


def get_latest_signals(df: pd.DataFrame) -> dict:
    """
    Extract latest-day signals from enriched K-line DataFrame.
    Returns dict with signal values for scoring.
    """
    if df.empty:
        return {}

    row = df.iloc[-1]

    def safe_float(val) -> Optional[float]:
        try:
            v = float(val)
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return None

    ma5 = safe_float(row.get("ma5"))
    ma20 = safe_float(row.get("ma20"))
    ma60 = safe_float(row.get("ma60"))
    rsi14 = safe_float(row.get("rsi14"))
    macd = safe_float(row.get("macd"))
    macd_signal = safe_float(row.get("macd_signal"))
    volume = safe_float(row.get("volume"))
    vol_ma20 = safe_float(row.get("vol_ma20"))

    bull_alignment = (
        ma5 is not None
        and ma20 is not None
        and ma60 is not None
        and ma5 > ma20 > ma60
    )

    rsi_healthy = rsi14 is not None and 50 <= rsi14 <= 70

    golden_cross = check_golden_cross(df)

    volume_surge = (
        volume is not None
        and vol_ma20 is not None
        and vol_ma20 > 0
        and volume > vol_ma20 * 1.5
    )

    return {
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "rsi14": rsi14,
        "macd": macd,
        "macd_signal": macd_signal,
        "volume": volume,
        "vol_ma20": vol_ma20,
        "bull_alignment": bull_alignment,
        "rsi_healthy": rsi_healthy,
        "golden_cross": golden_cross,
        "volume_surge": volume_surge,
    }
