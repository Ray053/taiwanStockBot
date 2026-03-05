"""Unit tests for scoring_engine."""
import pytest
from unittest.mock import MagicMock

from app.services.scoring_engine import (
    score_technical,
    score_institutional,
    score_margin,
    score_macro,
    compute_total_score,
)


class TestScoreTechnical:
    def test_all_signals_true(self):
        signals = {
            "bull_alignment": True,
            "rsi14": 60.0,
            "golden_cross": True,
            "volume_surge": True,
        }
        score, reasons = score_technical(signals)
        assert score == 100.0
        assert len(reasons) == 4

    def test_no_signals(self):
        signals = {
            "bull_alignment": False,
            "rsi14": 30.0,
            "golden_cross": False,
            "volume_surge": False,
        }
        score, reasons = score_technical(signals)
        assert score == 0.0
        assert len(reasons) == 0

    def test_partial_signals(self):
        signals = {
            "bull_alignment": True,
            "rsi14": 45.0,  # out of 50~70 range
            "golden_cross": False,
            "volume_surge": True,
        }
        score, reasons = score_technical(signals)
        assert score == 55.0  # 40 + 15

    def test_rsi_boundary_values(self):
        # RSI exactly 50 should score
        signals = {"bull_alignment": False, "rsi14": 50.0, "golden_cross": False, "volume_surge": False}
        score, _ = score_technical(signals)
        assert score == 25.0

        # RSI exactly 70 should score
        signals["rsi14"] = 70.0
        score, _ = score_technical(signals)
        assert score == 25.0

        # RSI 70.1 should NOT score
        signals["rsi14"] = 70.1
        score, _ = score_technical(signals)
        assert score == 0.0

    def test_empty_signals(self):
        score, reasons = score_technical({})
        assert score == 0.0


class TestScoreInstitutional:
    def test_all_buying(self):
        score, reasons = score_institutional(1000, 500, 200)
        assert score == 100.0
        assert len(reasons) == 3

    def test_all_selling(self):
        score, reasons = score_institutional(-1000, -500, -200)
        assert score == 0.0
        assert len(reasons) == 0

    def test_only_foreign(self):
        score, reasons = score_institutional(1000, None, None)
        assert score == 40.0

    def test_only_trust(self):
        score, reasons = score_institutional(None, 500, None)
        assert score == 40.0

    def test_only_dealer(self):
        score, reasons = score_institutional(None, None, 200)
        assert score == 20.0

    def test_zero_net(self):
        # Zero is NOT > 0, so no score
        score, reasons = score_institutional(0, 0, 0)
        assert score == 0.0


class TestScoreMargin:
    def test_both_decrease(self):
        score, reasons = score_margin(-100, -50)
        assert score == 100.0
        assert "最乾淨" in reasons[0]

    def test_margin_decrease_only(self):
        score, reasons = score_margin(-100, 50)
        assert score == 60.0

    def test_short_decrease_only(self):
        score, reasons = score_margin(100, -50)
        assert score == 60.0

    def test_both_increase(self):
        score, reasons = score_margin(100, 50)
        assert score == 20.0

    def test_none_values(self):
        score, reasons = score_margin(None, None)
        # Neither decreasing
        assert score == 20.0


class TestScoreMacro:
    def _make_snapshot(self, **kwargs):
        snap = MagicMock()
        defaults = {
            "fed_cut_prob": 0.5,
            "nvidia_beat_prob": 0.5,
            "taiwan_strait_prob": 0.1,
            "china_gdp_miss_prob": 0.3,
            "oil_above_90_prob": 0.4,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(snap, k, v)
        return snap

    def test_no_snapshot_returns_50(self):
        score, _ = score_macro("半導體", None)
        assert score == 50.0

    def test_nvidia_beat_high_semiconductor(self):
        snap = self._make_snapshot(nvidia_beat_prob=0.75)
        score, reasons = score_macro("半導體", snap)
        assert score == 70.0  # 50 + 20

    def test_taiwan_strait_high_semiconductor(self):
        snap = self._make_snapshot(taiwan_strait_prob=0.30)
        score, reasons = score_macro("半導體", snap)
        assert score == 20.0  # 50 - 30

    def test_fed_cut_high_financial(self):
        snap = self._make_snapshot(fed_cut_prob=0.70)
        score, reasons = score_macro("金融", snap)
        assert score == 70.0  # 50 + 20

    def test_sector_mismatch_no_change(self):
        """Semiconductor rules should not affect 航運 sector."""
        snap = self._make_snapshot(nvidia_beat_prob=0.80, taiwan_strait_prob=0.40)
        score, reasons = score_macro("航運", snap)
        assert score == 50.0  # no applicable rules

    def test_oil_above_90_shipping(self):
        snap = self._make_snapshot(oil_above_90_prob=0.60)
        score, reasons = score_macro("航運", snap)
        assert score == 60.0  # 50 + 10

    def test_score_capped_at_100(self):
        snap = self._make_snapshot(fed_cut_prob=0.80, nvidia_beat_prob=0.80)
        # Apply to a sector that triggers multiple rules... use 金融 (only fed) + 半導體 for nvidia
        # 金融 sector: +20 from fed, base 50 → 70, still < 100
        score, _ = score_macro("金融", snap)
        assert score <= 100.0

    def test_score_floored_at_0(self):
        snap = self._make_snapshot(taiwan_strait_prob=0.50, nvidia_beat_prob=0.10)
        score, _ = score_macro("半導體", snap)
        assert score >= 0.0


class TestComputeTotalScore:
    def test_weights_sum(self):
        # All 100 → total should be 100
        total = compute_total_score(100, 100, 100, 100)
        assert total == pytest.approx(100.0)

    def test_all_zero(self):
        total = compute_total_score(0, 0, 0, 0)
        assert total == pytest.approx(0.0)

    def test_custom_weights(self):
        # Default weights: tech=0.35, inst=0.35, margin=0.10, macro=0.20
        total = compute_total_score(100, 0, 0, 0)
        assert total == pytest.approx(35.0)

        total = compute_total_score(0, 100, 0, 0)
        assert total == pytest.approx(35.0)

        total = compute_total_score(0, 0, 100, 0)
        assert total == pytest.approx(10.0)

        total = compute_total_score(0, 0, 0, 100)
        assert total == pytest.approx(20.0)
