"""Unit tests for the IPO GMP fetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import IPORecord
from fetchers.ipo_fetcher import (
    _parse_ipo_table,
    _parse_numeric,
    fetch_ipo_gmp,
)


SAMPLE_IPO_HTML = """
<html>
<body>
<table class="table">
  <tr>
    <th>IPO</th><th>Price</th><th>GMP</th><th>Est Listing</th><th>Subscription</th>
  </tr>
  <tr>
    <td>Acme Corp IPO</td>
    <td>₹ 500 - 525</td>
    <td>₹ 150</td>
    <td>₹ 675</td>
    <td>12.5x</td>
  </tr>
  <tr>
    <td>Beta Ltd IPO</td>
    <td>₹ 200 - 210</td>
    <td>₹ -20</td>
    <td>₹ 190</td>
    <td>0.8x</td>
  </tr>
</table>
</body>
</html>
"""

SAMPLE_IPO_NO_TABLE = """
<html><body><p>No IPO data available</p></body></html>
"""


class TestParseNumeric:
    """Tests for _parse_numeric helper."""

    def test_plain_number(self):
        assert _parse_numeric("150") == 150.0

    def test_negative_number(self):
        assert _parse_numeric("-20") == -20.0

    def test_currency_format(self):
        assert _parse_numeric("₹ 675") == 675.0

    def test_empty_string(self):
        assert _parse_numeric("") == 0.0

    def test_no_number(self):
        assert _parse_numeric("N/A") == 0.0


class TestParseIpoTable:
    """Tests for _parse_ipo_table."""

    def test_parses_valid_table(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_IPO_HTML, "lxml")
        records = _parse_ipo_table(soup)
        assert len(records) == 2

    def test_record_fields(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_IPO_HTML, "lxml")
        records = _parse_ipo_table(soup)
        rec = records[0]
        assert rec.name == "Acme Corp IPO"
        assert "500" in rec.price_band
        assert rec.gmp == 150.0
        assert rec.estimated_listing_price == 675.0
        assert rec.subscription_status == "12.5x"

    def test_negative_gmp(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_IPO_HTML, "lxml")
        records = _parse_ipo_table(soup)
        rec = records[1]
        assert rec.gmp == -20.0

    def test_no_table_returns_empty(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SAMPLE_IPO_NO_TABLE, "lxml")
        records = _parse_ipo_table(soup)
        assert records == []


class TestFetchIpoGmp:
    """Tests for fetch_ipo_gmp with mocked HTTP."""

    @patch("fetchers.ipo_fetcher.requests.get")
    def test_successful_fetch(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_IPO_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        records = fetch_ipo_gmp()
        assert len(records) == 2
        assert records[0].name == "Acme Corp IPO"

    @patch("fetchers.ipo_fetcher.requests.get")
    def test_returns_empty_on_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        records = fetch_ipo_gmp()
        assert records == []

    @patch("fetchers.ipo_fetcher.requests.get")
    def test_returns_empty_on_no_table(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_IPO_NO_TABLE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        records = fetch_ipo_gmp()
        assert records == []
