"""Unit tests for the NSE Bulk/Block Deals fetcher."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from fetchers.models import DealRecord
from fetchers.nse_bulk_deals import (
    _parse_deals,
    _parse_numeric,
    fetch_bulk_deals,
)

SAMPLE_BULK_RESPONSE = {
    "data": [
        {
            "securityName": "Reliance Industries",
            "isin": "INE002A01018",
            "clientName": "Goldman Sachs",
            "quantity": "1,500,000",
            "price": "2470.50",
        },
        {
            "securityName": "Tata Motors",
            "isin": "INE155A01022",
            "clientName": "Morgan Stanley",
            "quantity": 800000,
            "price": 650.75,
        },
    ]
}

SAMPLE_BLOCK_RESPONSE = {
    "data": [
        {
            "securityName": "HDFC Bank",
            "isin": "INE040A01034",
            "clientName": "JP Morgan",
            "quantity": "2,000,000",
            "price": "1580.25",
        },
    ]
}


class TestParseNumeric:
    """Tests for _parse_numeric helper."""

    def test_parses_string_with_commas(self):
        assert _parse_numeric("1,500,000") == 1500000.0

    def test_parses_int(self):
        assert _parse_numeric(42) == 42.0

    def test_parses_float(self):
        assert _parse_numeric(3.14) == 3.14

    def test_returns_zero_for_invalid(self):
        assert _parse_numeric("not_a_number") == 0.0

    def test_returns_zero_for_empty(self):
        assert _parse_numeric("") == 0.0


class TestParseDeals:
    """Tests for _parse_deals."""

    def test_parses_bulk_deals(self):
        records = _parse_deals(SAMPLE_BULK_RESPONSE["data"], "bulk")
        assert len(records) == 2
        assert all(r.deal_type == "bulk" for r in records)

    def test_parses_block_deals(self):
        records = _parse_deals(SAMPLE_BLOCK_RESPONSE["data"], "block")
        assert len(records) == 1
        assert records[0].deal_type == "block"

    def test_record_fields_from_string_values(self):
        records = _parse_deals(SAMPLE_BULK_RESPONSE["data"], "bulk")
        rec = records[0]
        assert rec.security_name == "Reliance Industries"
        assert rec.isin == "INE002A01018"
        assert rec.client_name == "Goldman Sachs"
        assert rec.quantity == 1500000
        assert rec.price == 2470.50

    def test_record_fields_from_numeric_values(self):
        records = _parse_deals(SAMPLE_BULK_RESPONSE["data"], "bulk")
        rec = records[1]
        assert rec.security_name == "Tata Motors"
        assert rec.quantity == 800000
        assert rec.price == 650.75

    def test_skips_entry_missing_security_name(self):
        data = [
            {"clientName": "SomeClient", "quantity": 100, "price": 50.0},
        ]
        records = _parse_deals(data, "bulk")
        assert len(records) == 0

    def test_skips_entry_missing_client_name(self):
        data = [
            {"securityName": "SomeStock", "quantity": 100, "price": 50.0},
        ]
        records = _parse_deals(data, "bulk")
        assert len(records) == 0

    def test_handles_missing_isin_gracefully(self):
        data = [
            {
                "securityName": "SomeStock",
                "clientName": "SomeClient",
                "quantity": 100,
                "price": 50.0,
            },
        ]
        records = _parse_deals(data, "bulk")
        assert len(records) == 1
        assert records[0].isin == ""

    def test_empty_data_list(self):
        records = _parse_deals([], "bulk")
        assert records == []

    def test_handles_alternative_field_names(self):
        """NSE API may use different field names like symbolName, tradedQty."""
        data = [
            {
                "symbolName": "INFY",
                "buySellClientName": "Fidelity",
                "tradedQty": "500000",
                "weightedAvgPrice": "1450.00",
            },
        ]
        records = _parse_deals(data, "block")
        assert len(records) == 1
        assert records[0].security_name == "INFY"
        assert records[0].client_name == "Fidelity"
        assert records[0].quantity == 500000
        assert records[0].price == 1450.00


class TestFetchBulkDeals:
    """Tests for fetch_bulk_deals with mocked HTTP."""

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_successful_fetch_both_endpoints(self, mock_get):
        bulk_resp = MagicMock()
        bulk_resp.status_code = 200
        bulk_resp.json.return_value = SAMPLE_BULK_RESPONSE
        bulk_resp.raise_for_status = MagicMock()

        block_resp = MagicMock()
        block_resp.status_code = 200
        block_resp.json.return_value = SAMPLE_BLOCK_RESPONSE
        block_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [bulk_resp, block_resp]

        records = fetch_bulk_deals()
        assert len(records) == 3
        bulk_records = [r for r in records if r.deal_type == "bulk"]
        block_records = [r for r in records if r.deal_type == "block"]
        assert len(bulk_records) == 2
        assert len(block_records) == 1

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_returns_empty_on_both_failures(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        records = fetch_bulk_deals()
        assert records == []

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_partial_failure_returns_available_deals(self, mock_get):
        """If bulk fails but block succeeds, return block deals only."""
        block_resp = MagicMock()
        block_resp.status_code = 200
        block_resp.json.return_value = SAMPLE_BLOCK_RESPONSE
        block_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [Exception("Timeout"), block_resp]

        records = fetch_bulk_deals()
        assert len(records) == 1
        assert records[0].deal_type == "block"

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_handles_plain_list_response(self, mock_get):
        """Some NSE endpoints return a plain list instead of {data: [...]}."""
        plain_list = [
            {
                "securityName": "ITC",
                "isin": "INE154A01025",
                "clientName": "CLSA",
                "quantity": 300000,
                "price": 440.0,
            },
        ]

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = plain_list
        resp.raise_for_status = MagicMock()

        # Both calls return the same plain list
        mock_get.return_value = resp

        records = fetch_bulk_deals()
        # 1 from bulk + 1 from block (same mock for both)
        assert len(records) == 2

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_handles_malformed_json_response(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = json.JSONDecodeError("bad", "", 0)
        mock_get.return_value = resp

        records = fetch_bulk_deals()
        assert records == []

    @patch("fetchers.nse_bulk_deals.requests.get")
    def test_handles_non_list_data_value(self, mock_get):
        """If the 'data' key contains a non-list value, return empty."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": "unexpected_string"}
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        records = fetch_bulk_deals()
        assert records == []
