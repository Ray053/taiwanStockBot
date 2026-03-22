"""Unit tests for scoring_engine."""
import pytest
from unittest.mock import MagicMock

from app.services.scoring_engine import (
    score_technical,
    score_institutional,
    score_margin,
    score_macro,
    compute_total_score,
    _count_consecutive_buying,
)


class TestScoreTechnical:
    """
    New scoring breakdown (max 100):
      MA bull alignment              : +30
      RSI from oversold → ≥50        : +25
      RSI healthy 50-70 (no from-low): +15
      RSI overbought > 80            : -20 penalty
      MACD golden cross              : +20
      Volume surge                   : +15
      KD low golden cross            : +10
      KD high dead cross             : -10 penalty
    """

    def test_all_signals_max_score(self):
        """All positive swing signals → 100."""
        signals = {
            "bull_alignment": True,
            "rsi14": 60.0,
            "rsi_from_low": True,    # from oversold → +25
            "rsi_overbought": False,
            "golden_cross": True,
            "volume_surge": True,
            "kd_golden_cross_low": True,
            "kd_dead_cross_high": False,
        }
        score, reasons = score_technical(signals)
        assert score == 100.0  # 30+25+20+15+10
        assert len(reasons) == 5

    def test_healthy_rsi_without_from_low(self):
        """RSI 50-70 without from-low context scores +15 (not +25)."""
        signals = {
            "bull_alignment": False,
            "rsi14": 60.0,
            "rsi_from_low": False,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": False,
        }
        score, reasons = score_technical(signals)
        assert score == 15.0

    def test_rsi_from_low_bonus(self):
        """rsi_from_low + healthy RSI scores +25 (vs plain +15)."""
        base_signals = {
            "bull_alignment": False,
            "rsi14": 58.0,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": False,
        }
        # Without from_low
        s1, _ = score_technical({**base_signals, "rsi_from_low": False})
        # With from_low
        s2, _ = score_technical({**base_signals, "rsi_from_low": True})
        assert s1 == 15.0
        assert s2 == 25.0

    def test_rsi_overbought_penalty(self):
        """RSI > 80 subtracts 20 points."""
        signals = {
            "bull_alignment": True,   # +30
            "rsi14": 85.0,            # -20 penalty
            "rsi_from_low": False,
            "rsi_overbought": True,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": False,
        }
        score, reasons = score_technical(signals)
        assert score == 10.0  # 30 - 20
        assert any("超買" in r for r in reasons)

    def test_rsi_overbought_floor_at_zero(self):
        """Multiple penalties cannot drop score below 0."""
        signals = {
            "bull_alignment": False,
            "rsi14": 85.0,
            "rsi_from_low": False,
            "rsi_overbought": True,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": True,  # -10
        }
        score, _ = score_technical(signals)
        assert score == 0.0  # floored at 0

    def test_kd_golden_cross_low_bonus(self):
        """KD low golden cross adds +10."""
        signals = {
            "bull_alignment": False,
            "rsi14": 45.0,
            "rsi_from_low": False,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": True,
            "kd_dead_cross_high": False,
            "kd_k": 28.5,
            "kd_d": 27.0,
        }
        score, reasons = score_technical(signals)
        assert score == 10.0
        assert any("KD" in r and "金叉" in r for r in reasons)

    def test_kd_dead_cross_high_penalty(self):
        """KD high dead cross subtracts 10."""
        signals = {
            "bull_alignment": True,   # +30
            "rsi14": 55.0,            # +15
            "rsi_from_low": False,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": True,  # -10
            "kd_k": 78.0,
        }
        score, reasons = score_technical(signals)
        assert score == 35.0  # 30 + 15 - 10
        assert any("死叉" in r for r in reasons)

    def test_no_signals(self):
        signals = {
            "bull_alignment": False,
            "rsi14": 30.0,
            "rsi_from_low": False,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": False,
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": False,
        }
        score, reasons = score_technical(signals)
        assert score == 0.0
        assert len(reasons) == 0

    def test_partial_signals(self):
        """MA + volume (no RSI match) = 30 + 15 = 45."""
        signals = {
            "bull_alignment": True,   # +30
            "rsi14": 45.0,            # out of 50-70 range → 0
            "rsi_from_low": False,
            "rsi_overbought": False,
            "golden_cross": False,
            "volume_surge": True,     # +15
            "kd_golden_cross_low": False,
            "kd_dead_cross_high": False,
        }
        score, reasons = score_technical(signals)
        assert score == 45.0

    def test_rsi_boundary_healthy_lower(self):
        """RSI exactly 50 without from-low = +15."""
        signals = {
            "bull_alignment": False, "rsi14": 50.0, "rsi_from_low": False,
            "rsi_overbought": False, "golden_cross": False, "volume_surge": False,
            "kd_golden_cross_low": False, "kd_dead_cross_high": False,
        }
        score, _ = score_technical(signals)
        assert score == 15.0

    def test_rsi_boundary_healthy_upper(self):
        """RSI exactly 70 without from-low = +15."""
        signals = {
            "bull_alignment": False, "rsi14": 70.0, "rsi_from_low": False,
            "rsi_overbought": False, "golden_cross": False, "volume_surge": False,
            "kd_golden_cross_low": False, "kd_dead_cross_high": False,
        }
        score, _ = score_technical(signals)
        assert score == 15.0

    def test_rsi_just_above_70_no_score(self):
        """RSI 70.1 is above healthy range and not overbought → 0."""
        signals = {
            "bull_alignment": False, "rsi14": 70.1, "rsi_from_low": False,
            "rsi_overbought": False, "golden_cross": False, "volume_surge": False,
            "kd_golden_cross_low": False, "kd_dead_cross_high": False,
        }
        score, _ = score_technical(signals)
        assert score == 0.0

    def test_empty_signals(self):
        score, reasons = score_technical({})
        assert score == 0.0


class TestScoreInstitutional:
    def test_all_buying_single_day(self):
        """Single day buy: 40+40+20 = 100, capped at 100."""
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

    def test_foreign_3_consecutive_days_bonus(self):
        """3 consecutive days of foreign buy → base 40 + 8 bonus = 48."""
        score, reasons = score_institutional(1000, None, None, foreign_consec=3)
        assert score == 48.0
        assert any("連續" in r for r in reasons)

    def test_foreign_5_consecutive_days_bonus(self):
        """5 consecutive days → base 40 + 15 bonus = 55."""
        score, reasons = score_institutional(1000, None, None, foreign_consec=5)
        assert score == 55.0
        assert any("主力建倉" in r for r in reasons)

    def test_trust_3_consecutive_days_bonus(self):
        """Trust 3 consecutive days → base 40 + 5 = 45."""
        score, reasons = score_institutional(None, 500, None, trust_consec=3)
        assert score == 45.0

    def test_trust_5_consecutive_days_bonus(self):
        """Trust 5 consecutive days → base 40 + 10 = 50."""
        score, reasons = score_institutional(None, 500, None, trust_consec=5)
        assert score == 50.0

    def test_consecutive_bonus_no_buy_today_ignored(self):
        """Consecutive days bonus has no effect when net is not positive."""
        score, _ = score_institutional(-100, None, None, foreign_consec=5)
        assert score == 0.0

    def test_cap_at_100(self):
        """All buys + max consecutive bonuses should be capped at 100."""
        score, _ = score_institutional(1000, 500, 200, foreign_consec=5, trust_consec=5)
        assert score == 100.0


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

    def test_none_values_neutral(self):
        """No data → neutral 50, not penalised."""
        score, reasons = score_margin(None, None)
        assert score == 50.0
        assert reasons == []


class TestScoreMacro:
    def _make_snapshot(self, **kwargs):
        snap = MagicMock()
        defaults = {
            "fed_cut_prob": 0.5,
            "nvidia_beat_prob": 0.5,
            "taiwan_strait_prob": 0.1,
            "china_gdp_miss_prob": 0.3,
            "oil_above_90_prob": 0.4,
            # US market / night session fields — set None so they are not applied
            "txf_night_change": None,
            "sox_change": None,
            "nasdaq_change": None,
            "sp500_change": None,
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


class TestCountConsecutiveBuying:
    def _make_inst(self, foreign_net):
        rec = MagicMock()
        rec.foreign_net = foreign_net
        return rec

    def test_all_positive(self):
        records = [self._make_inst(500), self._make_inst(300), self._make_inst(100)]
        assert _count_consecutive_buying(records, "foreign_net") == 3

    def test_breaks_on_negative(self):
        records = [self._make_inst(500), self._make_inst(-100), self._make_inst(200)]
        assert _count_consecutive_buying(records, "foreign_net") == 1

    def test_first_record_negative(self):
        records = [self._make_inst(-100), self._make_inst(200)]
        assert _count_consecutive_buying(records, "foreign_net") == 0

    def test_empty_list(self):
        assert _count_consecutive_buying([], "foreign_net") == 0

    def test_none_value_breaks_streak(self):
        records = [self._make_inst(500), self._make_inst(None), self._make_inst(200)]
        assert _count_consecutive_buying(records, "foreign_net") == 1
