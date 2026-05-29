"""Tests for V3 trip wires."""
import sqlite3
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.trip_wires import TripWireMonitor, TW1_CONSECUTIVE_LOSSES, TW2_DRAWDOWN, TW3_LOW_WINRATE, TW4_TOO_FEW_TRADES, TW5_DAILY_LOSS, TW6_PNL_RECONCILIATION


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DB with intraday_trades table."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE intraday_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT,
            symbol TEXT,
            pnl REAL,
            status TEXT DEFAULT 'CLOSED'
        )
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def monitor(db_path):
    return TripWireMonitor(db_path)


class TestTW1ConsecutiveLosses:
    def test_ok_when_not_enough_trades(self, monitor):
        assert monitor.check_tw1_consecutive_losses() is True

    def test_trips_on_5_consecutive_losses(self, monitor, db_path):
        conn = sqlite3.connect(db_path)
        for i in range(5):
            conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
                         ("2026-05-27", f"STOCK{i}", -100.0, "CLOSED"))
        conn.commit()
        conn.close()
        assert monitor.check_tw1_consecutive_losses() is False

    def test_ok_when_one_winner_breaks_streak(self, monitor, db_path):
        conn = sqlite3.connect(db_path)
        for i in range(4):
            conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
                         ("2026-05-27", f"STOCK{i}", -100.0, "CLOSED"))
        conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
                     ("2026-05-27", "WINNER", 200.0, "CLOSED"))
        conn.commit()
        conn.close()
        assert monitor.check_tw1_consecutive_losses() is True


class TestTW2Drawdown:
    def test_ok_when_no_trades(self, monitor):
        assert monitor.check_tw2_drawdown() is True

    def test_trips_on_large_drawdown(self, monitor, db_path):
        conn = sqlite3.connect(db_path)
        # Win big then lose bigger
        conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl) VALUES (?, ?, ?)",
                     ("2026-05-20", "A", 10000.0))
        conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl) VALUES (?, ?, ?)",
                     ("2026-05-21", "B", -60000.0))
        conn.commit()
        conn.close()
        assert monitor.check_tw2_drawdown() is False


class TestTW3LowWinrate:
    def test_ok_when_not_enough_trades(self, monitor):
        assert monitor.check_tw3_low_winrate() is True

    def test_trips_when_wr_below_40(self, monitor, db_path):
        conn = sqlite3.connect(db_path)
        # 10 wins, 21 losses = 32% WR
        for i in range(10):
            conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
                         ("2026-05-27", f"W{i}", 100.0, "CLOSED"))
        for i in range(21):
            conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
                         ("2026-05-27", f"L{i}", -50.0, "CLOSED"))
        conn.commit()
        conn.close()
        assert monitor.check_tw3_low_winrate() is False


class TestTW4TooFewTrades:
    def test_ok_when_recent(self, monitor):
        # No trades in window but also not 21 days yet
        assert monitor.check_tw4_too_few_trades() is True


class TestTW5DailyLoss:
    def test_ok_when_no_trades(self, monitor):
        assert monitor.check_tw5_daily_loss(today="2026-05-27") is True

    def test_trips_on_large_daily_loss(self, monitor, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl) VALUES (?, ?, ?)",
                     ("2026-05-27", "A", -3000.0))
        conn.execute("INSERT INTO intraday_trades (trade_date, symbol, pnl) VALUES (?, ?, ?)",
                     ("2026-05-27", "B", -2500.0))
        conn.commit()
        conn.close()
        assert monitor.check_tw5_daily_loss(today="2026-05-27") is False


class TestTW6Reconciliation:
    def test_ok_when_close(self, monitor):
        assert monitor.check_tw6_pnl_reconciliation(db_pnl=500.0, dhan_pnl=520.0) is True

    def test_trips_when_large_diff(self, monitor):
        assert monitor.check_tw6_pnl_reconciliation(db_pnl=500.0, dhan_pnl=700.0) is False


class TestAllClear:
    def test_all_clear_when_no_trades(self, monitor):
        ok, tripped = monitor.all_clear()
        assert ok is True
        assert tripped == []

    def test_manual_reset(self, monitor):
        # Trip TW6 then reset
        monitor.check_tw6_pnl_reconciliation(db_pnl=0, dhan_pnl=500)
        ok, tripped = monitor.all_clear()
        assert TW6_PNL_RECONCILIATION in tripped

        monitor.manual_reset(TW6_PNL_RECONCILIATION)
        ok2, tripped2 = monitor.all_clear()
        assert TW6_PNL_RECONCILIATION not in tripped2
