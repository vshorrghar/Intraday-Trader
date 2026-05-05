"""Unit tests for the Portfolio Analyzer."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fetchers.models import BhavcopyRecord, StockFundamentals
from llm.models import StockVerdict
from llm.portfolio_analyzer import analyze_portfolio
from parsers.models import ScripSummary, StockHolding


def _make_holding(name="RELIANCE", isin="INE002A01018", unrealised_pnl=500.0) -> StockHolding:
    return StockHolding(
        name=name, isin=isin, quantity=10, avg_buy_price=2400.0,
        buy_value=24000.0, groww_closing_price=2450.0, groww_closing_value=24500.0,
        unrealised_pnl=unrealised_pnl, holding_type="stock", pnl_percent=2.08,
    )


def _make_scrip(isin="INE002A01018", tax_class="short_term") -> ScripSummary:
    return ScripSummary(
        isin=isin, symbol="RELIANCE", buy_date=datetime(2024, 6, 1),
        buy_quantity=10, buy_avg_price=2400.0, sell_quantity=0,
        sell_avg_price=0.0, realised_pnl=0.0, holding_period_days=180,
        tax_classification=tax_class,
    )


def _make_client_returning(items: list[dict]) -> MagicMock:
    client = MagicMock()
    client.invoke.return_value = {"items": items}
    return client


class TestAnalyzePortfolio:
    """Tests for analyze_portfolio."""

    def test_returns_verdicts_from_valid_response(self):
        holdings = [_make_holding()]
        bhavcopy = {"INE002A01018": BhavcopyRecord("INE002A01018", "RELIANCE", 2470.0, "2025-01-15")}
        fundamentals = {"RELIANCE": StockFundamentals("RELIANCE", 25.0, 1700000.0, 1100.0, 0.8, 20.0, 51.0)}
        pnl_data = [_make_scrip()]

        client = _make_client_returning([{
            "name": "RELIANCE", "isin": "INE002A01018", "verdict": "buy",
            "target_price": 2700.0, "stop_loss": 2300.0,
            "rationale": "Strong fundamentals", "tax_harvest_flag": False,
        }])

        result = analyze_portfolio(holdings, bhavcopy, fundamentals, pnl_data, client)

        assert len(result) == 1
        assert isinstance(result[0], StockVerdict)
        assert result[0].verdict == "buy"
        assert result[0].target_price == 2700.0
        assert result[0].stop_loss == 2300.0

    def test_empty_holdings_returns_empty(self):
        client = MagicMock()
        result = analyze_portfolio([], {}, {}, [], client)
        assert result == []
        client.invoke.assert_not_called()

    def test_bedrock_failure_returns_empty(self):
        client = MagicMock()
        client.invoke.side_effect = RuntimeError("API down")

        result = analyze_portfolio([_make_holding()], {}, {}, [], client)
        assert result == []

    def test_empty_response_returns_empty(self):
        client = MagicMock()
        client.invoke.return_value = {}

        result = analyze_portfolio([_make_holding()], {}, {}, [], client)
        assert result == []

    def test_invalid_verdict_defaults_to_hold(self):
        client = _make_client_returning([{
            "name": "TCS", "isin": "INE467B01029", "verdict": "STRONG_BUY",
            "target_price": 4000.0, "stop_loss": 3500.0,
            "rationale": "Good stock", "tax_harvest_flag": False,
        }])

        result = analyze_portfolio([_make_holding("TCS", "INE467B01029")], {}, {}, [], client)
        assert len(result) == 1
        assert result[0].verdict == "hold"

    def test_tax_harvest_flag_computed_from_data(self):
        """Negative unrealised P&L + short-term holding = tax harvest candidate."""
        holding = _make_holding(unrealised_pnl=-1500.0)
        pnl = _make_scrip(tax_class="short_term")

        client = _make_client_returning([{
            "name": "RELIANCE", "isin": "INE002A01018", "verdict": "sell",
            "target_price": 2600.0, "stop_loss": 2200.0,
            "rationale": "Underperforming", "tax_harvest_flag": False,
        }])

        result = analyze_portfolio([holding], {}, {}, [pnl], client)
        assert len(result) == 1
        assert result[0].tax_harvest_flag is True

    def test_tax_harvest_flag_false_for_long_term(self):
        """Negative P&L but long-term holding should NOT be flagged."""
        holding = _make_holding(unrealised_pnl=-1500.0)
        pnl = _make_scrip(tax_class="long_term")

        client = _make_client_returning([{
            "name": "RELIANCE", "isin": "INE002A01018", "verdict": "hold",
            "target_price": 2600.0, "stop_loss": 2200.0,
            "rationale": "Hold for now", "tax_harvest_flag": True,
        }])

        result = analyze_portfolio([holding], {}, {}, [pnl], client)
        assert len(result) == 1
        assert result[0].tax_harvest_flag is False

    def test_skips_items_with_zero_prices(self):
        client = _make_client_returning([{
            "name": "BAD", "isin": "INE000X00000", "verdict": "buy",
            "target_price": 0, "stop_loss": 0,
            "rationale": "Invalid", "tax_harvest_flag": False,
        }])

        result = analyze_portfolio([_make_holding()], {}, {}, [], client)
        assert result == []
