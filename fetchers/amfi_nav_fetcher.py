"""AMFI NAV fetcher.

Downloads and parses the daily NAV data from the AMFI (Association of Mutual
Funds in India) website. The data is a semicolon-separated text file with
header lines for each AMC and scheme entries.

AMFI NAV URL:
    https://www.amfiindia.com/spages/NAVAll.txt

Format:
    Lines starting with a number are scheme data rows:
        scheme_code;isin_div_payout;isin_div_reinvest;scheme_name;nav;date
    Other lines are AMC headers or blank lines.
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime

import requests

from fetchers.models import NAVRecord

logger = logging.getLogger(__name__)

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

AMFI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, */*",
}

REQUEST_TIMEOUT = 60


def _parse_amfi_nav_text(text: str) -> dict[str, NAVRecord]:
    """Parse AMFI NAV text data into a dict keyed by scheme code.

    The AMFI NAV file has the following structure:
    - AMC header lines (text, not starting with a digit)
    - Blank lines
    - Scheme data lines: scheme_code;isin_div_payout;isin_div_reinvest;scheme_name;nav;date

    Args:
        text: Raw text content from the AMFI NAV file.

    Returns:
        Dictionary mapping scheme_code to NAVRecord.
    """
    records: dict[str, NAVRecord] = {}

    for line_num, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue

        # Scheme data lines start with a digit (scheme code)
        if not line[0].isdigit():
            continue

        parts = line.split(";")
        if len(parts) < 5:
            logger.warning("Line %d: expected at least 5 fields, got %d — skipping", line_num, len(parts))
            continue

        try:
            scheme_code = parts[0].strip()
            # The scheme name is at index 3, NAV at index 4, date at index 5
            # Format: scheme_code;isin_div_payout;isin_div_reinvest;scheme_name;nav;date
            scheme_name = parts[3].strip() if len(parts) > 3 else ""
            nav_str = parts[4].strip() if len(parts) > 4 else ""
            date_str = parts[5].strip() if len(parts) > 5 else ""

            if not scheme_code or not nav_str:
                continue

            # Some NAV values may be "N.A." or "-"
            if nav_str.upper() in ("N.A.", "-", ""):
                continue

            nav = float(nav_str)

            records[scheme_code] = NAVRecord(
                scheme_code=scheme_code,
                scheme_name=scheme_name,
                nav=nav,
                date=date_str,
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Line %d: failed to parse NAV record — %s", line_num, exc)
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
    return os.path.join(cache_dir, f"amfi_nav_{date_str}.txt")


def fetch_amfi_nav(cache_dir: str) -> dict[str, NAVRecord]:
    """Download and parse the latest AMFI NAV data.

    On success, caches the raw text with a date-stamped filename.
    On failure, falls back to the most recent cached NAV data.

    Args:
        cache_dir: Directory to store/read cached NAV files.

    Returns:
        Dictionary mapping scheme_code to NAVRecord. May be empty if
        both download and cache fallback fail.
    """
    os.makedirs(cache_dir, exist_ok=True)

    try:
        logger.info("Fetching AMFI NAV data from %s", AMFI_NAV_URL)
        response = requests.get(AMFI_NAV_URL, headers=AMFI_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        text = response.text
        records = _parse_amfi_nav_text(text)

        if records:
            date_str = datetime.now().strftime("%Y-%m-%d")
            cache_path = _cache_filename(cache_dir, date_str)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info(
                "AMFI NAV: %d schemes parsed and cached at %s",
                len(records),
                cache_path,
            )
            return records

        logger.warning("AMFI NAV data returned 0 records")

    except Exception as exc:
        logger.error("Failed to fetch AMFI NAV data: %s", exc)

    # Fall back to cache
    logger.warning("Falling back to cached AMFI NAV data")
    cached = get_cached_amfi_nav(cache_dir)
    if cached is not None:
        return cached

    logger.error("No cached AMFI NAV data available")
    return {}


def get_cached_amfi_nav(cache_dir: str) -> dict[str, NAVRecord] | None:
    """Load the most recent cached AMFI NAV file.

    Scans the cache directory for files matching ``amfi_nav_YYYY-MM-DD.txt``
    and returns the parsed contents of the most recent one.

    Args:
        cache_dir: Directory containing cached AMFI NAV files.

    Returns:
        Dictionary mapping scheme_code to NAVRecord, or None if no cache exists.
    """
    pattern = os.path.join(cache_dir, "amfi_nav_*.txt")
    cache_files = sorted(glob.glob(pattern), reverse=True)

    if not cache_files:
        logger.info("No cached AMFI NAV files found in %s", cache_dir)
        return None

    latest_file = cache_files[0]

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            text = f.read()

        records = _parse_amfi_nav_text(text)
        logger.info("Loaded cached AMFI NAV from %s: %d schemes", latest_file, len(records))
        return records
    except (OSError, IOError) as exc:
        logger.error("Failed to read cached AMFI NAV %s: %s", latest_file, exc)
        return None
