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

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
