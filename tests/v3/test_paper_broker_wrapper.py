"""Tests for PaperBrokerWrapper — proves paper=True path physically blocks orders.

This test matches the EXACT path cron will use:
  dry_run=False (real data) + paper=True (orders blocked)
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.paper_broker_wrapper import PaperBrokerWrapper, PaperModeError, wrap_broker_for_paper
from intraday.v3.executor import place_v3_orders


class TestPaperBrokerWrapper:
    def test_data_calls_pass_through(self):
        """Real data methods work — positions, orders, OHLC."""
        real_broker = MagicMock()
        real_broker.get_positions.return_value = [{"symbol": "INFY", "netQty": 0}]
        real_broker.get_order_list.return_value = []
        real_broker.get_historical_ohlc.return_value = {"open": [100], "close": [101]}

        paper = PaperBrokerWrapper(real_broker)

        assert paper.get_positions() == [{"symbol": "INFY", "netQty": 0}]
        assert paper.get_order_list() == []
        assert paper.get_historical_ohlc("1594", "NSE_EQ", "EQUITY", "5", "2026-05-29", "2026-05-29") == {"open": [100], "close": [101]}

    def test_place_order_raises_paper_mode_error(self):
        """place_order is PHYSICALLY BLOCKED — raises, not returns empty."""
        real_broker = MagicMock()
        paper = PaperBrokerWrapper(real_broker)

        with pytest.raises(PaperModeError, match="PAPER MODE.*place_order BLOCKED"):
            paper.place_order(symbol="INFY", transaction_type="BUY", quantity=20, price=1200)

        # CRITICAL: real broker's place_order was NEVER called
        real_broker.place_order.assert_not_called()

    def test_cancel_order_raises_paper_mode_error(self):
        """cancel_order is PHYSICALLY BLOCKED."""
        real_broker = MagicMock()
        paper = PaperBrokerWrapper(real_broker)

        with pytest.raises(PaperModeError):
            paper.cancel_order("ORDER123")

        real_broker.cancel_order.assert_not_called()

    def test_executor_with_paper_wrapper_fails_gracefully(self):
        """V3 executor handles PaperModeError gracefully — no crash, no naked position."""
        real_broker = MagicMock()
        paper = wrap_broker_for_paper(real_broker)

        # This is the EXACT path cron uses: dry_run=False + paper broker
        result = place_v3_orders(paper, [
            {"symbol": "INFY", "direction": "LONG", "entry_price": 1200,
             "stop_loss": 1180, "target": 1250, "qty": 20, "confidence": 8},
        ], dry_run=False)

        # Order fails gracefully (PaperModeError caught by executor)
        assert result["placed"] == 0
        assert result["failed"] == 1
        # CRITICAL: real broker's place_order was NEVER called
        real_broker.place_order.assert_not_called()

    def test_orchestrator_paper_path_never_reaches_real_orders(self):
        """Full orchestrator path: dry_run=False + paper broker = data works, orders blocked."""
        real_broker = MagicMock()
        real_broker.get_positions.return_value = []
        paper = wrap_broker_for_paper(real_broker)

        # Simulate what orchestrator does: fetch data (works) then try to place (blocked)
        positions = paper.get_positions()  # Should work
        assert positions == []

        # Try to place order — must raise
        with pytest.raises(PaperModeError):
            paper.place_order(symbol="TCS", transaction_type="BUY", quantity=10, price=2300)

        # Real broker order method never touched
        real_broker.place_order.assert_not_called()
