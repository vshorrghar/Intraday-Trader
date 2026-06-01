#!/usr/bin/env python3
"""
Pretty-print swing backtest results from JSON.

Usage:
    .venv/bin/python scripts/print_swing_backtest_summary.py
    .venv/bin/python scripts/print_swing_backtest_summary.py --file backtest/results/swing_backtest_20260528.json
"""

import json
import sys
from pathlib import Path


def find_latest_result() -> Path | None:
    """Find the most recent backtest result file."""
    results_dir = Path(__file__).parent.parent / "backtest" / "results"
    if not results_dir.exists():
        return None
    files = sorted(results_dir.glob("swing_backtest_*.json"))
    return files[-1] if files else None


def print_summary(results: dict):
    m = results["metrics"]
    trades = results.get("trades_detail", [])

    print("=" * 70)
    print("📊 SWING BACKTEST SUMMARY")
    print("=" * 70)
    print(f"  Period: {results['period']}")
    print(f"  Universe: {results['universe_size']} stocks")
    print(f"  Data source: {results['data_source']}")
    print()

    # Core metrics
    print("─── METRICS ───")
    print(f"  Total trades:      {m['trades']}")
    print(f"  Wins / Losses:     {m['wins']} / {m['losses']}")
    print(f"  Win rate:          {m['win_rate']*100:.1f}%")
    print(f"  Profit factor:     {m['profit_factor']:.2f}")
    print(f"  Cumulative P&L:    ₹{m['cumulative_pnl']:,.0f}")
    print(f"  Max drawdown:      ₹{m['max_drawdown']:,.0f}")
    print(f"  Avg holding days:  {m['avg_holding_days']:.1f}")
    print(f"  Max holding days:  {m['max_holding_days']}")
    print(f"  Entries/day avg:   {m['entries_per_day_avg']:.2f}")
    print(f"  Max entries/day:   {m['max_entries_single_day']}")
    print()

    # Exit reasons
    print("─── EXIT REASONS ───")
    exit_reasons = results.get("exit_reasons", {})
    for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        pct = count / m["trades"] * 100 if m["trades"] > 0 else 0
        bar = "█" * int(pct / 3)
        print(f"  {reason:<30} {count:>3} ({pct:>5.1f}%) {bar}")
    print()

    # Top 5 winners
    if trades:
        sorted_by_pnl = sorted(trades, key=lambda t: t["pnl_after_charges"], reverse=True)
        print("─── TOP 5 WINNERS ───")
        for t in sorted_by_pnl[:5]:
            print(f"  {t['symbol']:<12} entry={t['entry_date']} "
                  f"days={t['days_held']:>2} P&L=₹{t['pnl_after_charges']:>+8.0f} "
                  f"({t['exit_reason']})")
        print()

        # Top 5 losers
        print("─── TOP 5 LOSERS ───")
        for t in sorted_by_pnl[-5:]:
            print(f"  {t['symbol']:<12} entry={t['entry_date']} "
                  f"days={t['days_held']:>2} P&L=₹{t['pnl_after_charges']:>+8.0f} "
                  f"({t['exit_reason']})")
        print()

    # Pass/fail criteria
    print("─── PASS CRITERIA ───")
    criteria = [
        ("Trades >= 30", m["trades"] >= 30, f"{m['trades']} trades"),
        ("Win rate >= 45%", m["win_rate"] >= 0.45, f"{m['win_rate']*100:.1f}%"),
        ("Profit factor >= 1.3", m["profit_factor"] >= 1.3, f"{m['profit_factor']:.2f}"),
        ("Max drawdown <= ₹3,000", m["max_drawdown"] <= 3000, f"₹{m['max_drawdown']:,.0f}"),
        ("Max entries/day <= 5", m["max_entries_single_day"] <= 5, f"{m['max_entries_single_day']}"),
    ]
    passed = 0
    for name, result, value in criteria:
        status = "✅" if result else "❌"
        print(f"  {status} {name:<30} → {value}")
        if result:
            passed += 1

    print()
    print(f"  CRITERIA MET: {passed}/5")
    print()

    if passed == 5:
        decision = "🚀 SHIP — Deploy to paper trading"
    elif passed == 4:
        decision = "📝 SHIP-WITH-NOTES — Deploy with documented weak metric"
    elif passed == 3:
        decision = "⚠️ SHIP-LIMITED — Paper-only with reduced position size"
    else:
        decision = "🛑 KILL — Do not deploy. Strategy needs redesign."

    print(f"  DECISION: {decision}")
    print("=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Print swing backtest summary")
    parser.add_argument("--file", help="Path to backtest result JSON")
    args = parser.parse_args()

    if args.file:
        result_file = Path(args.file)
    else:
        result_file = find_latest_result()

    if not result_file or not result_file.exists():
        print("ERROR: No backtest result file found.")
        print("  Run: .venv/bin/python backtest/run_swing_backtest.py")
        sys.exit(1)

    with open(result_file) as f:
        results = json.load(f)

    print(f"  Reading: {result_file}")
    print()
    print_summary(results)


if __name__ == "__main__":
    main()
