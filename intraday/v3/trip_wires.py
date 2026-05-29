"""V3 Trip Wires — safety halts that protect capital.

6 trip wires, each independently monitored. Any tripped wire halts trading.
State persisted in SQLite trip_wire_status table.
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Trip wire IDs
TW1_CONSECUTIVE_LOSSES = "TW1_CONSECUTIVE_LOSSES"
TW2_DRAWDOWN = "TW2_DRAWDOWN"
TW3_LOW_WINRATE = "TW3_LOW_WINRATE"
TW4_TOO_FEW_TRADES = "TW4_TOO_FEW_TRADES"
TW5_DAILY_LOSS = "TW5_DAILY_LOSS"
TW6_PNL_RECONCILIATION = "TW6_PNL_RECONCILIATION"

ALL_WIRES = [TW1_CONSECUTIVE_LOSSES, TW2_DRAWDOWN, TW3_LOW_WINRATE,
             TW4_TOO_FEW_TRADES, TW5_DAILY_LOSS, TW6_PNL_RECONCILIATION]

# Thresholds (LOCKED)
TW1_THRESHOLD = 5       # consecutive losing trades
TW2_THRESHOLD = 50000   # drawdown from peak in Rs
TW3_MIN_TRADES = 30     # minimum trades before checking WR
TW3_MIN_WR = 0.40       # minimum win rate
TW4_DAYS = 21           # trading days window
TW4_MIN_TRADES = 5      # minimum trades in window
TW5_THRESHOLD = 5000    # daily loss limit in Rs
TW6_THRESHOLD = 100     # max acceptable DB vs Dhan diff in Rs

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trip_wire_status (
    wire_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'OK',
    triggered_at TEXT,
    reason TEXT,
    manual_reset_required INTEGER DEFAULT 0,
    last_checked TEXT
)
"""


class TripWireMonitor:
    """Monitors all 6 trip wires against trade database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_table(self):
        conn = self._get_conn()
        conn.execute(CREATE_TABLE_SQL)
        # Initialize all wires as OK if not present
        for wire_id in ALL_WIRES:
            conn.execute(
                "INSERT OR IGNORE INTO trip_wire_status (wire_id, status, last_checked) VALUES (?, 'OK', ?)",
                (wire_id, datetime.now(IST).isoformat())
            )
        conn.commit()
        conn.close()

    def _trip(self, wire_id: str, reason: str, manual_reset: bool = False):
        """Mark a wire as tripped."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE trip_wire_status SET status='TRIPPED', triggered_at=?, reason=?, "
            "manual_reset_required=?, last_checked=? WHERE wire_id=?",
            (datetime.now(IST).isoformat(), reason, int(manual_reset),
             datetime.now(IST).isoformat(), wire_id)
        )
        conn.commit()
        conn.close()
        logger.warning("TRIP WIRE %s TRIPPED: %s", wire_id, reason)

    def _mark_ok(self, wire_id: str):
        """Mark a wire as OK (only if not manual_reset_required)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE trip_wire_status SET status='OK', last_checked=? "
            "WHERE wire_id=? AND manual_reset_required=0",
            (datetime.now(IST).isoformat(), wire_id)
        )
        conn.commit()
        conn.close()

    def check_tw1_consecutive_losses(self) -> bool:
        """TW1: 5 consecutive losing trades → halt 24h."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT pnl FROM intraday_trades WHERE status NOT IN ('REJECTED','CANCELLED','PENDING') "
            "ORDER BY id DESC LIMIT ?", (TW1_THRESHOLD,)
        ).fetchall()
        conn.close()

        if len(rows) < TW1_THRESHOLD:
            self._mark_ok(TW1_CONSECUTIVE_LOSSES)
            return True  # OK — not enough trades yet

        all_losing = all(r[0] is not None and r[0] < 0 for r in rows)
        if all_losing:
            self._trip(TW1_CONSECUTIVE_LOSSES,
                       f"Last {TW1_THRESHOLD} trades all losing")
            return False
        self._mark_ok(TW1_CONSECUTIVE_LOSSES)
        return True

    def check_tw2_drawdown(self) -> bool:
        """TW2: Drawdown > ₹50,000 from peak → hard halt."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT pnl FROM intraday_trades WHERE pnl IS NOT NULL "
            "ORDER BY id ASC"
        ).fetchall()
        conn.close()

        if not rows:
            self._mark_ok(TW2_DRAWDOWN)
            return True

        cumulative = 0
        peak = 0
        max_drawdown = 0
        for (pnl,) in rows:
            cumulative += pnl
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_drawdown = max(max_drawdown, drawdown)

        if max_drawdown > TW2_THRESHOLD:
            self._trip(TW2_DRAWDOWN,
                       f"Drawdown ₹{max_drawdown:.0f} exceeds ₹{TW2_THRESHOLD}",
                       manual_reset=True)
            return False
        self._mark_ok(TW2_DRAWDOWN)
        return True

    def check_tw3_low_winrate(self) -> bool:
        """TW3: 30+ V3 trades with WR < 40% → halt for review."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT pnl FROM intraday_trades WHERE pnl IS NOT NULL "
            "AND status NOT IN ('REJECTED','CANCELLED','PENDING')"
        ).fetchall()
        conn.close()

        if len(rows) < TW3_MIN_TRADES:
            self._mark_ok(TW3_LOW_WINRATE)
            return True  # Not enough trades yet

        wins = sum(1 for (pnl,) in rows if pnl > 0)
        wr = wins / len(rows)
        if wr < TW3_MIN_WR:
            self._trip(TW3_LOW_WINRATE,
                       f"Win rate {wr:.1%} < {TW3_MIN_WR:.0%} over {len(rows)} trades")
            return False
        self._mark_ok(TW3_LOW_WINRATE)
        return True

    def check_tw4_too_few_trades(self) -> bool:
        """TW4: 21 trading days with < 5 trades → regime detection broken."""
        conn = self._get_conn()
        cutoff = (datetime.now(IST) - timedelta(days=TW4_DAYS)).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT COUNT(DISTINCT trade_date) as days, COUNT(*) as trades "
            "FROM intraday_trades WHERE trade_date >= ? "
            "AND status NOT IN ('REJECTED','CANCELLED','PENDING')",
            (cutoff,)
        ).fetchone()
        conn.close()

        if not rows:
            self._mark_ok(TW4_TOO_FEW_TRADES)
            return True

        days, trades = rows
        if days >= TW4_DAYS and trades < TW4_MIN_TRADES:
            self._trip(TW4_TOO_FEW_TRADES,
                       f"Only {trades} trades in {days} trading days (need {TW4_MIN_TRADES}+)")
            return False
        self._mark_ok(TW4_TOO_FEW_TRADES)
        return True

    def check_tw5_daily_loss(self, today: str = None) -> bool:
        """TW5: Daily loss > ₹5,000 → halt for the day."""
        if today is None:
            today = datetime.now(IST).strftime("%Y-%m-%d")

        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM intraday_trades "
            "WHERE trade_date = ? AND pnl IS NOT NULL",
            (today,)
        ).fetchone()
        conn.close()

        daily_pnl = row[0] if row else 0
        if daily_pnl < -TW5_THRESHOLD:
            self._trip(TW5_DAILY_LOSS,
                       f"Daily loss ₹{abs(daily_pnl):.0f} exceeds ₹{TW5_THRESHOLD}")
            return False
        self._mark_ok(TW5_DAILY_LOSS)
        return True

    def check_tw6_pnl_reconciliation(self, db_pnl: float, dhan_pnl: float) -> bool:
        """TW6: P&L doesn't reconcile between DB and Dhan."""
        diff = abs(db_pnl - dhan_pnl)
        if diff > TW6_THRESHOLD:
            self._trip(TW6_PNL_RECONCILIATION,
                       f"DB P&L ₹{db_pnl:.2f} vs Dhan ₹{dhan_pnl:.2f} — diff ₹{diff:.2f}",
                       manual_reset=True)
            return False
        self._mark_ok(TW6_PNL_RECONCILIATION)
        return True

    def all_clear(self) -> tuple[bool, list[str]]:
        """Check all trip wires. Returns (True, []) if all clear.

        Note: TW1-TW5 are auto-checked from DB. TW6 requires external input.
        This method checks TW1-TW5 and reads TW6 status from DB.
        """
        tripped = []

        if not self.check_tw1_consecutive_losses():
            tripped.append(TW1_CONSECUTIVE_LOSSES)
        if not self.check_tw2_drawdown():
            tripped.append(TW2_DRAWDOWN)
        if not self.check_tw3_low_winrate():
            tripped.append(TW3_LOW_WINRATE)
        if not self.check_tw4_too_few_trades():
            tripped.append(TW4_TOO_FEW_TRADES)
        if not self.check_tw5_daily_loss():
            tripped.append(TW5_DAILY_LOSS)

        # TW6 — check persisted state (set externally by reconciliation script)
        conn = self._get_conn()
        row = conn.execute(
            "SELECT status FROM trip_wire_status WHERE wire_id=?",
            (TW6_PNL_RECONCILIATION,)
        ).fetchone()
        conn.close()
        if row and row[0] == "TRIPPED":
            tripped.append(TW6_PNL_RECONCILIATION)

        if tripped:
            logger.warning("TRIP WIRES TRIPPED: %s — TRADING HALTED", tripped)
            return False, tripped

        return True, []

    def manual_reset(self, wire_id: str) -> bool:
        """Manually reset a tripped wire. Returns True if successful."""
        if wire_id not in ALL_WIRES:
            return False
        conn = self._get_conn()
        conn.execute(
            "UPDATE trip_wire_status SET status='OK', triggered_at=NULL, "
            "reason=NULL, manual_reset_required=0, last_checked=? WHERE wire_id=?",
            (datetime.now(IST).isoformat(), wire_id)
        )
        conn.commit()
        conn.close()
        logger.info("Trip wire %s manually reset", wire_id)
        return True
