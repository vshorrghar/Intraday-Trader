#!/usr/bin/env python3
"""Idempotent migration: add days_held column to swing_trades.

The swing monitor passes days_held to update_swing_trade, but the column does
not exist, so the whitelist in db_manager currently drops it. Adding the column
lets hold-time persist (WIN_RATE_TRACKING hold-time analysis needs it).

Safe to run repeatedly: skips any DB that already has the column. Does not
touch any other column or row. Read-modify at schema level only.

Usage: python3 scripts/migrate_add_days_held.py [db1 db2 ...]
       (defaults to all database/*.db)
"""
from __future__ import annotations

import glob
import sqlite3
import sys


def has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def main() -> None:
    dbs = sys.argv[1:] or sorted(glob.glob("database/*.db"))
    if not dbs:
        print("no databases found")
        return

    for db in dbs:
        try:
            conn = sqlite3.connect(db)
            if not table_exists(conn, "swing_trades"):
                print(f"{db}: no swing_trades table — skip")
                conn.close()
                continue
            if has_column(conn, "swing_trades", "days_held"):
                print(f"{db}: days_held already present — skip")
                conn.close()
                continue
            conn.execute("ALTER TABLE swing_trades ADD COLUMN days_held INTEGER DEFAULT 0")
            conn.commit()
            conn.close()
            print(f"{db}: added days_held column")
        except Exception as e:  # noqa: BLE001
            print(f"{db}: ERROR {e}")


if __name__ == "__main__":
    main()
