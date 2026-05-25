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
        time.sleep(1.0)

    return results


def fetch_universe_for_dates(
    universe: dict[str, str],
    dates: list[str],
    broker,
    interval: str = "1",
    cache_dir: str = "cache/historical",
) -> dict[str, dict]:
    """Fetch 1-min OHLC for universe stocks covering the date range.

    Computes from_date (min of dates - 1 day for prev_close) and to_date (max of dates).
    Cache per symbol per date range.
    Rate limit: 200ms between calls.
    Show progress every 50 stocks.

    Parameters
    ----------
    universe : dict
        {symbol: security_id}
    dates : list[str]
        List of target dates ['2026-05-12', '2026-05-14', ...]
    broker : DhanBrokerClient
        Authenticated broker instance.
    interval : str
        Candle interval (default '1' for 1-min).
    cache_dir : str
        Directory for cache files.

    Returns
    -------
    dict[str, dict]
        {symbol: ohlc_dict} where ohlc_dict has open/high/low/close/volume/timestamp arrays.
    """
    from datetime import datetime, timedelta

    if not dates:
        raise ValueError("dates list cannot be empty")

    # Compute date range: from_date = min(dates) - 3 days (for prev_close + weekends)
    sorted_dates = sorted(dates)
    min_dt = datetime.strptime(sorted_dates[0], "%Y-%m-%d")
    max_dt = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")
    from_date = (min_dt - timedelta(days=3)).strftime("%Y-%m-%d")
    to_date = max_dt.strftime("%Y-%m-%d")

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    results = {}
    total = len(universe)
    fetched_count = 0
    cached_count = 0

    print(f"Fetching {interval}-min OHLC for {total} stocks, {from_date} to {to_date}")

    for idx, (symbol, sec_id) in enumerate(universe.items(), 1):
        fname = f"{symbol}_{interval}min_{from_date}_{to_date}.json"
        fpath = cache_path / fname

        # Use cache if exists
        if fpath.exists():
            try:
                with open(fpath) as f_in:
                    data = json.load(f_in)
                if data and data.get("open") and len(data["open"]) > 0:
                    results[symbol] = data
                    cached_count += 1
                    if idx % 50 == 0:
                        print(f"  Progress: {idx}/{total} ({cached_count} cached, {fetched_count} fetched)")
                    continue
            except Exception:
                pass  # Re-fetch on corrupt cache

        # Fetch from Dhan
        if not broker:
            logger.warning("No broker — cannot fetch %s", symbol)
            continue

        try:
            data = broker.get_historical_ohlc(
                security_id=sec_id,
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                interval=interval,
                from_date=from_date,
                to_date=to_date,
            )
        except Exception as e:
            logger.warning("Error fetching %s: %s", symbol, e)
            data = None

        if data and data.get("open") and len(data["open"]) > 0:
            with open(fpath, "w") as f_out:
                json.dump(data, f_out)
            results[symbol] = data
            fetched_count += 1
            logger.info("Fetched %s: %d candles", symbol, len(data["open"]))
        else:
            logger.warning("No data for %s (sec_id=%s)", symbol, sec_id)

        # Rate limit: 200ms between API calls
        time.sleep(1.0)

        # Progress every 50 stocks
        if idx % 50 == 0:
            print(f"  Progress: {idx}/{total} ({cached_count} cached, {fetched_count} fetched)")

    print(f"Done: {cached_count} cached + {fetched_count} fetched = {len(results)} total")
    return results


def load_nifty500_universe(min_volume_check: bool = False) -> dict[str, str]:
    """Load Nifty 500-equivalent universe from nse_security_ids.json.
    
    Filters to liquid NSE_EQ common stocks, excluding:
    - Bonds (numeric prefixes like '656MH32', '94SFL28')
    - Mutual fund units (often have 'MF' or specific patterns)
    - ETFs (typically end with 'BEES' or 'ETF')
    - Government securities ('GS' suffix patterns)
    - Stocks with security_id < 100 (often non-equity)
    
    Returns ~400-500 tradeable equities matching scanner.py universe.
    """
    import json
    import re
    
    with open("config/nse_security_ids.json") as f:
        all_symbols = json.load(f)
    
    # Filter rules — keep only proper equity tickers
    EXCLUDE_PATTERNS = [
        r'^\d',                    # Starts with digit (bonds: 656MH32)
        r'GS\d{4}$',               # Government securities (GS2033)
        r'BEES$',                  # ETFs (NIFTYBEES, BANKBEES)
        r'IETF$',                  # ETFs
        r'GOLD$',                  # Gold ETFs
        r'LIQUID$',                # Liquid funds
        r'^N\d',                   # N-prefixed (often debt)
    ]
    
    # Excluded suffixes/keywords
    EXCLUDE_KEYWORDS = ['ETF', 'BEES', 'LIQUID', 'GILT', 'GSEC']
    
    universe = {}
    for symbol, sec_id in all_symbols.items():
        # Skip if any exclusion pattern matches
        if any(re.search(pat, symbol) for pat in EXCLUDE_PATTERNS):
            continue
        if any(kw in symbol.upper() for kw in EXCLUDE_KEYWORDS):
            continue
        
        # Keep alphabetic-only symbols (most equities)
        if not symbol.replace('-', '').replace('&', '').isalpha():
            continue
        
        # Sanity: security_id should be reasonable (ID <= 6000 covers most liquid equities)
        try:
            sid_int = int(sec_id)
            if sid_int < 7 or sid_int > 6000:
                continue
        except (ValueError, TypeError):
            continue
        
        universe[symbol] = str(sec_id)
    
    # Explicitly add known reference stocks that may have IDs > 6000
    # These are confirmed Nifty 500 constituents with higher Dhan IDs
    REFERENCE_STOCKS = {
        "SAREGAMA": "4892", "NLCINDIA": "8585", "TDPOWERSYS": "25178",
        "CIPLA": "694", "GODREJIND": "10925", "VEDL": "3063",
        "HINDZINC": "1424", "SAIL": "2963", "TCS": "11536",
        "INFY": "1594", "HDFCBANK": "1333", "RELIANCE": "2885",
        "ICICIBANK": "4963", "BHARTIARTL": "10604", "MARUTI": "10999",
        "ASIANPAINT": "236", "BAJFINANCE": "317", "HCLTECH": "7229",
        "WIPRO": "3787", "SBIN": "3045", "AXISBANK": "5900",
        "KOTAKBANK": "1922", "LT": "11483", "TITAN": "3506",
        "SUNPHARMA": "3351", "NTPC": "11630", "ONGC": "2475",
        "TATAMOTORS": "3456", "TATASTEEL": "3499", "TECHM": "13538",
        "ADANIENT": "25", "ADANIPORTS": "15083", "APOLLOHOSP": "157",
        "BAJAJ-AUTO": "16669", "BAJAJFINSV": "16675", "BEL": "383",
        "BPCL": "526", "BRITANNIA": "547", "COALINDIA": "20374",
        "DRREDDY": "881", "EICHERMOT": "910", "GRASIM": "1232",
        "HDFCLIFE": "467", "HEROMOTOCO": "1348", "HINDALCO": "1363",
        "HINDUNILVR": "1394", "ITC": "1660", "INDUSINDBK": "5258",
        "JSWSTEEL": "11723", "NESTLEIND": "17963", "POWERGRID": "14977",
        "SBILIFE": "21808", "TATACONSUM": "3432", "ULTRACEMCO": "11532",
        "SHRIRAMFIN": "4306", "TRENT": "1964",
    }
    for sym, sid in REFERENCE_STOCKS.items():
        if sym not in universe:
            universe[sym] = sid

    return universe


def fetch_with_retry(broker, security_id, exchange_segment, instrument,
                     interval, from_date, to_date, max_retries=3) -> dict:
    """Fetch OHLC with exponential backoff on 429."""
    import time
    for attempt in range(max_retries):
        data = broker.get_historical_ohlc(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument=instrument,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
        )
        if data and data.get("open"):
            return data
        # If failed, wait longer before retry
        wait = (attempt + 1) * 3  # 3s, 6s, 9s
        print(f"  Retry {attempt+1}/{max_retries} for {security_id}, waiting {wait}s...")
        time.sleep(wait)
    return None
