"""NSE Bulk and Block Deals fetcher.

Fetches daily bulk deal and block deal data from the NSE API. On failure,
logs the error and returns an empty list.

NSE Bulk Deals API URL:
    https://www.nseindia.com/api/bulk-deal-data
NSE Block Deals API URL:
    https://www.nseindia.com/api/block-deal
"""

from __future__ import annotations

import logging

import requests

from fetchers.models import DealRecord

logger = logging.getLogger(__name__)

NSE_BULK_DEALS_URL = "https://www.nseindia.com/api/bulk-deal-data"
NSE_BLOCK_DEALS_URL = "https://www.nseindia.com/api/block-deal"

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


def _parse_deals(data: list[dict], deal_type: str) -> list[DealRecord]:
    """Parse a list of deal entries from the NSE API into DealRecord objects.

    Args:
        data: List of deal dicts from the NSE API response.
        deal_type: Either "bulk" or "block".

    Returns:
        List of parsed DealRecord objects. Malformed entries are skipped.
    """
    records: list[DealRecord] = []

    for idx, entry in enumerate(data):
        try:
            security_name = str(entry.get("securityName", entry.get("symbolName", ""))).strip()
            if not security_name:
                security_name = str(entry.get("symbol", "")).strip()

            isin = str(entry.get("isin", "")).strip()
            client_name = str(entry.get("clientName", entry.get("buySellClientName", ""))).strip()

            quantity_raw = entry.get("quantity", entry.get("tradedQty", 0))
            quantity = int(_parse_numeric(quantity_raw))

            price_raw = entry.get("price", entry.get("weightedAvgPrice", entry.get("tradedPrice", 0)))
            price = _parse_numeric(price_raw)

            if not security_name or not client_name:
                logger.warning(
                    "%s deal entry %d: missing security_name or client_name — skipping",
                    deal_type,
                    idx,
                )
                continue

            records.append(
                DealRecord(
                    deal_type=deal_type,
                    security_name=security_name,
                    isin=isin,
                    client_name=client_name,
                    quantity=quantity,
                    price=price,
                )
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("%s deal entry %d: failed to parse — %s", deal_type, idx, exc)
            continue

    return records


def _fetch_deals_from_url(url: str, deal_type: str) -> list[DealRecord]:
    """Fetch and parse deals from a single NSE API endpoint.

    Args:
        url: The NSE API URL to fetch from.
        deal_type: Either "bulk" or "block".

    Returns:
        List of DealRecord objects. Empty list on failure.
    """
    try:
        logger.info("Fetching %s deals from %s", deal_type, url)
        response = requests.get(url, headers=NSE_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()

        # The API may return a dict with a "data" key or a plain list
        if isinstance(data, dict):
            data = data.get("data", [])

        if not isinstance(data, list):
            logger.warning(
                "%s deals response is not a list (got %s) — returning empty",
                deal_type,
                type(data).__name__,
            )
            return []

        records = _parse_deals(data, deal_type)
        logger.info("Parsed %d %s deal records", len(records), deal_type)
        return records

    except Exception as exc:
        logger.error("Failed to fetch %s deals: %s", deal_type, exc)
        return []


def fetch_bulk_deals() -> list[DealRecord]:
    """Fetch the latest bulk and block deals from NSE.

    Calls both the bulk deals and block deals API endpoints, parses the
    responses, and returns a combined list of DealRecord objects.

    On failure for either endpoint, logs the error and continues with
    the other endpoint. Returns an empty list if both fail.

    Returns:
        Combined list of bulk and block DealRecord objects.
    """
    bulk_records = _fetch_deals_from_url(NSE_BULK_DEALS_URL, "bulk")
    block_records = _fetch_deals_from_url(NSE_BLOCK_DEALS_URL, "block")

    combined = bulk_records + block_records
    logger.info("Total deals fetched: %d (bulk=%d, block=%d)",
                len(combined), len(bulk_records), len(block_records))
    return combined
