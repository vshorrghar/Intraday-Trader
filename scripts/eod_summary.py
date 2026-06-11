#!/usr/bin/env python3
"""Comprehensive EOD summary - all profiles, F&O, scanner accuracy."""
import sys
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from _status_lib import (
    PROFILES_LIVE, PROFILES_PAPER, ALL_PROFILES,
    fetch_trades, fetch_fno, fetch_top_movers, stats_for_profile,
    fmt_pnl, EXCLUDED_STATUSES
)


def render_eod(date):
    print("=" * 62)
    print(f"  EOD SUMMARY - {date}")
    print("=" * 62)

    print("\n--- REAL MONEY P&L ---")
    total_real = 0
    for prof in PROFILES_LIVE:
        stats = stats_for_profile(prof["name"], date)
        total_real += stats["total_pnl"]
        pnl_str, marker = fmt_pnl(stats["total_pnl"])
        print(f"  {marker} {prof['name']:<12s}: {pnl_str}  ({stats['trade_count']} trades, {stats['winners']}W/{stats['losers']}L)")
    pnl_str, marker = fmt_pnl(total_real)
    print(f"  COMBINED: {pnl_str} {marker}")

    for prof in ALL_PROFILES:
        stats = stats_for_profile(prof["name"], date)
        if not stats["counted"]:
            continue
        print(f"\n--- {prof['name'].upper()} ({prof['label']}) ---")
        print(f"  Trades placed:    {stats['trade_count']}")
        print(f"  Capital deployed: Rs.{stats['capital_used']:,.0f}")
        pnl_str, marker = fmt_pnl(stats["total_pnl"])
        print(f"  Realized P&L:     {pnl_str} {marker}")
        print(f"  Win/Loss:         {stats['winners']}W / {stats['losers']}L")
        print("  Trade detail:")
        for t in stats["counted"]:
            ts = (t.get("timestamp") or "")[11:16]
            sym = t.get("tradingsymbol") or "?"
            qty = int(t.get("quantity") or 0)
            entry = float(t.get("entry_price") or 0)
            exit_p = t.get("exit_price")
            exit_str = f"Rs.{exit_p:.2f}" if exit_p else "--"
            status = t.get("status") or "?"
            pnl_str, marker = fmt_pnl(t.get("pnl"))
            print(f"    {ts} {sym:<12s} x{qty:<3d}  Rs.{entry:<8.2f} -> {exit_str:<10s} {status:<14s} {pnl_str} {marker}")

    print("\n--- F&O TODAY ---")
    fno_profiles = ["vishal-live", "vishal", "neha"]
    any_fno = False
    for name in fno_profiles:
        fno = fetch_fno(name, date)
        if fno["strategies"] or fno["trade_count"]:
            any_fno = True
            pnl_str, marker = fmt_pnl(fno["pnl"])
            print(f"  {name}: {len(fno['strategies'])} strategies, {fno['trade_count']} legs, paper P&L {pnl_str} {marker}")
            for s in fno["strategies"][:3]:
                st = s.get("strategy_type", "?")
                idx = s.get("index_name", "?")
                status = s.get("status", "?")
                print(f"    -> {st:<15s} {idx:<12s} {status}")
    if not any_fno:
        print("  No F&O activity")

    print("\n--- SCANNER PERFORMANCE ---")
    movers = fetch_top_movers("vishal-live", date)
    if not movers:
        movers = fetch_top_movers("vishal", date)
    if movers:
        picked = []
        for m in movers:
            for k in ["picked_by_us", "picked", "we_picked"]:
                if m.get(k):
                    picked.append(m)
                    break
        missed = [m for m in movers if m not in picked]
        print(f"  Top 20 movers captured: yes ({len(movers)} stocks)")
        print(f"  Stocks we picked: {len(picked)} / {len(movers)}")
        if movers:
            acc = len(picked) / len(movers) * 100
            print(f"  Accuracy: {acc:.0f}%")
        if missed:
            print("  Top 3 missed:")
            for m in missed[:3]:
                sym = m.get("symbol", "?")
                pct = m.get("change_pct", 0)
                why = m.get("why_missed", "unknown")
                print(f"    {sym:<12s} +{pct:.2f}%  ({why})")
    else:
        print("  Top performers data not yet captured (cron at 3:35 PM IST)")

    print("\n--- ISSUES HIT TODAY ---")
    log_dir = Path.home() / "dev-sandbox" / "logs"
    any_issue = False
    for prof in ALL_PROFILES:
        log_file = log_dir / f"intraday_{prof['name']}_{date}.log"
        if log_file.exists():
            txt = log_file.read_text()
            failed = txt.count("did not fill")
            if failed > 0:
                any_issue = True
                print(f"  {prof['name']}: {failed} limit order(s) didnt fill")
    if not any_issue:
        print("  No fill issues today")

    print("\n--- WEEK-TO-DATE REAL MONEY ---")
    end = datetime.strptime(date, "%Y-%m-%d")
    start = end - timedelta(days=6)
    wtd_pnl = 0
    wtd_trades = 0
    wtd_wins = 0
    for prof in PROFILES_LIVE:
        db = Path(__file__).parent.parent / "database" / f"{prof['name']}.db"
        if not db.exists():
            continue
        con = sqlite3.connect(str(db))
        cur = con.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(pnl), 0)
                FROM intraday_trades
                WHERE trade_date BETWEEN ? AND ?
                  AND action = 'BUY'
            """, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
            row = cur.fetchone()
            wtd_trades += row[0] or 0
            wtd_wins += row[1] or 0
            wtd_pnl += float(row[2] or 0)
        except Exception:
            pass
        con.close()
    if wtd_trades:
        wr = wtd_wins / wtd_trades * 100
        pnl_str, marker = fmt_pnl(wtd_pnl)
        print(f"  Cumulative P&L: {pnl_str} {marker}")
        print(f"  Total trades:   {wtd_trades}")
        print(f"  Win rate:       {wr:.0f}%")
    else:
        print("  No trades in window")

    print("=" * 62)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    render_eod(args.date)


if __name__ == "__main__":
    main()
