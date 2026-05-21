#!/usr/bin/env python3
"""Build daily audit JSON per profile.

Merges Dhan API truth + DB metadata into a comprehensive per-day audit file.
Output: dashboard/api/v2/{profile}/audit/{date}.json

Usage:
    python scripts/build_daily_audit.py --profile vishal-live --date 2026-05-20
    python scripts/build_daily_audit.py --profile vishal-live  # defaults to today
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

# Phase definitions per BUSINESS_DOC.md
PHASES = [
    {"phase": 1, "name": "Validation", "capital": 15000, "trades_needed": 50},
    {"phase": 2, "name": "Scaling", "capital": 50000, "trades_needed": 100},
    {"phase": 3, "name": "Growth", "capital": 200000, "trades_needed": 200},
    {"phase": 4, "name": "Maturity", "capital": 500000, "trades_needed": 500},
    {"phase": 5, "name": "Full Deploy", "capital": 2500000, "trades_needed": None},
]

EXCLUDED_STATUSES = {"REJECTED", "CANCELLED", "FAILED", "ABANDONED", "PENDING"}


def db_path(profile):
    return Path(__file__).parent.parent / "database" / f"{profile}.db"


def dhan_live_path(profile):
    return Path(__file__).parent.parent / "dashboard" / "api" / profile / "dhan_live.json"


def output_dir(profile):
    return Path(__file__).parent.parent / "dashboard" / "api" / "v2" / profile / "audit"


def fetch_db_trades(profile, date):
    """Fetch trades from DB for a given date."""
    p = db_path(profile)
    if not p.exists():
        return []
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT id, trade_date, timestamp, symbol, tradingsymbol, action,
                   quantity, entry_price, exit_price, target_price, stop_loss_price,
                   status, pnl, confidence_score, strategy_type, rationale, mode
            FROM intraday_trades
            WHERE trade_date = ? AND action IN ('BUY', 'SELL')
            ORDER BY timestamp
        """, (date,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def fetch_dhan_data(profile, date):
    """Load Dhan live JSON if available and from the correct date."""
    p = dhan_live_path(profile)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
        # Check if dhan_live.json is from the requested date
        ts = data.get("timestamp", "")
        if date not in ts:
            return None  # Stale data from different day
        return data
    except Exception:
        return None


def fetch_all_profitable_trades(profile):
    """Count all real-money trades for phase calculation."""
    p = db_path(profile)
    if not p.exists():
        return 0, 0
    con = sqlite3.connect(str(p))
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM intraday_trades
            WHERE action IN ('BUY', 'SELL')
              AND status NOT IN ('REJECTED', 'CANCELLED', 'FAILED', 'ABANDONED', 'PENDING', 'OPEN')
              AND mode = 'LIVE'
        """)
        row = cur.fetchone()
        return row[0] or 0, row[1] or 0
    except Exception:
        return 0, 0
    finally:
        con.close()


def compute_phase(total_trades, wins):
    """Determine current phase and progress."""
    for phase in PHASES:
        needed = phase["trades_needed"]
        if needed is None or total_trades < needed:
            return {
                "current_phase": phase["phase"],
                "current_phase_name": phase["name"],
                "trades_this_phase": total_trades,
                "trades_needed_next": needed,
                "trades_remaining": (needed - total_trades) if needed else 0,
                "win_count": wins,
                "win_rate": round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
                "phase_progress": f"{total_trades}/{needed} trades to Phase {phase['phase'] + 1}" if needed else "Final phase",
            }
    return {"current_phase": 5, "current_phase_name": "Full Deploy", "phase_progress": "Final phase"}


def estimate_charges(entry_price, quantity):
    """Estimate round-trip charges for intraday equity trade.

    Approximation: Rs.50 flat + 0.05% of trade value.
    Real breakdown: brokerage Rs.40, STT 0.025% sell, exchange 0.00325%,
    GST 18% of brokerage, stamp 0.003% buy.
    """
    trade_value = entry_price * quantity
    return round(50 + trade_value * 0.0005, 2)


def build_audit(profile, date):
    """Build the complete audit JSON for a profile+date."""
    db_trades = fetch_db_trades(profile, date)
    dhan_data = fetch_dhan_data(profile, date)

    now = datetime.now(IST)

    # Determine direction for each trade
    trades_out = []
    for t in db_trades:
        action = t.get("action", "BUY")
        direction = "SHORT" if action == "SELL" else "LONG"
        entry_price = float(t.get("entry_price") or 0)
        exit_price = float(t.get("exit_price") or 0)
        quantity = int(t.get("quantity") or 0)
        pnl_db = float(t.get("pnl") or 0)

        # Compute charges
        charges = estimate_charges(entry_price, quantity) if entry_price > 0 else 0

        # Check Dhan for qty drift
        qty_actual_dhan = quantity  # default: assume match
        qty_drift = 0
        qty_drift_reason = ""
        pnl_dhan = pnl_db  # default: trust DB

        if dhan_data and dhan_data.get("positions"):
            symbol = t.get("tradingsymbol", "")
            for pos in dhan_data["positions"]:
                if pos.get("tradingSymbol", "").upper() == symbol.upper():
                    # Dhan shows total buy+sell qty for the day
                    dhan_buy = pos.get("buyQty", 0)
                    dhan_sell = pos.get("sellQty", 0)
                    # For LONG: our qty should match buyQty
                    # For SHORT: our qty should match sellQty (entry side)
                    if direction == "LONG":
                        qty_actual_dhan = dhan_buy
                    else:
                        qty_actual_dhan = dhan_sell

                    qty_drift = qty_actual_dhan - quantity
                    if qty_drift != 0:
                        qty_drift_reason = f"Bug A - Dhan shows {qty_actual_dhan} vs DB {quantity}"

                    pnl_dhan = float(pos.get("realizedProfit", pnl_db))
                    break

        # R:R calculation (direction-aware)
        target = float(t.get("target_price") or 0)
        sl = float(t.get("stop_loss_price") or 0)
        if direction == "LONG" and entry_price > 0 and sl > 0 and (entry_price - sl) > 0:
            rr = round((target - entry_price) / (entry_price - sl), 1)
        elif direction == "SHORT" and entry_price > 0 and sl > 0 and (sl - entry_price) > 0:
            rr = round((entry_price - target) / (sl - entry_price), 1)
        else:
            rr = 0

        # Determine outcome
        status = t.get("status", "")
        won = None
        if status in ("TARGET_HIT", "PARTIAL_BOOKED"):
            won = True
        elif status == "STOPPED_OUT":
            won = True if pnl_db > 0 else False
        elif status in ("FORCE_EXITED", "CLOSED"):
            won = True if pnl_db > 0 else (False if pnl_db < 0 else None)

        trades_out.append({
            "trade_id": t.get("id"),
            "symbol": t.get("symbol", ""),
            "tradingsymbol": t.get("tradingsymbol", ""),
            "direction": direction,
            "action_db": action,
            "entry_price": entry_price,
            "exit_price": exit_price if exit_price > 0 else None,
            "qty_intended": quantity,
            "qty_actual_dhan": qty_actual_dhan,
            "qty_drift": qty_drift,
            "qty_drift_reason": qty_drift_reason,
            "target_price": target,
            "stop_loss_price": sl,
            "rr_planned": rr,
            "confidence": t.get("confidence_score"),
            "strategy_type": t.get("strategy_type", ""),
            "rationale_llm": t.get("rationale", ""),
            "outcome": status,
            "outcome_reason": "",
            "duration_min": None,
            "won": won,
            "pnl_db": round(pnl_db, 2),
            "pnl_dhan": round(pnl_dhan, 2),
            "charges_estimated": charges,
            "pnl_net_estimated": round(pnl_dhan - charges, 2),
            "tags": _build_tags(direction, t, qty_drift),
        })

    # Summary
    counted = trades_out
    gross_pnl_db = sum(t["pnl_db"] for t in counted)
    gross_pnl_dhan = sum(t["pnl_dhan"] for t in counted)
    total_charges = sum(t["charges_estimated"] for t in counted)
    capital_deployed = sum(t["entry_price"] * t["qty_intended"] for t in counted)
    drift_amount = abs(gross_pnl_dhan - gross_pnl_db)

    winners = len([t for t in counted if t["won"] is True])
    losers = len([t for t in counted if t["won"] is False])

    # Phase calculation
    total_real_trades, total_wins = fetch_all_profitable_trades(profile)
    phase_info = compute_phase(total_real_trades, total_wins)

    # Dhan summary
    dhan_summary = {}
    if dhan_data:
        dhan_summary = dhan_data.get("summary", {})

    audit = {
        "profile": profile,
        "date": date,
        "generated_at": now.isoformat(),
        "source": "merged" if dhan_data else "db",
        "staleness_seconds": 0,

        "summary": {
            "trades_attempted": len(counted),
            "trades_executed": len(counted),
            "trades_won": winners,
            "trades_lost": losers,
            "gross_pnl_db": round(gross_pnl_db, 2),
            "gross_pnl_dhan": round(gross_pnl_dhan, 2),
            "estimated_charges": round(total_charges, 2),
            "net_pnl_estimated": round(gross_pnl_dhan - total_charges, 2),
            "drift_vs_db": "OK" if drift_amount < 1 else f"DRIFT Rs.{drift_amount:.2f}",
            "drift_amount_rs": round(drift_amount, 2),
            "capital_deployed_max": round(capital_deployed, 0),
            "dhan_available_balance": dhan_summary.get("available_balance"),
            "phase": phase_info["current_phase"],
            "phase_progress": phase_info["phase_progress"],
        },

        "trades": trades_out,

        "phase_status": phase_info,

        "dhan_raw_summary": dhan_summary if dhan_data else None,

        "bugs_observed": _detect_bugs(trades_out),
    }

    return audit


def _build_tags(direction, trade, qty_drift):
    """Build tags for a trade."""
    tags = [direction.lower()]
    if trade.get("strategy_type"):
        tags.append(trade["strategy_type"].lower())
    if qty_drift != 0:
        tags.append("drift_detected")
    status = trade.get("status", "")
    if status == "FORCE_EXITED":
        tags.append("force_exit")
    return tags


def _detect_bugs(trades):
    """Detect known bug patterns in today's trades."""
    bugs = []
    for t in trades:
        if t["qty_drift"] != 0:
            bugs.append(f"Qty drift on {t['tradingsymbol']}: DB={t['qty_intended']}, Dhan={t['qty_actual_dhan']}")
    return bugs


def main():
    parser = argparse.ArgumentParser(description="Build daily audit JSON")
    parser.add_argument("--profile", required=True, help="Profile name")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    date = args.date or datetime.now(IST).strftime("%Y-%m-%d")

    audit = build_audit(args.profile, date)

    # Write output
    out_dir = output_dir(args.profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date}.json"

    with open(out_file, "w") as f:
        json.dump(audit, f, indent=2, default=str)

    print(f"Audit written: {out_file}")
    print(f"  Trades: {audit['summary']['trades_attempted']}")
    print(f"  P&L (Dhan): Rs.{audit['summary']['gross_pnl_dhan']}")
    print(f"  P&L (DB):   Rs.{audit['summary']['gross_pnl_db']}")
    print(f"  Drift:      {audit['summary']['drift_vs_db']}")
    print(f"  Phase:      {audit['summary']['phase']} ({audit['summary']['phase_progress']})")


if __name__ == "__main__":
    main()
