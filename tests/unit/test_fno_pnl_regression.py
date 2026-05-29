"""Regression test: P&L must NOT be multiplied by num_lots.

Bug f77de67 (2026-04-28): _execute_exit() multiplied realized_pnl by num_lots,
but net_premium already includes total quantity (premium × lot_size × num_lots).
This caused 3× overcounting for 3-lot strategies.

Fixed in c36773a (2026-05-03): removed lot multiplier, added cap.

This test ensures the bug stays dead.
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

IST = timezone(timedelta(hours=5, minutes=30))


def _create_test_db():
    """Create an in-memory DB with fno_strategies and fno_trades tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE fno_strategies (
        id INTEGER PRIMARY KEY,
        trade_date TEXT,
        timestamp TEXT,
        strategy_type TEXT,
        index_name TEXT,
        legs_json TEXT,
        net_premium REAL,
        max_profit REAL,
        max_loss REAL,
        net_delta REAL DEFAULT 0,
        net_gamma REAL DEFAULT 0,
        net_theta REAL DEFAULT 0,
        net_vega REAL DEFAULT 0,
        status TEXT DEFAULT 'OPEN',
        entry_time TEXT,
        exit_time TEXT,
        realized_pnl REAL,
        mode TEXT DEFAULT 'PAPER',
        confidence_score INTEGER,
        confluence_score REAL,
        rationale TEXT
    )""")
    conn.execute("""CREATE TABLE fno_trades (
        id INTEGER PRIMARY KEY,
        trade_date TEXT,
        timestamp TEXT,
        index_name TEXT,
        tradingsymbol TEXT,
        option_type TEXT,
        strike_price REAL,
        expiry_date TEXT,
        action TEXT,
        order_type TEXT,
        quantity INTEGER,
        lots INTEGER DEFAULT 1,
        price REAL DEFAULT 0,
        trigger_price REAL DEFAULT 0,
        broker_order_id TEXT,
        broker_name TEXT,
        status TEXT DEFAULT 'OPEN',
        entry_price REAL DEFAULT 0,
        exit_price REAL,
        pnl REAL,
        mode TEXT DEFAULT 'PAPER',
        strategy_id INTEGER
    )""")
    conn.execute("""CREATE TABLE intraday_audit_log (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        event_type TEXT,
        details_json TEXT,
        trade_id INTEGER
    )""")
    conn.commit()
    return conn


def _insert_strategy_35_scenario(conn):
    """Insert the exact scenario from strategy id=35 that triggered the bug.

    Strategy: IRON_CONDOR on FINNIFTY, 3 lots (75 qty per leg)
    net_premium = 23226.0 (already includes 75 qty multiplication)

    Uses TODAY's date so _execute_exit can find it (it queries by now.strftime).
    """
    legs_json = json.dumps([
        {"strike": 23350.0, "option_type": "CE", "transaction_type": "SELL",
         "num_lots": 3, "entry_price": 300.95, "expiry_date": "2026-04-28"},
        {"strike": 23650.0, "option_type": "CE", "transaction_type": "BUY",
         "num_lots": 3, "entry_price": 146.69, "expiry_date": "2026-04-28"},
        {"strike": 23650.0, "option_type": "PE", "transaction_type": "SELL",
         "num_lots": 3, "entry_price": 302.14, "expiry_date": "2026-04-28"},
        {"strike": 23350.0, "option_type": "PE", "transaction_type": "BUY",
         "num_lots": 3, "entry_price": 146.72, "expiry_date": "2026-04-28"},
    ])

    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    conn.execute(
        """INSERT INTO fno_strategies
           (id, trade_date, timestamp, strategy_type, index_name, legs_json,
            net_premium, max_profit, max_loss, status, entry_time, mode,
            confidence_score, confluence_score, net_theta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (35, today, now.isoformat(), "IRON_CONDOR", "FINNIFTY", legs_json,
         23226.0, 23226.0, -726.0, "OPEN", now.isoformat(), "PAPER", 8, 60.0, 45.0),
    )
    conn.commit()


class TestPnlBugRegression:
    """Regression tests for the lot-multiplication P&L bug (f77de67)."""

    def test_execute_exit_does_not_multiply_by_num_lots(self):
        """Regression: realized_pnl must NOT be multiplied by num_lots.

        net_premium already includes total quantity, so multiplying again
        would produce 3× overcounting for 3-lot strategies.

        This test reproduces the exact scenario from strategy id=35:
        - net_premium = 23226 (includes 75 qty per leg)
        - num_lots = 3
        - force_exit with current_premium near 0

        Bug behavior: realized_pnl = 23226 × 3 = 69678 (WRONG)
        Correct behavior: realized_pnl <= 23226 (capped at entry_premium)
        """
        from fno.monitor import FnO_Position_Monitor

        conn = _create_test_db()
        _insert_strategy_35_scenario(conn)

        # Create mock DB manager
        db = MagicMock()
        db.conn = conn
        db.get_fno_strategies_for_date = lambda date: [dict(r) for r in
            conn.execute("SELECT * FROM fno_strategies WHERE trade_date=?", (date,)).fetchall()]
        db.update_fno_strategy = MagicMock()
        db.insert_audit_log = MagicMock()

        # Create mock config
        config = MagicMock()
        config.force_exit_time = "15:00"
        config.trailing_sl_trigger_pct = 150
        config.partial_book_pct = 50
        config.max_delta_exposure = 100
        config.max_vega_exposure = 100
        config.broker = "dhan"

        # Create monitor
        monitor = FnO_Position_Monitor(config, db, MagicMock(), broker=None, paper_engine=None)

        # Call _execute_exit with current_premium = 0 (force exit scenario)
        now = datetime.now(IST)
        monitor._execute_exit(35, "FORCE_EXITED", 0.05, now)

        # Verify: realized_pnl must be <= net_premium (1×), NOT 3× net_premium
        call_args = db.update_fno_strategy.call_args
        assert call_args is not None, "update_fno_strategy was not called"

        kwargs = call_args[1] if call_args[1] else {}
        # update_fno_strategy is called with keyword args
        realized_pnl = kwargs.get("realized_pnl", call_args[0][2] if len(call_args[0]) > 2 else None)

        # The key assertion: P&L must NOT exceed net_premium (23226)
        # Bug would produce 69678 (3× net_premium)
        assert realized_pnl is not None, "realized_pnl not passed to update"
        assert realized_pnl <= 23226.0, (
            f"BUG REGRESSION: realized_pnl={realized_pnl} exceeds net_premium=23226. "
            f"Lot multiplication bug has returned!"
        )
        assert realized_pnl >= -23226.0 * 3, (
            f"realized_pnl={realized_pnl} below -3× net_premium cap"
        )

        conn.close()

    def test_execute_exit_force_exit_premium_near_zero(self):
        """Force exit with premium decayed to near-zero should give ~1× profit."""
        from fno.monitor import FnO_Position_Monitor

        conn = _create_test_db()
        _insert_strategy_35_scenario(conn)

        db = MagicMock()
        db.conn = conn
        db.get_fno_strategies_for_date = lambda date: [dict(r) for r in
            conn.execute("SELECT * FROM fno_strategies WHERE trade_date=?", (date,)).fetchall()]
        db.update_fno_strategy = MagicMock()
        db.insert_audit_log = MagicMock()

        config = MagicMock()
        config.force_exit_time = "15:00"
        config.trailing_sl_trigger_pct = 150
        config.partial_book_pct = 50
        config.max_delta_exposure = 100
        config.max_vega_exposure = 100
        config.broker = "dhan"

        monitor = FnO_Position_Monitor(config, db, MagicMock(), broker=None, paper_engine=None)

        # Force exit with current_premium = 0.05 (nearly fully decayed)
        now = datetime.now(IST)
        monitor._execute_exit(35, "FORCE_EXITED", 0.05, now)

        kwargs = db.update_fno_strategy.call_args[1]
        realized_pnl = kwargs.get("realized_pnl")

        # For selling strategy: profit = entry_premium - current_premium
        # = 23226 - 0.05 = 23225.95, capped at entry_premium = 23226
        assert 23000 <= realized_pnl <= 23226, (
            f"Expected ~23226 for fully decayed premium, got {realized_pnl}"
        )

        conn.close()

    def test_execute_exit_loss_scenario(self):
        """When current_premium > entry_premium, P&L should be negative (loss)."""
        from fno.monitor import FnO_Position_Monitor

        conn = _create_test_db()
        _insert_strategy_35_scenario(conn)

        db = MagicMock()
        db.conn = conn
        db.get_fno_strategies_for_date = lambda date: [dict(r) for r in
            conn.execute("SELECT * FROM fno_strategies WHERE trade_date=?", (date,)).fetchall()]
        db.update_fno_strategy = MagicMock()
        db.insert_audit_log = MagicMock()

        config = MagicMock()
        config.force_exit_time = "15:00"
        config.trailing_sl_trigger_pct = 150
        config.partial_book_pct = 50
        config.max_delta_exposure = 100
        config.max_vega_exposure = 100
        config.broker = "dhan"

        monitor = FnO_Position_Monitor(config, db, MagicMock(), broker=None, paper_engine=None)

        # Exit with current_premium = 30000 (premium expanded = loss for seller)
        now = datetime.now(IST)
        monitor._execute_exit(35, "STOPPED_OUT", 30000.0, now)

        kwargs = db.update_fno_strategy.call_args[1]
        realized_pnl = kwargs.get("realized_pnl")

        # For selling: profit = 23226 - 30000 = -6774
        # Capped at -3 × 23226 = -69678 (won't hit this cap here)
        assert realized_pnl < 0, f"Expected negative P&L for loss, got {realized_pnl}"
        assert realized_pnl >= -23226 * 3, f"P&L {realized_pnl} below -3× cap"

        conn.close()

    def test_pnl_bounds_for_any_num_lots(self):
        """For any num_lots value, realized_pnl must stay within [-3×, 1×] of net_premium."""
        from fno.monitor import FnO_Position_Monitor

        for num_lots in [1, 2, 3, 5, 10]:
            conn = _create_test_db()

            # Insert strategy with variable num_lots
            net_premium = 1000.0 * num_lots  # Simulates already-multiplied premium
            legs_json = json.dumps([
                {"strike": 24000.0, "option_type": "CE", "transaction_type": "SELL",
                 "num_lots": num_lots, "entry_price": 50.0, "expiry_date": "2026-05-01"},
                {"strike": 24200.0, "option_type": "CE", "transaction_type": "BUY",
                 "num_lots": num_lots, "entry_price": 30.0, "expiry_date": "2026-05-01"},
            ])
            now = datetime.now(IST)
            today = now.strftime("%Y-%m-%d")
            now_str = now.isoformat()
            conn.execute(
                """INSERT INTO fno_strategies
                   (id, trade_date, timestamp, strategy_type, index_name, legs_json,
                    net_premium, max_profit, max_loss, status, entry_time, mode,
                    confidence_score, confluence_score, net_theta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (1, today, now_str, "IRON_CONDOR", "NIFTY", legs_json,
                 net_premium, net_premium, -5000.0, "OPEN", now_str, "PAPER", 8, 60.0, 30.0),
            )
            conn.commit()

            db = MagicMock()
            db.conn = conn
            db.get_fno_strategies_for_date = lambda date: [dict(r) for r in
                conn.execute("SELECT * FROM fno_strategies WHERE trade_date=?", (date,)).fetchall()]
            db.update_fno_strategy = MagicMock()
            db.insert_audit_log = MagicMock()

            config = MagicMock()
            config.force_exit_time = "15:00"
            config.trailing_sl_trigger_pct = 150
            config.partial_book_pct = 50
            config.max_delta_exposure = 100
            config.max_vega_exposure = 100
            config.broker = "dhan"

            monitor = FnO_Position_Monitor(config, db, MagicMock(), broker=None, paper_engine=None)
            monitor._execute_exit(1, "FORCE_EXITED", 0.05, datetime.now(IST))

            kwargs = db.update_fno_strategy.call_args[1]
            realized_pnl = kwargs.get("realized_pnl")

            assert realized_pnl <= net_premium, (
                f"num_lots={num_lots}: realized_pnl={realized_pnl} > net_premium={net_premium}. "
                f"Lot multiplication bug!"
            )
            assert realized_pnl >= -net_premium * 3, (
                f"num_lots={num_lots}: realized_pnl={realized_pnl} below -3× cap"
            )

            conn.close()
