#!/usr/bin/env python3
"""Live mid-day status across all profiles."""
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from _status_lib import (
    PROFILES_LIVE, PROFILES_PAPER, ALL_PROFILES,
    fetch_trades, fetch_fno, stats_for_profile,
    fmt_pnl, get_today
)


def render_status():
    date = get_today()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("=" * 60)
    print(f"  LIVE STATUS - {now_str} IST")
    print("=" * 60)

    total_real_exp = 0
    total_real_lim = 0
    for prof in PROFILES_LIVE:
        stats = stats_for_profile(prof["name"], date)
        total_real_exp += stats["capital_used"]
        total_real_lim += prof["capital"]

    if total_real_lim:
        pct = total_real_exp / total_real_lim * 100
        marker = "[WARN]" if pct > 75 else "[OK]"
        print(f"\n{marker} REAL MONEY EXPOSURE: Rs.{total_real_exp:,.0f} / Rs.{total_real_lim:,.0f} ({pct:.0f}%)")

    now = datetime.now()
    session_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    session_end = now.replace(hour=15, minute=15, second=0, microsecond=0)
    if now < session_start:
        print("Session not started yet (opens 9:30 IST)")
    elif now > session_end:
        print("Session ended (force exit was 15:15 IST)")
    else:
        elapsed = int((now - session_start).total_seconds() / 60)
        remaining = int((session_end - now).total_seconds() / 60)
        print(f"{elapsed}m into session, {remaining}m to force exit")

    for prof in ALL_PROFILES:
        stats = stats_for_profile(prof["name"], date)
        print(f"\n--- {prof['name'].upper()} ({prof['label']}) ---")

        cap_pct = stats["capital_used"] / prof["capital"] * 100 if prof["capital"] else 0
        loss_pct = stats["realized_loss"] / prof["loss_limit"] * 100 if prof["loss_limit"] else 0

        trade_marker = "[AT LIMIT]" if stats["trade_count"] >= prof["max_trades"] else "[OK]"
        print(f"  {trade_marker} Trades placed:   {stats['trade_count']} / {prof['max_trades']}")
        print(f"  Capital used:    Rs.{stats['capital_used']:,.0f} / Rs.{prof['capital']:,.0f} ({cap_pct:.0f}%)")
        print(f"  Realized loss:   -Rs.{stats['realized_loss']:,.2f} / -Rs.{prof['loss_limit']} ({loss_pct:.0f}%)")

        if stats["open"]:
            print("  Open positions:")
            for t in stats["open"]:
                ts = (t.get("timestamp") or "")[11:16]
                sym = t.get("tradingsymbol", "?")
                qty = int(t.get("quantity") or 0)
                entry = float(t.get("entry_price") or 0)
                pnl_str, marker = fmt_pnl(t.get("pnl"))
                print(f"    {ts} {sym:<12s} x{qty:<3d} @ Rs.{entry:<8.2f}  P&L {pnl_str} {marker}")
        else:
            if stats["trade_count"] > 0:
                pnl_str, marker = fmt_pnl(stats['total_pnl'])
                print(f"  Open: 0 (all closed). P&L {pnl_str} {marker} ({stats['winners']}W/{stats['losers']}L)")
            else:
                print("  No trades today")

    print("\n--- F&O TODAY (paper) ---")
    fno_names = ["vishal-live", "vishal", "neha"]
    any_fno = False
    for name in fno_names:
        fno = fetch_fno(name, date)
        if fno["strategies"] or fno["trade_count"]:
            any_fno = True
            pnl_str, marker = fmt_pnl(fno["pnl"])
            print(f"  {name:<12s}: {len(fno['strategies'])} strategies, {fno['trade_count']} legs, P&L {pnl_str} {marker}")
            for s in fno["strategies"][:2]:
                st = s.get("strategy_type", "?")
                idx = s.get("index_name", "?")
                status = s.get("status", "?")
                print(f"    -> {st:<15s} {idx:<10s} {status}")
    if not any_fno:
        print("  No F&O activity")

    print("\n--- FAILED FILLS TODAY ---")
    log_dir = Path.home() / "dev-sandbox" / "logs"
    any_failed = False
    for prof in ALL_PROFILES:
        log_file = log_dir / f"intraday_{prof['name']}_{date}.log"
        if log_file.exists():
            try:
                txt = log_file.read_text()
                failed = txt.count("did not fill")
                if failed > 0:
                    any_failed = True
                    print(f"  {prof['name']}: {failed} limit order(s) didnt fill")
            except Exception:
                pass
    if not any_failed:
        print("  None")

    print("\n--- HEALTH ---")
    try:
        td = subprocess.run(["timedatectl"], capture_output=True, text=True, timeout=5)
        if "synchronized: yes" in td.stdout:
            print("  Time sync: synchronized")
        else:
            print("  Time sync: NOT synchronized")
    except Exception:
        print("  Time sync: could not check")
    try:
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path.home() / "dev-sandbox")
        )
        print(f"  Commit: {commit.stdout.strip()}")
    except Exception:
        pass
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="Refresh every 30s")
    args = parser.parse_args()
    if args.watch:
        import os, time
        try:
            while True:
                os.system("clear")
                render_status()
                print("\nRefreshing in 30s. Ctrl+C to stop.")
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        render_status()


if __name__ == "__main__":
    main()
