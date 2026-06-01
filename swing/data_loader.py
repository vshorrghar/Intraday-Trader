"""
Swing data loader — loads cached daily OHLC for scanner consumption.

Reads from cache/swing_daily/{SYMBOL}.json (written by backtest/fetch_swing_data.py).
Converts structured candle format to flat-list format expected by swing/scanner.py.

Scanner expects:
    daily_data = {
        "open": [float, ...],    # oldest first, newest last
        "high": [float, ...],
        "low": [float, ...],
        "close": [float, ...],
        "volume": [float, ...]
    }
    Minimum 200 data points required for 200-DMA.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache" / "swing_daily"


def load_daily_candles(symbol: str, lookback_days: int = 200) -> list[dict]:
    """Load cached daily OHLC for a symbol.

    Args:
        symbol: NSE symbol (e.g. "TCS", "RELIANCE")
        lookback_days: Max number of candles to return (newest N).
                       Default 200 matches scanner's 200-DMA requirement.

    Returns:
        List of candle dicts with keys: date, open, high, low, close, volume.
        Oldest first, newest last. Returns [] if cache missing or corrupt.
    """
    cache_file = CACHE_DIR / f"{symbol}.json"
    if not cache_file.exists():
        return []

    try:
        with open(cache_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load cache for %s: %s", symbol, e)
        return []

    candles = data.get("candles", [])
    if not candles:
        return []

    # Return last N candles (oldest first, newest last)
    if len(candles) > lookback_days:
        return candles[-lookback_days:]
    return candles


def load_scanner_format(symbol: str, lookback_days: int = 270) -> dict:
    """Load cached data in the flat-list format expected by swing/scanner.py.

    Args:
        symbol: NSE symbol
        lookback_days: Number of candles to load (default 270 to cover 200-DMA + buffer)

    Returns:
        Dict with keys: open, high, low, close, volume — each a list of floats.
        Returns empty dict {} if data unavailable or insufficient.
    """
    candles = load_daily_candles(symbol, lookback_days)
    if len(candles) < 200:
        return {}

    return {
        "open": [c["open"] for c in candles],
        "high": [c["high"] for c in candles],
        "low": [c["low"] for c in candles],
        "close": [c["close"] for c in candles],
        "volume": [c["volume"] for c in candles],
    }


def get_universe_with_data(min_candles: int = 200) -> list[str]:
    """Returns list of symbols that have sufficient cached data.

    Args:
        min_candles: Minimum number of candles required (default 200 for 200-DMA).

    Returns:
        List of symbol strings with enough data for swing scoring.
    """
    if not CACHE_DIR.exists():
        return []

    symbols = []
    for f in CACHE_DIR.glob("*.json"):
        symbol = f.stem
        try:
            with open(f) as fh:
                data = json.load(fh)
            n = len(data.get("candles", []))
            if n >= min_candles:
                symbols.append(symbol)
        except (json.JSONDecodeError, OSError):
            continue

    return sorted(symbols)


def is_data_fresh(symbol: str, max_age_hours: int = 24) -> bool:
    """Check if cached data is recent enough.

    Args:
        symbol: NSE symbol
        max_age_hours: Maximum age in hours (default 24).
                       For weekend handling: Friday's data is fresh until Monday
                       if max_age_hours=72 is passed.

    Returns:
        True if file modification time is within max_age_hours of now.
    """
    cache_file = CACHE_DIR / f"{symbol}.json"
    if not cache_file.exists():
        return False

    import time
    mtime = cache_file.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    return age_hours <= max_age_hours


def load_universe_for_scanner(min_candles: int = 200) -> dict[str, dict]:
    """Load all cached data in scanner-ready format.

    Returns:
        Dict of {symbol: flat_ohlc_dict} for all stocks with sufficient data.
        This is the exact format expected by swing.scanner.scan_universe().
    """
    symbols = get_universe_with_data(min_candles)
    universe_data = {}

    for symbol in symbols:
        data = load_scanner_format(symbol)
        if data:
            universe_data[symbol] = data

    return universe_data
