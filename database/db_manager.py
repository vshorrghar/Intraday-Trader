"""SQLite database manager for Wealth Builder Pro.

Handles persistence of portfolio holdings, AI verdicts, trade records,
and cached market data. All timestamps are stored in IST (UTC+05:30).
Write failures are logged and do not halt the application.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

from parsers.models import StockHolding, MFHolding, TradeRecord
from llm.models import StockVerdict, MFRecommendation

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class DBManager:
    """SQLite database manager with fail-soft write semantics."""

    def __init__(self, db_path: str) -> None:
        """Initialize SQLite connection and create all tables.

        Args:
            db_path: Path to the SQLite database file, or ':memory:' for testing.
        """
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create all required tables if they don't exist."""
        statements = [
            # --- Intraday tables ---
            """CREATE TABLE IF NOT EXISTS intraday_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                tradingsymbol TEXT NOT NULL,
                action TEXT NOT NULL,
                order_type TEXT NOT NULL,
                product_type TEXT NOT NULL DEFAULT 'INTRADAY',
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                trigger_price REAL NOT NULL DEFAULT 0,
                broker_order_id TEXT,
                broker_name TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                entry_price REAL NOT NULL DEFAULT 0,
                exit_price REAL,
                target_price REAL,
                stop_loss_price REAL,
                confidence_score INTEGER,
                strategy_type TEXT,
                rationale TEXT,
                pnl REAL,
                mode TEXT NOT NULL DEFAULT 'DRY_RUN'
            )""",
            """CREATE TABLE IF NOT EXISTS intraday_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                total_trades INTEGER NOT NULL DEFAULT 0,
                winning_trades INTEGER NOT NULL DEFAULT 0,
                losing_trades INTEGER NOT NULL DEFAULT 0,
                total_pnl REAL NOT NULL DEFAULT 0,
                total_realized_loss REAL NOT NULL DEFAULT 0,
                max_drawdown REAL NOT NULL DEFAULT 0,
                broker_name TEXT,
                mode TEXT NOT NULL DEFAULT 'DRY_RUN'
            )""",
            """CREATE TABLE IF NOT EXISTS intraday_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT,
                trade_id INTEGER,
                FOREIGN KEY (trade_id) REFERENCES intraday_trades(id)
            )""",
            # --- Existing tables ---
            """CREATE TABLE IF NOT EXISTS stock_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                name TEXT NOT NULL,
                isin TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_buy_price REAL NOT NULL,
                buy_value REAL NOT NULL,
                closing_price REAL NOT NULL,
                closing_value REAL NOT NULL,
                unrealised_pnl REAL NOT NULL,
                holding_type TEXT NOT NULL,
                pnl_percent REAL NOT NULL,
                live_price REAL,
                live_value REAL,
                nse_symbol TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS mf_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                scheme_name TEXT NOT NULL,
                amc TEXT NOT NULL,
                category TEXT NOT NULL,
                sub_category TEXT NOT NULL,
                folio_no TEXT NOT NULL,
                source TEXT NOT NULL,
                units REAL NOT NULL,
                invested_value REAL NOT NULL,
                current_value REAL NOT NULL,
                returns_absolute REAL NOT NULL,
                xirr REAL NOT NULL,
                returns_percent REAL NOT NULL,
                current_nav REAL,
                scheme_code TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS stock_verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                name TEXT NOT NULL,
                isin TEXT NOT NULL,
                verdict TEXT NOT NULL,
                target_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                rationale TEXT NOT NULL,
                tax_harvest_flag INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS mf_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                scheme_name TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                alternative_scheme TEXT,
                rationale TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                isin TEXT NOT NULL,
                symbol TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS bhavcopy_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                data_json TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS fii_dii_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                data_json TEXT NOT NULL
            )""",
            # --- F&O tables ---
            """CREATE TABLE IF NOT EXISTS fno_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                index_name TEXT NOT NULL,
                tradingsymbol TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike_price REAL NOT NULL,
                expiry_date TEXT NOT NULL,
                action TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                lots INTEGER NOT NULL DEFAULT 1,
                price REAL NOT NULL DEFAULT 0,
                trigger_price REAL NOT NULL DEFAULT 0,
                broker_order_id TEXT,
                broker_name TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                entry_price REAL NOT NULL DEFAULT 0,
                exit_price REAL,
                pnl REAL,
                mode TEXT NOT NULL DEFAULT 'PAPER',
                strategy_id INTEGER,
                FOREIGN KEY (strategy_id) REFERENCES fno_strategies(id)
            )""",
            """CREATE TABLE IF NOT EXISTS fno_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                index_name TEXT NOT NULL,
                legs_json TEXT,
                net_premium REAL NOT NULL DEFAULT 0,
                max_profit REAL NOT NULL DEFAULT 0,
                max_loss REAL NOT NULL DEFAULT 0,
                net_delta REAL NOT NULL DEFAULT 0,
                net_gamma REAL NOT NULL DEFAULT 0,
                net_theta REAL NOT NULL DEFAULT 0,
                net_vega REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDING',
                entry_time TEXT,
                exit_time TEXT,
                realized_pnl REAL,
                mode TEXT NOT NULL DEFAULT 'PAPER',
                confidence_score INTEGER,
                confluence_score REAL,
                rationale TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS fno_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                total_strategies INTEGER NOT NULL DEFAULT 0,
                winning_strategies INTEGER NOT NULL DEFAULT 0,
                losing_strategies INTEGER NOT NULL DEFAULT 0,
                total_pnl REAL NOT NULL DEFAULT 0,
                total_realized_loss REAL NOT NULL DEFAULT 0,
                max_drawdown REAL NOT NULL DEFAULT 0,
                broker_name TEXT,
                mode TEXT NOT NULL DEFAULT 'PAPER',
                paper_capital_remaining REAL
            )""",
            """CREATE TABLE IF NOT EXISTS fno_iv_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                index_name TEXT NOT NULL,
                atm_iv REAL NOT NULL,
                spot_close REAL NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS fno_spot_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                index_name TEXT NOT NULL,
                close_price REAL NOT NULL,
                log_return REAL NOT NULL DEFAULT 0
            )""",
            # --- F&O Adjustments table (Phase 4) ---
            """CREATE TABLE IF NOT EXISTS fno_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER,
                adjustment_time TEXT,
                trigger_reason TEXT,
                legs_closed TEXT,
                legs_opened TEXT,
                net_pnl_impact REAL,
                FOREIGN KEY(strategy_id) REFERENCES fno_strategies(id)
            )""",
            # --- Swing trading tables ---
            """CREATE TABLE IF NOT EXISTS swing_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                target_price REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                current_price REAL DEFAULT 0,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                pnl REAL DEFAULT 0,
                exit_price REAL DEFAULT 0,
                exit_date TEXT DEFAULT '',
                strategy_type TEXT DEFAULT '',
                confidence_score INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )""",
            # --- Positional trading tables ---
            """CREATE TABLE IF NOT EXISTS positional_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                target_price REAL NOT NULL,
                stop_loss_price REAL NOT NULL,
                current_price REAL DEFAULT 0,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                pnl REAL DEFAULT 0,
                exit_price REAL DEFAULT 0,
                exit_date TEXT DEFAULT '',
                strategy_type TEXT DEFAULT '',
                confidence_score INTEGER DEFAULT 0,
                sector TEXT DEFAULT '',
                market_cap TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )""",
        ]
        cursor = self.conn.cursor()
        for sql in statements:
            cursor.execute(sql)
        self.conn.commit()

    @staticmethod
    def _ist_now() -> str:
        """Return current time in IST as ISO 8601 string."""
        return datetime.now(IST).isoformat()

    # ── Store operations ──────────────────────────────────────────────

    def store_holdings(self, holdings: list[StockHolding], timestamp: datetime | None = None) -> None:
        """Store stock holdings snapshot with IST timestamp."""
        ts = timestamp.isoformat() if timestamp else self._ist_now()
        try:
            cursor = self.conn.cursor()
            for h in holdings:
                cursor.execute(
                    """INSERT INTO stock_holdings
                       (timestamp, name, isin, quantity, avg_buy_price, buy_value,
                        closing_price, closing_value, unrealised_pnl, holding_type,
                        pnl_percent, live_price, live_value, nse_symbol)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, h.name, h.isin, h.quantity, h.avg_buy_price, h.buy_value,
                     h.groww_closing_price, h.groww_closing_value, h.unrealised_pnl,
                     h.holding_type, h.pnl_percent, h.live_price, h.live_value, h.nse_symbol),
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to store stock holdings", exc_info=True)

    def store_mf_holdings(self, holdings: list[MFHolding], timestamp: datetime | None = None) -> None:
        """Store mutual fund holdings snapshot with IST timestamp."""
        ts = timestamp.isoformat() if timestamp else self._ist_now()
        try:
            cursor = self.conn.cursor()
            for h in holdings:
                cursor.execute(
                    """INSERT INTO mf_holdings
                       (timestamp, scheme_name, amc, category, sub_category, folio_no,
                        source, units, invested_value, current_value, returns_absolute,
                        xirr, returns_percent, current_nav, scheme_code)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, h.scheme_name, h.amc, h.category, h.sub_category, h.folio_no,
                     h.source, h.units, h.invested_value, h.current_value,
                     h.returns_absolute, h.xirr, h.returns_percent, h.current_nav, h.scheme_code),
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to store MF holdings", exc_info=True)

    def store_verdicts(self, verdicts: list[StockVerdict], timestamp: datetime | None = None) -> None:
        """Store AI stock verdicts with IST timestamp."""
        ts = timestamp.isoformat() if timestamp else self._ist_now()
        try:
            cursor = self.conn.cursor()
            for v in verdicts:
                cursor.execute(
                    """INSERT INTO stock_verdicts
                       (timestamp, name, isin, verdict, target_price, stop_loss,
                        rationale, tax_harvest_flag)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ts, v.name, v.isin, v.verdict, v.target_price, v.stop_loss,
                     v.rationale, int(v.tax_harvest_flag)),
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to store stock verdicts", exc_info=True)

    def store_mf_recommendations(self, recs: list[MFRecommendation], timestamp: datetime | None = None) -> None:
        """Store AI mutual fund recommendations with IST timestamp."""
        ts = timestamp.isoformat() if timestamp else self._ist_now()
        try:
            cursor = self.conn.cursor()
            for r in recs:
                cursor.execute(
                    """INSERT INTO mf_recommendations
                       (timestamp, scheme_name, recommendation, alternative_scheme, rationale)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ts, r.scheme_name, r.recommendation, r.alternative_scheme, r.rationale),
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to store MF recommendations", exc_info=True)

    # ── Query operations ──────────────────────────────────────────────

    def get_holdings_at(self, date: datetime) -> list[StockHolding]:
        """Retrieve stock holdings stored at a specific date (matches by date prefix)."""
        date_str = date.isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM stock_holdings WHERE timestamp = ?", (date_str,)
            )
            rows = cursor.fetchall()
            return [
                StockHolding(
                    name=row["name"], isin=row["isin"], quantity=row["quantity"],
                    avg_buy_price=row["avg_buy_price"], buy_value=row["buy_value"],
                    groww_closing_price=row["closing_price"],
                    groww_closing_value=row["closing_value"],
                    unrealised_pnl=row["unrealised_pnl"],
                    holding_type=row["holding_type"], pnl_percent=row["pnl_percent"],
                    live_price=row["live_price"], live_value=row["live_value"],
                    nse_symbol=row["nse_symbol"],
                )
                for row in rows
            ]
        except Exception:
            logger.error("Failed to query holdings", exc_info=True)
            return []

    def get_latest_verdicts(self) -> list[StockVerdict]:
        """Retrieve the most recent set of stock verdicts."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT DISTINCT timestamp FROM stock_verdicts ORDER BY timestamp DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                return []
            latest_ts = row["timestamp"]
            cursor.execute(
                "SELECT * FROM stock_verdicts WHERE timestamp = ?", (latest_ts,)
            )
            rows = cursor.fetchall()
            return [
                StockVerdict(
                    name=r["name"], isin=r["isin"], verdict=r["verdict"],
                    target_price=r["target_price"], stop_loss=r["stop_loss"],
                    rationale=r["rationale"],
                    tax_harvest_flag=bool(r["tax_harvest_flag"]),
                )
                for r in rows
            ]
        except Exception:
            logger.error("Failed to query latest verdicts", exc_info=True)
            return []

    # ── Intraday trade operations ────────────────────────────────────

    def insert_intraday_trade(self, **kwargs) -> int | None:
        """Insert a new intraday trade row. Returns the row id."""
        ts = kwargs.pop("timestamp", None) or self._ist_now()
        trade_date = kwargs.pop("trade_date", None) or datetime.now(IST).strftime("%Y-%m-%d")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO intraday_trades
                   (trade_date, timestamp, symbol, tradingsymbol, action, order_type,
                    product_type, quantity, price, trigger_price, broker_order_id,
                    broker_name, status, entry_price, exit_price, target_price,
                    stop_loss_price, confidence_score, strategy_type, rationale, pnl, mode)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade_date, ts,
                    kwargs.get("symbol", ""), kwargs.get("tradingsymbol", ""),
                    kwargs.get("action", "BUY"), kwargs.get("order_type", "LIMIT"),
                    kwargs.get("product_type", "INTRADAY"),
                    kwargs.get("quantity", 0), kwargs.get("price", 0),
                    kwargs.get("trigger_price", 0), kwargs.get("broker_order_id", ""),
                    kwargs.get("broker_name", ""), kwargs.get("status", "PENDING"),
                    kwargs.get("entry_price", 0), kwargs.get("exit_price"),
                    kwargs.get("target_price"), kwargs.get("stop_loss_price"),
                    kwargs.get("confidence_score"), kwargs.get("strategy_type"),
                    kwargs.get("rationale"), kwargs.get("pnl"),
                    kwargs.get("mode", "DRY_RUN"),
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            logger.error("Failed to insert intraday trade", exc_info=True)
            return None

    def update_intraday_trade(self, trade_id: int, **kwargs) -> None:
        """Update fields on an existing intraday trade row."""
        if not kwargs:
            return
        allowed = {
            "status", "exit_price", "pnl", "stop_loss_price",
            "broker_order_id", "quantity", "trigger_price", "timestamp",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [trade_id]
        try:
            self.conn.execute(
                f"UPDATE intraday_trades SET {set_clause} WHERE id = ?", values
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to update intraday trade %d", trade_id, exc_info=True)

    def get_trades_for_date(self, date_str: str) -> list[dict]:
        """Return all intraday trades for a given date as dicts."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM intraday_trades WHERE trade_date = ? ORDER BY id", (date_str,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query intraday trades", exc_info=True)
            return []

    def get_daily_realized_loss(self, date_str: str) -> float:
        """Sum of absolute negative P&L for the given date."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(ABS(pnl)), 0) FROM intraday_trades WHERE trade_date = ? AND pnl < 0",
                (date_str,),
            )
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            logger.error("Failed to query daily realized loss", exc_info=True)
            return 0.0

    def get_daily_summary(self, date_str: str) -> dict | None:
        """Return the daily summary row for a date, or None."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM intraday_daily_summary WHERE trade_date = ?", (date_str,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            logger.error("Failed to query daily summary", exc_info=True)
            return None

    def get_cumulative_pnl(self, start_date: str = "", end_date: str = "") -> float:
        """Sum of all intraday trade P&L between dates (inclusive)."""
        try:
            cursor = self.conn.cursor()
            if start_date and end_date:
                cursor.execute(
                    "SELECT COALESCE(SUM(pnl), 0) FROM intraday_trades WHERE trade_date BETWEEN ? AND ? AND pnl IS NOT NULL",
                    (start_date, end_date),
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(pnl), 0) FROM intraday_trades WHERE pnl IS NOT NULL"
                )
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            logger.error("Failed to query cumulative P&L", exc_info=True)
            return 0.0

    def upsert_daily_summary(self, trade_date: str, **kwargs) -> None:
        """Insert or update the daily summary for a date."""
        try:
            existing = self.get_daily_summary(trade_date)
            if existing:
                sets = ", ".join(f"{k} = ?" for k in kwargs)
                vals = list(kwargs.values()) + [trade_date]
                self.conn.execute(
                    f"UPDATE intraday_daily_summary SET {sets} WHERE trade_date = ?", vals
                )
            else:
                cols = ["trade_date"] + list(kwargs.keys())
                placeholders = ", ".join(["?"] * len(cols))
                vals = [trade_date] + list(kwargs.values())
                self.conn.execute(
                    f"INSERT INTO intraday_daily_summary ({', '.join(cols)}) VALUES ({placeholders})",
                    vals,
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to upsert daily summary", exc_info=True)

    def insert_audit_log(self, event_type: str, details_json: str = "", trade_id: int | None = None) -> None:
        """Insert an audit log entry."""
        try:
            self.conn.execute(
                "INSERT INTO intraday_audit_log (timestamp, event_type, details_json, trade_id) VALUES (?,?,?,?)",
                (self._ist_now(), event_type, details_json, trade_id),
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to insert audit log", exc_info=True)

    # ── F&O trade operations ─────────────────────────────────────────

    def insert_fno_trade(self, **kwargs) -> int | None:
        """Insert a new F&O trade row. Returns the row id."""
        ts = kwargs.pop("timestamp", None) or self._ist_now()
        trade_date = kwargs.pop("trade_date", None) or datetime.now(IST).strftime("%Y-%m-%d")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO fno_trades
                   (trade_date, timestamp, index_name, tradingsymbol, option_type,
                    strike_price, expiry_date, action, order_type, quantity, lots,
                    price, trigger_price, broker_order_id, broker_name, status,
                    entry_price, exit_price, pnl, mode, strategy_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade_date, ts,
                    kwargs.get("index_name", ""),
                    kwargs.get("tradingsymbol", ""),
                    kwargs.get("option_type", "CE"),
                    kwargs.get("strike_price", 0),
                    kwargs.get("expiry_date", ""),
                    kwargs.get("action", "BUY"),
                    kwargs.get("order_type", "LIMIT"),
                    kwargs.get("quantity", 0),
                    kwargs.get("lots", 1),
                    kwargs.get("price", 0),
                    kwargs.get("trigger_price", 0),
                    kwargs.get("broker_order_id", ""),
                    kwargs.get("broker_name", ""),
                    kwargs.get("status", "PENDING"),
                    kwargs.get("entry_price", 0),
                    kwargs.get("exit_price"),
                    kwargs.get("pnl"),
                    kwargs.get("mode", "PAPER"),
                    kwargs.get("strategy_id"),
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            logger.error("Failed to insert fno trade", exc_info=True)
            return None

    def update_fno_trade(self, trade_id: int, **kwargs) -> None:
        """Update fields on an existing F&O trade row."""
        if not kwargs:
            return
        allowed = {
            "status", "exit_price", "pnl", "trigger_price",
            "broker_order_id", "quantity", "timestamp",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [trade_id]
        try:
            self.conn.execute(
                f"UPDATE fno_trades SET {set_clause} WHERE id = ?", values
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to update fno trade %d", trade_id, exc_info=True)

    def insert_fno_strategy(self, **kwargs) -> int | None:
        """Insert a new F&O strategy row. Returns the row id."""
        ts = kwargs.pop("timestamp", None) or self._ist_now()
        trade_date = kwargs.pop("trade_date", None) or datetime.now(IST).strftime("%Y-%m-%d")
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO fno_strategies
                   (trade_date, timestamp, strategy_type, index_name, legs_json,
                    net_premium, max_profit, max_loss, net_delta, net_gamma,
                    net_theta, net_vega, status, entry_time, exit_time,
                    realized_pnl, mode, confidence_score, confluence_score, rationale)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade_date, ts,
                    kwargs.get("strategy_type", ""),
                    kwargs.get("index_name", ""),
                    kwargs.get("legs_json", "[]"),
                    kwargs.get("net_premium", 0),
                    kwargs.get("max_profit", 0),
                    kwargs.get("max_loss", 0),
                    kwargs.get("net_delta", 0),
                    kwargs.get("net_gamma", 0),
                    kwargs.get("net_theta", 0),
                    kwargs.get("net_vega", 0),
                    kwargs.get("status", "PENDING"),
                    kwargs.get("entry_time"),
                    kwargs.get("exit_time"),
                    kwargs.get("realized_pnl"),
                    kwargs.get("mode", "PAPER"),
                    kwargs.get("confidence_score"),
                    kwargs.get("confluence_score"),
                    kwargs.get("rationale"),
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            logger.error("Failed to insert fno strategy", exc_info=True)
            return None

    def update_fno_strategy(self, strategy_id: int, **kwargs) -> None:
        """Update fields on an existing F&O strategy row."""
        if not kwargs:
            return
        allowed = {
            "status", "exit_time", "realized_pnl", "net_delta", "net_gamma",
            "net_theta", "net_vega", "legs_json", "timestamp",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [strategy_id]
        try:
            self.conn.execute(
                f"UPDATE fno_strategies SET {set_clause} WHERE id = ?", values
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to update fno strategy %d", strategy_id, exc_info=True)

    def get_fno_trades_for_date(self, date_str: str) -> list[dict]:
        """Return all F&O trades for a given date as dicts."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_trades WHERE trade_date = ? ORDER BY id",
                (date_str,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query fno trades", exc_info=True)
            return []

    def get_fno_strategies_for_date(self, date_str: str) -> list[dict]:
        """Return all F&O strategies for a given date as dicts."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_strategies WHERE trade_date = ? ORDER BY id",
                (date_str,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query fno strategies", exc_info=True)
            return []

    def get_fno_daily_summary(self, date_str: str) -> dict | None:
        """Return the F&O daily summary row for a date, or None."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_daily_summary WHERE trade_date = ?",
                (date_str,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            logger.error("Failed to query fno daily summary", exc_info=True)
            return None

    def upsert_fno_daily_summary(self, trade_date: str, **kwargs) -> None:
        """Insert or update the F&O daily summary for a date."""
        try:
            existing = self.get_fno_daily_summary(trade_date)
            if existing:
                sets = ", ".join(f"{k} = ?" for k in kwargs)
                vals = list(kwargs.values()) + [trade_date]
                self.conn.execute(
                    f"UPDATE fno_daily_summary SET {sets} WHERE trade_date = ?",
                    vals,
                )
            else:
                cols = ["trade_date"] + list(kwargs.keys())
                placeholders = ", ".join(["?"] * len(cols))
                vals = [trade_date] + list(kwargs.values())
                self.conn.execute(
                    f"INSERT INTO fno_daily_summary ({', '.join(cols)}) VALUES ({placeholders})",
                    vals,
                )
            self.conn.commit()
        except Exception:
            logger.error("Failed to upsert fno daily summary", exc_info=True)

    def get_fno_cumulative_pnl(self, start_date: str = "", end_date: str = "") -> float:
        """Sum of all F&O strategy realized P&L between dates (inclusive)."""
        try:
            cursor = self.conn.cursor()
            if start_date and end_date:
                cursor.execute(
                    "SELECT COALESCE(SUM(realized_pnl), 0) FROM fno_strategies "
                    "WHERE trade_date BETWEEN ? AND ? AND realized_pnl IS NOT NULL",
                    (start_date, end_date),
                )
            else:
                cursor.execute(
                    "SELECT COALESCE(SUM(realized_pnl), 0) FROM fno_strategies "
                    "WHERE realized_pnl IS NOT NULL"
                )
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            logger.error("Failed to query fno cumulative P&L", exc_info=True)
            return 0.0

    def get_fno_daily_realized_loss(self, date_str: str) -> float:
        """Sum of absolute negative realized P&L for F&O strategies on a date."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(ABS(realized_pnl)), 0) FROM fno_strategies "
                "WHERE trade_date = ? AND realized_pnl < 0",
                (date_str,),
            )
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            logger.error("Failed to query fno daily realized loss", exc_info=True)
            return 0.0

    def get_paper_trading_history(self, weeks: int = 3) -> list[dict]:
        """Return paper trading daily summaries for the last N weeks."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_daily_summary WHERE mode = 'PAPER' "
                "ORDER BY trade_date DESC LIMIT ?",
                (weeks * 5,),  # ~5 trading days per week
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query paper trading history", exc_info=True)
            return []

    def insert_fno_iv_history(
        self, date: str, index_name: str, atm_iv: float, spot_close: float,
    ) -> None:
        """Insert a daily ATM IV record for IV Percentile computation."""
        try:
            self.conn.execute(
                "INSERT INTO fno_iv_history (date, index_name, atm_iv, spot_close) "
                "VALUES (?,?,?,?)",
                (date, index_name, atm_iv, spot_close),
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to insert fno iv history", exc_info=True)

    def get_fno_iv_history(self, index_name: str, days: int = 252) -> list[dict]:
        """Return the last N days of ATM IV history for an index."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_iv_history WHERE index_name = ? "
                "ORDER BY date DESC LIMIT ?",
                (index_name, days),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query fno iv history", exc_info=True)
            return []

    def insert_fno_spot_history(
        self, date: str, index_name: str, close_price: float, log_return: float,
    ) -> None:
        """Insert a daily spot close record for Realized Volatility computation."""
        try:
            self.conn.execute(
                "INSERT INTO fno_spot_history (date, index_name, close_price, log_return) "
                "VALUES (?,?,?,?)",
                (date, index_name, close_price, log_return),
            )
            self.conn.commit()
        except Exception:
            logger.error("Failed to insert fno spot history", exc_info=True)

    def get_fno_spot_history(self, index_name: str, days: int = 252) -> list[dict]:
        """Return the last N days of spot history for an index."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM fno_spot_history WHERE index_name = ? "
                "ORDER BY date DESC LIMIT ?",
                (index_name, days),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            logger.error("Failed to query fno spot history", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Swing Trading
    # ------------------------------------------------------------------

    def insert_swing_trade(self, pos=None, **kwargs) -> int | None:
        """Insert a swing trade position. Accepts object or keyword args."""
        try:
            if pos is not None:
                # Object-style call (legacy)
                symbol = getattr(pos, "nse_symbol", getattr(pos, "symbol", ""))
                entry_price = pos.entry_price
                entry_date = getattr(pos, "entry_date", self._ist_now()[:10])
                target_price = pos.target_price
                stop_loss_price = pos.stop_loss_price
                quantity = pos.quantity
                status = getattr(pos, "status", "OPEN")
                strategy_type = getattr(pos, "strategy_type", "")
                confidence_score = getattr(pos, "confidence_score", 0)
            else:
                # Keyword-style call (executor uses this)
                symbol = kwargs.get("nse_symbol", kwargs.get("symbol", ""))
                entry_price = kwargs.get("entry_price", 0)
                entry_date = kwargs.get("entry_date", self._ist_now()[:10])
                target_price = kwargs.get("target_price", 0)
                stop_loss_price = kwargs.get("stop_loss_price", 0)
                quantity = kwargs.get("quantity", 0)
                status = kwargs.get("status", "OPEN")
                strategy_type = kwargs.get("strategy_type", "")
                confidence_score = kwargs.get("confidence_score", 0)

            cursor = self.conn.execute(
                """INSERT INTO swing_trades
                   (symbol, entry_price, entry_date, target_price, stop_loss_price,
                    quantity, status, strategy_type, confidence_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, entry_price, entry_date, target_price, stop_loss_price,
                 quantity, status, strategy_type, confidence_score, self._ist_now()),
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            logger.error("Failed to insert swing trade", exc_info=True)
            return None

    def get_open_swing_trades(self) -> list:
        """Get open swing trades as list of dicts. Used by monitor."""
        return self.get_swing_positions(status="OPEN")

    def get_swing_positions(self, status: str | None = None) -> list:
        """Get swing positions, optionally filtered by status. Returns list of dicts."""
        try:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM swing_trades WHERE status = ? ORDER BY entry_date DESC", (status,)
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM swing_trades ORDER BY entry_date DESC"
                ).fetchall()

            return [dict(row) for row in rows]
        except Exception:
            logger.error("Failed to get swing positions", exc_info=True)
            return []

    def update_swing_trade(self, trade_id: int, **kwargs) -> None:
        """Update a swing trade."""
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [trade_id]
        try:
            self.conn.execute(f"UPDATE swing_trades SET {sets} WHERE id = ?", vals)
            self.conn.commit()
        except Exception:
            logger.error("Failed to update swing trade %d", trade_id, exc_info=True)

    # ------------------------------------------------------------------
    # Positional Trading
    # ------------------------------------------------------------------

    def insert_positional_trade(self, pos) -> int | None:
        """Insert a positional trade position."""
        try:
            cursor = self.conn.execute(
                """INSERT INTO positional_trades
                   (symbol, entry_price, entry_date, target_price, stop_loss_price,
                    quantity, status, strategy_type, confidence_score, sector, market_cap, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pos.nse_symbol, pos.entry_price, pos.entry_date,
                    pos.target_price, pos.stop_loss_price, pos.quantity,
                    pos.status, pos.strategy_type, pos.confidence_score,
                    pos.sector, pos.market_cap, self._ist_now(),
                ),
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            logger.error("Failed to insert positional trade", exc_info=True)
            return None

    def get_positional_positions(self, status: str | None = None) -> list:
        """Get positional positions, optionally filtered by status."""
        from positional.models import PositionalPosition
        try:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM positional_trades WHERE status = ? ORDER BY entry_date DESC", (status,)
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM positional_trades ORDER BY entry_date DESC"
                ).fetchall()

            positions = []
            for row in rows:
                r = dict(row)
                positions.append(PositionalPosition(
                    id=r.get("id", 0),
                    nse_symbol=r.get("symbol", ""),
                    entry_price=float(r.get("entry_price", 0)),
                    entry_date=r.get("entry_date", ""),
                    target_price=float(r.get("target_price", 0)),
                    stop_loss_price=float(r.get("stop_loss_price", 0)),
                    current_price=float(r.get("current_price", 0)),
                    quantity=int(r.get("quantity", 0)),
                    status=r.get("status", "OPEN"),
                    pnl=float(r.get("pnl", 0)),
                    exit_price=float(r.get("exit_price", 0)),
                    exit_date=r.get("exit_date", ""),
                    strategy_type=r.get("strategy_type", ""),
                    confidence_score=int(r.get("confidence_score", 0)),
                    sector=r.get("sector", ""),
                    market_cap=r.get("market_cap", ""),
                ))
            return positions
        except Exception:
            logger.error("Failed to get positional positions", exc_info=True)
            return []

    def update_positional_trade(self, trade_id: int, **kwargs) -> None:
        """Update a positional trade."""
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [trade_id]
        try:
            self.conn.execute(f"UPDATE positional_trades SET {sets} WHERE id = ?", vals)
            self.conn.commit()
        except Exception:
            logger.error("Failed to update positional trade %d", trade_id, exc_info=True)

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
