"""AiDEAR-style multi-category stock screener.

Each category independently filters and ranks stocks so the daily output
always contains results from at least the institutional-buying categories.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ScreenCategory:
    key: str
    name: str
    emoji: str
    description: str
    filter_fn: Callable[[dict], bool]
    sort_key: Callable[[dict], float]
    max_stocks: int = 5
    # When True, omit the category entirely if no stocks pass the filter.
    # When False, include an empty-stocks entry so the caller can show
    # a placeholder (useful for "always visible" categories).
    skip_if_empty: bool = True


def _sig(s: dict) -> dict:
    return s.get("signals") or {}


CATEGORIES: list[ScreenCategory] = [
    ScreenCategory(
        key="volume_momentum",
        name="有量大動能",
        emoji="🚀",
        description="成交量爆增 1.5 倍以上，強勢量能啟動",
        filter_fn=lambda s: _sig(s).get("volume_surge", False),
        sort_key=lambda s: float(_sig(s).get("volume") or 0),
        max_stocks=5,
        skip_if_empty=True,
    ),
    ScreenCategory(
        key="trust_consecutive",
        name="投信動能連買",
        emoji="🏦",
        description="投信連續 3 日以上買超，持續佈局中",
        filter_fn=lambda s: (s.get("trust_consec") or 0) >= 3 and (s.get("trust_net") or 0) > 0,
        sort_key=lambda s: float((s.get("trust_consec") or 0) * 1_000_000 + (s.get("trust_net") or 0)),
        max_stocks=5,
        skip_if_empty=True,
    ),
    ScreenCategory(
        key="trust_big_buy",
        name="投信剛大買",
        emoji="💰",
        description="今日投信大量買超",
        filter_fn=lambda s: (s.get("trust_net") or 0) > 0,
        sort_key=lambda s: float(s.get("trust_net") or 0),
        max_stocks=5,
        skip_if_empty=False,
    ),
    ScreenCategory(
        key="foreign_big_buy",
        name="外資剛大買",
        emoji="🌏",
        description="今日外資大量買超",
        filter_fn=lambda s: (s.get("foreign_net") or 0) > 0,
        sort_key=lambda s: float(s.get("foreign_net") or 0),
        max_stocks=5,
        skip_if_empty=False,
    ),
    ScreenCategory(
        key="both_buying",
        name="外資投信同買",
        emoji="🤝",
        description="外資與投信今日同步買超，籌碼共識強",
        filter_fn=lambda s: (s.get("foreign_net") or 0) > 0 and (s.get("trust_net") or 0) > 0,
        sort_key=lambda s: float((s.get("foreign_net") or 0) + (s.get("trust_net") or 0)),
        max_stocks=5,
        skip_if_empty=True,
    ),
    ScreenCategory(
        key="kd_golden_cross",
        name="KD低檔金叉",
        emoji="✨",
        description="KD 從超賣區（K<30）上穿 D，波段起點信號",
        filter_fn=lambda s: _sig(s).get("kd_golden_cross_low", False),
        sort_key=lambda s: -float(_sig(s).get("kd_k") or 100),
        max_stocks=5,
        skip_if_empty=True,
    ),
    ScreenCategory(
        key="rsi_recovery",
        name="RSI低檔反彈",
        emoji="💹",
        description="RSI 從超賣低檔回升，動能翻轉中",
        filter_fn=lambda s: _sig(s).get("rsi_from_low", False),
        sort_key=lambda s: float(s.get("tech_score") or 0),
        max_stocks=5,
        skip_if_empty=True,
    ),
    ScreenCategory(
        key="ma_breakout",
        name="均線多頭突破",
        emoji="📊",
        description="均線多頭排列且 MACD/KD 確認突破",
        filter_fn=lambda s: (
            _sig(s).get("bull_alignment", False)
            and (_sig(s).get("golden_cross", False) or _sig(s).get("kd_golden_cross_low", False))
        ),
        sort_key=lambda s: float(s.get("tech_score") or 0),
        max_stocks=5,
        skip_if_empty=True,
    ),
]


def categorize_stocks(scored_stocks: list[dict]) -> dict[str, dict]:
    """
    Assign scored stocks into named AiDEAR-style screening categories.

    Args:
        scored_stocks: list of dicts from run_scoring(), each must contain:
            - signals (dict): output of get_latest_signals()
            - foreign_net, trust_net (int | None)
            - foreign_consec, trust_consec (int)
            - stock_id, stock_name, sector, total_score, tech_score, inst_score
            - breakdown (dict with "reasons" list)

    Returns:
        Ordered dict keyed by category.key → {name, emoji, description, stocks}.
        Categories with skip_if_empty=True are omitted when no stocks match.
        Categories with skip_if_empty=False always appear (may have empty stocks list).
    """
    result: dict[str, dict] = {}

    for cat in CATEGORIES:
        matched = [s for s in scored_stocks if cat.filter_fn(s)]

        if not matched and cat.skip_if_empty:
            continue

        try:
            matched.sort(key=cat.sort_key, reverse=True)
        except TypeError:
            pass

        result[cat.key] = {
            "name": cat.name,
            "emoji": cat.emoji,
            "description": cat.description,
            "stocks": [
                {
                    "stock_id": s["stock_id"],
                    "stock_name": s.get("stock_name") or "",
                    "sector": s.get("sector") or "",
                    "total_score": round(float(s.get("total_score") or 0), 1),
                    "tech_score": round(float(s.get("tech_score") or 0), 1),
                    "inst_score": round(float(s.get("inst_score") or 0), 1),
                    "trust_net": s.get("trust_net"),
                    "foreign_net": s.get("foreign_net"),
                    "trust_consec": s.get("trust_consec") or 0,
                    "foreign_consec": s.get("foreign_consec") or 0,
                    "reasons": (s.get("breakdown") or {}).get("reasons", []),
                }
                for s in matched[: cat.max_stocks]
            ],
        }

    return result
