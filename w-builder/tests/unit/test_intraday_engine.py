"""Unit tests for the Intraday Engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm.intraday_engine import generate_intraday_setups
from llm.models import IntradaySetup


def _make_market_data() -> dict:
    return {
        "indices": [{"name": "Nifty 50", "last_price": 22500.0, "change": 150.0}],
        "top_gainers": [{"symbol": "RELIANCE", "price": 2470.0, "change_pct": 2.5}],
    }


def _make_five_setups() -> list[dict]:
    return [
        {"stock_name": f"STOCK_{i}", "entry_price": 100.0 + i * 10,
         "target_price": 120.0 + i * 10, "stop_loss": 95.0 + i * 10,
         "rationale": f"Setup rationale {i}"}
        for i in range(5)
    ]


def _make_client_returning(items: list[dict]) -> MagicMock:
    client = MagicMock()
    client.invoke.return_value = {"items": items}
    return client


class TestGenerateIntradaySetups:
    """Tests for generate_intraday_setups."""

    def test_returns_five_setups(self):
        client = _make_client_returning(_make_five_setups())
        result = generate_intraday_setups(_make_market_data(), client)

        assert len(result) == 5
        for setup in result:
            assert isinstance(setup, IntradaySetup)

    def test_setup_fields_populated(self):
        client = _make_client_returning(_make_five_setups())
        result = generate_intraday_setups(_make_market_data(), client)

        setup = result[0]
        assert setup.stock_name == "STOCK_0"
        assert setup.entry_price == 100.0
        assert setup.target_price == 120.0
        assert setup.stop_loss == 95.0
        assert setup.rationale == "Setup rationale 0"

    def test_skips_setups_with_zero_prices(self):
        items = _make_five_setups()
        items[2]["entry_price"] = 0  # Invalid
        client = _make_client_returning(items)

        result = generate_intraday_setups(_make_market_data(), client)
        assert len(result) == 4

    def test_skips_setups_with_missing_rationale(self):
        items = _make_five_setups()
        items[1]["rationale"] = ""
        client = _make_client_returning(items)

        result = generate_intraday_setups(_make_market_data(), client)
        assert len(result) == 4

    def test_bedrock_failure_returns_empty(self):
        client = MagicMock()
        client.invoke.side_effect = RuntimeError("API down")

        result = generate_intraday_setups(_make_market_data(), client)
        assert result == []

    def test_empty_response_returns_empty(self):
        client = MagicMock()
        client.invoke.return_value = {}

        result = generate_intraday_setups(_make_market_data(), client)
        assert result == []

    def test_response_with_top_level_list_key(self):
        """Test that response with a non-'items' list key is still parsed."""
        client = MagicMock()
        client.invoke.return_value = {"setups": _make_five_setups()}

        result = generate_intraday_setups(_make_market_data(), client)
        assert len(result) == 5
