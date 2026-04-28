"""Unit tests for the Market Scanner."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fetchers.models import DealRecord, FIIDIIFlow, StockFundamentals
from llm.models import MarketOpportunity
from llm.market_scanner import scan_opportunities


def _make_fii_dii() -> FIIDIIFlow:
    return FIIDIIFlow(
        date="2025-01-15", fii_buy=5000.0, fii_sell=3000.0, fii_net=2000.0,
        dii_buy=4000.0, dii_sell=3500.0, dii_net=500.0,
    )


def _make_deals() -> list[DealRecord]:
    return [
        DealRecord("bulk", "RELIANCE", "INE002A01018", "Promoter Group", 100000, 2450.0),
        DealRecord("block", "TCS", "INE467B01029", "FII Fund", 50000, 3800.0),
    ]


def _make_fundamentals() -> dict[str, StockFundamentals]:
    return {
        "RELIANCE": StockFundamentals("RELIANCE", 25.0, 1700000.0, 1100.0, 0.8, 20.0, 51.0),
    }


def _make_client_returning(items: list[dict]) -> MagicMock:
    client = MagicMock()
    client.invoke.return_value = {"items": items}
    return client


class TestScanOpportunities:
    """Tests for scan_opportunities."""

    def test_returns_opportunities_from_valid_response(self):
        client = _make_client_returning([{
            "stock_name": "RELIANCE",
            "signal_type": "promoter_buying",
            "rationale": "Promoter group buying 100K shares via bulk deal",
        }])

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)

        assert len(result) == 1
        assert isinstance(result[0], MarketOpportunity)
        assert result[0].signal_type == "promoter_buying"

    def test_all_signal_types_accepted(self):
        client = _make_client_returning([
            {"stock_name": "A", "signal_type": "promoter_buying", "rationale": "r1"},
            {"stock_name": "B", "signal_type": "multibagger", "rationale": "r2"},
            {"stock_name": "C", "signal_type": "fii_accumulation", "rationale": "r3"},
        ])

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)
        assert len(result) == 3
        assert {r.signal_type for r in result} == {"promoter_buying", "multibagger", "fii_accumulation"}

    def test_invalid_signal_type_skipped(self):
        client = _make_client_returning([
            {"stock_name": "A", "signal_type": "invalid_type", "rationale": "r1"},
            {"stock_name": "B", "signal_type": "multibagger", "rationale": "r2"},
        ])

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)
        assert len(result) == 1
        assert result[0].stock_name == "B"

    def test_bedrock_failure_returns_empty(self):
        client = MagicMock()
        client.invoke.side_effect = RuntimeError("API down")

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)
        assert result == []

    def test_empty_response_returns_empty(self):
        client = MagicMock()
        client.invoke.return_value = {}

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)
        assert result == []

    def test_empty_stock_name_skipped(self):
        client = _make_client_returning([
            {"stock_name": "", "signal_type": "multibagger", "rationale": "r1"},
        ])

        result = scan_opportunities(_make_deals(), _make_fii_dii(), _make_fundamentals(), client)
        assert result == []
