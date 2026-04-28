"""Unit tests for the NSE FII/DII flow fetcher."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import FIIDIIFlow
from fetchers.nse_fii_dii import (
    _parse_fii_dii_response,
    _parse_numeric,
    fetch_fii_dii,
    get_cached_fii_dii,
)

SAMPLE_API_RESPONSE = [
    {
        "category": "FII/FPI *",
        "date": "15-Jan-2025",
        "buyValue": "12,345.67",
        "sellValue": "10,234.56",
    },
    {
        "category": "DII *",
        "date": "15-Jan-2025",
        "buyValue": "8,765.43",
        "sellValue": "9,876.54",
    },
]


class TestParseNumeric:
    """Tests for _parse_numeric helper."""

    def test_parses_string_with_commas(self):
        assert _parse_numeric("12,345.67") == 12345.67

    def test_parses_plain_string(self):
        assert _parse_numeric("100.5") == 100.5

    def test_parses_int(self):
        assert _parse_numeric(42) == 42.0

    def test_parses_float(self):
        assert _parse_numeric(3.14) == 3.14

    def test_returns_zero_for_invalid(self):
        assert _parse_numeric("not_a_number") == 0.0

    def test_returns_zero_for_empty(self):
        assert _parse_numeric("") == 0.0


class TestParseFIIDIIResponse:
    """Tests for _parse_fii_dii_response."""

    def test_parses_valid_response(self):
        flow = _parse_fii_dii_response(SAMPLE_API_RESPONSE)
        assert isinstance(flow, FIIDIIFlow)
        assert flow.fii_buy == 12345.67
        assert flow.fii_sell == 10234.56
        assert flow.dii_buy == 8765.43
        assert flow.dii_sell == 9876.54

    def test_net_value_computation(self):
        flow = _parse_fii_dii_response(SAMPLE_API_RESPONSE)
        assert flow.fii_net == pytest.approx(flow.fii_buy - flow.fii_sell)
        assert flow.dii_net == pytest.approx(flow.dii_buy - flow.dii_sell)
        assert flow.fii_net == pytest.approx(12345.67 - 10234.56)
        assert flow.dii_net == pytest.approx(8765.43 - 9876.54)

    def test_extracts_date(self):
        flow = _parse_fii_dii_response(SAMPLE_API_RESPONSE)
        assert flow.date == "15-Jan-2025"

    def test_handles_numeric_values(self):
        data = [
            {"category": "FII/FPI *", "buyValue": 5000.0, "sellValue": 3000.0},
            {"category": "DII *", "buyValue": 4000, "sellValue": 2000},
        ]
        flow = _parse_fii_dii_response(data)
        assert flow.fii_buy == 5000.0
        assert flow.fii_sell == 3000.0
        assert flow.fii_net == 2000.0
        assert flow.dii_buy == 4000.0
        assert flow.dii_sell == 2000.0
        assert flow.dii_net == 2000.0

    def test_raises_on_empty_response(self):
        with pytest.raises(ValueError, match="no recognisable FII or DII"):
            _parse_fii_dii_response([])

    def test_raises_on_unrecognised_categories(self):
        data = [{"category": "UNKNOWN", "buyValue": "100", "sellValue": "50"}]
        with pytest.raises(ValueError, match="no recognisable FII or DII"):
            _parse_fii_dii_response(data)

    def test_handles_fpi_category(self):
        data = [{"category": "FPI", "buyValue": "1000", "sellValue": "500"}]
        flow = _parse_fii_dii_response(data)
        assert flow.fii_buy == 1000.0
        assert flow.fii_sell == 500.0
        assert flow.fii_net == 500.0

    def test_handles_missing_buy_sell_values(self):
        data = [{"category": "FII/FPI *"}, {"category": "DII *"}]
        flow = _parse_fii_dii_response(data)
        assert flow.fii_buy == 0.0
        assert flow.fii_sell == 0.0
        assert flow.fii_net == 0.0
        assert flow.dii_buy == 0.0
        assert flow.dii_sell == 0.0
        assert flow.dii_net == 0.0


class TestGetCachedFIIDII:
    """Tests for get_cached_fii_dii."""

    def test_returns_none_when_no_cache(self, tmp_path):
        result = get_cached_fii_dii(str(tmp_path))
        assert result is None

    def test_loads_most_recent_cache(self, tmp_path):
        older = tmp_path / "fii_dii_2025-01-14.json"
        newer = tmp_path / "fii_dii_2025-01-15.json"

        older_data = [
            {"category": "FII/FPI *", "date": "14-Jan-2025", "buyValue": "1000", "sellValue": "500"},
            {"category": "DII *", "date": "14-Jan-2025", "buyValue": "800", "sellValue": "600"},
        ]
        newer_data = [
            {"category": "FII/FPI *", "date": "15-Jan-2025", "buyValue": "2000", "sellValue": "1500"},
            {"category": "DII *", "date": "15-Jan-2025", "buyValue": "1800", "sellValue": "1600"},
        ]

        older.write_text(json.dumps(older_data))
        newer.write_text(json.dumps(newer_data))

        flow = get_cached_fii_dii(str(tmp_path))
        assert flow is not None
        assert flow.fii_buy == 2000.0
        assert flow.date == "15-Jan-2025"

    def test_handles_corrupt_cache_file(self, tmp_path):
        cache_file = tmp_path / "fii_dii_2025-01-15.json"
        cache_file.write_text("not valid json{{{")
        result = get_cached_fii_dii(str(tmp_path))
        assert result is None


class TestFetchFIIDII:
    """Tests for fetch_fii_dii with mocked HTTP."""

    @patch("fetchers.nse_fii_dii.requests.get")
    def test_successful_fetch_and_cache(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_API_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        flow = fetch_fii_dii(str(tmp_path))
        assert isinstance(flow, FIIDIIFlow)
        assert flow.fii_buy == 12345.67
        assert flow.fii_net == pytest.approx(12345.67 - 10234.56)

        # Verify cache file was written
        cache_files = list(tmp_path.glob("fii_dii_*.json"))
        assert len(cache_files) == 1

    @patch("fetchers.nse_fii_dii.requests.get")
    def test_falls_back_to_cache_on_network_error(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Connection refused")

        # Pre-populate cache
        cache_data = [
            {"category": "FII/FPI *", "date": "14-Jan-2025", "buyValue": "3000", "sellValue": "2000"},
            {"category": "DII *", "date": "14-Jan-2025", "buyValue": "4000", "sellValue": "3500"},
        ]
        cache_file = tmp_path / "fii_dii_2025-01-14.json"
        cache_file.write_text(json.dumps(cache_data))

        flow = fetch_fii_dii(str(tmp_path))
        assert flow.fii_buy == 3000.0
        assert flow.dii_buy == 4000.0

    @patch("fetchers.nse_fii_dii.requests.get")
    def test_returns_zeroed_flow_when_no_download_and_no_cache(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Connection refused")
        flow = fetch_fii_dii(str(tmp_path))
        assert flow.fii_buy == 0.0
        assert flow.fii_sell == 0.0
        assert flow.fii_net == 0.0
        assert flow.dii_buy == 0.0
        assert flow.dii_sell == 0.0
        assert flow.dii_net == 0.0

    @patch("fetchers.nse_fii_dii.requests.get")
    def test_falls_back_on_malformed_json(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_get.return_value = mock_resp

        flow = fetch_fii_dii(str(tmp_path))
        # No cache either, so zeroed out
        assert flow.fii_buy == 0.0
        assert flow.dii_buy == 0.0
