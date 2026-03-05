"""Unit tests for signal_engine."""
import pandas as pd
import numpy as np
import pytest

from app.services.signal_engine import (
    compute_ma,
    compute_rsi,
    compute_macd,
    enrich_kline_df,
    get_latest_signals,
    check_golden_cross,
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


class TestEnrichKlineDF:
    def test_columns_added(self):
        df = make_kline_df(100)
        enriched = enrich_kline_df(df)
        for col in ["ma5", "ma20", "ma60", "rsi14", "macd", "macd_signal", "vol_ma20"]:
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
            "high": close,
            "low": close,
            "close": close,
            "volume": volumes,
        })
        enriched = enrich_kline_df(df)
        signals = get_latest_signals(enriched)
        assert signals["bull_alignment"] is True


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
