#!/usr/bin/env python3
"""Compute daily capital + P&L metrics per profile.

Reads intraday_trades DB + profile yaml. Outputs JSON to
dashboard/api/v2/{profile}/daily_pnl/{date}.json

Usage:
    python scripts/compute_daily_pnl.py --profile vishal-live --date 2026-05-21
    python scripts/compute_daily_pnl.py --all  # backfill all profiles, last 14 trading days
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

# Capital configured per profile (canonical field: intraday.daily_capital_limit)
# Hardcoded here to avoid parsing multi-section yaml complexity.
# Source: config/profiles/*.yaml → intraday: → daily_capital_limit
CAPITAL_CONFIGURED = {
    "vishal-live": 15000,
    "vishal": 300000,
    "neha": 300000,
    "neha-live": 10000,
}

EXCLUDED_STATUSES = {"REJECTED", "CANCELLED", "FAILED", "ABANDONED", "PENDING"}


def db_path(profile):
    return Path(__file__).parent.parent / "database" / f"{profile}.db"


def output_dir(profile):
    return Path(__file__).parent.parent / "dashboard" / "api" / "v2" / profile / "daily_pnl"


def estimate_charges(entry_price, quantity):
    """Estimate round-trip charges: Rs.50 flat + 0.05% of trade value."""
    trade_value = entry_price * quantity
    return round(50 + trade_value * 0.0005, 2)


def fetch_closed_trades(profile, date):
    """Fetch all closed trades for a date (excludes PENDING/REJECTED/etc)."""
    p = db_path(profile)
    if not p.exists():
        return []
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT id, tradingsymbol, action, quantity, entry_price, exit_price,
                   pnl, status, confidence_score, strategy_type
            FROM intraday_trades
            WHERE trade_date = ? AND action IN ('BUY', 'SELL')
              AND status NOT IN ('REJECTED', 'CANCELLED', 'FAILED', 'ABANDONED', 'PENDING')
            ORDER BY timestamp
        """, (date,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


def get_trading_dates(profile, limit=14):
    """Get last N trading dates with trades for this profile."""
    p = db_path(profile)
    if not p.exists():
        return []
    con = sqlite3.connect(str(p))
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT trade_date FROM intraday_trades
            WHERE action IN ('BUY', 'SELL')
              AND status NOT IN ('REJECTED', 'CANCELLED', 'FAILED', 'ABANDONED', 'PENDING')
            ORDER BY trade_date DESC LIMIT ?
        """, (limit,))
        return [row[0] for row in cur.fetchall()]
    finally:
        con.close()



def _extract_skip_reasons(profile, date):
    """Extract skip/rejection reasons from the intraday log for a given date."""
    import re as _re
    log_dir = Path(__file__).parent.parent / "logs"
    log_file = log_dir / f"intraday_{profile}_{date}.log"

    result = {
        "system_ran": False,
        "scans_attempted": 0,
        "vix": None,
        "market_direction": None,
        "strategies_skipped": [],
        "errors": [],
        "no_trade_reason_summary": "Unknown",
    }

    if not log_file.exists():
        result["no_trade_reason_summary"] = "No log file - cron did not fire or profile not scheduled"
        return result

    result["system_ran"] = True
    content = log_file.read_text()
    lines = content.split("\n")

    scan_lines = [l for l in lines if "Scan:" in l and "candidates" in l]
    result["scans_attempted"] = len(scan_lines)

    vix_matches = _re.findall(r"VIX[:\s]+([\d.]+)", content)
    if vix_matches:
        result["vix"] = float(vix_matches[-1])

    direction_matches = _re.findall(r"market (?:direction |)(FLAT|BULLISH|BEARISH|SIDEWAYS|FLAT SIDEWAYS)", content)
    if direction_matches:
        result["market_direction"] = direction_matches[-1]

    skip_patterns = _re.findall(r"(\w+(?:_\w+)*): Skipping", content)
    seen = set()
    for strategy in skip_patterns:
        if strategy not in seen:
            seen.add(strategy)
            # Find the full reason
            match = _re.search(strategy + r": Skipping[^\n]*?([A-Z][^\n]{3,50})", content)
            reason = match.group(1).strip() if match else "unknown"
            result["strategies_skipped"].append({"strategy": strategy, "reason": reason})

    error_lines = [l for l in lines if "[ERROR]" in l]
    result["errors"] = [l.strip()[-100:] for l in error_lines[-3:]]

    if result["scans_attempted"] == 0:
        result["no_trade_reason_summary"] = "Log exists but no scans completed"
    elif result["strategies_skipped"]:
        reasons = list(set(s["reason"] for s in result["strategies_skipped"]))[:3]
        result["no_trade_reason_summary"] = f"Scanned {result['scans_attempted']}x, strategies skipped: {'; '.join(reasons)}"
    elif result["vix"] and result["vix"] > 25:
        result["no_trade_reason_summary"] = f"VIX too high ({result['vix']}) - session skipped"
    else:
        result["no_trade_reason_summary"] = f"Scanned {result['scans_attempted']}x but no valid setups found"

    return result

def compute_metrics(profile, date):
    """Compute all daily metrics for a profile/date."""
    trades = fetch_closed_trades(profile, date)
    capital_configured = CAPITAL_CONFIGURED.get(profile, 15000)

    if not trades:
        skip_info = _extract_skip_reasons(profile, date)
        return {
            "profile": profile,
            "date": date,
            "generated_at": datetime.now(IST).isoformat(),
            "capital_configured": capital_configured,
            "capital_deployed_peak": 0,
            "capital_deployed_pct": 0.0,
            "daily_gross_pnl": 0.0,
            "daily_charges": 0.0,
            "daily_net_pnl": 0.0,
            "daily_return_pct": 0.0,
            "charge_ratio_pct": "n/a",
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "trades": [],
            "no_trade_reason": skip_info,
        }

    # Compute per-trade metrics
    trade_details = []
    for t in trades:
        entry = float(t["entry_price"] or 0)
        qty = int(t["quantity"] or 0)
        net_pnl = float(t["pnl"] or 0)
        charges = estimate_charges(entry, qty) if entry > 0 else 0

        # Gross = net + charges (since DB pnl is net after charges)
        gross_pnl = net_pnl + charges

        trade_details.append({
            "trade_id": t["id"],
            "symbol": t["tradingsymbol"],
            "direction": "SHORT" if t["action"] == "SELL" else "LONG",
            "qty": qty,
            "entry_price": entry,
            "exit_price": float(t["exit_price"] or 0),
            "capital_used": round(entry * qty, 2),
            "gross_pnl": round(gross_pnl, 2),
            "charges": round(charges, 2),
            "net_pnl": round(net_pnl, 2),
            "status": t["status"],
        })

    # Aggregates
    # Capital deployed peak: sum of all qty*entry (upper bound — all open simultaneously)
    capital_deployed_peak = round(sum(td["capital_used"] for td in trade_details), 2)
    capital_deployed_pct = round(capital_deployed_peak / capital_configured * 100, 1) if capital_configured > 0 else 0

    daily_gross_pnl = round(sum(td["gross_pnl"] for td in trade_details), 2)
    daily_charges = round(sum(td["charges"] for td in trade_details), 2)
    daily_net_pnl = round(sum(td["net_pnl"] for td in trade_details), 2)
    daily_return_pct = round(daily_net_pnl / capital_configured * 100, 3) if capital_configured > 0 else 0

    if abs(daily_gross_pnl) > 0:
        charge_ratio_pct = round(daily_charges / abs(daily_gross_pnl) * 100, 1)
    else:
        charge_ratio_pct = "n/a"

    wins = sum(1 for td in trade_details if td["net_pnl"] > 0)
    losses = sum(1 for td in trade_details if td["net_pnl"] < 0)

    return {
        "profile": profile,
        "date": date,
        "generated_at": datetime.now(IST).isoformat(),
        "capital_configured": capital_configured,
        "capital_deployed_peak": capital_deployed_peak,
        "capital_deployed_pct": capital_deployed_pct,
        "daily_gross_pnl": daily_gross_pnl,
        "daily_charges": daily_charges,
        "daily_net_pnl": daily_net_pnl,
        "daily_return_pct": daily_return_pct,
        "charge_ratio_pct": charge_ratio_pct,
        "trade_count": len(trade_details),
        "wins": wins,
        "losses": losses,
        "trades": trade_details,
    }


def write_metrics(profile, date, metrics):
    """Write metrics JSON."""
    out = output_dir(profile)
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / f"{date}.json"
    with open(out_file, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Compute daily P&L metrics")
    parser.add_argument("--profile", help="Profile name")
    parser.add_argument("--date", help="Date YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="Backfill last 14 days, all profiles")
    args = parser.parse_args()

    profiles = ["vishal-live", "vishal", "neha"]

    if args.all:
        for profile in profiles:
            dates = get_trading_dates(profile, 14)
            for date in dates:
                m = compute_metrics(profile, date)
                write_metrics(profile, date, m)
                sign = "+" if m["daily_net_pnl"] >= 0 else ""
                print(f"  {profile}/{date}: {sign}Rs.{m['daily_net_pnl']:.2f} "
                      f"({m['trade_count']} trades, {m['wins']}W/{m['losses']}L, "
                      f"deployed {m['capital_deployed_pct']}%)")
    elif args.profile:
        date = args.date or datetime.now(IST).strftime("%Y-%m-%d")
        m = compute_metrics(args.profile, date)
        out = write_metrics(args.profile, date, m)
        print(f"Written: {out}")
        print(json.dumps(m, indent=2, default=str))
    else:
        print("Usage: --all or --profile X [--date Y]")


if __name__ == "__main__":
    main()
