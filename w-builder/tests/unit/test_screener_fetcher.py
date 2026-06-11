"""Unit tests for the Screener.in stock fundamentals fetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import StockFundamentals
from fetchers.screener_fetcher import (
    _extract_metric,
    _parse_numeric,
    fetch_fundamentals,
)


SAMPLE_SCREENER_HTML = """
<html>
<body>
<div id="top-ratios">
  <ul>
    <li class="flex">
      <span class="name">Stock P/E</span>
      <span class="number">28.5</span>
    </li>
    <li class="flex">
      <span class="name">Market Cap</span>
      <span class="number">₹ 18,50,000 Cr.</span>
    </li>
    <li class="flex">
      <span class="name">Book Value</span>
      <span class="number">1,234.56</span>
    </li>
    <li class="flex">
      <span class="name">Dividend Yield</span>
      <span class="number">0.35 %</span>
    </li>
    <li class="flex">
      <span class="name">ROCE</span>
      <span class="number">22.1 %</span>
    </li>
    <li class="flex">
      <span class="name">Promoter Holding</span>
      <span class="number">50.3 %</span>
    </li>
  </ul>
</div>
</body>
</html>
"""


class TestParseNumeric:
    """Tests for _parse_numeric helper."""

    def test_plain_number(self):
        assert _parse_numeric("28.5") == 28.5

    def test_number_with_commas(self):
        assert _parse_numeric("1,234.56") == 1234.56

    def test_number_with_currency(self):
        assert _parse_numeric("₹ 1,850,000 Cr.") == 1850000.0

    def test_percentage(self):
        assert _parse_numeric("22.1 %") == 22.1

    def test_empty_string(self):
        assert _parse_numeric("") is None

    def test_none_input(self):
        assert _parse_numeric(None) is None


class TestExtractMetric:
    """Tests for _extract_metric from HTML."""

    def test_extracts_pe_ratio(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_SCREENER_HTML, "lxml")
        result = _extract_metric(soup, "Stock P/E")
        assert result == 28.5

    def test_extracts_market_cap(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_SCREENER_HTML, "lxml")
        result = _extract_metric(soup, "Market Cap")
        assert result == 1850000.0

    def test_extracts_roce(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_SCREENER_HTML, "lxml")
        result = _extract_metric(soup, "ROCE")
        assert result == 22.1

    def test_returns_none_for_missing_metric(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        result = _extract_metric(soup, "Stock P/E")
        assert result is None


class TestFetchFundamentals:
    """Tests for fetch_fundamentals with mocked HTTP."""

    @patch("fetchers.screener_fetcher._last_request_time", 0.0)
    @patch("fetchers.screener_fetcher.time.sleep")
    @patch("fetchers.screener_fetcher.requests.get")
    def test_successful_fetch(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_SCREENER_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_fundamentals("RELIANCE")
        assert result.symbol == "RELIANCE"
        assert result.pe_ratio == 28.5
        assert result.roce == 22.1

    @patch("fetchers.screener_fetcher._last_request_time", 0.0)
    @patch("fetchers.screener_fetcher.time.sleep")
    @patch("fetchers.screener_fetcher.requests.get")
    def test_returns_none_metrics_on_failure(self, mock_get, mock_sleep):
        mock_get.side_effect = Exception("Connection refused")

        result = fetch_fundamentals("INVALID")
        assert result.symbol == "INVALID"
        assert result.pe_ratio is None
        assert result.market_cap is None
        assert result.book_value is None
        assert result.dividend_yield is None
        assert result.roce is None
        assert result.promoter_holding is None

    @patch("fetchers.screener_fetcher._last_request_time", 0.0)
    @patch("fetchers.screener_fetcher.time.sleep")
    @patch("fetchers.screener_fetcher.requests.get")
    def test_returns_none_metrics_on_empty_page(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>No data</body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_fundamentals("UNKNOWN")
        assert result.symbol == "UNKNOWN"
        assert result.pe_ratio is None
