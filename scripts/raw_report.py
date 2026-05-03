#!/usr/bin/env python3
"""Show raw P&L data from all report files — no caps, no manipulation."""
import json, glob

print("=" * 70)
print("RAW DATA — EVERY REPORT FILE")
print("=" * 70)

print("\nINTRADAY:")
print(f"{'Date':<12} {'Trades':<7} {'Capital':<12} {'P&L':<10}")
print("-" * 50)
it = 0
for f in sorted(glob.glob("output/reports/intraday_*.json")):
    if "demo" in f:
        continue
    try:
        with open(f) as fh:
            d = json.load(fh)
        date = d.get("trade_date", "?")
        trades = d.get("trades", [])
        pnl = sum(float(t.get("pnl", 0)) for t in trades)
        cap = sum(float(t.get("entry_price", 0)) * int(t.get("quantity", 0)) for t in trades)
        print(f"{date:<12} {len(trades):<7} {cap:>10,.0f}  {pnl:>+10,.2f}")
        it += pnl
    except:
        pass
print(f"INTRADAY TOTAL: {it:+,.2f}")

print("\nFNO:")
print(f"{'Date':<12} {'Strats':<7} {'P&L':<12} {'WinRate':<8}")
print("-" * 50)
ft = 0
for f in sorted(glob.glob("output/reports/fno_*.json")):
    try:
        with open(f) as fh:
            d = json.load(fh)
        date = d.get("trade_date", "?")
        pnl = float(d.get("total_pnl", 0))
        s = int(d.get("total_strategies", 0))
        wr = d.get("win_rate", 0)
        print(f"{date:<12} {s:<7} {pnl:>+10,.2f}  {wr}%")
        ft += pnl
    except:
        pass
print(f"FNO TOTAL: {ft:+,.2f}")
print(f"\nGRAND TOTAL: {it+ft:+,.2f}")
