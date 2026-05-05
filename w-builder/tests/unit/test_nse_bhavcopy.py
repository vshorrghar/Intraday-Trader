"""Unit tests for the NSE Bhavcopy fetcher."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import BhavcopyRecord
from fetchers.nse_bhavcopy import (
    _parse_bhavcopy_csv,
    fetch_bhavcopy,
    get_cached_bhavcopy,
)

SAMPLE_CSV = (
    " SYMBOL, SERIES, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,"
    " LAST_PRICE, PREV_CLOSE, TOT_TRD_QTY, TOT_TRD_VAL, TIMESTAMP, ISIN_CODE\n"
    " RELIANCE, EQ, 2450.00, 2480.00, 2440.00, 2470.50,"
    " 2468.00, 2445.00, 5000000, 12352500000.00, 15-JAN-2025, INE002A01018\n"
    " TCS, EQ, 3800.00, 3850.00, 3790.00, 3830.25,"
    " 3825.00, 3795.00, 3000000, 11490750000.00, 15-JAN-2025, INE467B01029\n"
)


class TestParseBhavcopyCSV:
    """Tests for _parse_bhavcopy_csv."""

    def test_parses_valid_csv(self):
        records = _parse_bhavcopy_csv(SAMPLE_CSV, "2025-01-15")
        assert len(records) == 2
        assert "INE002A01018" in records
        assert "INE467B01029" in records

    def test_record_fields(self):
        records = _parse_bhavcopy_csv(SAMPLE_CSV, "2025-01-15")
        rec = records["INE002A01018"]
        assert rec.isin == "INE002A01018"
        assert rec.symbol == "RELIANCE"
        assert rec.close_price == 2470.50
        assert rec.date == "2025-01-15"

    def test_skips_rows_with_missing_isin(self):
        csv_text = (
            "SYMBOL,SERIES,CLOSE_PRICE,ISIN_CODE\n"
            "RELIANCE,EQ,2470.50,\n"
            "TCS,EQ,3830.25,INE467B01029\n"
        )
        records = _parse_bhavcopy_csv(csv_text, "2025-01-15")
        assert len(records) == 1
        assert "INE467B01029" in records

    def test_skips_rows_with_bad_price(self):
        csv_text = (
            "SYMBOL,SERIES,CLOSE_PRICE,ISIN_CODE\n"
            "RELIANCE,EQ,NOT_A_NUMBER,INE002A01018\n"
            "TCS,EQ,3830.25,INE467B01029\n"
        )
        records = _parse_bhavcopy_csv(csv_text, "2025-01-15")
        assert len(records) == 1

    def test_empty_csv(self):
        records = _parse_bhavcopy_csv("SYMBOL,CLOSE_PRICE,ISIN_CODE\n", "2025-01-15")
        assert records == {}


class TestGetCachedBhavcopy:
    """Tests for get_cached_bhavcopy."""

    def test_returns_none_when_no_cache(self, tmp_path):
        result = get_cached_bhavcopy(str(tmp_path))
        assert result is None

    def test_loads_most_recent_cache(self, tmp_path):
        # Write two cache files — the later date should be picked
        older = tmp_path / "bhavcopy_2025-01-14.csv"
        newer = tmp_path / "bhavcopy_2025-01-15.csv"
        older.write_text(
            "SYMBOL,CLOSE_PRICE,ISIN_CODE\nRELIANCE,2400.00,INE002A01018\n"
        )
        newer.write_text(
            "SYMBOL,CLOSE_PRICE,ISIN_CODE\nRELIANCE,2470.50,INE002A01018\n"
        )

        records = get_cached_bhavcopy(str(tmp_path))
        assert records is not None
        assert records["INE002A01018"].close_price == 2470.50
        assert records["INE002A01018"].date == "2025-01-15"

    def test_handles_corrupt_cache_file(self, tmp_path):
        cache_file = tmp_path / "bhavcopy_2025-01-15.csv"
        cache_file.write_text("")  # empty / no header
        result = get_cached_bhavcopy(str(tmp_path))
        # Should return empty dict (parsed 0 rows), not None
        assert result == {}


class TestFetchBhavcopy:
    """Tests for fetch_bhavcopy with mocked HTTP."""

    @patch("fetchers.nse_bhavcopy.requests.get")
    def test_successful_download_and_cache(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_CSV
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        records = fetch_bhavcopy(str(tmp_path))
        assert len(records) == 2
        assert "INE002A01018" in records

        # Verify cache file was written
        cache_files = list(tmp_path.glob("bhavcopy_*.csv"))
        assert len(cache_files) == 1

    @patch("fetchers.nse_bhavcopy.requests.get")
    def test_falls_back_to_cache_on_network_error(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Connection refused")

        # Pre-populate cache
        cache_file = tmp_path / "bhavcopy_2025-01-14.csv"
        cache_file.write_text(
            "SYMBOL,CLOSE_PRICE,ISIN_CODE\nTCS,3830.25,INE467B01029\n"
        )

        records = fetch_bhavcopy(str(tmp_path))
        assert len(records) == 1
        assert "INE467B01029" in records

    @patch("fetchers.nse_bhavcopy.requests.get")
    def test_returns_empty_when_no_download_and_no_cache(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Connection refused")
        records = fetch_bhavcopy(str(tmp_path))
        assert records == {}
