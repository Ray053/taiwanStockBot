"""US market & Taiwan night session data via yfinance."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# EWT (iShares MSCI Taiwan ETF) trades in US hours and closely tracks TAIEX.
# Used as a proxy for Taiwan futures night session (夜盤) sentiment,
# since the ETF closes ~04:00 Taiwan time — before our 06:00 job runs.
NIGHT_SESSION_PROXY = "EWT"

US_INDICES = {
    "sox_change": "^SOX",       # Philadelphia Semiconductor Index
    "nasdaq_change": "^IXIC",   # NASDAQ Composite
    "sp500_change": "^GSPC",    # S&P 500
}


def _pct_change(symbol: str) -> Optional[float]:
    """Fetch most recent 1-day % change for a yfinance symbol. Returns None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="5d")
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            curr = float(hist["Close"].iloc[-1])
            if prev > 0:
                return round((curr - prev) / prev, 4)
    except Exception as e:
        logger.warning(f"yfinance fetch error for {symbol}: {e}")
    return None


def fetch_us_indices() -> dict:
    """
    Fetch SOX, NASDAQ, S&P500 daily % change.
    Best called at 06:00 Taiwan time after US market close (~05:00 Taiwan).
    Returns dict with keys: sox_change, nasdaq_change, sp500_change.
    """
    result = {}
    for key, symbol in US_INDICES.items():
        result[key] = _pct_change(symbol)
        logger.info(f"US market {symbol}: {result[key]:+.2%}" if result[key] is not None else f"US market {symbol}: N/A")
    return result


def fetch_night_session_change() -> Optional[float]:
    """
    Fetch Taiwan night session proxy via EWT ETF % change.
    Returns % change as float (e.g. 0.012 = +1.2%) or None on failure.
    """
    change = _pct_change(NIGHT_SESSION_PROXY)
    if change is not None:
        logger.info(f"Night session proxy ({NIGHT_SESSION_PROXY}): {change:+.2%}")
    else:
        logger.warning(f"Night session proxy ({NIGHT_SESSION_PROXY}): N/A")
    return change
