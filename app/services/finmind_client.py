"""FinMind REST API wrapper with Redis caching."""
import json
import logging
from typing import Optional

import httpx
import redis

from app.config import settings

logger = logging.getLogger(__name__)

FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
TIMEOUT = 15
MAX_RETRIES = 3

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _cache_key(stock_id: str, data_type: str, trade_date: str) -> str:
    return f"finmind:{stock_id}:{data_type}:{trade_date}"


def _get_cached(key: str) -> Optional[list]:
    try:
        r = get_redis()
        val = r.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        logger.warning(f"Redis get error: {e}")
    return None


def _set_cached(key: str, data: list, ttl: int = 3600) -> None:
    try:
        r = get_redis()
        r.setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.warning(f"Redis set error: {e}")


def _fetch(dataset: str, stock_id: str, start_date: str, end_date: str) -> list[dict]:
    """Core FinMind API fetch with retry logic."""
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
        "token": settings.finmind_api_token,
    }
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(FINMIND_API_URL, params=params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("status") == 200:
                    return body.get("data", [])
                logger.warning(f"FinMind API non-200 status for {dataset}/{stock_id}: {body.get('msg')}")
                return []
        except Exception as e:
            last_err = e
            logger.warning(f"FinMind fetch error ({dataset}/{stock_id}) attempt {attempt + 1}: {e}")
    logger.error(f"FinMind: all retries exhausted for {dataset}/{stock_id}: {last_err}")
    return []


def fetch_stock_price(stock_id: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch daily K-line data (TaiwanStockPrice) with Redis caching."""
    cache_key = _cache_key(stock_id, "price", end_date)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached
    records = _fetch("TaiwanStockPrice", stock_id, start_date, end_date)
    _set_cached(cache_key, records)
    return records


def fetch_institutional_investors(stock_id: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch three major institutional investors (TaiwanStockInstitutionalInvestorsBuySell)."""
    cache_key = _cache_key(stock_id, "institutional", end_date)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached
    records = _fetch("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date)
    _set_cached(cache_key, records)
    return records


def fetch_margin_trading(stock_id: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch margin trading data (TaiwanStockMarginPurchaseShortSale)."""
    cache_key = _cache_key(stock_id, "margin", end_date)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached
    records = _fetch("TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date)
    _set_cached(cache_key, records)
    return records


def fetch_stock_info() -> list[dict]:
    """Fetch stock basic info (TaiwanStockInfo) — no stock_id filter needed."""
    cache_key = "finmind:all:stock_info:latest"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached
    try:
        params = {
            "dataset": "TaiwanStockInfo",
            "token": settings.finmind_api_token,
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(FINMIND_API_URL, params=params)
            resp.raise_for_status()
            body = resp.json()
            records = body.get("data", []) if body.get("status") == 200 else []
        _set_cached(cache_key, records, ttl=86400)
        return records
    except Exception as e:
        logger.error(f"FinMind fetch_stock_info error: {e}")
        return []
