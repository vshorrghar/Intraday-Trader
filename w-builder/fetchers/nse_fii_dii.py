"""NSE FII/DII flow fetcher.

Fetches daily Foreign Institutional Investor (FII) and Domestic Institutional
Investor (DII) buy/sell activity from the NSE API. Supports caching with
date-stamped JSON filenames and automatic fallback to cached data on failure.

NSE FII/DII API URL:
    https://www.nseindia.com/api/fiidiiTradeReact
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime

import requests

from fetchers.models import FIIDIIFlow

logger = logging.getLogger(__name__)

NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
}

REQUEST_TIMEOUT = 30


def _parse_fii_dii_response(data: list[dict]) -> FIIDIIFlow:
    """Parse the NSE FII/DII API JSON response into a FIIDIIFlow object.

    The API returns a list of dicts, each with a ``category`` key that is
    either ``"FII/FPI *"`` or ``"DII *"``. Buy and sell values are in the
    ``buyValue`` and ``sellValue`` fields (strings with commas).

    Args:
        data: Parsed JSON list from the NSE FII/DII API.

    Returns:
        FIIDIIFlow with computed net values.

    Raises:
        ValueError: If the response does not contain recognisable FII/DII entries.
    """
    fii_buy = 0.0
    fii_sell = 0.0
    dii_buy = 0.0
    dii_sell = 0.0
    date_str = datetime.now().strftime("%Y-%m-%d")

    found_fii = False
    found_dii = False

    for entry in data:
        category = entry.get("category", "").upper()
        buy_val = _parse_numeric(entry.get("buyValue", "0"))
        sell_val = _parse_numeric(entry.get("sellValue", "0"))

        if "FII" in category or "FPI" in category:
            fii_buy += buy_val
            fii_sell += sell_val
            found_fii = True
            if "date" in entry:
                date_str = entry["date"]
        elif "DII" in category:
            dii_buy += buy_val
            dii_sell += sell_val
            found_dii = True
            if "date" in entry:
                date_str = entry["date"]

    if not found_fii and not found_dii:
        raise ValueError("Response contains no recognisable FII or DII entries")

    return FIIDIIFlow(
        date=date_str,
        fii_buy=fii_buy,
        fii_sell=fii_sell,
        fii_net=fii_buy - fii_sell,
        dii_buy=dii_buy,
        dii_sell=dii_sell,
        dii_net=dii_buy - dii_sell,
    )


def _parse_numeric(value: str | int | float) -> float:
    """Convert a value that may contain commas or be numeric to a float.

    Args:
        value: A string (possibly with commas), int, or float.

    Returns:
        The numeric value as a float, or 0.0 on failure.
    """
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _cache_filename(cache_dir: str, date_str: str) -> str:
    """Build the cache file path for a given date.

    Args:
        cache_dir: Directory for cached files.
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Full path to the cache file.
    """
    return os.path.join(cache_dir, f"fii_dii_{date_str}.json")


def fetch_fii_dii(cache_dir: str) -> FIIDIIFlow:
    """Fetch the latest FII/DII flow data from the NSE API.

    On success, caches the response as JSON with a date-stamped filename.
    On failure, falls back to the most recent cached FII/DII data.

    Args:
        cache_dir: Directory to store/read cached FII/DII JSON files.

    Returns:
        FIIDIIFlow object with buy, sell, and computed net values.
        Returns a zeroed-out FIIDIIFlow if both fetch and cache fail.
    """
    os.makedirs(cache_dir, exist_ok=True)

    try:
        logger.info("Fetching FII/DII data from %s", NSE_FII_DII_URL)
        response = requests.get(
            NSE_FII_DII_URL, headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()
        flow = _parse_fii_dii_response(data)

        # Cache the raw JSON response
        date_str = datetime.now().strftime("%Y-%m-%d")
        cache_path = _cache_filename(cache_dir, date_str)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("FII/DII data cached at %s", cache_path)

        return flow

    except Exception as exc:
        logger.error("Failed to fetch FII/DII data: %s", exc)

    # Fall back to cache
    logger.warning("Falling back to cached FII/DII data")
    cached = get_cached_fii_dii(cache_dir)
    if cached is not None:
        return cached

    logger.error("No cached FII/DII data available")
    return FIIDIIFlow(
        date=datetime.now().strftime("%Y-%m-%d"),
        fii_buy=0.0,
        fii_sell=0.0,
        fii_net=0.0,
        dii_buy=0.0,
        dii_sell=0.0,
        dii_net=0.0,
    )


def get_cached_fii_dii(cache_dir: str) -> FIIDIIFlow | None:
    """Load the most recent cached FII/DII JSON file.

    Scans the cache directory for files matching ``fii_dii_YYYY-MM-DD.json``
    and returns the parsed contents of the most recent one.

    Args:
        cache_dir: Directory containing cached FII/DII JSON files.

    Returns:
        FIIDIIFlow object, or None if no cache exists.
    """
    pattern = os.path.join(cache_dir, "fii_dii_*.json")
    cache_files = sorted(glob.glob(pattern), reverse=True)

    if not cache_files:
        logger.info("No cached FII/DII files found in %s", cache_dir)
        return None

    latest_file = cache_files[0]

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        flow = _parse_fii_dii_response(data)
        logger.info("Loaded cached FII/DII data from %s", latest_file)
        return flow
    except (OSError, IOError, json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to read cached FII/DII %s: %s", latest_file, exc)
        return None
