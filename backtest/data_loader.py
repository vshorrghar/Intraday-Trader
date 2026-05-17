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
        time.sleep(0.2)

        # Progress every 50 stocks
        if idx % 50 == 0:
            print(f"  Progress: {idx}/{total} ({cached_count} cached, {fetched_count} fetched)")

    print(f"Done: {cached_count} cached + {fetched_count} fetched = {len(results)} total")
    return results
