"""Tests for swing Super Order executor — proves SL is at broker, not software."""

import pytest
from unittest.mock import MagicMock, patch
from swing.executor import SwingExecutor
from swing.models import SwingConfig, SwingTradeSetup


def _make_trade(symbol="DRREDDY", entry=1319.0, sl=1266.0, target=1451.0, qty=5, conf=8):
    return SwingTradeSetup(
        stock_name=symbol, tradingsymbol=symbol, nse_symbol=symbol,
        entry_price=entry, target_price=target, stop_loss_price=sl,
        quantity=qty, confidence_score=conf, rationale="test",
        holding_days_estimate=10, thesis_invalidation="test",
        sector="PHARMA", strategy_type="PULLBACK",
    )


def _make_config(capital=15000, per_trade_max=5000, max_positions=8):
    return SwingConfig(
        swing_capital_limit=capital,
        swing_per_trade_max=per_trade_max,
        swing_max_open_positions=max_positions,
        swing_min_score=6, swing_min_confidence=5, swing_min_rr=1.8,
    )


class TestZeroSLGuard:
    """HARD GUARD: No Super Order ever placed with stopLossPrice <= 0."""

    def test_zero_sl_blocked(self):
        """Trade with SL=0 is refused — no order placed."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade(sl=0.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result is None, "Must refuse order when SL=0"

    def test_negative_sl_blocked(self):
        """Trade with negative SL is refused."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade(sl=-100.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result is None, "Must refuse order when SL < 0"

    def test_valid_sl_passes(self):
        """Trade with valid SL > 0 proceeds normally."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade(sl=1266.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result is not None
        assert result["payload"]["stopLossPrice"] == 1266.0


class TestBrokerSLInPayload:
    """BLOCKER 1: Prove SL is sent to Dhan in Super Order payload."""

    def test_super_order_payload_contains_stop_loss_price(self):
        """THE ₹910 FIX: stopLossPrice must be in the broker payload."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade(sl=1266.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result is not None
        payload = result["payload"]
        # THE KEY ASSERTION: SL is in the payload sent to broker
        assert "stopLossPrice" in payload
        assert payload["stopLossPrice"] == executor._tick_align(1266.0)
        assert payload["stopLossPrice"] == 1266.0  # Already tick-aligned

    def test_super_order_payload_has_cnc_product_type(self):
        """Confirm CNC delivery, not MIS intraday."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade()

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result["payload"]["productType"] == "CNC"

    def test_super_order_payload_has_target_price(self):
        """Target also at broker — auto-sells on target hit."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade(target=1451.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result["payload"]["targetPrice"] == executor._tick_align(1451.0)

    def test_order_id_captured(self):
        """We store the Super Order ID for tracking."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade()

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        assert result["order_id"].startswith("DRY-SUPER-")

    def test_broker_sl_confirmed_flag_in_record(self):
        """Record explicitly marks SL as broker-held."""
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade()

        with patch.object(executor, '_get_security_id', return_value="881"):
            record = executor._place_single_trade(trade, "DRY_RUN")

        assert record is not None
        assert record["broker_sl_confirmed"] is True


class TestAtomicSuperOrder:
    """BLOCKER 1 part 3: Super Order is atomic — no orphan positions."""

    def test_rejection_returns_none_no_position(self):
        """If Super Order rejected, nothing fills. No orphan position."""
        config = _make_config()
        mock_broker = MagicMock()
        mock_broker._headers.return_value = {"access-token": "test"}
        executor = SwingExecutor(config, broker=mock_broker, db=None, dry_run=False)
        trade = _make_trade()

        # Mock HTTP 400 rejection
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Invalid order"

        with patch.object(executor, '_get_security_id', return_value="881"):
            with patch("requests.post", return_value=mock_resp):
                result = executor._place_super_order(trade)

        # Rejection = None = no position held
        assert result is None

    def test_no_position_without_sl(self):
        """We NEVER hold a position without broker SL.
        Since Super Order is atomic, this is guaranteed by design:
        - If order accepted: entry + SL + target all active
        - If order rejected: nothing fills
        There is no state where entry fills but SL doesn't.
        """
        config = _make_config()
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)
        trade = _make_trade()

        with patch.object(executor, '_get_security_id', return_value="881"):
            result = executor._place_super_order(trade)

        # If we get a result, SL is guaranteed in the payload
        if result:
            assert result["payload"]["stopLossPrice"] > 0
            assert result["sl_price"] > 0


class TestCapitalLimitEnforcement:
    """BLOCKER 2: Capital limit enforced by OUR code, not broker luck."""

    def test_capital_limit_blocks_excess_trades(self):
        """8 picks at ~₹2K each, ₹15K limit → only ~7 fit, rest blocked."""
        config = _make_config(capital=15000)
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)

        # 8 trades each costing ~₹2,600 (entry * qty)
        trades = [
            _make_trade(symbol=f"STOCK{i}", entry=1300.0, qty=2, sl=1250.0, target=1430.0)
            for i in range(8)
        ]
        # 8 × 1300 × 2 = ₹20,800 > ₹15,000 limit

        with patch.object(executor, '_get_security_id', return_value="12345"):
            placed = executor.execute_trades(trades)

        # Should place fewer than 8 (capital limit hit)
        total_deployed = sum(r["entry_price"] * r["quantity"] for r in placed)
        assert total_deployed <= 15000, f"Deployed Rs.{total_deployed} > limit Rs.15000"
        assert len(placed) < 8, f"Placed {len(placed)} trades, should be < 8"

    def test_deployed_includes_existing_positions(self):
        """Capital check includes already-open positions from DB."""
        config = _make_config(capital=15000)
        mock_db = MagicMock()
        # Simulate ₹10K already deployed
        mock_db.get_open_swing_trades.return_value = [
            {"entry_price": 1000, "quantity": 10},  # ₹10,000 deployed
        ]
        executor = SwingExecutor(config, broker=None, db=mock_db, dry_run=True)

        # Try to place ₹6K more (would exceed ₹15K)
        trade = _make_trade(entry=1200.0, qty=5, sl=1150.0, target=1320.0)
        # 1200 * 5 = ₹6,000. Existing ₹10K + ₹6K = ₹16K > ₹15K limit

        with patch.object(executor, '_get_security_id', return_value="881"):
            placed = executor.execute_trades([trade])

        assert len(placed) == 0, "Should be blocked — would exceed capital limit"

    def test_within_limit_passes(self):
        """Trades within capital limit are placed normally."""
        config = _make_config(capital=15000)
        executor = SwingExecutor(config, broker=None, db=None, dry_run=True)

        # Single trade costing ₹2,600 — well within ₹15K
        trade = _make_trade(entry=1300.0, qty=2, sl=1250.0, target=1430.0)

        with patch.object(executor, '_get_security_id', return_value="881"):
            placed = executor.execute_trades([trade])

        assert len(placed) == 1
        assert executor.total_deployed <= 15000
