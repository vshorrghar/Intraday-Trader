"""Test: ALL-LEGS-OR-NONE fill guarantee.
If ANY leg fails to fill, executor MUST unwind all previously filled legs.
A partial Iron Condor (sells filled, buys failed) = NAKED = UNLIMITED LOSS.
"""
import json
from unittest.mock import MagicMock, patch
from fno.models import FnOStrategySetup, StrategyLeg

def _make_ic_strategy():
    legs = [
        StrategyLeg(index="NIFTY", strike_price=24200, expiry_date="2026-06-10",
            option_type="CE", transaction_type="SELL", lot_size=25, num_lots=1, entry_price=50),
        StrategyLeg(index="NIFTY", strike_price=24400, expiry_date="2026-06-10",
            option_type="CE", transaction_type="BUY", lot_size=25, num_lots=1, entry_price=30),
        StrategyLeg(index="NIFTY", strike_price=23800, expiry_date="2026-06-10",
            option_type="PE", transaction_type="SELL", lot_size=25, num_lots=1, entry_price=45),
        StrategyLeg(index="NIFTY", strike_price=23600, expiry_date="2026-06-10",
            option_type="PE", transaction_type="BUY", lot_size=25, num_lots=1, entry_price=25),
    ]
    return FnOStrategySetup(
        strategy_type="IRON_CONDOR", index="NIFTY", legs=legs,
        net_premium=1000, max_profit=1000, max_loss=-4000,
        net_delta=-2, net_gamma=-0.5, net_theta=45, net_vega=-15,
        confidence_score=8, rationale="test", market_regime="SIDEWAYS",
        confluence_score=60, expiry_date="2026-06-10")

class TestAllLegsOrNone:
    def test_partial_fill_triggers_rollback(self):
        """If buy-leg fails after sell-legs filled, executor MUST rollback."""
        from fno.executor import FnO_Order_Executor
        config = MagicMock()
        config.broker = "dhan"
        config.mode = "live"
        config.entry_delay_minutes = 0
        config.force_exit_time = "15:15"
        config.monitor_interval_seconds = 60
        db = MagicMock()
        db.insert_fno_strategy.return_value = 1
        db.insert_fno_trade.return_value = 1
        db.insert_audit_log = MagicMock()
        db.update_fno_strategy = MagicMock()

        broker = MagicMock()
        call_count = [0]
        def mock_place_order(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First 2 legs (SELL) succeed
                return {"broker_order_id": f"ORD_{call_count[0]}", "status": "TRADED"}
            else:
                # 3rd leg (BUY) FAILS
                raise Exception("Order rejected: insufficient margin")
        broker.place_fno_order = mock_place_order
        broker.cancel_order = MagicMock(return_value={"status": "CANCELLED"})

        executor = FnO_Order_Executor(config, db, broker=broker)
        strategy = _make_ic_strategy()

        # Execute — should fail and rollback
        result = executor.execute_strategy(strategy, broker=broker)

        # CRITICAL ASSERTION: result should be None (strategy NOT opened)
        assert result is None, (
            "DANGER: Strategy was opened despite leg failure! "
            "Partial condor = NAKED POSITION = UNLIMITED LOSS!")

        # Verify rollback was attempted (cancel_order called for filled legs)
        assert broker.cancel_order.call_count >= 1, (
            "DANGER: No rollback attempted! Filled SELL legs left naked!")

    def test_all_legs_fill_success(self):
        """When all 4 legs fill, strategy opens normally."""
        from fno.executor import FnO_Order_Executor
        config = MagicMock()
        config.broker = "dhan"
        config.mode = "live"
        config.entry_delay_minutes = 0
        config.force_exit_time = "15:15"
        config.monitor_interval_seconds = 60
        db = MagicMock()
        db.insert_fno_strategy.return_value = 1
        db.insert_fno_trade.return_value = 1
        db.insert_audit_log = MagicMock()

        broker = MagicMock()
        broker.place_fno_order.return_value = {"broker_order_id": "ORD_OK", "status": "TRADED"}

        executor = FnO_Order_Executor(config, db, broker=broker)
        strategy = _make_ic_strategy()

        result = executor.execute_strategy(strategy, broker=broker)

        # All legs filled = strategy opens
        assert result is not None, "Strategy should open when all legs fill"
        # Verify 4 legs were placed
        assert broker.place_fno_order.call_count == 4

    def test_no_naked_position_survives_partial_failure(self):
        """Even if rollback partially fails, DB must NOT show OPEN status."""
        from fno.executor import FnO_Order_Executor
        config = MagicMock()
        config.broker = "dhan"
        config.mode = "live"
        config.entry_delay_minutes = 0
        config.force_exit_time = "15:15"
        config.monitor_interval_seconds = 60
        db = MagicMock()
        db.insert_fno_strategy.return_value = 1
        db.insert_fno_trade.return_value = 1
        db.insert_audit_log = MagicMock()
        db.update_fno_strategy = MagicMock()

        broker = MagicMock()
        call_count = [0]
        def mock_place(**kwargs):
            call_count[0] += 1
            if call_count[0] == 3:
                raise Exception("BUY leg rejected")
            return {"broker_order_id": f"ORD_{call_count[0]}", "status": "TRADED"}
        broker.place_fno_order = mock_place
        broker.cancel_order = MagicMock(side_effect=Exception("Cancel also failed"))

        executor = FnO_Order_Executor(config, db, broker=broker)
        strategy = _make_ic_strategy()

        result = executor.execute_strategy(strategy, broker=broker)

        # Even with failed rollback, strategy must NOT be marked OPEN
        assert result is None, "Strategy must not open on partial fill"
