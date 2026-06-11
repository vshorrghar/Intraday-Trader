"""Unit tests for the AMFI NAV fetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import NAVRecord
from fetchers.amfi_nav_fetcher import (
    _parse_amfi_nav_text,
    fetch_amfi_nav,
    get_cached_amfi_nav,
)


SAMPLE_AMFI_TEXT = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
Open Ended Schemes(Debt Scheme - Banking and PSU Fund)
Aditya Birla Sun Life Mutual Fund
119551;INF209K01YY0;INF209K01YZ7;Aditya Birla Sun Life Banking & PSU Debt Fund  - Direct Plan-Dividend;175.4321;14-Jan-2025
119552;INF209K01ZA8;-;Aditya Birla Sun Life Banking & PSU Debt Fund  - Direct Plan-Growth;345.6789;14-Jan-2025

HDFC Mutual Fund
100032;INF179K01234;-;HDFC Balanced Advantage Fund - Growth;412.5600;14-Jan-2025
"""

SAMPLE_AMFI_WITH_NA = """Scheme Code;ISIN;ISIN Reinvest;Scheme Name;NAV;Date
100001;INF001;-;Test Fund A;N.A.;14-Jan-2025
100002;INF002;-;Test Fund B;25.50;14-Jan-2025
"""


class TestParseAmfiNavText:
    """Tests for _parse_amfi_nav_text."""

    def test_parses_valid_text(self):
        records = _parse_amfi_nav_text(SAMPLE_AMFI_TEXT)
        assert len(records) == 3
        assert "119551" in records
        assert "119552" in records
        assert "100032" in records

    def test_record_fields(self):
        records = _parse_amfi_nav_text(SAMPLE_AMFI_TEXT)
        rec = records["119551"]
        assert rec.scheme_code == "119551"
        assert "Aditya Birla" in rec.scheme_name
        assert rec.nav == 175.4321
        assert rec.date == "14-Jan-2025"

    def test_skips_header_and_amc_lines(self):
        records = _parse_amfi_nav_text(SAMPLE_AMFI_TEXT)
        # Only scheme data lines should be parsed, not headers or AMC names
        for code in records:
            assert code.isdigit()

    def test_skips_na_nav_values(self):
        records = _parse_amfi_nav_text(SAMPLE_AMFI_WITH_NA)
        assert "100001" not in records  # N.A. NAV should be skipped
        assert "100002" in records
        assert records["100002"].nav == 25.50

    def test_empty_text(self):
        records = _parse_amfi_nav_text("")
        assert records == {}

    def test_only_headers(self):
        text = "Scheme Code;ISIN;Scheme Name;NAV;Date\n"
        records = _parse_amfi_nav_text(text)
        assert records == {}


class TestGetCachedAmfiNav:
    """Tests for get_cached_amfi_nav."""

    def test_returns_none_when_no_cache(self, tmp_path):
        result = get_cached_amfi_nav(str(tmp_path))
        assert result is None

    def test_loads_most_recent_cache(self, tmp_path):
        older = tmp_path / "amfi_nav_2025-01-14.txt"
        newer = tmp_path / "amfi_nav_2025-01-15.txt"
        older.write_text("100001;INF001;-;Old Fund;10.00;14-Jan-2025\n")
        newer.write_text("100002;INF002;-;New Fund;20.00;15-Jan-2025\n")

        records = get_cached_amfi_nav(str(tmp_path))
        assert records is not None
        assert "100002" in records
        assert records["100002"].nav == 20.00


class TestFetchAmfiNav:
    """Tests for fetch_amfi_nav with mocked HTTP."""

    @patch("fetchers.amfi_nav_fetcher.requests.get")
    def test_successful_download_and_cache(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_AMFI_TEXT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        records = fetch_amfi_nav(str(tmp_path))
        assert len(records) == 3
        assert "119551" in records

        cache_files = list(tmp_path.glob("amfi_nav_*.txt"))
        assert len(cache_files) == 1

    @patch("fetchers.amfi_nav_fetcher.requests.get")
    def test_falls_back_to_cache_on_error(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Network error")

        cache_file = tmp_path / "amfi_nav_2025-01-14.txt"
        cache_file.write_text("100032;INF179;-;HDFC Fund;412.56;14-Jan-2025\n")

        records = fetch_amfi_nav(str(tmp_path))
        assert len(records) == 1
        assert "100032" in records

    @patch("fetchers.amfi_nav_fetcher.requests.get")
    def test_returns_empty_when_no_download_and_no_cache(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Network error")
        records = fetch_amfi_nav(str(tmp_path))
        assert records == {}
