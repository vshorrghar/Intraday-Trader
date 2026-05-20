"""Shared library for status scripts (live_status, eod_summary)."""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

EXCLUDED_STATUSES = {"REJECTED", "CANCELLED", "FAILED", "ABANDONED", "PENDING"}
OPEN_STATES = {"OPEN", "PARTIAL_BOOKED"}

PROFILES_LIVE = [
    {"name": "vishal-live", "label": "Real Rs.15K", "capital": 15000, "max_trades": 3, "loss_limit": 900},
    {"name": "neha-live", "label": "Real Rs.10K", "capital": 10000, "max_trades": 3, "loss_limit": 900},
]
PROFILES_PAPER = [
    {"name": "vishal", "label": "Paper Rs.3L", "capital": 300000, "max_trades": 6, "loss_limit": 9000},
    {"name": "neha", "label": "Paper Rs.3L", "capital": 300000, "max_trades": 6, "loss_limit": 9000},
]
ALL_PROFILES = PROFILES_LIVE + PROFILES_PAPER


def get_today():
    return datetime.now().strftime("%Y-%m-%d")


def db_path(profile):
    p = Path(__file__).parent.parent / "database" / f"{profile}.db"
    
    # Bug 6 fix: neha-live runs on NEW EC2. OLD EC2 pulls from S3.
    # Detect if we are on OLD EC2 by checking hostname.
    if profile == "neha-live":
        import socket, subprocess
        hostname = socket.gethostname()
        if "172-31-32" in hostname:  # OLD EC2 IP range
            try:
                pull_script = Path(__file__).parent / "pull_neha_live_db.sh"
                if pull_script.exists():
                    subprocess.run(
                        ["bash", str(pull_script)],
                        timeout=10, capture_output=True
                    )
            except Exception:
                pass  # Use stale local copy if pull fails
    
    return p


def fetch_trades(profile, date):
    p = db_path(profile)
    if not p.exists():
        return []
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT timestamp, tradingsymbol, quantity, entry_price, exit_price,
                   status, pnl, target_price, stop_loss_price, action
            FROM intraday_trades
            WHERE trade_date = ? AND action IN ('BUY', 'SELL')
            ORDER BY timestamp
        """, (date,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def fetch_fno(profile, date):
    p = db_path(profile)
    if not p.exists():
        return {"strategies": [], "trade_count": 0, "pnl": 0}
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    out = {"strategies": [], "trade_count": 0, "pnl": 0}
    try:
        cur.execute("SELECT * FROM fno_strategies WHERE date(created_at) = ?", (date,))
        out["strategies"] = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    try:
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM fno_trades WHERE trade_date = ?",
            (date,)
        )
        row = cur.fetchone()
        out["trade_count"] = row[0] or 0
        out["pnl"] = float(row[1] or 0)
    except Exception:
        pass
    con.close()
    return out


def fetch_top_movers(profile, date):
    p = db_path(profile)
    if not p.exists():
        return []
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT * FROM daily_top_performers WHERE date = ?
            ORDER BY change_pct DESC LIMIT 20
        """, (date,))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        con.close()


def trade_is_counted(trade):
    status = (trade.get("status") or "").upper()
    return status not in EXCLUDED_STATUSES


def trade_is_open(trade):
    status = (trade.get("status") or "").upper()
    return status in OPEN_STATES


def fmt_pnl(pnl):
    if pnl is None:
        return "Rs.--", "--"
    pnl = float(pnl)
    emoji = "[+]" if pnl > 0 else ("[-]" if pnl < 0 else "[=]")
    sign = "+" if pnl >= 0 else "-"
    return f"{sign}Rs.{abs(pnl):,.2f}", emoji


def stats_for_profile(profile, date):
    trades = fetch_trades(profile, date)
    counted = [t for t in trades if trade_is_counted(t)]
    open_t = [t for t in trades if trade_is_open(t)]

    total_pnl = sum(float(t.get("pnl") or 0) for t in counted)
    capital_used = sum(
        float(t.get("entry_price") or 0) * int(t.get("quantity") or 0)
        for t in counted
    )
    realized_loss = abs(sum(float(t.get("pnl") or 0) for t in counted if (t.get("pnl") or 0) < 0))
    winners = len([t for t in counted if (t.get("pnl") or 0) > 0])
    losers = len([t for t in counted if (t.get("pnl") or 0) < 0])

    return {
        "trades": trades,
        "counted": counted,
        "open": open_t,
        "trade_count": len(counted),
        "open_count": len(open_t),
        "capital_used": capital_used,
        "realized_loss": realized_loss,
        "total_pnl": total_pnl,
        "winners": winners,
        "losers": losers,
    }

