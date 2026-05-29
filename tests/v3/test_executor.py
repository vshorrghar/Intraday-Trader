"""Tests for V3 executor — atomic entry+SL with safety guarantees."""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.executor import place_v3_orders, _execute_atomic_trade, _poll_fill_status


def _make_setup(symbol="RELIANCE", entry=1350, sl=1330, target=1390, qty=7, confidence=8):
    return {"symbol": symbol, "direction": "LONG", "entry_price": entry,
            "stop_loss": sl, "target": target, "qty": qty, "confidence": confidence}


class TestDryRun:
    def test_dry_run_places_nothing(self):
        result = place_v3_orders(None, [_make_setup(), _make_setup("TCS")], dry_run=True)
        assert result["placed"] == 2
        assert result["failed"] == 0
        assert result["naked_exits"] == 0
        assert all(d["status"] == "DRY_RUN" for d in result["details"])


class TestHappyPath:
    def test_entry_fills_then_sl_placed(self):
        broker = MagicMock()
        # Entry order returns ID
        broker.place_order.side_effect = [
            {"broker_order_id": "ENTRY123"},  # Entry LIMIT
            {"broker_order_id": "SL456"},     # SL order
        ]
        # Poll returns filled
        broker.get_order_list.return_value = [
            {"orderId": "ENTRY123", "orderStatus": "TRADED", "filledQty": 7}
        ]

        result = place_v3_orders(broker, [_make_setup()], dry_run=False)

        assert result["placed"] == 1
        assert result["failed"] == 0
        assert result["naked_exits"] == 0
        # Verify SL was placed (second place_order call)
        assert broker.place_order.call_count == 2
        sl_call = broker.place_order.call_args_list[1]
        assert sl_call.kwargs["order_type"] == "SL"
        assert sl_call.kwargs["transaction_type"] == "SELL"


class TestUnfilled:
    def test_entry_unfilled_aborts_no_position(self):
        broker = MagicMock()
        broker.place_order.return_value = {"broker_order_id": "ENTRY123"}
        # Poll always returns pending (never fills)
        broker.get_order_list.return_value = [
            {"orderId": "ENTRY123", "orderStatus": "PENDING", "filledQty": 0}
        ]

        # Low confidence (7) — no MARKET retry
        setup = _make_setup(confidence=7)
        result = place_v3_orders(broker, [setup], dry_run=False)

        assert result["placed"] == 0
        assert result["failed"] == 1
        # Verify cancel was called (safe cancel)
        broker.cancel_order.assert_called_once_with("ENTRY123")
        # SL should NOT have been placed (only 1 place_order call = entry)
        assert broker.place_order.call_count == 1


class TestSLFailEmergencyExit:
    def test_sl_fail_triggers_emergency_market_exit(self):
        broker = MagicMock()
        # Entry succeeds, SL fails (returns no order ID)
        broker.place_order.side_effect = [
            {"broker_order_id": "ENTRY123"},  # Entry
            {"broker_order_id": ""},          # SL FAILS (empty ID)
            {"broker_order_id": "EXIT789"},   # Emergency exit
        ]
        broker.get_order_list.return_value = [
            {"orderId": "ENTRY123", "orderStatus": "TRADED", "filledQty": 7}
        ]

        result = place_v3_orders(broker, [_make_setup()], dry_run=False)

        assert result["naked_exits"] == 1
        assert result["placed"] == 0
        # Third call should be MARKET exit
        exit_call = broker.place_order.call_args_list[2]
        assert exit_call.kwargs["order_type"] == "MARKET"
        assert exit_call.kwargs["transaction_type"] == "SELL"  # Exit a LONG


class TestNoDH906:
    def test_no_dh906_cancel_race(self):
        """Verify we POLL instead of cancel-replace. Cancel only happens ONCE
        after poll timeout, not mid-fill."""
        broker = MagicMock()
        broker.place_order.side_effect = [
            {"broker_order_id": "ENTRY123"},  # Entry LIMIT
            {"broker_order_id": "MKT456"},    # MARKET retry
            {"broker_order_id": "SL789"},     # SL
        ]
        # First 5 polls: PENDING (unfilled). Then after MARKET: TRADED.
        pending = [{"orderId": "ENTRY123", "orderStatus": "PENDING", "filledQty": 0}]
        filled = [{"orderId": "MKT456", "orderStatus": "TRADED", "filledQty": 7}]
        broker.get_order_list.side_effect = [pending] * 5 + [filled] * 5

        setup = _make_setup(confidence=8)  # High confidence → MARKET retry
        result = place_v3_orders(broker, [setup], dry_run=False)

        # Cancel should be called exactly ONCE (after poll timeout, before MARKET)
        assert broker.cancel_order.call_count == 1
        broker.cancel_order.assert_called_with("ENTRY123")
        # Should succeed via MARKET retry
        assert result["placed"] == 1
