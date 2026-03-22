"""Technical indicator computation: MA, RSI, MACD, KD, Volume."""
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


def compute_kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 9,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """
    Compute KD (Stochastic Oscillator) — Taiwan convention.

    RSV = (close - lowest_low_k) / (highest_high_k - lowest_low_k) * 100
    K   = SMA(RSV, d_period)   [slow %K]
    D   = SMA(K, d_period)

    Returns (k_series, d_series), values 0–100.
    """
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()

    denom = highest_high - lowest_low
    rsv = pd.Series(index=close.index, dtype=float)
    valid = denom > 0
    rsv[valid] = (close[valid] - lowest_low[valid]) / denom[valid] * 100
    # When price range is zero (flat), set RSV to 50 (neutral)
    rsv[~valid & denom.notna()] = 50.0

    k = rsv.rolling(window=d_period, min_periods=d_period).mean()
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return k, d


def compute_volume_ma(volumes: pd.Series, window: int = 20) -> pd.Series:
    """Compute volume moving average."""
    return volumes.rolling(window=window, min_periods=1).mean()


def enrich_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a raw K-line DataFrame with columns [date/trade_date, close, volume, open, high, low],
    compute and append MA5, MA20, MA60, RSI14, MACD, MACD_signal, KD_K, KD_D columns.
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

    # KD — requires high/low columns; fall back gracefully if missing
    if "high" in df.columns and "low" in df.columns:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        kd_k, kd_d = compute_kd(high, low, close)
        df["kd_k"] = kd_k.round(2)
        df["kd_d"] = kd_d.round(2)
    else:
        df["kd_k"] = np.nan
        df["kd_d"] = np.nan

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


def check_kd_golden_cross_low(df: pd.DataFrame, low_threshold: float = 30.0) -> bool:
    """
    Check if KD had a golden cross (K crossed above D) while K was in the
    oversold zone (K < low_threshold yesterday).

    This is the classic swing-trade entry signal in Taiwan stocks.
    Requires at least 2 rows with valid kd_k / kd_d columns.
    """
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    for col in ["kd_k", "kd_d"]:
        if pd.isna(prev.get(col)) or pd.isna(curr.get(col)):
            return False
    prev_k = float(prev["kd_k"])
    prev_d = float(prev["kd_d"])
    curr_k = float(curr["kd_k"])
    curr_d = float(curr["kd_d"])
    # K was in oversold territory yesterday, and crossed above D today
    return prev_k < low_threshold and prev_k < prev_d and curr_k >= curr_d


def check_kd_dead_cross_high(df: pd.DataFrame, high_threshold: float = 70.0) -> bool:
    """
    Check if KD had a dead cross (K crossed below D) while K was in the
    overbought zone (K > high_threshold yesterday).

    This is a swing-trade exit / avoid-entry signal.
    Requires at least 2 rows with valid kd_k / kd_d columns.
    """
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    for col in ["kd_k", "kd_d"]:
        if pd.isna(prev.get(col)) or pd.isna(curr.get(col)):
            return False
    prev_k = float(prev["kd_k"])
    prev_d = float(prev["kd_d"])
    curr_k = float(curr["kd_k"])
    curr_d = float(curr["kd_d"])
    # K was overbought yesterday, and crossed below D today
    return prev_k > high_threshold and prev_k > prev_d and curr_k <= curr_d


def get_latest_signals(df: pd.DataFrame) -> dict:
    """
    Extract latest-day signals from enriched K-line DataFrame.
    Returns dict with signal values for scoring.

    New swing-trade signals vs original:
    - kd_k / kd_d         : KD indicator values
    - kd_golden_cross_low  : KD low golden cross (swing entry signal)
    - kd_dead_cross_high   : KD high dead cross (avoid / exit signal)
    - rsi_from_low         : RSI was oversold recently and is now recovering (≥50)
    - rsi_overbought       : RSI > 80 (chase risk)
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
    kd_k = safe_float(row.get("kd_k"))
    kd_d = safe_float(row.get("kd_d"))

    bull_alignment = (
        ma5 is not None
        and ma20 is not None
        and ma60 is not None
        and ma5 > ma20 > ma60
    )

    rsi_healthy = rsi14 is not None and 50 <= rsi14 <= 70

    # RSI direction: was oversold (< 40) in the past 7 bars and is now recovering (≥ 50)
    rsi_from_low = False
    rsi_overbought = rsi14 is not None and rsi14 > 80
    if rsi14 is not None and rsi14 >= 50 and len(df) >= 2:
        lookback = df.iloc[-7:]["rsi14"].dropna().astype(float)
        if len(lookback) >= 2 and lookback.iloc[:-1].min() < 40:
            rsi_from_low = True

    golden_cross = check_golden_cross(df)

    volume_surge = (
        volume is not None
        and vol_ma20 is not None
        and vol_ma20 > 0
        and volume > vol_ma20 * 1.5
    )

    kd_golden_cross_low = check_kd_golden_cross_low(df)
    kd_dead_cross_high = check_kd_dead_cross_high(df)

    return {
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "rsi14": rsi14,
        "macd": macd,
        "macd_signal": macd_signal,
        "volume": volume,
        "vol_ma20": vol_ma20,
        "kd_k": kd_k,
        "kd_d": kd_d,
        "bull_alignment": bull_alignment,
        "rsi_healthy": rsi_healthy,
        "rsi_from_low": rsi_from_low,
        "rsi_overbought": rsi_overbought,
        "golden_cross": golden_cross,
        "volume_surge": volume_surge,
        "kd_golden_cross_low": kd_golden_cross_low,
        "kd_dead_cross_high": kd_dead_cross_high,
    }
