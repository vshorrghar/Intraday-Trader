#!/usr/bin/env python3
"""
show_today_truth.py — Quick truth dashboard from terminal.

USAGE:
  .venv/bin/python scripts/show_today_truth.py --profile vishal-live
  .venv/bin/python scripts/show_today_truth.py --profile vishal-live --date 2026-05-19

Reads:
  dashboard/api/{profile}/dhan_live.json (Dhan truth)
  dashboard/api/{profile}/reconciliation_report.json (drift analysis if available)

Prints colored, human-readable truth summary.
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def color_pnl(value):
    if value > 0:
        return f"{GREEN}+Rs.{value:,.2f}{RESET}"
    elif value < 0:
        return f"{RED}-Rs.{abs(value):,.2f}{RESET}"
    else:
        return f"Rs.{value:,.2f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    
    trade_date = args.date or datetime.now(IST).strftime("%Y-%m-%d")
    
    # Load Dhan truth
    dhan_path = Path(f"dashboard/api/{args.profile}/dhan_live.json")
    if not dhan_path.exists():
        print(f"{RED}ERROR: {dhan_path} not found.{RESET}")
        print(f"Run: .venv/bin/python scripts/sync_dhan_live.py")
        sys.exit(1)
    
    with open(dhan_path) as f:
        dhan = json.load(f)
    
    summary = dhan.get("summary", {})
    funds = dhan.get("funds", {})
    positions = dhan.get("positions", [])
    
    total_pnl = summary.get("total_pnl", 0.0)
    available = funds.get("availabelBalance", 0.0)
    
    # Load reconciliation if available
    recon_path = Path(f"dashboard/api/{args.profile}/reconciliation_report.json")
    recon = None
    if recon_path.exists():
        with open(recon_path) as f:
            recon = json.load(f)
    
    # Header
    width = 70
    print()
    print("=" * width)
    title = f"  {args.profile.upper()} — REAL P&L (DHAN TRUTH) — {trade_date}  "
    print(f"{BOLD}{CYAN}{title.center(width)}{RESET}")
    print("=" * width)
    
    # P&L Summary
    print(f"\n{BOLD}TODAY'S P&L (Dhan API):{RESET}  {color_pnl(total_pnl)}")
    
    if recon:
        db_pnl = recon["summary"]["total_db_pnl"]
        drift = recon["summary"]["total_pnl_drift"]
        status = recon["summary"]["status"]
        issues = recon["summary"]["issues_count"]
        
        print(f"{BOLD}DB shows:{RESET}                {color_pnl(db_pnl)}")
        print(f"{BOLD}Drift:{RESET}                   {color_pnl(drift)}")
        
        if status == "PASS":
            print(f"{BOLD}Reconciliation:{RESET}          {GREEN}PASS{RESET} (drift within Rs.5)")
        else:
            print(f"{BOLD}Reconciliation:{RESET}          {RED}FAIL{RESET} ({issues} issues)")
    else:
        print(f"{BOLD}DB comparison:{RESET}           {YELLOW}Not run yet{RESET}")
        print(f"  Run: .venv/bin/python scripts/reconcile_dhan_db.py --profile {args.profile}")
    
    # Capital
    print(f"\n{BOLD}Available Balance:{RESET}       Rs.{available:,.2f}")
    
    # Position table
    closed = [p for p in positions if p.get("positionType") == "CLOSED"]
    open_pos = [p for p in positions if p.get("positionType") != "CLOSED" and p.get("netQty", 0) != 0]
    
    print(f"\n{BOLD}TRADES TODAY:{RESET} {len(closed)} closed, {len(open_pos)} open")
    
    if closed:
        wins = sum(1 for p in closed if p.get("realizedProfit", 0) > 0)
        losses = sum(1 for p in closed if p.get("realizedProfit", 0) <= 0)
        print(f"  Wins: {GREEN}{wins}{RESET}  /  Losses: {RED}{losses}{RESET}")
        
        win_rate = (wins / len(closed) * 100) if closed else 0
        wr_color = GREEN if win_rate >= 60 else (YELLOW if win_rate >= 50 else RED)
        print(f"  Win rate: {wr_color}{win_rate:.0f}%{RESET}")
        
        print()
        print(f"  {'SYMBOL':<14} {'QTY':>4} {'BUY':>9} {'SELL':>9} {'P&L':>12}")
        print(f"  {'-' * 60}")
        for p in closed:
            sym = p.get("tradingSymbol", "")[:13]
            qty = p.get("buyQty", 0)
            buy = p.get("buyAvg", 0)
            sell = p.get("sellAvg", 0)
            pnl = p.get("realizedProfit", 0)
            pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
            pnl_color = GREEN if pnl >= 0 else RED
            print(f"  {sym:<14} {qty:>4} {buy:>9.2f} {sell:>9.2f} {pnl_color}{pnl_str:>12}{RESET}")
    
    if open_pos:
        print(f"\n{YELLOW}{BOLD}OPEN POSITIONS:{RESET}")
        for p in open_pos:
            sym = p.get("tradingSymbol", "")[:13]
            qty = p.get("netQty", 0)
            unrealized = p.get("unrealizedProfit", 0)
            print(f"  {sym:<14} qty={qty:>4}  unrealized={color_pnl(unrealized)}")
    
    print()
    print("=" * width)
    print(f"  Source: Dhan API at {dhan.get('timestamp', 'unknown')}")
    print("=" * width)
    print()


if __name__ == "__main__":
    main()
