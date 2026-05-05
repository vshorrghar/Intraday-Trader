"""Market indices fetcher.

Fetches current values for key Indian market indices (Nifty 50, Sensex,
Nifty Bank, Nifty Midcap 100) from the NSE all-indices API. Supports
caching with date-stamped JSON filenames and automatic fallback to cached
data on failure.

NSE Indices API URL:
    https://www.nseindia.com/api/allIndices
"""

from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime

import requests

from fetchers.models import IndexData

logger = logging.getLogger(__name__)

NSE_INDICES_URL = "https://www.nseindia.com/api/allIndices"

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

# Target indices to extract
TARGET_INDICES = {
    "NIFTY 50",
    "NIFTY BANK",
    "NIFTY MIDCAP 100",
    "S&P BSE SENSEX",
}


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


def _parse_indices_response(data: dict) -> list[IndexData]:
    """Parse the NSE all-indices API response into IndexData objects.

    The API returns a dict with a ``data`` key containing a list of index
    entries. Each entry has ``index``, ``last``, ``variation``, and
    ``percentChange`` fields.

    Args:
        data: Parsed JSON dict from the NSE indices API.

    Returns:
        List of IndexData objects for the target indices.
    """
    records: list[IndexData] = []

    entries = data.get("data", [])
    if not isinstance(entries, list):
        logger.warning("Indices response 'data' is not a list")
        return records

    for entry in entries:
        index_name = str(entry.get("index", entry.get("indexName", ""))).strip().upper()

        # Check if this is one of our target indices
        matched = False
        for target in TARGET_INDICES:
            if target in index_name or index_name in target:
                matched = True
                break

        # Also match "SENSEX" loosely
        if not matched and "SENSEX" in index_name:
            matched = True

        if not matched:
            continue

        try:
            last_price = _parse_numeric(entry.get("last", entry.get("lastPrice", 0)))
            change = _parse_numeric(entry.get("variation", entry.get("change", 0)))
            change_percent = _parse_numeric(
                entry.get("percentChange", entry.get("pChange", 0))
            )

            display_name = entry.get("index", entry.get("indexName", index_name)).strip()

            records.append(
                IndexData(
                    name=display_name,
                    last_price=last_price,
                    change=change,
                    change_percent=change_percent,
                )
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse index entry %s: %s", index_name, exc)
            continue

    return records


def _cache_filename(cache_dir: str, date_str: str) -> str:
    """Build the cache file path for a given date."""
    return os.path.join(cache_dir, f"indices_{date_str}.json")


def fetch_indices(cache_dir: str) -> list[IndexData]:
    """Fetch Nifty 50, Sensex, Nifty Bank, and Nifty Midcap 100 from NSE.

    On success, caches the raw JSON response with a date-stamped filename.
    On failure, falls back to the most recent cached index data.

    Args:
        cache_dir: Directory to store/read cached index JSON files.

    Returns:
        List of IndexData objects for the target indices. May be empty if
        both download and cache fallback fail.
    """
    os.makedirs(cache_dir, exist_ok=True)

    try:
        logger.info("Fetching market indices from %s", NSE_INDICES_URL)
        response = requests.get(
            NSE_INDICES_URL, headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()
        records = _parse_indices_response(data)

        if records:
            date_str = datetime.now().strftime("%Y-%m-%d")
            cache_path = _cache_filename(cache_dir, date_str)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(
                "Market indices: %d indices parsed and cached at %s",
                len(records),
                cache_path,
            )
            return records

        logger.warning("Market indices response returned 0 target indices")

    except Exception as exc:
        logger.error("Failed to fetch market indices: %s", exc)

    # Fall back to cache
    logger.warning("Falling back to cached market indices data")
    cached = get_cached_indices(cache_dir)
    if cached is not None:
        return cached

    logger.error("No cached market indices data available")
    return []


def get_cached_indices(cache_dir: str) -> list[IndexData] | None:
    """Load the most recent cached market indices file.

    Scans the cache directory for files matching ``indices_YYYY-MM-DD.json``
    and returns the parsed contents of the most recent one.

    Args:
        cache_dir: Directory containing cached index JSON files.

    Returns:
        List of IndexData objects, or None if no cache exists.
    """
    pattern = os.path.join(cache_dir, "indices_*.json")
    cache_files = sorted(glob.glob(pattern), reverse=True)

    if not cache_files:
        logger.info("No cached index files found in %s", cache_dir)
        return None

    latest_file = cache_files[0]

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = _parse_indices_response(data)
        logger.info("Loaded cached indices from %s: %d indices", latest_file, len(records))
        return records
    except (OSError, IOError, json.JSONDecodeError) as exc:
        logger.error("Failed to read cached indices %s: %s", latest_file, exc)
        return None
