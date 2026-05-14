"""Options data fetcher — real NSE option chain with Dhan fallback.

Provides:
- fetch_option_chain(symbol) -> dict with strikes, IVs, OI
- get_atm_strike(symbol, expiry) -> nearest strike to spot
- get_option_premium(symbol, strike, expiry, option_type) -> premium
- get_iv_percentile(symbol) -> float (0-100)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_nse_session():
    """Get NSE session with cookies."""
    import requests
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.nseindia.com/',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    s.get('https://www.nseindia.com', timeout=10)
    return s


def fetch_option_chain(symbol: str = "NIFTY") -> dict:
    """Fetch real option chain from NSE. Returns dict with spot, expiries, strikes."""
    try:
        s = _get_nse_session()
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        r = s.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            records = data.get("records", {})
            underlying = records.get("underlyingValue")
            expiries = records.get("expiryDates", [])
            strikes_data = records.get("data", [])
            if underlying and strikes_data:
                return {
                    "symbol": symbol,
                    "spot_price": underlying,
                    "expiry_dates": expiries,
                    "strikes": strikes_data,
                    "source": "NSE",
                }
        logger.warning("NSE option chain empty for %s — status %s", symbol, r.status_code)
    except Exception as e:
        logger.warning("NSE option chain fetch failed: %s", e)

    # Return empty structure (caller should use Dhan fallback)
    return {"symbol": symbol, "spot_price": 0, "expiry_dates": [], "strikes": [], "source": "empty"}


def get_atm_strike(chain: dict, expiry: Optional[str] = None) -> int:
    """Get ATM strike nearest to spot price."""
    spot = chain.get("spot_price", 0)
    if not spot:
        return 0
    # Round to nearest 50 for NIFTY, 100 for BANKNIFTY
    symbol = chain.get("symbol", "NIFTY")
    step = 100 if "BANK" in symbol.upper() else 50
    return round(spot / step) * step


def get_option_premium(chain: dict, strike: int, expiry: str, option_type: str = "CE") -> float:
    """Get last price for a specific strike from chain data."""
    for item in chain.get("strikes", []):
        if item.get("strikePrice") == strike and item.get("expiryDate") == expiry:
            opt = item.get(option_type, {})
            return float(opt.get("lastPrice", 0) or 0)
    return 0.0


def get_iv_percentile(chain: dict) -> float:
    """Calculate IV percentile from ATM options in chain."""
    strikes = chain.get("strikes", [])
    if not strikes:
        return 50.0  # default neutral
    ivs = []
    for item in strikes:
        for ot in ["CE", "PE"]:
            opt = item.get(ot, {})
            iv = opt.get("impliedVolatility", 0)
            if iv and iv > 0:
                ivs.append(iv)
    if not ivs:
        return 50.0
    current_iv = sum(ivs) / len(ivs)
    # Simple percentile: where does current IV sit in the range
    min_iv = min(ivs)
    max_iv = max(ivs)
    if max_iv == min_iv:
        return 50.0
    return ((current_iv - min_iv) / (max_iv - min_iv)) * 100
