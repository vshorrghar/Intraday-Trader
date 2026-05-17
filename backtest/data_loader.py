"""Backtest data loader — fetch + cache historical OHLC from Dhan API."""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Nifty 50 constituents (symbol → Dhan securityId)
NIFTY50_SYMBOLS = {
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "APOLLOHOSP": "157",
    "ASIANPAINT": "236",
    "AXISBANK": "5900",
    "BAJAJ-AUTO": "16669",
    "BAJFINANCE": "317",
    "BAJAJFINSV": "16675",
    "BEL": "383",
    "BPCL": "526",
    "BHARTIARTL": "10604",
    "BRITANNIA": "547",
    "CIPLA": "694",
    "COALINDIA": "20374",
    "DRREDDY": "881",
    "EICHERMOT": "910",
    "GRASIM": "1232",
    "HCLTECH": "7229",
    "HDFCBANK": "1333",
    "HDFCLIFE": "467",
    "HEROMOTOCO": "1348",
    "HINDALCO": "1363",
    "HINDUNILVR": "1394",
    "ICICIBANK": "4963",
    "ITC": "1660",
    "INDUSINDBK": "5258",
    "INFY": "1594",
    "JSWSTEEL": "11723",
    "KOTAKBANK": "1922",
    "LT": "11483",
    "M&M": "2031",
    "MARUTI": "10999",
    "NTPC": "11630",
    "NESTLEIND": "17963",
    "ONGC": "2475",
    "POWERGRID": "14977",
    "RELIANCE": "2885",
    "SBILIFE": "21808",
    "SBIN": "3045",
    "SUNPHARMA": "3351",
    "TCS": "11536",
    "TATACONSUM": "3432",
    "TATAMOTORS": "3456",
    "TATASTEEL": "3499",
    "TECHM": "13538",
    "TITAN": "3506",
    "ULTRACEMCO": "11532",
    "WIPRO": "3787",
    "SHRIRAMFIN": "4306",
    "TRENT": "1964",
}


def load_nifty50_universe() -> dict[str, str]:
    """Return Nifty 50 symbol→securityId mapping."""
    return NIFTY50_SYMBOLS.copy()


def fetch_and_cache_historical(
    symbols: dict[str, str],
    from_date: str,
    to_date: str,
    interval: str = "5",
    cache_dir: str = "cache/historical",
    broker=None,
) -> dict[str, dict]:
    """Fetch + cache OHLC for each symbol. Skip if cache exists.

    Parameters
    ----------
    symbols : dict
        {symbol_name: security_id}
    from_date, to_date : str
        'YYYY-MM-DD' format.
    interval : str
        Candle interval ('1', '5', '15', '25', '60').
    cache_dir : str
        Directory for cache files.
    broker : DhanBrokerClient
        Authenticated broker instance.

    Returns
    -------
    dict[str, dict]
        {symbol: ohlc_dict} where ohlc_dict has open/high/low/close/volume/timestamp arrays.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    results = {}
    for symbol, sec_id in symbols.items():
        fname = f"{symbol}_{interval}min_{from_date}_{to_date}.json"
        fpath = cache_path / fname

        # Use cache if exists
        if fpath.exists():
            try:
                with open(fpath) as f:
                    data = json.load(f)
                if data and data.get("open"):
                    results[symbol] = data
                    logger.debug("Cache hit: %s (%d candles)", symbol, len(data["open"]))
                    continue
            except Exception:
                pass  # Re-fetch on corrupt cache

        # Fetch from Dhan
        if not broker:
            logger.warning("No broker — cannot fetch %s", symbol)
            continue

        data = broker.get_historical_ohlc(
            security_id=sec_id,
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            interval=interval,
            from_date=from_date,
            to_date=to_date,
        )

        if data and data.get("open"):
            # Cache it
            with open(fpath, "w") as f:
                json.dump(data, f)
            results[symbol] = data
            logger.info("Fetched %s: %d candles", symbol, len(data["open"]))
        else:
            logger.warning("Failed to fetch %s (sec_id=%s)", symbol, sec_id)

        # Rate limit: 200ms between calls
        time.sleep(0.2)

    return results
