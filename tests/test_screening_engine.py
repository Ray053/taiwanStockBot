"""Unit tests for screening_engine."""
import pytest

from app.services.screening_engine import categorize_stocks, CATEGORIES


# ── Test-data helpers ──────────────────────────────────────────────────────────

def _sig(**kwargs) -> dict:
    defaults = {
        "volume_surge": False,
        "bull_alignment": False,
        "golden_cross": False,
        "kd_golden_cross_low": False,
        "rsi_from_low": False,
        "kd_k": None,
        "rsi14": 55.0,
        "volume": 1_000_000,
    }
    defaults.update(kwargs)
    return defaults


def make_stock(
    stock_id: str = "2330",
    stock_name: str = "台積電",
    sector: str = "半導體",
    total_score: float = 50.0,
    tech_score: float = 40.0,
    inst_score: float = 50.0,
    signals: dict | None = None,
    foreign_net: int | None = None,
    trust_net: int | None = None,
    foreign_consec: int = 0,
    trust_consec: int = 0,
) -> dict:
    return {
        "stock_id": stock_id,
        "stock_name": stock_name,
        "sector": sector,
        "total_score": total_score,
        "tech_score": tech_score,
        "inst_score": inst_score,
        "breakdown": {"reasons": []},
        "signals": signals if signals is not None else _sig(),
        "foreign_net": foreign_net,
        "trust_net": trust_net,
        "foreign_consec": foreign_consec,
        "trust_consec": trust_consec,
    }


# ── categorize_stocks() ────────────────────────────────────────────────────────

class TestCategorizeStocksEmpty:
    def test_empty_input_no_skip_categories_present(self):
        result = categorize_stocks([])
        # Categories with skip_if_empty=False must still appear even when empty
        non_skip = {c.key for c in CATEGORIES if not c.skip_if_empty}
        for key in non_skip:
            assert key in result, f"skip_if_empty=False category '{key}' missing"
            assert result[key]["stocks"] == []

    def test_skip_if_empty_categories_absent_when_no_stocks(self):
        result = categorize_stocks([])
        skip_keys = {c.key for c in CATEGORIES if c.skip_if_empty}
        for key in skip_keys:
            assert key not in result, f"skip_if_empty=True category '{key}' should be absent"


class TestVolumeMomentum:
    def test_volume_surge_included(self):
        stock = make_stock(signals=_sig(volume_surge=True, volume=5_000_000))
        result = categorize_stocks([stock])
        assert "volume_momentum" in result
        assert result["volume_momentum"]["stocks"][0]["stock_id"] == "2330"

    def test_no_surge_excluded_and_category_absent(self):
        stock = make_stock(signals=_sig(volume_surge=False))
        result = categorize_stocks([stock])
        # volume_momentum has skip_if_empty=True → absent
        assert "volume_momentum" not in result

    def test_sorted_by_volume_desc(self):
        s1 = make_stock("2330", signals=_sig(volume_surge=True, volume=2_000_000))
        s2 = make_stock("2317", signals=_sig(volume_surge=True, volume=5_000_000))
        result = categorize_stocks([s1, s2])
        stocks = result["volume_momentum"]["stocks"]
        assert stocks[0]["stock_id"] == "2317"


class TestTrustConsecutive:
    def test_min_3_days_required(self):
        s_2d = make_stock("2317", trust_consec=2, trust_net=100)
        s_3d = make_stock("2330", trust_consec=3, trust_net=200)
        result = categorize_stocks([s_2d, s_3d])
        assert "trust_consecutive" in result
        ids = [s["stock_id"] for s in result["trust_consecutive"]["stocks"]]
        assert "2330" in ids
        assert "2317" not in ids

    def test_absent_when_no_3d_stocks(self):
        stock = make_stock(trust_consec=2, trust_net=100)
        result = categorize_stocks([stock])
        assert "trust_consecutive" not in result

    def test_sorted_by_consec_then_trust_net(self):
        s5 = make_stock("2330", trust_consec=5, trust_net=100)
        s3 = make_stock("2317", trust_consec=3, trust_net=9000)
        result = categorize_stocks([s5, s3])
        stocks = result["trust_consecutive"]["stocks"]
        # 5 consecutive days beats 3 even if trust_net is lower
        assert stocks[0]["stock_id"] == "2330"

    def test_trust_net_must_be_positive(self):
        stock = make_stock(trust_consec=5, trust_net=0)
        result = categorize_stocks([stock])
        assert "trust_consecutive" not in result


class TestTrustBigBuy:
    def test_positive_trust_net_included(self):
        stock = make_stock(trust_net=500)
        result = categorize_stocks([stock])
        assert "trust_big_buy" in result
        assert result["trust_big_buy"]["stocks"][0]["stock_id"] == "2330"

    def test_zero_or_none_excluded(self):
        s_zero = make_stock("2330", trust_net=0)
        s_none = make_stock("2317", trust_net=None)
        result = categorize_stocks([s_zero, s_none])
        assert result["trust_big_buy"]["stocks"] == []

    def test_sorted_by_trust_net_desc(self):
        s1 = make_stock("2330", trust_net=1000)
        s2 = make_stock("2317", trust_net=500)
        result = categorize_stocks([s1, s2])
        stocks = result["trust_big_buy"]["stocks"]
        assert stocks[0]["stock_id"] == "2330"

    def test_always_present_even_when_empty(self):
        result = categorize_stocks([])
        # skip_if_empty=False → always present
        assert "trust_big_buy" in result


class TestForeignBigBuy:
    def test_positive_foreign_net_included(self):
        stock = make_stock(foreign_net=3000)
        result = categorize_stocks([stock])
        assert "foreign_big_buy" in result
        assert result["foreign_big_buy"]["stocks"][0]["stock_id"] == "2330"

    def test_negative_foreign_net_excluded(self):
        stock = make_stock(foreign_net=-500)
        result = categorize_stocks([stock])
        assert result["foreign_big_buy"]["stocks"] == []

    def test_sorted_by_foreign_net_desc(self):
        s1 = make_stock("2330", foreign_net=5000)
        s2 = make_stock("2317", foreign_net=2000)
        result = categorize_stocks([s1, s2])
        stocks = result["foreign_big_buy"]["stocks"]
        assert stocks[0]["stock_id"] == "2330"

    def test_always_present_even_when_empty(self):
        result = categorize_stocks([])
        assert "foreign_big_buy" in result


class TestBothBuying:
    def test_requires_both_positive(self):
        only_foreign = make_stock("2330", foreign_net=1000, trust_net=None)
        only_trust = make_stock("2317", foreign_net=None, trust_net=500)
        both = make_stock("2454", foreign_net=500, trust_net=200)
        result = categorize_stocks([only_foreign, only_trust, both])
        assert "both_buying" in result
        ids = [s["stock_id"] for s in result["both_buying"]["stocks"]]
        assert "2454" in ids
        assert "2330" not in ids
        assert "2317" not in ids

    def test_sorted_by_combined_net(self):
        s1 = make_stock("2330", foreign_net=1000, trust_net=200)
        s2 = make_stock("2317", foreign_net=500, trust_net=800)
        result = categorize_stocks([s1, s2])
        stocks = result["both_buying"]["stocks"]
        # s1: 1200, s2: 1300 → s2 first
        assert stocks[0]["stock_id"] == "2317"

    def test_absent_when_no_overlap(self):
        stock = make_stock(foreign_net=1000, trust_net=0)
        result = categorize_stocks([stock])
        assert "both_buying" not in result


class TestKDGoldenCross:
    def test_kd_golden_cross_low_included(self):
        stock = make_stock(signals=_sig(kd_golden_cross_low=True, kd_k=25.0))
        result = categorize_stocks([stock])
        assert "kd_golden_cross" in result
        assert result["kd_golden_cross"]["stocks"][0]["stock_id"] == "2330"

    def test_no_cross_excluded(self):
        stock = make_stock(signals=_sig(kd_golden_cross_low=False))
        result = categorize_stocks([stock])
        assert "kd_golden_cross" not in result

    def test_sorted_by_lower_k_first(self):
        s_low = make_stock("2330", signals=_sig(kd_golden_cross_low=True, kd_k=18.0))
        s_high = make_stock("2317", signals=_sig(kd_golden_cross_low=True, kd_k=28.0))
        result = categorize_stocks([s_low, s_high])
        stocks = result["kd_golden_cross"]["stocks"]
        assert stocks[0]["stock_id"] == "2330"


class TestRSIRecovery:
    def test_rsi_from_low_included(self):
        stock = make_stock(signals=_sig(rsi_from_low=True))
        result = categorize_stocks([stock])
        assert "rsi_recovery" in result

    def test_no_recovery_absent(self):
        stock = make_stock(signals=_sig(rsi_from_low=False))
        result = categorize_stocks([stock])
        assert "rsi_recovery" not in result

    def test_sorted_by_tech_score_desc(self):
        s1 = make_stock("2330", tech_score=70.0, signals=_sig(rsi_from_low=True))
        s2 = make_stock("2317", tech_score=50.0, signals=_sig(rsi_from_low=True))
        result = categorize_stocks([s1, s2])
        stocks = result["rsi_recovery"]["stocks"]
        assert stocks[0]["stock_id"] == "2330"


class TestMABreakout:
    def test_alignment_plus_golden_cross(self):
        stock = make_stock(signals=_sig(bull_alignment=True, golden_cross=True))
        result = categorize_stocks([stock])
        assert "ma_breakout" in result

    def test_alignment_plus_kd_cross(self):
        stock = make_stock(signals=_sig(bull_alignment=True, kd_golden_cross_low=True))
        result = categorize_stocks([stock])
        assert "ma_breakout" in result

    def test_alignment_only_excluded(self):
        stock = make_stock(signals=_sig(bull_alignment=True, golden_cross=False, kd_golden_cross_low=False))
        result = categorize_stocks([stock])
        assert "ma_breakout" not in result

    def test_cross_only_no_alignment_excluded(self):
        stock = make_stock(signals=_sig(bull_alignment=False, golden_cross=True))
        result = categorize_stocks([stock])
        assert "ma_breakout" not in result


class TestMaxStocksLimit:
    def test_max_5_stocks_per_category(self):
        stocks = [make_stock(str(i), foreign_net=1000 - i) for i in range(10)]
        result = categorize_stocks(stocks)
        assert len(result["foreign_big_buy"]["stocks"]) == 5

    def test_top_5_are_highest_foreign_net(self):
        stocks = [make_stock(str(i), foreign_net=i * 100) for i in range(10)]
        result = categorize_stocks(stocks)
        ids = [s["stock_id"] for s in result["foreign_big_buy"]["stocks"]]
        # Highest nets are indices 9,8,7,6,5
        assert "9" in ids and "5" in ids
        assert "0" not in ids


class TestStockInMultipleCategories:
    def test_stock_appears_in_multiple_categories(self):
        stock = make_stock(
            foreign_net=5000,
            trust_net=1000,
            trust_consec=4,
            signals=_sig(volume_surge=True, bull_alignment=True, golden_cross=True, rsi_from_low=True, volume=5_000_000),
        )
        result = categorize_stocks([stock])
        cats_with_stock = [
            key for key, cat_data in result.items()
            if any(s["stock_id"] == "2330" for s in cat_data["stocks"])
        ]
        assert len(cats_with_stock) >= 4

    def test_output_stock_fields(self):
        stock = make_stock(foreign_net=2000, trust_net=500, trust_consec=3)
        result = categorize_stocks([stock])
        s = result["foreign_big_buy"]["stocks"][0]
        assert s["stock_id"] == "2330"
        assert s["stock_name"] == "台積電"
        assert isinstance(s["total_score"], float)
        assert s["foreign_net"] == 2000
        assert s["trust_net"] == 500
        assert s["trust_consec"] == 3


class TestCategoryMetadata:
    def test_all_categories_have_required_fields(self):
        stocks = [make_stock(foreign_net=100)]
        result = categorize_stocks(stocks)
        for key, cat_data in result.items():
            assert "name" in cat_data, f"{key} missing 'name'"
            assert "emoji" in cat_data, f"{key} missing 'emoji'"
            assert "description" in cat_data, f"{key} missing 'description'"
            assert "stocks" in cat_data, f"{key} missing 'stocks'"

    def test_category_count_leq_defined(self):
        stocks = [make_stock(
            foreign_net=1000,
            trust_net=500,
            trust_consec=5,
            signals=_sig(volume_surge=True, bull_alignment=True, golden_cross=True,
                         kd_golden_cross_low=True, rsi_from_low=True, volume=2_000_000, kd_k=20.0),
        )]
        result = categorize_stocks(stocks)
        assert len(result) <= len(CATEGORIES)
