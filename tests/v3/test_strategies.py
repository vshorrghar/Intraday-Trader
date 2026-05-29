"""Tests for V3 strategy wrappers and diversifier."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.strategies.orb_v6 import detect_v6_signals
from intraday.v3.strategies.orb_v4 import detect_v4_signals
from intraday.v3.diversifier import apply_diversification


class TestOrbV6:
    @patch("intraday.v3.strategies.orb_v6.generate_orb_signals")
    def test_calls_rule_engine_with_v6_variant(self, mock_gen):
        mock_gen.return_value = [{"symbol": "HINDALCO", "direction": "LONG"}]
        result = detect_v6_signals(
            historical_data={"HINDALCO": {}},
            universe={"HINDALCO": "1363"},
            config={"per_trade_max_capital": 10000},
            target_date="2026-05-27",
            nifty_data={"open": [24000]},
        )
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs[1]["strategy_variant"] == "V6" or call_kwargs.kwargs.get("strategy_variant") == "V6"
        assert result == [{"symbol": "HINDALCO", "direction": "LONG"}]

    @patch("intraday.v3.strategies.orb_v6.generate_orb_signals")
    def test_returns_empty_when_no_signals(self, mock_gen):
        mock_gen.return_value = []
        result = detect_v6_signals({}, {}, {}, "2026-05-27")
        assert result == []


class TestOrbV4:
    @patch("intraday.v3.strategies.orb_v4.generate_orb_signals")
    def test_calls_rule_engine_with_v4_variant(self, mock_gen):
        mock_gen.return_value = [{"symbol": "TATASTEEL", "direction": "LONG"}]
        result = detect_v4_signals(
            historical_data={"TATASTEEL": {}},
            universe={"TATASTEEL": "3499"},
            config={"per_trade_max_capital": 10000},
            target_date="2026-05-27",
            nifty_data={"open": [24000]},
        )
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs[1]["strategy_variant"] == "V4" or call_kwargs.kwargs.get("strategy_variant") == "V4"
        assert result == [{"symbol": "TATASTEEL", "direction": "LONG"}]


class TestDiversifier:
    def _make_universe(self):
        return {
            "HDFCBANK": {"sector": "Financial Services", "mcap_bucket": "LARGE"},
            "ICICIBANK": {"sector": "Financial Services", "mcap_bucket": "LARGE"},
            "AXISBANK": {"sector": "Financial Services", "mcap_bucket": "LARGE"},
            "RELIANCE": {"sector": "Oil Gas & Consumable Fuels", "mcap_bucket": "LARGE"},
            "HINDALCO": {"sector": "Metals & Mining", "mcap_bucket": "LARGE"},
            "TATASTEEL": {"sector": "Metals & Mining", "mcap_bucket": "MID"},
            "VEDL": {"sector": "Metals & Mining", "mcap_bucket": "MID"},
            "BHEL": {"sector": "Capital Goods", "mcap_bucket": "MID"},
            "GRANULES": {"sector": "Healthcare", "mcap_bucket": "SMALL"},
            "HFCL": {"sector": "Telecommunication", "mcap_bucket": "SMALL"},
        }

    def test_max_2_per_sector_enforced(self):
        universe = self._make_universe()
        candidates = [
            {"symbol": "HDFCBANK", "score": 10},
            {"symbol": "ICICIBANK", "score": 9},
            {"symbol": "AXISBANK", "score": 8},  # Should be dropped (3rd Financial Services)
            {"symbol": "RELIANCE", "score": 7},
            {"symbol": "HINDALCO", "score": 6},
        ]
        result = apply_diversification(candidates, universe, max_per_sector=2)
        symbols = [c["symbol"] for c in result]
        assert "AXISBANK" not in symbols
        assert "HDFCBANK" in symbols
        assert "ICICIBANK" in symbols
        assert len(result) == 4

    def test_mcap_quota_optional(self):
        universe = self._make_universe()
        candidates = [
            {"symbol": "HDFCBANK", "score": 10},
            {"symbol": "RELIANCE", "score": 9},
            {"symbol": "HINDALCO", "score": 8},
            {"symbol": "TATASTEEL", "score": 7},
            {"symbol": "BHEL", "score": 6},
            {"symbol": "GRANULES", "score": 5},
            {"symbol": "HFCL", "score": 4},
        ]
        # Without quotas — all pass sector check
        result_no_quota = apply_diversification(candidates, universe, max_per_sector=2)
        assert len(result_no_quota) >= 5

    def test_returns_empty_when_input_empty(self):
        result = apply_diversification([], {})
        assert result == []

    def test_preserves_order_within_sector(self):
        universe = {
            "A": {"sector": "Tech", "mcap_bucket": "LARGE"},
            "B": {"sector": "Tech", "mcap_bucket": "LARGE"},
            "C": {"sector": "Finance", "mcap_bucket": "MID"},
        }
        candidates = [
            {"symbol": "A", "score": 10},
            {"symbol": "B", "score": 5},
            {"symbol": "C", "score": 3},
        ]
        result = apply_diversification(candidates, universe, max_per_sector=2)
        symbols = [c["symbol"] for c in result]
        assert symbols.index("A") < symbols.index("B")

    def test_handles_unknown_sector(self):
        universe = {}  # No sector info
        candidates = [
            {"symbol": "MYSTERY1", "score": 10},
            {"symbol": "MYSTERY2", "score": 9},
            {"symbol": "MYSTERY3", "score": 8},
        ]
        # All get "Unknown" sector — max 2 per sector applies
        result = apply_diversification(candidates, universe, max_per_sector=2)
        assert len(result) == 2
