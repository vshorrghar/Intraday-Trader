"""Market news fetcher.

Fetches market news from Economic Times RSS feed and BSE announcements RSS
feed. Filters items to retain only those published within the last 24 hours.

RSS Feed URLs:
    ET Markets: https://economictimes.indiatimes.com/markets/rss.cms
    BSE Announcements: https://www.bseindia.com/data/xml/notices.xml
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import feedparser

from fetchers.models import NewsItem

logger = logging.getLogger(__name__)

ET_RSS_URL = "https://economictimes.indiatimes.com/markets/rss.cms"
BSE_RSS_URL = "https://www.bseindia.com/data/xml/notices.xml"

# IST offset
IST = timezone(timedelta(hours=5, minutes=30))

FEED_SOURCES = [
    {"url": ET_RSS_URL, "source": "Economic Times"},
    {"url": BSE_RSS_URL, "source": "BSE Announcements"},
]


def _parse_pub_date(entry: dict) -> datetime | None:
    """Parse the publication date from a feedparser entry.

    feedparser provides ``published_parsed`` as a time.struct_time, or
    ``published`` as a string. This function tries both approaches.

    Args:
        entry: A feedparser entry dict.

    Returns:
        A timezone-aware datetime, or None if parsing fails.
    """
    # Try the parsed struct_time first
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            from time import mktime
            dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
            return dt
        except (ValueError, TypeError, OverflowError):
            pass

    # Try the updated_parsed as fallback
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            from time import mktime
            dt = datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
            return dt
        except (ValueError, TypeError, OverflowError):
            pass

    # Try parsing the raw string
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            for fmt in (
                "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(raw, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=IST)
                    return dt
                except ValueError:
                    continue

    return None


def _parse_feed(url: str, source: str) -> list[NewsItem]:
    """Parse a single RSS feed and extract news items.

    Args:
        url: RSS feed URL.
        source: Source name for attribution.

    Returns:
        List of NewsItem objects from the feed.
    """
    items: list[NewsItem] = []

    try:
        logger.info("Fetching news from %s (%s)", source, url)
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("Feed %s returned bozo error: %s", source, feed.bozo_exception)
            return items

        for entry in feed.entries:
            headline = getattr(entry, "title", "").strip()
            if not headline:
                continue

            pub_date = _parse_pub_date(entry)

            summary = getattr(entry, "summary", "")
            if not summary:
                summary = getattr(entry, "description", "")
            summary = summary.strip()

            items.append(
                NewsItem(
                    headline=headline,
                    pub_date=pub_date if pub_date else datetime.now(tz=timezone.utc),
                    source=source,
                    summary=summary,
                )
            )

        logger.info("Parsed %d items from %s", len(items), source)

    except Exception as exc:
        logger.error("Failed to fetch/parse feed %s: %s", source, exc)

    return items


def _filter_last_24_hours(items: list[NewsItem], reference_time: datetime | None = None) -> list[NewsItem]:
    """Filter news items to retain only those published within the last 24 hours.

    Args:
        items: List of NewsItem objects to filter.
        reference_time: Reference time for the 24-hour window. Defaults to now (UTC).

    Returns:
        Filtered list of NewsItem objects.
    """
    if reference_time is None:
        reference_time = datetime.now(tz=timezone.utc)

    cutoff = reference_time - timedelta(hours=24)

    filtered = []
    for item in items:
        pub_date = item.pub_date
        # Ensure timezone-aware comparison
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        if pub_date >= cutoff:
            filtered.append(item)

    return filtered


def fetch_news() -> list[NewsItem]:
    """Fetch market news from ET RSS and BSE announcements RSS feeds.

    Fetches from all configured feed sources, filters to retain only items
    published within the last 24 hours. On individual feed failure, logs
    the error and continues with available feeds.

    Returns:
        List of NewsItem objects from all feeds, filtered to last 24 hours.
        May be empty if all feeds fail.
    """
    all_items: list[NewsItem] = []

    for feed_config in FEED_SOURCES:
        items = _parse_feed(feed_config["url"], feed_config["source"])
        all_items.extend(items)

    # Filter to last 24 hours
    filtered = _filter_last_24_hours(all_items)

    logger.info(
        "News fetch complete: %d total items, %d within last 24 hours",
        len(all_items),
        len(filtered),
    )

    return filtered
