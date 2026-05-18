"""Backtest v1 — main entry point.

Runs the full backtest pipeline:
1. Stratify past 30 days → 8 representative days
2. Load Nifty 50 universe (50 stocks)
3. Fetch 1-min OHLC for those 8 days
4. For each day × each profile: simulate_day()
5. Aggregate and save results
6. Print human-readable summary

Usage:
    cd ~/dev-sandbox
    .venv/bin/python3 -m backtest.run_v1
"""

import json
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.day_stratifier import stratify_past_days
from backtest.data_loader import load_nifty500_universe, fetch_universe_for_dates
from backtest.trade_simulator import simulate_day

IST = timezone(timedelta(hours=5, minutes=30))

PROFILES = ["vishal", "vishal-live"]


def load_broker():
    """Load and authenticate Dhan broker using vishal profile."""
    profile_path = Path("config/profiles/vishal.yaml")
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(profile_path) as f:
        config = yaml.safe_load(f)

    from intraday.auth_server import authenticate_broker
    broker = authenticate_broker(
        broker_name="dhan",
        broker_config=config.get("dhan", {}),
        dry_run=False,
    )
    return broker


def run_backtest():
    """Main backtest execution."""
    start_time = time.time()
    print("=" * 60)
    print("BACKTEST v1 — Intraday Trade Simulator")
    print("=" * 60)
    print(f"Started: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print()

    # Step 1: Authenticate broker
    print("[1/5] Authenticating broker...")
    broker = load_broker()
    print("  ✓ Broker ready")

    # Step 2: Stratify days
    print("[2/5] Stratifying past 30 trading days...")
    strat_result = stratify_past_days(num_days=30, broker=broker)
    selected_days = strat_result["selected_days"]
    print(f"  ✓ Selected {len(selected_days)} days: {selected_days}")
    print(f"  Categories: {strat_result['categorized']}")
    print()

    # Step 3: Load universe
    print("[3/5] Loading Nifty 50 universe...")
    universe = load_nifty500_universe()
    print(f"  ✓ {len(universe)} stocks loaded")

    # Step 4: Fetch 1-min OHLC
    print("[4/5] Fetching 1-min OHLC data...")
    historical_data = fetch_universe_for_dates(
        universe=universe,
        dates=selected_days,
        broker=broker,
        interval="1",
        cache_dir="cache/historical",
    )
    print(f"  ✓ Data for {len(historical_data)} stocks")
    print()

    # Step 5: Simulate each day × each profile
    print("[5/5] Simulating trades...")
    all_results = []

    for profile in PROFILES:
        print(f"\n  --- Profile: {profile} ---")
        profile_results = []

        for day in selected_days:
            result = simulate_day(day, profile, universe, historical_data)
            profile_results.append(result)

            status = "SKIPPED" if result.get("skipped_reason") else f"{result['trades_placed']} trades, ₹{result['total_net_pnl']}"
            print(f"    {day}: {status}")

        all_results.append({
            "profile": profile,
            "days": profile_results,
        })

    # Aggregate results
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    output_dir = Path("backtest/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"backtest_v1_{timestamp}.json"

    summary = {
        "version": "v1",
        "timestamp": timestamp,
        "selected_days": selected_days,
        "universe_size": len(universe),
        "data_stocks_fetched": len(historical_data),
        "profiles_tested": PROFILES,
        "assumption": "LLM picks approximated by scanner v3 top-5 scores. Real LLM integration in v1.1.",
        "results": all_results,
    }

    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    elapsed = time.time() - start_time

    # Print human-readable summary
    print("\n" + "=" * 60)
    print("BACKTEST v1 RESULTS")
    print("=" * 60)

    for profile_result in all_results:
        profile = profile_result["profile"]
        days = profile_result["days"]

        total_pnl = sum(d.get("total_net_pnl", 0) for d in days)
        total_trades = sum(d.get("trades_placed", 0) for d in days)
        total_winners = sum(d.get("winners", 0) for d in days)
        total_losers = sum(d.get("losers", 0) for d in days)
        total_charges = sum(d.get("total_charges", 0) for d in days)
        skipped_days = sum(1 for d in days if d.get("skipped_reason"))

        win_rate = round(total_winners / total_trades * 100, 1) if total_trades > 0 else 0

        print(f"\n  Profile: {profile}")
        print(f"  {'─' * 40}")
        print(f"  Days simulated:    {len(days)} ({skipped_days} skipped)")
        print(f"  Total trades:      {total_trades}")
        print(f"  Winners/Losers:    {total_winners}W / {total_losers}L")
        print(f"  Win rate:          {win_rate}%")
        print(f"  Total charges:     ₹{total_charges:.2f}")
        print(f"  Net P&L:           ₹{total_pnl:.2f}")
        print(f"  Avg P&L/day:       ₹{total_pnl / max(len(days) - skipped_days, 1):.2f}")

        # Best and worst trades
        all_trades = [t for d in days for t in d.get("trades", [])]
        if all_trades:
            best = max(all_trades, key=lambda t: t["net_pnl"])
            worst = min(all_trades, key=lambda t: t["net_pnl"])
            print(f"  Best trade:        {best['symbol']} {best['direction']} ₹{best['net_pnl']:.2f} ({best['exit_reason']})")
            print(f"  Worst trade:       {worst['symbol']} {worst['direction']} ₹{worst['net_pnl']:.2f} ({worst['exit_reason']})")

    print(f"\n  Output: {output_file}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print("=" * 60)

    return str(output_file)


if __name__ == "__main__":
    run_backtest()
