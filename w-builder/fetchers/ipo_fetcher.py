"""IPO GMP (Grey Market Premium) fetcher.

Scrapes IPO grey market premium data from Chittorgarh, extracting name,
price band, GMP, estimated listing price, and subscription status for
active IPOs.

Chittorgarh IPO GMP URL:
    https://www.chittorgarh.com/report/ipo-grey-market-premium-latest-mainboard-sme/1/
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from fetchers.models import IPORecord

logger = logging.getLogger(__name__)

IPO_GMP_URL = (
    "https://www.chittorgarh.com/report/"
    "ipo-grey-market-premium-latest-mainboard-sme/1/"
)

IPO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

REQUEST_TIMEOUT = 30


def _parse_numeric(text: str) -> float:
    """Parse a numeric value from text, handling ₹ symbols and commas.

    Args:
        text: Raw text that may contain currency symbols, commas, etc.

    Returns:
        Parsed float value, or 0.0 if parsing fails.
    """
    if not text:
        return 0.0
    cleaned = text.replace(",", "").replace("₹", "").replace("Rs.", "").strip()
    # Extract the first numeric value (possibly negative)
    match = re.search(r"[-+]?\d+\.?\d*", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return 0.0
    return 0.0


def _parse_ipo_table(soup: BeautifulSoup) -> list[IPORecord]:
    """Parse the IPO GMP table from the Chittorgarh page.

    The page contains a table with columns typically including:
    IPO name, Price Band, GMP, Estimated Listing Price, and subscription info.

    Args:
        soup: Parsed BeautifulSoup of the page.

    Returns:
        List of IPORecord objects.
    """
    records: list[IPORecord] = []

    # Find the main data table
    table = soup.find("table", class_="table")
    if not table:
        # Try finding any table with IPO data
        tables = soup.find_all("table")
        for t in tables:
            header_text = t.get_text().lower()
            if "ipo" in header_text and ("gmp" in header_text or "premium" in header_text):
                table = t
                break

    if not table:
        logger.warning("No IPO GMP table found on page")
        return records

    rows = table.find_all("tr")
    if len(rows) < 2:
        logger.warning("IPO GMP table has fewer than 2 rows")
        return records

    # Skip header row(s)
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        try:
            name = cells[0].get_text(strip=True)
            if not name:
                continue

            price_band = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            gmp_text = cells[2].get_text(strip=True) if len(cells) > 2 else "0"
            est_listing_text = cells[3].get_text(strip=True) if len(cells) > 3 else "0"

            # Subscription status may be in the last or second-to-last column
            subscription_status = ""
            if len(cells) > 4:
                subscription_status = cells[-1].get_text(strip=True)

            gmp = _parse_numeric(gmp_text)
            estimated_listing_price = _parse_numeric(est_listing_text)

            records.append(
                IPORecord(
                    name=name,
                    price_band=price_band,
                    gmp=gmp,
                    estimated_listing_price=estimated_listing_price,
                    subscription_status=subscription_status,
                )
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse IPO row: %s", exc)
            continue

    return records


def fetch_ipo_gmp() -> list[IPORecord]:
    """Fetch IPO GMP data from Chittorgarh.

    Scrapes the Chittorgarh IPO GMP page and extracts name, price band,
    GMP value, estimated listing price, and subscription status for each
    active IPO.

    On failure, logs the error and returns an empty list.

    Returns:
        List of IPORecord objects. Empty list on failure.
    """
    try:
        logger.info("Fetching IPO GMP data from %s", IPO_GMP_URL)
        response = requests.get(IPO_GMP_URL, headers=IPO_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        records = _parse_ipo_table(soup)

        logger.info("Parsed %d IPO records", len(records))
        return records

    except Exception as exc:
        logger.error("Failed to fetch IPO GMP data: %s", exc)
        return []
