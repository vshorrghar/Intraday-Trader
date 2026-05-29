"""Tests for V3 orchestrator — end-to-end pipeline with mocks."""
import json
import sqlite3
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_db(tmp_path):
    """Create temp DB with required tables."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE intraday_trades (
            id INTEGER PRIMARY KEY, trade_date TEXT, symbol TEXT,
            pnl REAL, status TEXT DEFAULT 'CLOSED'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trip_wire_status (
            wire_id TEXT PRIMARY KEY, status TEXT DEFAULT 'OK',
            triggered_at TEXT, reason TEXT,
            manual_reset_required INTEGER DEFAULT 0, last_checked TEXT
        )
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_profile_cfg():
    return {
        "dhan": {"client_id": "123", "api_key": "x", "api_secret": "y"},
        "database": {"path": "database/test.db"},
        "intraday": {"per_trade_max_capital": 10000, "selector": "v3"},
    }


@pytest.fixture
def mock_universe():
    return {
        "RELIANCE": {"security_id": "2885", "sector": "Oil Gas", "mcap_bucket": "LARGE",
                     "is_suspended": False, "is_priority": False},
        "TCS": {"security_id": "11536", "sector": "IT", "mcap_bucket": "LARGE",
                "is_suspended": False, "is_priority": False},
        "HINDALCO": {"security_id": "1363", "sector": "Metals", "mcap_bucket": "LARGE",
                     "is_suspended": False, "is_priority": True},
    }


class TestOrchestratorDryRun:
    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    def test_dry_run_completes_without_errors(self, mock_tradeable,
                                              mock_universe_fn, mock_cfg,
                                              mock_db, mock_profile_cfg, mock_universe, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                mock_tw.return_value.all_clear.return_value = (True, [])
                with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=True)

        assert result.get("error") is None
        assert result.get("halted") is False
        assert result["regime"] == "TRENDING_UP"  # dry_run default


class TestOrchestratorTripWireHalt:
    @patch("intraday.v3.orchestrator._load_profile_config")
    def test_trip_wire_halt(self, mock_cfg, mock_db, mock_profile_cfg, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (False, ["TW5_DAILY_LOSS"])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=True)

        assert result.get("halted") is True
        assert "TW5_DAILY_LOSS" in result.get("tripped_wires", [])


class TestOrchestratorDataUnhealthy:
    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    @patch("intraday.v3.dhan_data.fetch_bulk_ltp")
    @patch("intraday.auth_server.authenticate_broker")
    def test_data_unhealthy_skips(self, mock_auth, mock_ltp, mock_tradeable,
                                  mock_universe_fn, mock_cfg,
                                  mock_db, mock_profile_cfg, mock_universe, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe
        mock_auth.return_value = MagicMock(access_token="x", client_id="123")
        # Return LTP data with all zeros (unhealthy)
        mock_ltp.return_value = {"2885": {"ltp": 0, "open": 0, "volume": 0, "prev_close": 0}}

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (True, [])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=False)

        assert result.get("reason") == "data_unhealthy"


class TestOrchestratorRegimeRouting:
    """Test regime routing — these use dry_run=True which defaults to TRENDING_UP.
    For non-TRENDING_UP regimes, we patch the regime constant assignment directly.
    """

    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    @patch("intraday.v3.strategies.orb_v6.detect_v6_signals")
    @patch("intraday.v3.strategies.orb_v4.detect_v4_signals")
    def test_trending_up_routes_v6_v4(self, mock_v4, mock_v6,
                                      mock_tradeable, mock_universe_fn, mock_cfg,
                                      mock_db, mock_profile_cfg, mock_universe, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe
        mock_v6.return_value = [{"symbol": "RELIANCE", "score": 18, "direction": "LONG",
                                 "entry_price": 1350, "stop_loss": 1330, "target": 1390}]
        mock_v4.return_value = []

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (True, [])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=True)

        assert result["regime"] == "TRENDING_UP"
        mock_v6.assert_called_once()
        mock_v4.assert_called_once()

    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    @patch("intraday.v3.dhan_data.fetch_bulk_ltp")
    @patch("intraday.auth_server.authenticate_broker")
    @patch("intraday.v3.regime.detect_regime")
    @patch("intraday.v3.strategies.vwap_mean_reversion.detect_vwap_mr_signals")
    @patch("intraday.v3.strategies.orb_v4.detect_v4_signals")
    def test_ranging_routes_vwap_v4(self, mock_v4, mock_vwap, mock_regime, mock_auth,
                                    mock_ltp, mock_tradeable, mock_universe_fn, mock_cfg,
                                    mock_db, mock_profile_cfg, mock_universe, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe
        mock_auth.return_value = MagicMock(access_token="x", client_id="123")
        # Provide healthy LTP data
        mock_ltp.return_value = {
            "2885": {"ltp": 1350, "open": 1340, "volume": 5000000, "prev_close": 1335},
            "11536": {"ltp": 2300, "open": 2290, "volume": 3000000, "prev_close": 2285},
            "1363": {"ltp": 1100, "open": 1090, "volume": 4000000, "prev_close": 1085},
        }
        mock_regime.return_value = {"regime": "RANGING", "reasoning": "test", "date": "2026-05-28"}
        mock_vwap.return_value = []
        mock_v4.return_value = []

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (True, [])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=False)

        mock_vwap.assert_called_once()
        mock_v4.assert_called_once()

    @patch("intraday.v3.orchestrator._load_profile_config")
    @patch("intraday.v3.universe.load_universe")
    @patch("intraday.v3.universe.get_tradeable_universe")
    @patch("intraday.v3.dhan_data.fetch_bulk_ltp")
    @patch("intraday.auth_server.authenticate_broker")
    @patch("intraday.v3.regime.detect_regime")
    def test_volatile_skips_strategies(self, mock_regime, mock_auth, mock_ltp,
                                       mock_tradeable, mock_universe_fn, mock_cfg,
                                       mock_db, mock_profile_cfg, mock_universe, tmp_path):
        mock_cfg.return_value = {**mock_profile_cfg, "database": {"path": mock_db}}
        mock_universe_fn.return_value = mock_universe
        mock_tradeable.return_value = mock_universe
        mock_auth.return_value = MagicMock(access_token="x", client_id="123")
        mock_ltp.return_value = {
            "2885": {"ltp": 1350, "open": 1340, "volume": 5000000, "prev_close": 1335},
            "11536": {"ltp": 2300, "open": 2290, "volume": 3000000, "prev_close": 2285},
            "1363": {"ltp": 1100, "open": 1090, "volume": 4000000, "prev_close": 1085},
        }
        mock_regime.return_value = {"regime": "VOLATILE", "reasoning": "VIX high", "date": "2026-05-28"}

        with patch("intraday.v3.orchestrator.ROOT", tmp_path):
            with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
                with patch("intraday.v3.trip_wires.TripWireMonitor") as mock_tw:
                    mock_tw.return_value.all_clear.return_value = (True, [])

                    from intraday.v3.orchestrator import run_v3_cycle
                    result = run_v3_cycle("test-profile", dry_run=False)

        assert result["regime"] == "VOLATILE"
        assert result["reason"] == "stay_flat_VOLATILE"
        assert result["trades_placed"] == 0
