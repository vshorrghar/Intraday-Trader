#!/usr/bin/env python3
"""
Swing paper trading daily status report.

Reads swing_trades from DB and prints a human-readable summary.
Designed to run via cron at 8:00 AM IST and output to /tmp/swing_status_today.txt.

Usage:
    .venv/bin/python scripts/swing_paper_status.py --profile vishal
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))


def get_db_path(profile: str) -> Path:
    return Path(__file__).parent.parent / "database" / f"{profile}.db"


def get_swing_trades(db_path: Path) -> list[dict]:
    """Load all swing trades from DB. Returns empty list if table missing."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM swing_trades ORDER BY entry_date DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def print_status(profile: str):
    now = datetime.now(IST)
    today_str = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    print(f"SWING PAPER STATUS — {profile} — {now.strftime('%Y-%m-%d %H:%M IST')}")
    print("=" * 56)
    print()

    db_path = get_db_path(profile)
    if not db_path.exists():
        print(f"  Database not found: {db_path}")
        print("  No positions yet. Waiting for first scan to place trades.")
        print()
        _print_footer(profile, 0, 0, 0)
        return

    trades = get_swing_trades(db_path)
    if not trades:
        print("  No swing trades in database yet.")
        print("  First scan runs at 4:30 PM IST. Trades will appear after that.")
        print()
        _print_footer(profile, 0, 0, 0)
        return

    # Separate open vs closed
    open_positions = [t for t in trades if t.get("status") == "OPEN"]
    closed_recent = [t for t in trades
                     if t.get("status") != "OPEN"
                     and t.get("exit_date", "") >= week_ago]
    all_closed = [t for t in trades if t.get("status") != "OPEN"]

    # Open positions
    print(f"  Open positions: {len(open_positions)}")
    if open_positions:
        for p in open_positions:
            symbol = p.get("symbol", "?")
            entry_date = p.get("entry_date", "?")
            entry_price = p.get("entry_price", 0)
            # Days held
            try:
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
                days_held = (now.replace(tzinfo=None) - entry_dt).days
            except (ValueError, TypeError):
                days_held = 0

            # Current price (if available)
            current = p.get("current_price", 0) or p.get("ltp", 0)
            if current and entry_price:
                pnl = (current - entry_price) * p.get("quantity", 1)
                pnl_str = f"₹{pnl:+.0f}"
            else:
                pnl_str = "price unavailable"

            qty = p.get("quantity", 0)
            print(f"    {symbol}: bought {entry_date} @ ₹{entry_price:.2f} "
                  f"qty={qty}, days={days_held}, pnl={pnl_str}")
    else:
        print("    (none)")
    print()

    # Closed positions (last 7 days)
    print(f"  Closed positions (last 7 days): {len(closed_recent)}")
    if closed_recent:
        for t in closed_recent[:10]:  # Cap at 10
            symbol = t.get("symbol", "?")
            days_held = t.get("days_held", 0)
            if not days_held:
                try:
                    entry_dt = datetime.strptime(t.get("entry_date", ""), "%Y-%m-%d")
                    exit_dt = datetime.strptime(t.get("exit_date", ""), "%Y-%m-%d")
                    days_held = (exit_dt - entry_dt).days
                except (ValueError, TypeError):
                    days_held = 0
            exit_reason = t.get("status", "CLOSED")
            pnl = t.get("pnl", 0) or 0
            print(f"    {symbol}: held {days_held} days, exit {exit_reason}, pnl=₹{pnl:+.0f}")
    else:
        print("    (none)")
    print()

    # Cumulative P&L
    cum_pnl = sum(t.get("pnl", 0) or 0 for t in all_closed)
    deployed = sum(
        (p.get("entry_price", 0) * p.get("quantity", 0)) for p in open_positions
    )
    capital_limit = 50000  # Default; could read from config

    _print_footer(profile, cum_pnl, deployed, len(open_positions))


def _print_footer(profile: str, cum_pnl: float, deployed: float, open_count: int):
    """Print the summary footer."""
    capital_limit = 50000
    max_positions = 8

    print(f"  Cumulative paper P&L: ₹{cum_pnl:+,.0f}")
    print(f"  Capital deployed: ₹{deployed:,.0f} / ₹{capital_limit:,.0f}")
    print(f"  Trades open: {open_count} / {max_positions} max")
    print()

    # Backtest reference
    print("  --- Backtest reference (Phase 4.5) ---")
    print("  Expected: ~9 trades/month, 41.8% WR, PF 1.84")
    print("  Kill signal: WR < 30% with 5+ trades at Day 30")
    print("  Ship-live signal: WR >= 42% AND PF >= 1.7 at Day 30")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Swing paper status report")
    parser.add_argument("--profile", default="vishal", help="Profile name")
    args = parser.parse_args()

    print_status(args.profile)


if __name__ == "__main__":
    main()
