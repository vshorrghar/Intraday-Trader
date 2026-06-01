"""
Swing strategy historical backtest.

Replays the swing scanner + rules_selector over cached daily OHLC data.
Strict no-future-leak: each scan day only sees candles up to that date.
Entry: at latest_close on scan day (same-day entry, matching rules_selector).
Exit: walk forward day-by-day checking SL, target, time stops.
Charges: 0.1% per side (delivery brokerage estimate).

Usage:
    .venv/bin/python backtest/run_swing_backtest.py
    .venv/bin/python backtest/run_swing_backtest.py --lookback 90
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from swing.scanner import scan_universe, score_swing_candidate
from swing.rules_selector import select_swing_trades
from swing.models import SwingConfig
from swing.sector_map import SECTOR_MAP
from swing.data_loader import CACHE_DIR

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
RESULTS_DIR = Path(__file__).parent / "results"
CHARGE_PER_SIDE = 0.001  # 0.1% per side


@dataclass
class BacktestTrade:
    symbol: str
    entry_date: str
    entry_price: float
    sl_price: float
    target_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    days_held: int = 0
    pnl_gross: float = 0.0
    pnl_after_charges: float = 0.0
    score: int = 0
    quantity: int = 1


def load_all_cached_data() -> dict[str, list[dict]]:
    """Load all cached daily candles. Returns {symbol: [candle_dicts]}."""
    all_data = {}
    if not CACHE_DIR.exists():
        return all_data

    for f in CACHE_DIR.glob("*.json"):
        symbol = f.stem
        try:
            with open(f) as fh:
                data = json.load(fh)
            candles = data.get("candles", [])
            if len(candles) >= 200:
                all_data[symbol] = candles
        except (json.JSONDecodeError, OSError):
            continue

    return all_data


def get_trading_dates(all_data: dict[str, list[dict]], lookback_days: int = 125) -> list[str]:
    """Extract sorted list of unique trading dates from cached data.

    Returns the last `lookback_days` trading dates available.
    """
    dates = set()
    for candles in all_data.values():
        for c in candles:
            d = c.get("date", "")
            if d:
                dates.add(d)

    sorted_dates = sorted(dates)
    # Return last N trading dates
    if len(sorted_dates) > lookback_days:
        return sorted_dates[-lookback_days:]
    return sorted_dates


def build_universe_as_of_date(
    all_data: dict[str, list[dict]],
    scan_date: str,
) -> dict[str, dict]:
    """Build scanner-format universe using only data up to (and including) scan_date.

    Returns {symbol: {open: [...], high: [...], low: [...], close: [...], volume: [...]}}
    Only includes data points with date <= scan_date. Strict no-future-leak.
    """
    universe = {}
    for symbol, candles in all_data.items():
        # Filter to candles on or before scan_date
        filtered = [c for c in candles if c.get("date", "") <= scan_date]
        if len(filtered) < 200:
            continue

        universe[symbol] = {
            "open": [c["open"] for c in filtered],
            "high": [c["high"] for c in filtered],
            "low": [c["low"] for c in filtered],
            "close": [c["close"] for c in filtered],
            "volume": [c["volume"] for c in filtered],
        }

    return universe


def get_candles_after_date(candles: list[dict], entry_date: str) -> list[dict]:
    """Get candles strictly after entry_date for forward simulation."""
    return [c for c in candles if c.get("date", "") > entry_date]


def simulate_exit(
    forward_candles: list[dict],
    entry_price: float,
    sl_price: float,
    target_price: float,
    entry_date: str,
) -> tuple[str, float, str, int]:
    """Walk forward day-by-day to find exit.

    Returns: (exit_date, exit_price, exit_reason, days_held)
    """
    for i, candle in enumerate(forward_candles):
        days_held = i + 1
        low = candle["low"]
        high = candle["high"]
        close = candle["close"]
        date = candle.get("date", "")

        # Check SL hit (conservative: check SL before target on same day)
        if low <= sl_price:
            return (date, sl_price, "STOPPED_OUT", days_held)

        # Check target hit
        if high >= target_price:
            return (date, target_price, "TARGET_HIT", days_held)

        # Time stops (using close price for P&L calculation)
        pnl_pct = ((close - entry_price) / entry_price) * 100

        if days_held >= 30:
            return (date, close, "TIME_STOP_30D", days_held)
        if days_held >= 21 and pnl_pct < 3:
            return (date, close, "TIME_STOP_21D_LOW_PROGRESS", days_held)
        if days_held >= 15 and pnl_pct < 0:
            return (date, close, "TIME_STOP_15D_LOSING", days_held)
        if days_held >= 10 and -1 <= pnl_pct <= 1:
            return (date, close, "TIME_STOP_10D_FLAT", days_held)
        if days_held >= 7 and pnl_pct <= -3:
            return (date, close, "TIME_STOP_7D_DRAWDOWN", days_held)

    # Ran out of data — exit at last available close
    if forward_candles:
        last = forward_candles[-1]
        return (last.get("date", ""), last["close"], "DATA_END", len(forward_candles))

    return (entry_date, entry_price, "NO_DATA", 0)


def compute_charges(entry_price: float, exit_price: float, quantity: int) -> float:
    """Compute round-trip charges at 0.1% per side."""
    buy_charges = entry_price * quantity * CHARGE_PER_SIDE
    sell_charges = exit_price * quantity * CHARGE_PER_SIDE
    return buy_charges + sell_charges


def run_backtest(lookback_days: int = 125, max_positions: int = 8) -> dict:
    """Run the full swing backtest.

    Args:
        lookback_days: Number of trading days to backtest over.
        max_positions: Max concurrent positions (matches SwingConfig default).

    Returns:
        Full results dict with metrics and trade details.
    """
    print("Loading cached daily data...")
    all_data = load_all_cached_data()
    print(f"  Loaded {len(all_data)} stocks with >= 200 candles")

    if len(all_data) < 100:
        print("ERROR: Insufficient data. Need at least 100 stocks.")
        sys.exit(1)

    trading_dates = get_trading_dates(all_data, lookback_days)
    print(f"  Trading dates: {len(trading_dates)} ({trading_dates[0]} to {trading_dates[-1]})")

    config = SwingConfig()
    trades: list[BacktestTrade] = []
    open_positions: list[BacktestTrade] = []
    entries_per_day: dict[str, int] = {}

    # Track equity curve for drawdown
    cumulative_pnl = 0.0
    peak_pnl = 0.0
    max_drawdown = 0.0

    print(f"\nRunning backtest over {len(trading_dates)} trading days...")
    print(f"  Config: min_score={config.swing_min_score}, max_positions={max_positions}")
    print()

    for day_idx, scan_date in enumerate(trading_dates):
        # First, check exits for open positions
        positions_to_close = []
        for pos in open_positions:
            symbol_candles = all_data.get(pos.symbol, [])
            # Get candle for today
            today_candles = [c for c in symbol_candles if c.get("date", "") == scan_date]
            if not today_candles:
                continue

            today = today_candles[0]
            days_held = pos.days_held + 1
            pos.days_held = days_held

            low = today["low"]
            high = today["high"]
            close = today["close"]

            # Check SL (conservative: SL before target)
            if low <= pos.sl_price:
                pos.exit_date = scan_date
                pos.exit_price = pos.sl_price
                pos.exit_reason = "STOPPED_OUT"
                positions_to_close.append(pos)
                continue

            # Check target
            if high >= pos.target_price:
                pos.exit_date = scan_date
                pos.exit_price = pos.target_price
                pos.exit_reason = "TARGET_HIT"
                positions_to_close.append(pos)
                continue

            # Time stops
            pnl_pct = ((close - pos.entry_price) / pos.entry_price) * 100

            if days_held >= 30:
                pos.exit_date = scan_date
                pos.exit_price = close
                pos.exit_reason = "TIME_STOP_30D"
                positions_to_close.append(pos)
            elif days_held >= 21 and pnl_pct < 3:
                pos.exit_date = scan_date
                pos.exit_price = close
                pos.exit_reason = "TIME_STOP_21D_LOW_PROGRESS"
                positions_to_close.append(pos)
            elif days_held >= 15 and pnl_pct < 0:
                pos.exit_date = scan_date
                pos.exit_price = close
                pos.exit_reason = "TIME_STOP_15D_LOSING"
                positions_to_close.append(pos)
            elif days_held >= 10 and -1 <= pnl_pct <= 1:
                pos.exit_date = scan_date
                pos.exit_price = close
                pos.exit_reason = "TIME_STOP_10D_FLAT"
                positions_to_close.append(pos)
            elif days_held >= 7 and pnl_pct <= -3:
                pos.exit_date = scan_date
                pos.exit_price = close
                pos.exit_reason = "TIME_STOP_7D_DRAWDOWN"
                positions_to_close.append(pos)

        # Close positions and compute P&L
        for pos in positions_to_close:
            pnl_gross = (pos.exit_price - pos.entry_price) * pos.quantity
            charges = compute_charges(pos.entry_price, pos.exit_price, pos.quantity)
            pos.pnl_gross = round(pnl_gross, 2)
            pos.pnl_after_charges = round(pnl_gross - charges, 2)
            trades.append(pos)
            open_positions.remove(pos)

            # Update equity curve
            cumulative_pnl += pos.pnl_after_charges
            peak_pnl = max(peak_pnl, cumulative_pnl)
            drawdown = peak_pnl - cumulative_pnl
            max_drawdown = max(max_drawdown, drawdown)

        # Now scan for new entries (only if we have capacity)
        if len(open_positions) >= max_positions:
            continue

        # Build universe as of this date (no future leak)
        universe = build_universe_as_of_date(all_data, scan_date)

        # Run scanner
        candidates = scan_universe(universe, min_score=config.swing_min_score)

        # Run rules_selector
        available_slots = max_positions - len(open_positions)
        if candidates and available_slots > 0:
            picks = select_swing_trades(candidates, config, live_mode=False)
            picks = picks[:available_slots]

            # Filter out symbols already in open positions
            open_symbols = {p.symbol for p in open_positions}
            picks = [p for p in picks if p.nse_symbol not in open_symbols]

            day_entries = 0
            for pick in picks:
                # Entry at latest_close (same-day entry)
                new_trade = BacktestTrade(
                    symbol=pick.nse_symbol,
                    entry_date=scan_date,
                    entry_price=pick.entry_price,
                    sl_price=pick.stop_loss_price,
                    target_price=pick.target_price,
                    score=pick.confidence_score,
                    quantity=pick.quantity,
                    days_held=0,
                )
                open_positions.append(new_trade)
                day_entries += 1

            if day_entries > 0:
                entries_per_day[scan_date] = entries_per_day.get(scan_date, 0) + day_entries

        # Progress every 25 days
        if (day_idx + 1) % 25 == 0:
            print(f"  Day {day_idx + 1}/{len(trading_dates)}: "
                  f"{len(trades)} closed, {len(open_positions)} open, "
                  f"cumPnL=₹{cumulative_pnl:.0f}")

    # Force-close any remaining open positions at last available price
    for pos in open_positions:
        symbol_candles = all_data.get(pos.symbol, [])
        if symbol_candles:
            last_candle = symbol_candles[-1]
            pos.exit_date = last_candle.get("date", trading_dates[-1])
            pos.exit_price = last_candle["close"]
        else:
            pos.exit_date = trading_dates[-1]
            pos.exit_price = pos.entry_price
        pos.exit_reason = "DATA_END"
        pnl_gross = (pos.exit_price - pos.entry_price) * pos.quantity
        charges = compute_charges(pos.entry_price, pos.exit_price, pos.quantity)
        pos.pnl_gross = round(pnl_gross, 2)
        pos.pnl_after_charges = round(pnl_gross - charges, 2)
        trades.append(pos)
        cumulative_pnl += pos.pnl_after_charges
        peak_pnl = max(peak_pnl, cumulative_pnl)
        drawdown = peak_pnl - cumulative_pnl
        max_drawdown = max(max_drawdown, drawdown)

    # Compute metrics
    wins = [t for t in trades if t.pnl_after_charges > 0]
    losses = [t for t in trades if t.pnl_after_charges <= 0]
    gross_wins = sum(t.pnl_after_charges for t in wins)
    gross_losses = abs(sum(t.pnl_after_charges for t in losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    avg_holding = sum(t.days_held for t in trades) / len(trades) if trades else 0
    max_holding = max((t.days_held for t in trades), default=0)

    entries_values = list(entries_per_day.values()) if entries_per_day else [0]
    max_entries_single_day = max(entries_values)
    total_entry_days = len(entries_per_day)
    entries_per_day_avg = sum(entries_values) / total_entry_days if total_entry_days > 0 else 0

    # Exit reason distribution
    exit_reasons = {}
    for t in trades:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    metrics = {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 3) if trades else 0,
        "profit_factor": round(profit_factor, 2),
        "cumulative_pnl": round(cumulative_pnl, 2),
        "max_drawdown": round(max_drawdown, 2),
        "avg_holding_days": round(avg_holding, 1),
        "max_holding_days": max_holding,
        "entries_per_day_avg": round(entries_per_day_avg, 2),
        "max_entries_single_day": max_entries_single_day,
    }

    results = {
        "period": f"{trading_dates[0]} to {trading_dates[-1]}",
        "data_source": str(CACHE_DIR),
        "universe_size": len(all_data),
        "metrics": metrics,
        "exit_reasons": exit_reasons,
        "trades_detail": [asdict(t) for t in trades],
    }

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Swing strategy backtest")
    parser.add_argument("--lookback", type=int, default=125, help="Trading days to backtest")
    parser.add_argument("--max-positions", type=int, default=8, help="Max concurrent positions")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,  # Suppress scanner/selector INFO spam
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("SWING STRATEGY BACKTEST")
    print("=" * 60)
    print()

    results = run_backtest(lookback_days=args.lookback, max_positions=args.max_positions)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    output_file = RESULTS_DIR / f"swing_backtest_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_file}")

    # Print summary
    m = results["metrics"]
    print()
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Period: {results['period']}")
    print(f"  Universe: {results['universe_size']} stocks")
    print(f"  Trades: {m['trades']}")
    print(f"  Wins: {m['wins']} | Losses: {m['losses']}")
    print(f"  Win rate: {m['win_rate']*100:.1f}%")
    print(f"  Profit factor: {m['profit_factor']}")
    print(f"  Cumulative P&L: ₹{m['cumulative_pnl']:.0f}")
    print(f"  Max drawdown: ₹{m['max_drawdown']:.0f}")
    print(f"  Avg holding: {m['avg_holding_days']} days")
    print(f"  Max entries/day: {m['max_entries_single_day']}")
    print()
    print("  Exit reasons:")
    for reason, count in sorted(results["exit_reasons"].items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count}")
    print()

    # Pass/fail criteria
    print("=" * 60)
    print("PASS CRITERIA CHECK")
    print("=" * 60)
    criteria = [
        ("Trades >= 30", m["trades"] >= 30),
        ("Win rate >= 45%", m["win_rate"] >= 0.45),
        ("Profit factor >= 1.3", m["profit_factor"] >= 1.3),
        ("Max drawdown <= ₹3,000", m["max_drawdown"] <= 3000),
        ("Max entries/day <= 5", m["max_entries_single_day"] <= 5),
    ]
    passed = 0
    for name, result in criteria:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} — {name}")
        if result:
            passed += 1

    print(f"\n  Result: {passed}/5 criteria met")

    if passed == 5:
        print("  DECISION: SHIP")
    elif passed == 4:
        print("  DECISION: SHIP-WITH-NOTES")
    elif passed == 3:
        print("  DECISION: SHIP-LIMITED")
    else:
        print("  DECISION: KILL")

    print("=" * 60)


if __name__ == "__main__":
    main()
