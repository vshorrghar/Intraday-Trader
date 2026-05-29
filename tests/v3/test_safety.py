"""Tests for V3 broker-truth safety layer."""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.safety import fetch_dhan_truth, check_hard_loss_cap, emergency_square_off_all, poll_exit_fill


def _mock_positions(realized=-500, unrealized=-1500, net_qty=20):
    """Create mock Dhan positions response."""
    return [
        {
            "tradingSymbol": "INFY",
            "securityId": "1594",
            "positionType": "LONG",
            "buyAvg": 1203.30,
            "buyQty": 20,
            "sellAvg": 0,
            "sellQty": 0,
            "netQty": net_qty,
            "realizedProfit": realized,
            "unrealizedProfit": unrealized,
        }
    ]


class TestFetchDhanTruth:
    def test_computes_real_pnl(self):
        broker = MagicMock()
        broker.get_positions.return_value = _mock_positions(realized=-200, unrealized=-700)

        result = fetch_dhan_truth(broker)

        assert result["total_realized"] == -200
        assert result["total_unrealized"] == -700
        assert result["total_pnl"] == -900
        assert result["open_count"] == 1

    def test_handles_empty_positions(self):
        broker = MagicMock()
        broker.get_positions.return_value = []

        result = fetch_dhan_truth(broker)
        assert result["total_pnl"] == 0
        assert result["open_count"] == 0


class TestHardLossCap:
    def test_not_breached_under_limit(self):
        broker = MagicMock()
        broker.get_positions.return_value = _mock_positions(realized=-100, unrealized=-200)

        result = check_hard_loss_cap(broker, daily_cap=1500)

        assert result["breached"] is False
        assert result["total_pnl"] == -300
        assert result["action"] is None

    def test_breached_triggers_square_off(self):
        """THE CRITICAL TEST: Dhan shows -Rs2000, cap is Rs1500 → breach detected."""
        broker = MagicMock()
        broker.get_positions.return_value = _mock_positions(realized=-800, unrealized=-1200)
        # Total = -2000, cap = 1500 → BREACHED

        result = check_hard_loss_cap(broker, daily_cap=1500)

        assert result["breached"] is True
        assert result["total_pnl"] == -2000
        assert result["action"] == "SQUARE_OFF_ALL"


class TestEmergencySquareOff:
    def test_polls_real_fills(self):
        broker = MagicMock()
        broker.get_positions.return_value = _mock_positions(net_qty=20)
        broker.place_order.return_value = {"broker_order_id": "EXIT123"}
        broker.get_order_list.return_value = [
            {"orderId": "EXIT123", "orderStatus": "TRADED", "averageTradedPrice": 1156.0}
        ]

        result = emergency_square_off_all(broker)

        assert result["squared_off"] == 1
        assert result["details"][0]["fill_price"] == 1156.0
        assert result["details"][0]["symbol"] == "INFY"
        # P&L: (1156 - 1203.30) * 20 = -946
        assert result["details"][0]["pnl"] == pytest.approx(-946.0, abs=1)


class TestPollExitFill:
    def test_returns_actual_not_assumed_price(self):
        broker = MagicMock()
        broker.get_order_list.return_value = [
            {"orderId": "EXIT456", "orderStatus": "TRADED", "averageTradedPrice": 1156.50}
        ]

        price = poll_exit_fill(broker, "EXIT456", 20)

        assert price == 1156.50
        # NOT 1203.30 (entry price) or 0 (the old lie)

    def test_returns_zero_when_no_order_id(self):
        broker = MagicMock()
        price = poll_exit_fill(broker, "", 20)
        assert price == 0.0
        broker.get_order_list.assert_not_called()
