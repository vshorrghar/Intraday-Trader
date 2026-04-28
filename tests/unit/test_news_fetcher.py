"""Unit tests for the market news fetcher."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import NewsItem
from fetchers.news_fetcher import (
    _filter_last_24_hours,
    _parse_feed,
    fetch_news,
)


# IST timezone for test data
IST = timezone(timedelta(hours=5, minutes=30))


class TestFilterLast24Hours:
    """Tests for _filter_last_24_hours."""

    def test_retains_recent_items(self):
        now = datetime.now(tz=timezone.utc)
        items = [
            NewsItem(headline="Recent", pub_date=now - timedelta(hours=1), source="ET", summary=""),
            NewsItem(headline="Old", pub_date=now - timedelta(hours=25), source="ET", summary=""),
        ]
        filtered = _filter_last_24_hours(items, reference_time=now)
        assert len(filtered) == 1
        assert filtered[0].headline == "Recent"

    def test_retains_items_at_boundary(self):
        now = datetime.now(tz=timezone.utc)
        items = [
            NewsItem(headline="Exactly 24h", pub_date=now - timedelta(hours=24), source="ET", summary=""),
        ]
        filtered = _filter_last_24_hours(items, reference_time=now)
        assert len(filtered) == 1

    def test_empty_list(self):
        now = datetime.now(tz=timezone.utc)
        filtered = _filter_last_24_hours([], reference_time=now)
        assert filtered == []

    def test_all_old_items(self):
        now = datetime.now(tz=timezone.utc)
        items = [
            NewsItem(headline="Old1", pub_date=now - timedelta(hours=48), source="ET", summary=""),
            NewsItem(headline="Old2", pub_date=now - timedelta(hours=72), source="BSE", summary=""),
        ]
        filtered = _filter_last_24_hours(items, reference_time=now)
        assert filtered == []

    def test_handles_naive_datetime(self):
        """Items with naive datetimes should be treated as UTC."""
        now = datetime.now(tz=timezone.utc)
        naive_recent = now.replace(tzinfo=None) - timedelta(hours=2)
        items = [
            NewsItem(headline="Naive", pub_date=naive_recent, source="ET", summary=""),
        ]
        filtered = _filter_last_24_hours(items, reference_time=now)
        assert len(filtered) == 1


class TestParseFeed:
    """Tests for _parse_feed with mocked feedparser."""

    @patch("fetchers.news_fetcher.feedparser.parse")
    def test_parses_valid_feed(self, mock_parse):
        now = datetime.now(tz=timezone.utc)
        mock_entry = MagicMock()
        mock_entry.title = "Market rallies on FII buying"
        mock_entry.published_parsed = now.timetuple()
        mock_entry.summary = "Markets surged 2% today."

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        items = _parse_feed("http://example.com/rss", "Test Source")
        assert len(items) == 1
        assert items[0].headline == "Market rallies on FII buying"
        assert items[0].source == "Test Source"
        assert items[0].summary == "Markets surged 2% today."

    @patch("fetchers.news_fetcher.feedparser.parse")
    def test_handles_bozo_with_no_entries(self, mock_parse):
        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("Malformed XML")
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        items = _parse_feed("http://example.com/rss", "Test Source")
        assert items == []

    @patch("fetchers.news_fetcher.feedparser.parse")
    def test_skips_entries_without_title(self, mock_parse):
        mock_entry = MagicMock()
        mock_entry.title = ""
        mock_entry.summary = "No title"

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        items = _parse_feed("http://example.com/rss", "Test Source")
        assert items == []

    @patch("fetchers.news_fetcher.feedparser.parse")
    def test_handles_exception(self, mock_parse):
        mock_parse.side_effect = Exception("Network error")
        items = _parse_feed("http://example.com/rss", "Test Source")
        assert items == []


class TestFetchNews:
    """Tests for fetch_news with mocked feeds."""

    @patch("fetchers.news_fetcher._parse_feed")
    def test_combines_feeds_and_filters(self, mock_parse_feed):
        now = datetime.now(tz=timezone.utc)
        mock_parse_feed.side_effect = [
            [NewsItem(headline="ET News", pub_date=now - timedelta(hours=1), source="ET", summary="")],
            [NewsItem(headline="BSE News", pub_date=now - timedelta(hours=30), source="BSE", summary="")],
        ]

        items = fetch_news()
        assert len(items) == 1
        assert items[0].headline == "ET News"

    @patch("fetchers.news_fetcher._parse_feed")
    def test_returns_empty_when_all_feeds_fail(self, mock_parse_feed):
        mock_parse_feed.return_value = []
        items = fetch_news()
        assert items == []
