"""Orchestrator-level test: proves paper=True path NEVER reaches real place_order.

This test matches the EXACT cron path:
  run_v3_cycle('vishal-s3', dry_run=False) with paper=True in profile config.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestOrchestratorPaperPath:
    """The critical test: orchestrator with dry_run=False + paper=True
    must NEVER call the real broker's place_order."""

    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    @patch("intraday.v3.dhan_data.fetch_bulk_ltp")
    @patch("intraday.auth_server.authenticate_broker")
    @patch("intraday.v3.regime.detect_regime")
    @patch("intraday.v3.strategies.orb_v6.detect_v6_signals")
    def test_paper_true_never_reaches_real_place_order(
        self, mock_v6, mock_regime, mock_auth, mock_ltp,
        mock_tradeable, mock_universe_fn, mock_cfg, tmp_path
    ):
        """Force a signal through the pipeline and prove place_order is blocked."""

        # Profile config with paper: true
        mock_cfg.return_value = {
            "profile": {"name": "vishal-s3", "paper": True},
            "dhan": {"client_id": "123", "api_key": "x", "api_secret": "y"},
            "database": {"path": str(tmp_path / "test.db")},
            "intraday": {"per_trade_max_capital": 25000, "daily_loss_limit": 5000,
                         "selector": "v3"},
        }

        # Universe
        mock_universe = {
            "RELIANCE": {"security_id": "2885", "sector": "Oil Gas",
                         "mcap_bucket": "LARGE", "is_suspended": False, "is_priority": False},
        }
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe

        # Real broker mock — tracks if place_order is called
        real_broker = MagicMock()
        real_broker.access_token = "real_token"
        real_broker.client_id = "1110941563"
        real_broker.get_positions.return_value = []
        real_broker.get_order_list.return_value = []
        mock_auth.return_value = real_broker

        # Provide healthy LTP data so pipeline doesn't skip
        mock_ltp.return_value = {
            "2885": {"ltp": 1350, "open": 1340, "volume": 5000000, "prev_close": 1335},
        }

        # Regime = TRENDING_UP so V6 fires
        mock_regime.return_value = {"regime": "TRENDING_UP", "reasoning": "test", "date": "2026-05-30"}

        # V6 returns a signal (forces order placement attempt)
        mock_v6.return_value = [{
            "symbol": "RELIANCE", "direction": "LONG", "score": 18,
            "entry_price": 1350, "stop_loss": 1330, "target": 1390, "qty": 7,
            "entry_candle_idx": 5, "confidence": 8,
        }]

        # Create the test DB with required tables
        import sqlite3
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS intraday_trades (
            id INTEGER PRIMARY KEY, trade_date TEXT, symbol TEXT,
            pnl REAL, status TEXT DEFAULT 'CLOSED')""")
        conn.execute("""CREATE TABLE IF NOT EXISTS trip_wire_status (
            wire_id TEXT PRIMARY KEY, status TEXT DEFAULT 'OK',
            triggered_at TEXT, reason TEXT,
            manual_reset_required INTEGER DEFAULT 0, last_checked TEXT)""")
        conn.commit()
        conn.close()

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (True, [])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("vishal-s3", dry_run=False)

        # THE CRITICAL ASSERTION:
        # Real broker's place_order must NEVER have been called
        # (PaperBrokerWrapper should have intercepted it)
        real_broker.place_order.assert_not_called()

        # Pipeline should have attempted to place (signal was provided)
        # but the wrapper blocked it gracefully
        assert result.get("halted") is not True  # Didn't crash
