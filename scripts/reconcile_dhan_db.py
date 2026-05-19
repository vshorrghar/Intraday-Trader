#!/usr/bin/env python3
"""
reconcile_dhan_db.py — Compare Dhan API truth vs DB records.

USAGE:
  python scripts/reconcile_dhan_db.py --profile vishal-live
  python scripts/reconcile_dhan_db.py --profile vishal-live --date 2026-05-19

OUTPUT:
  dashboard/api/{profile}/reconciliation_report.json
  Human-readable summary to stdout.

Exit code 0 if drift < Rs.5, 1 if drift > Rs.5.

Does NOT modify DB. Reports only.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Indian Standard Time
IST = timezone(timedelta(hours=5, minutes=30))

DRIFT_THRESHOLD = 5.0  # Rupees


def load_dhan_truth(profile):
    """Load Dhan API positions from sync_dhan_live.py output."""
    path = Path(f"dashboard/api/{profile}/dhan_live.json")
    if not path.exists():
        print(f"ERROR: {path} not found. Run scripts/sync_dhan_live.py first.")
        sys.exit(2)
    with open(path) as f:
        data = json.load(f)
    
    positions_by_symbol = {}
    for pos in data.get("positions", []):
        sym = pos.get("tradingSymbol", "")
        if not sym:
            continue
        # Use realized P&L for closed positions
        positions_by_symbol[sym] = {
            "symbol": sym,
            "buy_qty": pos.get("buyQty", 0),
            "sell_qty": pos.get("sellQty", 0),
            "buy_avg": pos.get("buyAvg", 0.0),
            "sell_avg": pos.get("sellAvg", 0.0),
            "realized_pnl": pos.get("realizedProfit", 0.0),
            "unrealized_pnl": pos.get("unrealizedProfit", 0.0),
            "total_pnl": pos.get("realizedProfit", 0.0) + pos.get("unrealizedProfit", 0.0),
            "position_type": pos.get("positionType", ""),
        }
    
    return {
        "positions": positions_by_symbol,
        "total_pnl": data.get("summary", {}).get("total_pnl", 0.0),
        "total_positions": data.get("summary", {}).get("total_positions_today", 0),
        "available_balance": data.get("summary", {}).get("available_balance", 0.0),
        "timestamp": data.get("timestamp", ""),
    }


def load_db_trades(profile, trade_date):
    """Load DB trades for given profile and date. Map by tradingsymbol."""
    db_path = Path(f"database/{profile}.db")
    if not db_path.exists():
        print(f"ERROR: {db_path} not found.")
        sys.exit(2)
    
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT id, symbol, tradingsymbol, action, quantity, entry_price,
               exit_price, pnl, status, mode, trade_date, broker_order_id
        FROM intraday_trades
        WHERE trade_date = ?
        ORDER BY id
    """, (trade_date,))
    
    trades_by_symbol = {}
    rows = cur.fetchall()
    for row in rows:
        (id_, symbol, ts, action, qty, entry, exit_p, pnl, status, mode, td, oid) = row
        # Use tradingsymbol as primary key (matches Dhan)
        key = ts.upper() if ts else symbol.upper()
        if key not in trades_by_symbol:
            trades_by_symbol[key] = []
        trades_by_symbol[key].append({
            "id": id_,
            "symbol": symbol,
            "tradingsymbol": ts,
            "action": action,
            "quantity": qty,
            "entry_price": entry,
            "exit_price": exit_p,
            "pnl": pnl if pnl else 0.0,
            "status": status,
            "mode": mode,
            "trade_date": td,
            "broker_order_id": oid,
        })
    
    conn.close()
    
    total_pnl = sum(
        t["pnl"]
        for trades in trades_by_symbol.values()
        for t in trades
    )
    
    return {
        "trades_by_symbol": trades_by_symbol,
        "total_pnl": total_pnl,
        "total_trades": sum(len(t) for t in trades_by_symbol.values()),
    }



def compare(dhan, db):
    """Compare Dhan truth vs DB records. Return per-symbol drift report."""
    all_symbols = set(dhan["positions"].keys()) | set(db["trades_by_symbol"].keys())
    
    report_rows = []
    total_drift = 0.0
    issues_count = 0
    
    for sym in sorted(all_symbols):
        dhan_pos = dhan["positions"].get(sym)
        db_trades = db["trades_by_symbol"].get(sym, [])
        
        # Calculate aggregate DB values for this symbol
        if db_trades:
            db_qty = sum(t["quantity"] for t in db_trades)
            db_pnl = sum(t["pnl"] for t in db_trades)
            db_status = ", ".join(set(t["status"] for t in db_trades))
            db_ids = [t["id"] for t in db_trades]
        else:
            db_qty = 0
            db_pnl = 0.0
            db_status = "MISSING"
            db_ids = []
        
        if dhan_pos:
            dhan_qty = dhan_pos["buy_qty"]
            dhan_pnl = dhan_pos["total_pnl"]
        else:
            dhan_qty = 0
            dhan_pnl = 0.0
        
        drift_pnl = round(dhan_pnl - db_pnl, 2)
        drift_qty = dhan_qty - db_qty
        
        # Classify issue
        issue = "OK"
        if not db_trades and dhan_pos:
            issue = "PHANTOM_TRADE — in Dhan, missing from DB"
            issues_count += 1
        elif db_trades and not dhan_pos:
            issue = "ORPHAN_DB — in DB, missing from Dhan"
            issues_count += 1
        elif abs(drift_pnl) > DRIFT_THRESHOLD:
            issue = f"PNL_DRIFT — DB off by Rs.{drift_pnl:+.2f}"
            issues_count += 1
        elif drift_qty != 0:
            issue = f"QTY_DRIFT — DB off by {drift_qty:+d} shares"
            issues_count += 1
        
        total_drift += abs(drift_pnl)
        
        report_rows.append({
            "symbol": sym,
            "dhan_qty": dhan_qty,
            "db_qty": db_qty,
            "qty_drift": drift_qty,
            "dhan_pnl": round(dhan_pnl, 2),
            "db_pnl": round(db_pnl, 2),
            "pnl_drift": drift_pnl,
            "db_status": db_status,
            "db_ids": db_ids,
            "issue": issue,
        })
    
    return {
        "rows": report_rows,
        "total_drift_abs": round(total_drift, 2),
        "total_dhan_pnl": round(dhan["total_pnl"], 2),
        "total_db_pnl": round(db["total_pnl"], 2),
        "total_pnl_drift": round(dhan["total_pnl"] - db["total_pnl"], 2),
        "dhan_position_count": len(dhan["positions"]),
        "db_trade_count": db["total_trades"],
        "issues_count": issues_count,
    }


def print_report(profile, trade_date, dhan, db, comparison):
    """Print human-readable report to stdout."""
    print("=" * 80)
    print(f"RECONCILIATION REPORT — {profile} — {trade_date}")
    print("=" * 80)
    print(f"Dhan timestamp: {dhan['timestamp']}")
    print(f"Available balance: Rs.{dhan['available_balance']:,.2f}")
    print()
    print(f"Trade count: Dhan={comparison['dhan_position_count']} vs DB={comparison['db_trade_count']}")
    print(f"Total P&L:   Dhan=Rs.{comparison['total_dhan_pnl']:+.2f} vs DB=Rs.{comparison['total_db_pnl']:+.2f}")
    print(f"Total drift: Rs.{comparison['total_pnl_drift']:+.2f} (absolute Rs.{comparison['total_drift_abs']:.2f})")
    print(f"Issues:      {comparison['issues_count']} of {len(comparison['rows'])} symbols")
    print()
    print("-" * 80)
    print(f"{'SYMBOL':<14} {'DHAN QTY':>9} {'DB QTY':>7} {'DHAN P&L':>10} {'DB P&L':>10} {'DRIFT':>9}  ISSUE")
    print("-" * 80)
    for r in comparison["rows"]:
        print(f"{r['symbol']:<14} {r['dhan_qty']:>9} {r['db_qty']:>7} {r['dhan_pnl']:>+10.2f} {r['db_pnl']:>+10.2f} {r['pnl_drift']:>+9.2f}  {r['issue']}")
    print("-" * 80)
    print()
    
    status = "PASS" if abs(comparison["total_pnl_drift"]) <= DRIFT_THRESHOLD else "FAIL"
    print(f"OVERALL: {status} (threshold Rs.{DRIFT_THRESHOLD:.2f})")
    print("=" * 80)


def write_report(profile, trade_date, dhan, db, comparison):
    """Write JSON report to dashboard/api/{profile}/reconciliation_report.json."""
    out_path = Path(f"dashboard/api/{profile}/reconciliation_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    report = {
        "profile": profile,
        "trade_date": trade_date,
        "generated_at": datetime.now(IST).isoformat(),
        "dhan_timestamp": dhan["timestamp"],
        "summary": {
            "dhan_position_count": comparison["dhan_position_count"],
            "db_trade_count": comparison["db_trade_count"],
            "total_dhan_pnl": comparison["total_dhan_pnl"],
            "total_db_pnl": comparison["total_db_pnl"],
            "total_pnl_drift": comparison["total_pnl_drift"],
            "total_drift_abs": comparison["total_drift_abs"],
            "issues_count": comparison["issues_count"],
            "status": "PASS" if abs(comparison["total_pnl_drift"]) <= DRIFT_THRESHOLD else "FAIL",
            "drift_threshold": DRIFT_THRESHOLD,
        },
        "available_balance": dhan["available_balance"],
        "rows": comparison["rows"],
    }
    
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"Report written: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, help="Profile name (e.g. vishal-live)")
    parser.add_argument("--date", default=None, help="Trade date YYYY-MM-DD (default: today IST)")
    args = parser.parse_args()
    
    trade_date = args.date or datetime.now(IST).strftime("%Y-%m-%d")
    
    print(f"Loading Dhan truth for {args.profile}...")
    dhan = load_dhan_truth(args.profile)
    
    print(f"Loading DB trades for {args.profile} on {trade_date}...")
    db = load_db_trades(args.profile, trade_date)
    
    comparison = compare(dhan, db)
    print_report(args.profile, trade_date, dhan, db, comparison)
    write_report(args.profile, trade_date, dhan, db, comparison)
    
    # Exit code: 0 if PASS, 1 if FAIL
    sys.exit(0 if abs(comparison["total_pnl_drift"]) <= DRIFT_THRESHOLD else 1)


if __name__ == "__main__":
    main()
