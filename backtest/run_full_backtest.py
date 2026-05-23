"""
Full 6-month backtest framework.
Tests all strategy variants across all market scenarios.
Designed to run in background on EC2.

Usage:
    cd ~/dev-sandbox
    nohup .venv/bin/python3 -m backtest.run_full_backtest \
        > backtest/results/backtest_run.log 2>&1 &
    echo "PID: $!"
"""

import json
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.universes import get_universe, BLACKLIST
from backtest.rule_engine import (
    get_candles_for_date, get_prev_close, generate_orb_signals,
    get_market_direction,
)
from backtest.data_loader import fetch_and_cache_historical
from intraday.charges import calculate_intraday_charges

IST = timezone(timedelta(hours=5, minutes=30))

# ============================================================
# CONFIGURATION
# ============================================================

STRATEGY_VARIANTS = ["V1", "V2", "V3", "V4", "V6"]
UNIVERSES = ["nifty50", "next50", "tier1"]
POSITION_SIZES = [15000, 50000]

# Date range: 6 months in two 90-day chunks
DATE_CHUNKS = [
    ("2025-12-01", "2026-03-01"),
    ("2026-03-01", "2026-05-23"),
]

# ============================================================
# DATA FETCHING
# ============================================================

def fetch_all_data(broker, universe_name: str) -> dict:
    """Fetch 6 months of 15-min data for universe. Uses cache."""
    universe = get_universe(universe_name)
    all_data = {}

    print(f"\nFetching data for {len(universe)} stocks in {universe_name}...")

    for from_date, to_date in DATE_CHUNKS:
        print(f"  Chunk: {from_date} to {to_date}")
        chunk_data = fetch_and_cache_historical(
            symbols=universe,
            from_date=from_date,
            to_date=to_date,
            interval="15",
            cache_dir="cache/historical_6m",
            
            broker=broker,
        )
        # Merge chunks
        for symbol, ohlc in chunk_data.items():
            if symbol not in all_data:
                all_data[symbol] = ohlc
            else:
                # Append new data to existing
                for key in ["open", "high", "low", "close", "volume", "timestamp"]:
                    all_data[symbol][key].extend(ohlc.get(key, []))

    print(f"  Data ready for {len(all_data)} stocks")
    return all_data


def get_all_trading_days(historical_data: dict) -> list:
    """Extract all unique trading days from fetched data."""
    days = set()
    sample_symbol = next(iter(historical_data))
    timestamps = historical_data[sample_symbol].get("timestamp", [])

    for ts in timestamps:
        dt = datetime.fromtimestamp(ts, tz=IST)
        days.add(dt.strftime("%Y-%m-%d"))

    return sorted(days)


# ============================================================
# SINGLE DAY SIMULATION
# ============================================================

def simulate_day_rules(
    target_date: str,
    historical_data: dict,
    universe: dict,
    nifty_data: dict,
    strategy_variant: str,
    per_trade_cap: int,
    max_trades: int = 3,
    daily_loss_limit: float = 1500,
) -> dict:
    """Simulate one day using rule-based signals."""

    config = {
        "per_trade_max_capital": per_trade_cap,
        "max_trades_per_day": max_trades,
        "daily_loss_limit": daily_loss_limit,
    }

    # Generate signals
    signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant=strategy_variant,
        nifty_data=nifty_data,
    )

    if not signals:
        return {
            "date": target_date,
            "trades": [],
            "total_gross": 0,
            "total_charges": 0,
            "total_net": 0,
            "winners": 0,
            "losers": 0,
            "skipped": True,
            "skip_reason": "NO_SIGNALS",
        }

    # Simulate each signal
    trades = []
    cumulative_loss = 0.0

    for signal in signals[:max_trades]:
        if abs(cumulative_loss) >= daily_loss_limit:
            break

        symbol = signal["symbol"]
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if not candles:
            continue

        entry_price = signal["entry_price"]
        target_price = signal["target_price"]
        sl_price = signal["stop_loss_price"]
        direction = signal["direction"]
        qty = max(1, int(per_trade_cap / entry_price))

        # Find entry candle
        entry_candle_idx = None
        for i, c in enumerate(candles):
            if c["close"] == entry_price or (
                direction == "LONG" and c["high"] >= entry_price and
                c["time"].strftime("%H:%M") == signal.get("breakout_time", "09:35")
            ):
                entry_candle_idx = i
                break

        if entry_candle_idx is None:
            # Find by time
            for i, c in enumerate(candles):
                if c["time"].hour >= 9 and c["time"].minute >= 31:
                    entry_candle_idx = i
                    break

        if entry_candle_idx is None:
            continue

        # Walk candles to find exit
        exit_price = None
        exit_reason = None
        exit_time = None

        for i in range(entry_candle_idx + 1, len(candles)):
            c = candles[i]

            # Time stop at 14:30
            if c["time"].hour >= 14 and c["time"].minute >= 30:
                exit_price = c["close"]
                exit_reason = "TIME_STOP_1430"
                exit_time = c["time"].strftime("%H:%M")
                break

            if direction == "LONG":
                if c["low"] <= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOPPED_OUT"
                    exit_time = c["time"].strftime("%H:%M")
                    break
                if c["high"] >= target_price:
                    exit_price = target_price
                    exit_reason = "TARGET_HIT"
                    exit_time = c["time"].strftime("%H:%M")
                    break
            else:
                if c["high"] >= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOPPED_OUT"
                    exit_time = c["time"].strftime("%H:%M")
                    break
                if c["low"] <= target_price:
                    exit_price = target_price
                    exit_reason = "TARGET_HIT"
                    exit_time = c["time"].strftime("%H:%M")
                    break

        if exit_price is None:
            exit_price = candles[-1]["close"]
            exit_reason = "EOD_CLOSE"
            exit_time = "15:30"

        # P&L
        if direction == "LONG":
            gross = (exit_price - entry_price) * qty
            charges = calculate_intraday_charges(entry_price, exit_price, qty)
        else:
            gross = (entry_price - exit_price) * qty
            charges = calculate_intraday_charges(exit_price, entry_price, qty)

        net = round(gross - charges, 2)

        if net < 0:
            cumulative_loss += abs(net)

        trades.append({
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 2),
            "sl_price": sl_price,
            "target_price": target_price,
            "qty": qty,
            "gross_pnl": round(gross, 2),
            "charges": round(charges, 2),
            "net_pnl": net,
            "exit_reason": exit_reason,
            "exit_time": exit_time,
            "gap_pct": signal.get("gap_pct", 0),
            "rel_volume": signal.get("rel_volume", 0),
            "score": signal.get("score", 0),
            "market_direction": signal.get("market_direction", ""),
        })

    total_gross = sum(t["gross_pnl"] for t in trades)
    total_charges = sum(t["charges"] for t in trades)
    total_net = sum(t["net_pnl"] for t in trades)
    winners = sum(1 for t in trades if t["net_pnl"] > 0)
    losers = sum(1 for t in trades if t["net_pnl"] <= 0)

    return {
        "date": target_date,
        "trades": trades,
        "total_gross": round(total_gross, 2),
        "total_charges": round(total_charges, 2),
        "total_net": round(total_net, 2),
        "winners": winners,
        "losers": losers,
        "skipped": False,
    }


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_report(results: dict, output_path: str):
    """Generate human-readable backtest report."""

    lines = []
    lines.append("=" * 70)
    lines.append("BACKTEST REPORT — 6 Month Strategy Analysis")
    lines.append(f"Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    lines.append("=" * 70)

    for combo_key, combo_result in results.items():
        strategy = combo_result["strategy"]
        universe_name = combo_result["universe"]
        cap = combo_result["per_trade_cap"]
        days = combo_result["days"]

        all_trades = [t for d in days for t in d.get("trades", [])]
        total_net = sum(d["total_net"] for d in days)
        total_charges = sum(d["total_charges"] for d in days)
        total_gross = sum(d["total_gross"] for d in days)
        total_winners = sum(d["winners"] for d in days)
        total_losers = sum(d["losers"] for d in days)
        total_trades = total_winners + total_losers
        skipped = sum(1 for d in days if d.get("skipped"))
        trading_days = len(days) - skipped
        win_rate = (total_winners / total_trades * 100) if total_trades > 0 else 0
        pf = abs(total_gross / total_charges) if total_charges > 0 else 0

        lines.append(f"\n{'─' * 70}")
        lines.append(f"Strategy: {strategy} | Universe: {universe_name} | Cap: ₹{cap:,}")
        lines.append(f"{'─' * 70}")
        lines.append(f"  Period:         Dec 2025 — May 2026 (~6 months)")
        lines.append(f"  Trading days:   {trading_days} active / {skipped} skipped")
        lines.append(f"  Total trades:   {total_trades}")
        lines.append(f"  Win rate:       {win_rate:.1f}%  ({total_winners}W / {total_losers}L)")
        lines.append(f"  Profit factor:  {pf:.2f}")
        lines.append(f"  Total gross:    ₹{total_gross:,.2f}")
        lines.append(f"  Total charges:  ₹{total_charges:,.2f}")
        lines.append(f"  Total net:      ₹{total_net:,.2f}")
        lines.append(f"  Avg net/day:    ₹{total_net/max(trading_days,1):,.2f}")
        lines.append(f"  Avg net/trade:  ₹{total_net/max(total_trades,1):,.2f}")

        if all_trades:
            best = max(all_trades, key=lambda t: t["net_pnl"])
            worst = min(all_trades, key=lambda t: t["net_pnl"])
            lines.append(f"  Best trade:     {best['symbol']} ₹{best['net_pnl']:,.2f} ({best['exit_reason']})")
            lines.append(f"  Worst trade:    {worst['symbol']} ₹{worst['net_pnl']:,.2f} ({worst['exit_reason']})")

        # By market direction
        by_direction = {}
        for t in all_trades:
            md = t.get("market_direction", "UNKNOWN")
            if md not in by_direction:
                by_direction[md] = {"trades": 0, "net": 0, "wins": 0}
            by_direction[md]["trades"] += 1
            by_direction[md]["net"] += t["net_pnl"]
            if t["net_pnl"] > 0:
                by_direction[md]["wins"] += 1

        lines.append(f"\n  By Market Direction:")
        for md, stats in sorted(by_direction.items()):
            wr = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            lines.append(f"    {md:8}: {stats['trades']:3} trades, {wr:.0f}% WR, ₹{stats['net']:,.0f}")

        # By stock
        by_stock = {}
        for t in all_trades:
            s = t["symbol"]
            if s not in by_stock:
                by_stock[s] = {"trades": 0, "net": 0, "wins": 0}
            by_stock[s]["trades"] += 1
            by_stock[s]["net"] += t["net_pnl"]
            if t["net_pnl"] > 0:
                by_stock[s]["wins"] += 1

        lines.append(f"\n  Top 5 stocks by P&L:")
        for s, stats in sorted(by_stock.items(), key=lambda x: -x[1]["net"])[:5]:
            wr = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            lines.append(f"    {s:15}: {stats['trades']:3} trades, {wr:.0f}% WR, ₹{stats['net']:,.0f}")

        lines.append(f"\n  Bottom 5 stocks by P&L:")
        for s, stats in sorted(by_stock.items(), key=lambda x: x[1]["net"])[:5]:
            wr = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            lines.append(f"    {s:15}: {stats['trades']:3} trades, {wr:.0f}% WR, ₹{stats['net']:,.0f}")

        # VERDICT
        lines.append(f"\n  VERDICT:")
        if win_rate >= 45 and pf >= 1.3 and total_net > 0:
            lines.append(f"  ✅ DEPLOY — Edge confirmed. Win rate and profit factor meet criteria.")
        elif win_rate >= 40 and total_net > 0:
            lines.append(f"  ⚠️  PAPER ONLY — Marginal edge. Test in paper before live deployment.")
        else:
            lines.append(f"  ❌ DO NOT DEPLOY — No consistent edge found.")

    lines.append("\n" + "=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)

    report_text = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(report_text)

    print(report_text)
    return report_text


# ============================================================
# MAIN RUNNER
# ============================================================

def run():
    start_time = time.time()
    print("=" * 70)
    print("FULL 6-MONTH BACKTEST FRAMEWORK")
    print("=" * 70)
    print(f"Started: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"Strategies: {STRATEGY_VARIANTS}")
    print(f"Universes: {UNIVERSES}")
    print(f"Position sizes: {POSITION_SIZES}")

    # Load broker
    print("\n[1] Authenticating broker...")
    with open("config/profiles/vishal.yaml") as f:
        config = yaml.safe_load(f)
    from intraday.auth_server import authenticate_broker
    broker = authenticate_broker(
        broker_name="dhan",
        broker_config=config.get("dhan", {}),
        dry_run=False,
    )
    print("  ✓ Broker ready")

    # Fetch Nifty 50 index data for market direction
    print("\n[2] Fetching Nifty index data...")
    from intraday.dhan_broker import DhanBrokerClient
    nifty_data = None
    for from_d, to_d in DATE_CHUNKS:
        chunk = broker.get_historical_ohlc(
            security_id="13",
            exchange_segment="IDX_I",
            instrument="INDEX",
            interval="15",
            from_date=from_d,
            to_date=to_d,
        )
        if chunk and chunk.get("open"):
            if nifty_data is None:
                nifty_data = chunk
            else:
                for key in ["open", "high", "low", "close", "volume", "timestamp"]:
                    nifty_data[key].extend(chunk.get(key, []))
    print(f"  ✓ Nifty data: {len(nifty_data.get('open', []))} candles")

    # Run all combinations
    all_results = {}
    output_dir = Path("backtest/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    for universe_name in UNIVERSES:
        # Fetch data for this universe
        universe = get_universe(universe_name)
        historical_data = fetch_all_data(broker, universe_name)
        trading_days = get_all_trading_days(historical_data)
        print(f"\n  Universe {universe_name}: {len(trading_days)} trading days")

        for strategy in STRATEGY_VARIANTS:
            for cap in POSITION_SIZES:
                combo_key = f"{strategy}_{universe_name}_cap{cap}"
                print(f"\n[Running] {combo_key}")

                day_results = []
                for day in trading_days:
                    result = simulate_day_rules(
                        target_date=day,
                        historical_data=historical_data,
                        universe=universe,
                        nifty_data=nifty_data,
                        strategy_variant=strategy,
                        per_trade_cap=cap,
                    )
                    day_results.append(result)

                    # Progress update every 10 days
                    if len(day_results) % 10 == 0:
                        net_so_far = sum(d["total_net"] for d in day_results)
                        print(f"  Day {len(day_results)}/{len(trading_days)}: cumulative ₹{net_so_far:,.0f}")

                all_results[combo_key] = {
                    "strategy": strategy,
                    "universe": universe_name,
                    "per_trade_cap": cap,
                    "days": day_results,
                }

                # Save intermediate results
                intermediate_file = output_dir / f"intermediate_{combo_key}.json"
                with open(intermediate_file, "w") as f:
                    json.dump(all_results[combo_key], f, indent=2, default=str)

    # Generate final report
    elapsed = time.time() - start_time
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"backtest_report_{timestamp}.txt"
    json_path = output_dir / f"backtest_full_{timestamp}.json"

    print(f"\n[Final] Generating report...")
    generate_report(all_results, str(report_path))

    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nCompleted in {elapsed/60:.1f} minutes")
    print(f"Report: {report_path}")
    print(f"Data:   {json_path}")


if __name__ == "__main__":
    run()
