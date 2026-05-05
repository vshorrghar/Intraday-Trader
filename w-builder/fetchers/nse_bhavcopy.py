"""NSE Bhavcopy fetcher.

Downloads and parses the daily NSE Bhavcopy CSV file containing end-of-day
closing prices for all listed securities. Supports caching with date-stamped
filenames and automatic fallback to cached data on network failure.

NSE Bhavcopy URL pattern:
    https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv
"""

from __future__ import annotations

import csv
import glob
import io
import logging
import os
from datetime import datetime, timedelta

import requests

from fetchers.models import BhavcopyRecord

logger = logging.getLogger(__name__)

NSE_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
)

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
}

REQUEST_TIMEOUT = 30


def _parse_bhavcopy_csv(csv_text: str, date_str: str) -> dict[str, BhavcopyRecord]:
    """Parse Bhavcopy CSV text into a dict keyed by ISIN.

    Args:
        csv_text: Raw CSV content from NSE Bhavcopy file.
        date_str: Date string (YYYY-MM-DD) for the records.

    Returns:
        Dictionary mapping ISIN to BhavcopyRecord.
    """
    records: dict[str, BhavcopyRecord] = {}
    reader = csv.DictReader(io.StringIO(csv_text))

    for row_num, row in enumerate(reader, start=2):
        try:
            # Strip whitespace from keys and values
            cleaned = {k.strip(): v.strip() for k, v in row.items() if k}

            isin = cleaned.get("ISIN_CODE", "").strip()
            symbol = cleaned.get("SYMBOL", "").strip()
            close_price_str = cleaned.get("CLOSE_PRICE", "").strip()

            if not isin or not symbol or not close_price_str:
                logger.warning("Row %d: missing ISIN, SYMBOL, or CLOSE_PRICE — skipping", row_num)
                continue

            close_price = float(close_price_str)

            records[isin] = BhavcopyRecord(
                isin=isin,
                symbol=symbol,
                close_price=close_price,
                date=date_str,
            )
        except (ValueError, KeyError) as exc:
            logger.warning("Row %d: failed to parse — %s", row_num, exc)
            continue

    return records


def _cache_filename(cache_dir: str, date_str: str) -> str:
    """Build the cache file path for a given date.

    Args:
        cache_dir: Directory for cached files.
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Full path to the cache file.
    """
    return os.path.join(cache_dir, f"bhavcopy_{date_str}.csv")


def fetch_bhavcopy(cache_dir: str) -> dict[str, BhavcopyRecord]:
    """Download and parse the latest NSE Bhavcopy CSV.

    Tries today's date first, then yesterday's (markets may not have today's
    data yet). On success, caches the CSV with a date-stamped filename.
    On network failure, falls back to the most recent cached Bhavcopy.

    Args:
        cache_dir: Directory to store/read cached Bhavcopy files.

    Returns:
        Dictionary mapping ISIN to BhavcopyRecord. May be empty if both
        download and cache fallback fail.
    """
    os.makedirs(cache_dir, exist_ok=True)

    # Try today and previous days (markets may be closed on weekends/holidays)
    today = datetime.now()
    dates_to_try = [today - timedelta(days=i) for i in range(5)]

    for dt in dates_to_try:
        url_date = dt.strftime("%d%m%Y")
        date_str = dt.strftime("%Y-%m-%d")
        url = NSE_BHAVCOPY_URL.format(date=url_date)

        try:
            logger.info("Fetching Bhavcopy for %s from %s", date_str, url)
            response = requests.get(url, headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            csv_text = response.text
            records = _parse_bhavcopy_csv(csv_text, date_str)

            if records:
                # Cache the raw CSV
                cache_path = _cache_filename(cache_dir, date_str)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(csv_text)
                logger.info(
                    "Bhavcopy for %s: %d records parsed and cached at %s",
                    date_str,
                    len(records),
                    cache_path,
                )
                return records

            logger.warning("Bhavcopy for %s returned 0 records", date_str)

        except Exception as exc:
            logger.error("Failed to fetch Bhavcopy for %s: %s", date_str, exc)
            continue

    # All download attempts failed — fall back to cache
    logger.warning("All Bhavcopy download attempts failed, falling back to cache")
    cached = get_cached_bhavcopy(cache_dir)
    if cached is not None:
        return cached

    logger.error("No cached Bhavcopy available")
    return {}


def get_cached_bhavcopy(cache_dir: str) -> dict[str, BhavcopyRecord] | None:
    """Load the most recent cached Bhavcopy file.

    Scans the cache directory for files matching ``bhavcopy_YYYY-MM-DD.csv``
    and returns the parsed contents of the most recent one.

    Args:
        cache_dir: Directory containing cached Bhavcopy CSV files.

    Returns:
        Dictionary mapping ISIN to BhavcopyRecord, or None if no cache exists.
    """
    pattern = os.path.join(cache_dir, "bhavcopy_*.csv")
    cache_files = sorted(glob.glob(pattern), reverse=True)

    if not cache_files:
        logger.info("No cached Bhavcopy files found in %s", cache_dir)
        return None

    latest_file = cache_files[0]
    # Extract date from filename: bhavcopy_YYYY-MM-DD.csv
    basename = os.path.basename(latest_file)
    date_str = basename.replace("bhavcopy_", "").replace(".csv", "")

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            csv_text = f.read()

        records = _parse_bhavcopy_csv(csv_text, date_str)
        logger.info(
            "Loaded cached Bhavcopy from %s: %d records", latest_file, len(records)
        )
        return records
    except (OSError, IOError) as exc:
        logger.error("Failed to read cached Bhavcopy %s: %s", latest_file, exc)
        return None
