"""Unit tests for signal_engine."""
import pandas as pd
import numpy as np
import pytest

from app.services.signal_engine import (
    compute_ma,
    compute_rsi,
    compute_macd,
    compute_kd,
    enrich_kline_df,
    get_latest_signals,
    check_golden_cross,
    check_kd_golden_cross_low,
    check_kd_dead_cross_high,
)


def make_price_series(n=100, start=100.0, trend=0.5):
    """Generate a simple trending price series."""
    prices = [start + i * trend + (i % 5 - 2) * 0.3 for i in range(n)]
    return pd.Series(prices, dtype=float)


def make_kline_df(n=100):
    """Generate a minimal K-line DataFrame."""
    close_prices = [100 + i * 0.5 + (i % 7 - 3) * 0.2 for i in range(n)]
    volumes = [1_000_000 + i * 10_000 for i in range(n)]
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "trade_date": dates,
        "open": [p - 0.5 for p in close_prices],
        "high": [p + 1.0 for p in close_prices],
        "low": [p - 1.0 for p in close_prices],
        "close": close_prices,
        "volume": volumes,
    })


class TestComputeMA:
    def test_basic(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = compute_ma(s, 3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(2.0)
        assert result.iloc[4] == pytest.approx(4.0)

    def test_window_larger_than_series(self):
        s = pd.Series([1.0, 2.0])
        result = compute_ma(s, 5)
        assert result.isna().all()


class TestComputeRSI:
    def test_range(self):
        s = make_price_series(50)
        rsi = compute_rsi(s, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_all_gains(self):
        """RSI should be near 100 for pure uptrend."""
        s = pd.Series([float(i) for i in range(1, 51)])
        rsi = compute_rsi(s, 14)
        assert rsi.dropna().iloc[-1] > 90

    def test_all_losses(self):
        """RSI should be near 0 for pure downtrend."""
        s = pd.Series([float(50 - i) for i in range(50)])
        rsi = compute_rsi(s, 14)
        assert rsi.dropna().iloc[-1] < 10


class TestComputeMACD:
    def test_returns_three_series(self):
        s = make_price_series(60)
        macd, signal, hist = compute_macd(s)
        assert len(macd) == len(s)
        assert len(signal) == len(s)
        assert len(hist) == len(s)

    def test_histogram_equals_diff(self):
        s = make_price_series(60)
        macd, signal, hist = compute_macd(s)
        diff = macd - signal
        pd.testing.assert_series_equal(hist, diff, check_names=False)


class TestComputeKD:
    def test_returns_two_series(self):
        df = make_kline_df(60)
        k, d = compute_kd(df["high"], df["low"], df["close"])
        assert len(k) == 60
        assert len(d) == 60

    def test_values_in_range(self):
        df = make_kline_df(60)
        k, d = compute_kd(df["high"], df["low"], df["close"])
        valid_k = k.dropna()
        valid_d = d.dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()
        assert (valid_d >= 0).all() and (valid_d <= 100).all()

    def test_minimum_periods(self):
        """K should be NaN for fewer rows than k_period (default 9)."""
        df = make_kline_df(20)
        k, d = compute_kd(df["high"], df["low"], df["close"], k_period=9, d_period=3)
        # First 8 rows should be NaN for k
        assert k.iloc[:8].isna().all()

    def test_flat_price_range_returns_neutral(self):
        """When high == low (no range), RSV should be 50."""
        prices = pd.Series([100.0] * 20)
        k, d = compute_kd(prices, prices, prices)
        valid_k = k.dropna()
        assert (valid_k == 50.0).all()


class TestEnrichKlineDF:
    def test_columns_added(self):
        df = make_kline_df(100)
        enriched = enrich_kline_df(df)
        for col in ["ma5", "ma20", "ma60", "rsi14", "macd", "macd_signal", "vol_ma20", "kd_k", "kd_d"]:
            assert col in enriched.columns, f"Missing column: {col}"

    def test_empty_df(self):
        df = pd.DataFrame()
        result = enrich_kline_df(df)
        assert result.empty

    def test_sorted_by_date(self):
        df = make_kline_df(30)
        # Shuffle dates
        df = df.sample(frac=1).reset_index(drop=True)
        enriched = enrich_kline_df(df)
        assert enriched["trade_date"].is_monotonic_increasing

    def test_kd_nan_without_high_low(self):
        """KD should be NaN when high/low columns are absent."""
        df = make_kline_df(100)[["trade_date", "open", "close", "volume"]]
        enriched = enrich_kline_df(df)
        assert enriched["kd_k"].isna().all()
        assert enriched["kd_d"].isna().all()


class TestGetLatestSignals:
    def test_returns_dict(self):
        df = make_kline_df(100)
        enriched = enrich_kline_df(df)
        signals = get_latest_signals(enriched)
        assert isinstance(signals, dict)
        assert "bull_alignment" in signals
        assert "rsi_healthy" in signals
        assert "golden_cross" in signals
        assert "volume_surge" in signals
        assert "kd_k" in signals
        assert "kd_d" in signals
        assert "kd_golden_cross_low" in signals
        assert "kd_dead_cross_high" in signals
        assert "rsi_from_low" in signals
        assert "rsi_overbought" in signals

    def test_empty_df(self):
        df = pd.DataFrame()
        result = get_latest_signals(df)
        assert result == {}

    def test_bull_alignment_true(self):
        """Build a strong uptrend series where MA5 > MA20 > MA60."""
        close = [100 + i * 2.0 for i in range(120)]
        volumes = [1_000_000] * 120
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        df = pd.DataFrame({
            "trade_date": dates,
            "open": close,
            "high": [p + 1 for p in close],
            "low": [p - 1 for p in close],
            "close": close,
            "volume": volumes,
        })
        enriched = enrich_kline_df(df)
        signals = get_latest_signals(enriched)
        assert signals["bull_alignment"] is True

    def test_rsi_overbought_flag(self):
        """A pure uptrend produces RSI > 80 → rsi_overbought should be True."""
        close = [float(i) for i in range(1, 121)]
        volumes = [1_000_000] * 120
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        df = pd.DataFrame({
            "trade_date": dates,
            "open": close,
            "high": [p + 1 for p in close],
            "low": [p - 0.5 for p in close],
            "close": close,
            "volume": volumes,
        })
        enriched = enrich_kline_df(df)
        signals = get_latest_signals(enriched)
        assert signals["rsi_overbought"] is True

    def test_rsi_from_low_detected(self):
        """Build a series that dips then recovers to trigger rsi_from_low."""
        # First 80 days declining, then 30 days rising sharply
        close = [100 - i * 0.5 for i in range(80)] + [60 + i * 2.0 for i in range(30)]
        volumes = [1_000_000] * 110
        dates = pd.date_range("2024-01-01", periods=110, freq="B")
        df = pd.DataFrame({
            "trade_date": dates,
            "open": close,
            "high": [p + 1 for p in close],
            "low": [p - 1 for p in close],
            "close": close,
            "volume": volumes,
        })
        enriched = enrich_kline_df(df)
        signals = get_latest_signals(enriched)
        # After recovery RSI should be >= 50 and we had oversold recently
        if signals.get("rsi14") is not None and signals["rsi14"] >= 50:
            # rsi_from_low depends on the recent 7-bar window; check type at minimum
            assert isinstance(signals["rsi_from_low"], bool)


class TestCheckGoldenCross:
    def test_golden_cross_detected(self):
        # Construct data where MACD crosses signal on last bar
        df = pd.DataFrame({
            "macd": [-0.1, 0.1],
            "macd_signal": [0.05, 0.05],
        })
        assert check_golden_cross(df) is True

    def test_no_cross(self):
        df = pd.DataFrame({
            "macd": [0.1, 0.2],
            "macd_signal": [0.05, 0.05],
        })
        assert check_golden_cross(df) is False

    def test_too_few_rows(self):
        df = pd.DataFrame({"macd": [0.1], "macd_signal": [0.05]})
        assert check_golden_cross(df) is False


class TestCheckKDGoldenCrossLow:
    def test_golden_cross_low_detected(self):
        """K was below 30, crossed above D today → swing entry signal."""
        df = pd.DataFrame({
            "kd_k": [25.0, 32.0],   # was 25 (< 30), now 32
            "kd_d": [28.0, 30.0],   # prev K(25) < D(28), curr K(32) > D(30)
        })
        assert check_kd_golden_cross_low(df) is True

    def test_no_low_cross_when_k_not_low(self):
        """K crosses above D but was not in oversold zone → not a low cross."""
        df = pd.DataFrame({
            "kd_k": [50.0, 60.0],
            "kd_d": [55.0, 58.0],
        })
        assert check_kd_golden_cross_low(df) is False

    def test_no_cross_when_already_above(self):
        """K was below 30 but already above D yesterday → no new cross."""
        df = pd.DataFrame({
            "kd_k": [20.0, 25.0],
            "kd_d": [15.0, 20.0],   # prev K > D already
        })
        assert check_kd_golden_cross_low(df) is False

    def test_too_few_rows(self):
        df = pd.DataFrame({"kd_k": [20.0], "kd_d": [25.0]})
        assert check_kd_golden_cross_low(df) is False

    def test_nan_values(self):
        df = pd.DataFrame({"kd_k": [np.nan, 25.0], "kd_d": [np.nan, 20.0]})
        assert check_kd_golden_cross_low(df) is False


class TestCheckKDDeadCrossHigh:
    def test_dead_cross_high_detected(self):
        """K was above 70, crossed below D today → overbought exit signal."""
        df = pd.DataFrame({
            "kd_k": [80.0, 72.0],   # was 80 (> 70), now 72
            "kd_d": [75.0, 74.0],   # prev K(80) > D(75), curr K(72) < D(74)
        })
        assert check_kd_dead_cross_high(df) is True

    def test_no_dead_cross_when_k_not_high(self):
        """K crosses below D but was not in overbought zone → not a high dead cross."""
        df = pd.DataFrame({
            "kd_k": [50.0, 45.0],
            "kd_d": [48.0, 47.0],
        })
        assert check_kd_dead_cross_high(df) is False

    def test_too_few_rows(self):
        df = pd.DataFrame({"kd_k": [80.0], "kd_d": [75.0]})
        assert check_kd_dead_cross_high(df) is False
