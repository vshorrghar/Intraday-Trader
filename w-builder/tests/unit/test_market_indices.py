"""Unit tests for the market indices fetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import IndexData
from fetchers.market_indices import (
    _parse_indices_response,
    _parse_numeric,
    fetch_indices,
    get_cached_indices,
)


SAMPLE_INDICES_RESPONSE = {
    "data": [
        {
            "index": "NIFTY 50",
            "last": "23456.78",
            "variation": "123.45",
            "percentChange": "0.53",
        },
        {
            "index": "NIFTY BANK",
            "last": "49876.50",
            "variation": "-234.10",
            "percentChange": "-0.47",
        },
        {
            "index": "NIFTY MIDCAP 100",
            "last": "52345.00",
            "variation": "456.00",
            "percentChange": "0.88",
        },
        {
            "index": "S&P BSE SENSEX",
            "last": "77123.45",
            "variation": "345.67",
            "percentChange": "0.45",
        },
        {
            "index": "NIFTY IT",
            "last": "38000.00",
            "variation": "100.00",
            "percentChange": "0.26",
        },
    ]
}


class TestParseNumeric:
    """Tests for _parse_numeric helper."""

    def test_plain_number(self):
        assert _parse_numeric("23456.78") == 23456.78

    def test_number_with_commas(self):
        assert _parse_numeric("1,234.56") == 1234.56

    def test_integer_input(self):
        assert _parse_numeric(100) == 100.0

    def test_float_input(self):
        assert _parse_numeric(3.14) == 3.14

    def test_invalid_string(self):
        assert _parse_numeric("N/A") == 0.0


class TestParseIndicesResponse:
    """Tests for _parse_indices_response."""

    def test_extracts_target_indices(self):
        records = _parse_indices_response(SAMPLE_INDICES_RESPONSE)
        names = {r.name for r in records}
        assert "NIFTY 50" in names
        assert "NIFTY BANK" in names
        assert "NIFTY MIDCAP 100" in names
        assert "S&P BSE SENSEX" in names

    def test_excludes_non_target_indices(self):
        records = _parse_indices_response(SAMPLE_INDICES_RESPONSE)
        names = {r.name for r in records}
        assert "NIFTY IT" not in names

    def test_record_fields(self):
        records = _parse_indices_response(SAMPLE_INDICES_RESPONSE)
        nifty = next(r for r in records if r.name == "NIFTY 50")
        assert nifty.last_price == 23456.78
        assert nifty.change == 123.45
        assert nifty.change_percent == 0.53

    def test_negative_change(self):
        records = _parse_indices_response(SAMPLE_INDICES_RESPONSE)
        bank = next(r for r in records if r.name == "NIFTY BANK")
        assert bank.change == -234.10
        assert bank.change_percent == -0.47

    def test_empty_data(self):
        records = _parse_indices_response({"data": []})
        assert records == []

    def test_missing_data_key(self):
        records = _parse_indices_response({})
        assert records == []


class TestGetCachedIndices:
    """Tests for get_cached_indices."""

    def test_returns_none_when_no_cache(self, tmp_path):
        result = get_cached_indices(str(tmp_path))
        assert result is None

    def test_loads_most_recent_cache(self, tmp_path):
        import json
        older = tmp_path / "indices_2025-01-14.json"
        newer = tmp_path / "indices_2025-01-15.json"
        older.write_text(json.dumps({"data": [
            {"index": "NIFTY 50", "last": "23000", "variation": "100", "percentChange": "0.4"}
        ]}))
        newer.write_text(json.dumps(SAMPLE_INDICES_RESPONSE))

        records = get_cached_indices(str(tmp_path))
        assert records is not None
        assert len(records) == 4


class TestFetchIndices:
    """Tests for fetch_indices with mocked HTTP."""

    @patch("fetchers.market_indices.requests.get")
    def test_successful_download_and_cache(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_INDICES_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        records = fetch_indices(str(tmp_path))
        assert len(records) == 4

        import glob
        cache_files = list(tmp_path.glob("indices_*.json"))
        assert len(cache_files) == 1

    @patch("fetchers.market_indices.requests.get")
    def test_falls_back_to_cache_on_error(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Network error")

        import json
        cache_file = tmp_path / "indices_2025-01-14.json"
        cache_file.write_text(json.dumps(SAMPLE_INDICES_RESPONSE))

        records = fetch_indices(str(tmp_path))
        assert len(records) == 4

    @patch("fetchers.market_indices.requests.get")
    def test_returns_empty_when_no_download_and_no_cache(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Network error")
        records = fetch_indices(str(tmp_path))
        assert records == []
