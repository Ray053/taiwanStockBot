"""Polymarket gamma API wrapper."""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

POLYMARKET_BASE_URL = "https://gamma-api.polymarket.com"
TIMEOUT = 15
MAX_RETRIES = 3


def _fetch_market_prob(slug: str) -> float:
    """
    Fetch YES probability for a Polymarket market slug.
    Returns 0.5 (neutral) if the market is not found or API fails.
    """
    url = f"{POLYMARKET_BASE_URL}/markets"
    params = {"slug": slug}

    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    logger.warning(f"Polymarket: no market found for slug '{slug}', returning 0.5")
                    return 0.5

                market = data[0] if isinstance(data, list) else data
                outcome_prices = market.get("outcomePrices", [])
                if outcome_prices:
                    return float(outcome_prices[0])

                logger.warning(f"Polymarket: no outcomePrices for slug '{slug}', returning 0.5")
                return 0.5

        except httpx.HTTPStatusError as e:
            logger.warning(f"Polymarket HTTP error for slug '{slug}' (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.warning(f"Polymarket error for slug '{slug}' (attempt {attempt + 1}): {e}")

    logger.error(f"Polymarket: all retries exhausted for slug '{slug}', returning 0.5")
    return 0.5


def fetch_macro_snapshot() -> dict:
    """
    Fetch all configured Polymarket macro signals.
    Returns a dict with probabilities for each event.
    """
    return {
        "fed_cut_prob": _fetch_market_prob(settings.poly_fed_cut_slug),
        "nvidia_beat_prob": _fetch_market_prob(settings.poly_nvidia_beat_slug),
        "taiwan_strait_prob": _fetch_market_prob(settings.poly_taiwan_strait_slug),
        "china_gdp_miss_prob": _fetch_market_prob(settings.poly_china_gdp_slug),
        "oil_above_90_prob": _fetch_market_prob(settings.poly_oil_90_slug),
    }
