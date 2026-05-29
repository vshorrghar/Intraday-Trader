#!/usr/bin/env python3
"""Backtest VWAP Mean Reversion strategy on historical 15-min data.

Uses cached intraday data from cache/historical_90d/.
Filters to RANGING regime days only.
Outputs results to backtest/results/vwap_mr_v3.json.
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from intraday.v3.regime import classify_regime
from intraday.v3.strategies.vwap_mean_reversion import (
    detect_vwap_mr_signals, _get_candles_columnar, _calculate_vwap_columnar,
    TIME_STOP_CANDLES,
)

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = ROOT / "cache" / "historical_90d"
OUTPUT_PATH = ROOT / "backtest" / "results" / "vwap_mr_v3.json"

# Backtest config
POSITION_SIZE = 10000
CHARGES_PER_TRADE = 60  # Rs per round trip
SLIPPAGE_PCT = 0.05     # 0.05%


def load_all_data():
    """Load all 15-min OHLC from cache."""
    data = {}
    if not CACHE_DIR.exists():
        print(f"ERROR: {CACHE_DIR} not found")
        sys.exit(1)

    files = list(CACHE_DIR.glob("*_15min_*.json"))
    print(f"Loading {len(files)} cached files...")

    for f in files:
        symbol = f.name.split("_15min_")[0]
        try:
            d = json.loads(f.read_text())
            if isinstance(d, dict) and d.get("open"):
                data[symbol] = d
        except:
            pass

    print(f"Loaded {len(data)} stocks with valid data")
    return data


def get_trading_dates(data: dict) -> list:
    """Extract unique trading dates from data."""
    dates = set()
    # Sample from first stock
    for symbol, ohlc in list(data.items())[:1]:
        timestamps = ohlc.get("start_Time", ohlc.get("timestamp", []))
        for ts in timestamps:
            if isinstance(ts, (int, float)) and ts > 1000000000:
                dt = datetime.fromtimestamp(ts, tz=IST)
                if dt.weekday() < 5:  # Mon-Fri
                    dates.add(dt.strftime("%Y-%m-%d"))
    return sorted(dates)


def estimate_regime_for_date(data: dict, date: str) -> str:
    """Estimate regime from available data (simplified for backtest).

    Uses NIFTY proxy: average change of top 50 stocks as breadth proxy.
    """
    up_count = 0
    total = 0
    changes = []

    for symbol, ohlc in list(data.items())[:100]:
        candles = _get_candles_columnar(ohlc, date)
        if not candles or len(candles) < 4:
            continue
        first_open = candles[0]["open"]
        # Use candle at 10:15 (index 4) for regime check
        check_idx = min(4, len(candles) - 1)
        check_close = candles[check_idx]["close"]
        if first_open > 0:
            change = (check_close - first_open) / first_open * 100
            changes.append(change)
            if check_close > first_open:
                up_count += 1
            total += 1

    if total == 0:
        return "UNCLEAR"

    breadth = (up_count / total) * 100
    avg_change = sum(changes) / len(changes) if changes else 0

    # Simplified regime (no VIX in backtest — assume normal)
    result = classify_regime(
        nifty_change_pct=avg_change,
        nifty_30min_range_pct=0.5,  # Assume normal range
        breadth_pct=breadth,
        vix=16,  # Assume normal VIX for backtest
    )
    return result["regime"]


def simulate_trade(candles: list, signal: dict) -> dict:
    """Simulate a single VWAP MR trade from entry to exit."""
    entry_idx = signal["entry_candle_idx"]
    entry_price = signal["entry_price"]
    stop_loss = signal["stop_loss"]
    target = signal["target"]
    time_stop = signal.get("time_stop_candles", TIME_STOP_CANDLES)

    # Apply slippage on entry
    entry_price_actual = entry_price * (1 + SLIPPAGE_PCT / 100)
    qty = max(1, int(POSITION_SIZE / entry_price_actual))

    exit_price = None
    exit_reason = None
    holding_candles = 0

    for i in range(entry_idx + 1, min(entry_idx + time_stop + 1, len(candles))):
        holding_candles += 1
        candle = candles[i]

        # Check stop loss (hit during candle)
        if candle["low"] <= stop_loss:
            exit_price = stop_loss
            exit_reason = "STOPPED_OUT"
            break

        # Check target (hit during candle)
        if candle["high"] >= target:
            exit_price = target
            exit_reason = "TARGET_HIT"
            break

    # Time stop
    if exit_price is None:
        last_idx = min(entry_idx + time_stop, len(candles) - 1)
        exit_price = candles[last_idx]["close"]
        exit_reason = "TIME_STOP"
        holding_candles = time_stop

    # Apply slippage on exit
    exit_price_actual = exit_price * (1 - SLIPPAGE_PCT / 100)

    gross_pnl = (exit_price_actual - entry_price_actual) * qty
    net_pnl = gross_pnl - CHARGES_PER_TRADE

    return {
        "symbol": signal["symbol"],
        "entry_price": round(entry_price_actual, 2),
        "exit_price": round(exit_price_actual, 2),
        "qty": qty,
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "exit_reason": exit_reason,
        "holding_candles": holding_candles,
        "holding_minutes": holding_candles * 15,
    }


def main():
    print("=" * 60)
    print("VWAP MEAN REVERSION BACKTEST")
    print("=" * 60)

    data = load_all_data()
    dates = get_trading_dates(data)
    print(f"Trading dates available: {len(dates)} ({dates[0]} to {dates[-1]})")

    # Universe = all loaded symbols
    universe = {sym: sym for sym in data.keys()}
    config = {"per_trade_max_capital": POSITION_SIZE}

    ranging_days = 0
    all_trades = []

    for date in dates:
        regime = estimate_regime_for_date(data, date)
        if regime != "RANGING":
            continue

        ranging_days += 1
        signals = detect_vwap_mr_signals(
            historical_data=data,
            universe=universe,
            config=config,
            target_date=date,
            regime="RANGING",
        )

        # Take top 3 signals by score
        signals_sorted = sorted(signals, key=lambda s: s.get("score", 0), reverse=True)[:3]

        for signal in signals_sorted:
            candles = _get_candles_columnar(data[signal["symbol"]], date)
            if not candles:
                continue
            trade = simulate_trade(candles, signal)
            trade["date"] = date
            all_trades.append(trade)

    # Compute metrics
    total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t["net_pnl"] > 0)
    losses = total_trades - wins
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    gross_profits = sum(t["net_pnl"] for t in all_trades if t["net_pnl"] > 0)
    gross_losses = abs(sum(t["net_pnl"] for t in all_trades if t["net_pnl"] <= 0))
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else float("inf")

    cumulative_pnl = sum(t["net_pnl"] for t in all_trades)

    # Max drawdown
    running = 0
    peak = 0
    max_dd = 0
    for t in all_trades:
        running += t["net_pnl"]
        peak = max(peak, running)
        dd = peak - running
        max_dd = max(max_dd, dd)

    avg_holding = (sum(t["holding_minutes"] for t in all_trades) / total_trades) if total_trades > 0 else 0

    # Decision gate
    if total_trades >= 30 and win_rate >= 50 and profit_factor >= 1.3:
        decision = "SHIP_CONFIDENT"
        next_action = "Wire into router. Paper for 5 days. Then go live."
    elif total_trades >= 30 and win_rate >= 45 and profit_factor >= 1.1:
        decision = "SHIP_CAUTIOUS"
        next_action = "Wire into router (paper-only). Run 10 days. Review."
    elif total_trades >= 30 and win_rate >= 40 and profit_factor >= 1.0:
        decision = "TEST_LIMITED"
        next_action = "Wire with reduced position size (Rs.5,000). Paper 14 days."
    elif total_trades < 30:
        decision = "INSUFFICIENT_DATA"
        next_action = "Insufficient backtest data. Ship to paper anyway with small size."
    else:
        decision = "KILL"
        next_action = "Don't wire. V3 ships with V6+V4 only."

    reasoning = (
        f"{total_trades} trades over {ranging_days} RANGING days. "
        f"WR={win_rate:.1f}%, PF={profit_factor:.2f}, "
        f"Cumulative={cumulative_pnl:.0f}, MaxDD={max_dd:.0f}"
    )

    # Print results
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Period: {dates[0]} to {dates[-1]}")
    print(f"  Total trading days: {len(dates)}")
    print(f"  RANGING days: {ranging_days}")
    print(f"  Trades: {total_trades}")
    print(f"  Wins: {wins} | Losses: {losses}")
    print(f"  Win Rate: {win_rate:.1f}%")
    print(f"  Profit Factor: {profit_factor:.2f}")
    print(f"  Cumulative P&L: Rs.{cumulative_pnl:.0f}")
    print(f"  Max Drawdown: Rs.{max_dd:.0f}")
    print(f"  Avg Holding: {avg_holding:.0f} min")
    print(f"\n  DECISION: {decision}")
    print(f"  NEXT ACTION: {next_action}")
    print(f"  REASONING: {reasoning}")

    # Save results
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "strategy": "VWAP_MEAN_REVERSION",
        "period": f"{dates[0]} to {dates[-1]}",
        "data_source": "intraday cache (15-min candles, 90 days)",
        "ranging_days_count": ranging_days,
        "total_trading_days": len(dates),
        "metrics": {
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "max_drawdown": round(max_dd, 2),
            "avg_holding_minutes": round(avg_holding, 1),
        },
        "decision": decision,
        "reasoning": reasoning,
        "next_action": next_action,
        "trades_detail": all_trades[:50],  # First 50 for inspection
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\n  Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
