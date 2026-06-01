#!/usr/bin/env python3
"""
Swing backtest at Rs2,00,000 capital with market-regime day classification.

Reuses existing backtest/run_swing_backtest.py engine logic.
Classifies each entry day as UP/DOWN/SIDEWAYS using Nifty large-cap proxy.

Usage:
    .venv/bin/python scripts/backtest_swing_2L_regime.py
"""

import json
import logging
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.run_swing_backtest import (
    load_all_cached_data,
    get_trading_dates,
    build_universe_as_of_date,
    compute_charges,
    BacktestTrade,
    CHARGE_PER_SIDE,
)
from swing.scanner import scan_universe
from swing.rules_selector import select_swing_trades
from swing.models import SwingConfig

IST = timezone(timedelta(hours=5, minutes=30))
RESULTS_DIR = Path(__file__).parent.parent / "backtest" / "results"

# Large-cap proxy for Nifty regime detection
NIFTY_PROXY_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "BHARTIARTL", "SBIN", "ITC", "LT", "KOTAKBANK",
    "HINDUNILVR", "AXISBANK", "BAJFINANCE", "MARUTI", "TITAN",
    "SUNPHARMA", "NTPC", "TATAMOTORS", "WIPRO", "ADANIENT",
]

# Config overrides for Rs2L
CAPITAL = 200000
PER_TRADE_MAX = 40000
MAX_POSITIONS = 8


def classify_regime(all_data: dict, date: str) -> str:
    """Classify a trading day as UP/DOWN/SIDEWAYS using large-cap proxy.

    Computes mean daily return of NIFTY_PROXY_SYMBOLS for the given date.
    UP: > +0.4%, DOWN: < -0.4%, SIDEWAYS: between.
    """
    returns = []
    for symbol in NIFTY_PROXY_SYMBOLS:
        candles = all_data.get(symbol, [])
        # Find this date and previous date
        for i, c in enumerate(candles):
            if c.get("date") == date and i > 0:
                prev_close = candles[i - 1]["close"]
                today_close = c["close"]
                if prev_close > 0:
                    ret = (today_close - prev_close) / prev_close * 100
                    returns.append(ret)
                break

    if not returns:
        return "SIDEWAYS"

    mean_return = sum(returns) / len(returns)
    if mean_return > 0.4:
        return "UP"
    elif mean_return < -0.4:
        return "DOWN"
    return "SIDEWAYS"


def run_2L_backtest():
    """Run 3-month backtest at Rs2L with regime tagging."""
    print("=" * 60)
    print("SWING BACKTEST — Rs2,00,000 — MAX AVAILABLE (~6.5 MONTHS) — REGIME TAGGED")
    print("=" * 60)
    print()

    logging.basicConfig(level=logging.WARNING)

    print("Loading cached daily data...")
    all_data = load_all_cached_data()
    print(f"  Loaded {len(all_data)} stocks")

    # Get last 63 trading days (3 months)
    all_dates = get_trading_dates(all_data, lookback_days=300)
    trading_dates = all_dates[-138:]
    print(f"  Period: {trading_dates[0]} to {trading_dates[-1]} ({len(trading_dates)} days)")

    # Build config with 2L capital
    config = SwingConfig(
        swing_capital_limit=CAPITAL,
        swing_per_trade_max=PER_TRADE_MAX,
        swing_max_open_positions=MAX_POSITIONS,
        swing_min_score=6,
        swing_min_confidence=5,
        swing_min_rr=1.8,
    )

    # Classify each day's regime
    day_regimes = {}
    for date in trading_dates:
        day_regimes[date] = classify_regime(all_data, date)

    regime_counts = defaultdict(int)
    for r in day_regimes.values():
        regime_counts[r] += 1
    print(f"  Regime distribution: UP={regime_counts['UP']}, DOWN={regime_counts['DOWN']}, SIDEWAYS={regime_counts['SIDEWAYS']}")
    print()

    # Run backtest
    trades: list[BacktestTrade] = []
    open_positions: list[BacktestTrade] = []

    # Equity tracking
    cumulative_pnl = 0.0
    peak_pnl = 0.0
    max_drawdown = 0.0
    daily_pnl = {}  # date -> pnl realized that day

    print("Running backtest...")
    for day_idx, scan_date in enumerate(trading_dates):
        day_realized = 0.0

        # Check exits for open positions
        positions_to_close = []
        for pos in open_positions:
            symbol_candles = all_data.get(pos.symbol, [])
            today_candles = [c for c in symbol_candles if c.get("date") == scan_date]
            if not today_candles:
                continue

            today = today_candles[0]
            days_held = pos.days_held + 1
            pos.days_held = days_held

            low = today["low"]
            high = today["high"]
            close = today["close"]

            # SL check (conservative: SL before target)
            if low <= pos.sl_price:
                pos.exit_date = scan_date
                pos.exit_price = pos.sl_price
                pos.exit_reason = "STOPPED_OUT"
                positions_to_close.append(pos)
                continue

            # Target check
            if high >= pos.target_price:
                pos.exit_date = scan_date
                pos.exit_price = pos.target_price
                pos.exit_reason = "TARGET_HIT"
                positions_to_close.append(pos)
                continue

            # Time stops
            pnl_pct = ((close - pos.entry_price) / pos.entry_price) * 100
            if days_held >= 30:
                pos.exit_date, pos.exit_price, pos.exit_reason = scan_date, close, "TIME_STOP_30D"
                positions_to_close.append(pos)
            elif days_held >= 21 and pnl_pct < 3:
                pos.exit_date, pos.exit_price, pos.exit_reason = scan_date, close, "TIME_STOP_21D_LOW_PROGRESS"
                positions_to_close.append(pos)
            elif days_held >= 15 and pnl_pct < 0:
                pos.exit_date, pos.exit_price, pos.exit_reason = scan_date, close, "TIME_STOP_15D_LOSING"
                positions_to_close.append(pos)
            elif days_held >= 10 and -1 <= pnl_pct <= 1:
                pos.exit_date, pos.exit_price, pos.exit_reason = scan_date, close, "TIME_STOP_10D_FLAT"
                positions_to_close.append(pos)
            elif days_held >= 7 and pnl_pct <= -3:
                pos.exit_date, pos.exit_price, pos.exit_reason = scan_date, close, "TIME_STOP_7D_DRAWDOWN"
                positions_to_close.append(pos)

        # Close positions
        for pos in positions_to_close:
            pnl_gross = (pos.exit_price - pos.entry_price) * pos.quantity
            charges = compute_charges(pos.entry_price, pos.exit_price, pos.quantity)
            pos.pnl_gross = round(pnl_gross, 2)
            pos.pnl_after_charges = round(pnl_gross - charges, 2)
            trades.append(pos)
            open_positions.remove(pos)
            day_realized += pos.pnl_after_charges
            cumulative_pnl += pos.pnl_after_charges
            peak_pnl = max(peak_pnl, cumulative_pnl)
            max_drawdown = max(max_drawdown, peak_pnl - cumulative_pnl)

        daily_pnl[scan_date] = day_realized

        # Scan for new entries
        if len(open_positions) >= MAX_POSITIONS:
            continue

        universe = build_universe_as_of_date(all_data, scan_date)
        candidates = scan_universe(universe, min_score=config.swing_min_score)

        if candidates:
            available_slots = MAX_POSITIONS - len(open_positions)
            picks = select_swing_trades(candidates, config, live_mode=False)
            picks = picks[:available_slots]

            open_symbols = {p.symbol for p in open_positions}
            picks = [p for p in picks if p.nse_symbol not in open_symbols]

            for pick in picks:
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

        if (day_idx + 1) % 20 == 0:
            print(f"  Day {day_idx+1}/{len(trading_dates)}: {len(trades)} closed, {len(open_positions)} open, cum=₹{cumulative_pnl:.0f}")

    # Force-close remaining
    for pos in open_positions:
        symbol_candles = all_data.get(pos.symbol, [])
        if symbol_candles:
            last = symbol_candles[-1]
            pos.exit_date = last.get("date", trading_dates[-1])
            pos.exit_price = last["close"]
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
        max_drawdown = max(max_drawdown, peak_pnl - cumulative_pnl)

    # Tag each trade with entry-day regime
    for t in trades:
        t_regime = day_regimes.get(t.entry_date, "SIDEWAYS")
        # Store regime in the score field's high bits (hack: use a separate dict)
        # Actually, add to the dataclass output via a wrapper
        pass

    # Build regime-tagged trade list
    trades_with_regime = []
    for t in trades:
        td = asdict(t)
        td["regime"] = day_regimes.get(t.entry_date, "SIDEWAYS")
        trades_with_regime.append(td)

    # Compute metrics
    wins = [t for t in trades if t.pnl_after_charges > 0]
    losses = [t for t in trades if t.pnl_after_charges <= 0]
    gross_wins = sum(t.pnl_after_charges for t in wins)
    gross_losses = abs(sum(t.pnl_after_charges for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # By regime
    regime_stats = {}
    for regime in ["UP", "DOWN", "SIDEWAYS"]:
        r_trades = [t for t in trades_with_regime if t["regime"] == regime]
        r_wins = [t for t in r_trades if t["pnl_after_charges"] > 0]
        r_pnl = sum(t["pnl_after_charges"] for t in r_trades)
        regime_stats[regime] = {
            "days": regime_counts[regime],
            "trades": len(r_trades),
            "wins": len(r_wins),
            "win_rate": round(len(r_wins) / len(r_trades), 3) if r_trades else 0,
            "pnl": round(r_pnl, 2),
            "avg_per_trade": round(r_pnl / len(r_trades), 2) if r_trades else 0,
        }

    # Monthly breakdown
    monthly = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "wins": 0})
    for t in trades_with_regime:
        month = t["entry_date"][:7]  # YYYY-MM
        monthly[month]["trades"] += 1
        monthly[month]["pnl"] += t["pnl_after_charges"]
        if t["pnl_after_charges"] > 0:
            monthly[month]["wins"] += 1

    # Exit reasons
    exit_reasons = defaultdict(int)
    for t in trades:
        exit_reasons[t.exit_reason] += 1

    # Best/worst day
    best_day = max(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("", 0)
    worst_day = min(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ("", 0)

    # Build results
    results = {
        "config": {
            "capital": CAPITAL,
            "per_trade_max": PER_TRADE_MAX,
            "max_positions": MAX_POSITIONS,
            "period": f"{trading_dates[0]} to {trading_dates[-1]}",
            "trading_days": len(trading_dates),
        },
        "overall": {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades), 3) if trades else 0,
            "profit_factor": round(pf, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "pnl_pct": round(cumulative_pnl / CAPITAL * 100, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_drawdown / CAPITAL * 100, 2),
            "avg_holding_days": round(sum(t.days_held for t in trades) / len(trades), 1) if trades else 0,
            "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)},
            "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)},
            "final_capital": round(CAPITAL + cumulative_pnl, 2),
        },
        "by_regime": regime_stats,
        "monthly": {k: {"trades": v["trades"], "wins": v["wins"],
                        "pnl": round(v["pnl"], 2),
                        "wr": round(v["wins"] / v["trades"], 3) if v["trades"] else 0}
                    for k, v in sorted(monthly.items())},
        "exit_reasons": dict(exit_reasons),
        "trades_detail": trades_with_regime,
    }

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / "swing_2L_365d.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved: {output_file}")

    # Print summary
    print_summary(results)


def print_summary(r: dict):
    o = r["overall"]
    print()
    print("=" * 60)
    print("OVERALL (Rs2,00,000 capital, ~6.5 months / 138 trading days)")
    print("=" * 60)
    print(f"  Trades: {o['trades']} (W:{o['wins']} / L:{o['losses']})")
    print(f"  Win rate: {o['win_rate']*100:.1f}%")
    print(f"  Profit factor: {o['profit_factor']}")
    print(f"  Cumulative P&L: ₹{o['cumulative_pnl']:+,.0f} ({o['pnl_pct']:+.2f}%)")
    print(f"  Max drawdown: ₹{o['max_drawdown']:,.0f} ({o['max_drawdown_pct']:.2f}%)")
    print(f"  Avg holding: {o['avg_holding_days']} days")
    print(f"  Best day: {o['best_day']['date']} ₹{o['best_day']['pnl']:+,.0f}")
    print(f"  Worst day: {o['worst_day']['date']} ₹{o['worst_day']['pnl']:+,.0f}")
    print(f"  Final capital: ₹{o['final_capital']:,.0f}")
    print()

    print("─── BY DAY TYPE (KEY TABLE) ───")
    print(f"  {'Regime':<10} {'Days':<6} {'Trades':<8} {'WR%':<7} {'P&L (₹)':<12} {'Avg/trade':<10}")
    print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*7} {'-'*12} {'-'*10}")
    for regime in ["UP", "DOWN", "SIDEWAYS"]:
        s = r["by_regime"][regime]
        print(f"  {regime:<10} {s['days']:<6} {s['trades']:<8} "
              f"{s['win_rate']*100:<7.1f} ₹{s['pnl']:<+11,.0f} ₹{s['avg_per_trade']:<+9,.0f}")
    print()

    print("─── MONTHLY BREAKDOWN ───")
    for month, m in r["monthly"].items():
        wr = m["wr"] * 100
        print(f"  {month}: {m['trades']} trades, WR {wr:.0f}%, P&L ₹{m['pnl']:+,.0f}")
    print()

    print("─── EXIT REASONS ───")
    for reason, count in sorted(r["exit_reasons"].items(), key=lambda x: -x[1]):
        pct = count / o["trades"] * 100
        print(f"  {reason:<30} {count:>3} ({pct:>5.1f}%)")
    print()

    # Top 5 winners/losers
    sorted_trades = sorted(r["trades_detail"], key=lambda t: t["pnl_after_charges"], reverse=True)
    print("─── TOP 5 WINNERS ───")
    for t in sorted_trades[:5]:
        print(f"  {t['symbol']:<12} regime={t['regime']:<8} days={t['days_held']:>2} "
              f"P&L=₹{t['pnl_after_charges']:>+8,.0f} ({t['exit_reason']})")
    print()
    print("─── TOP 5 LOSERS ───")
    for t in sorted_trades[-5:]:
        print(f"  {t['symbol']:<12} regime={t['regime']:<8} days={t['days_held']:>2} "
              f"P&L=₹{t['pnl_after_charges']:>+8,.0f} ({t['exit_reason']})")
    print()


if __name__ == "__main__":
    run_2L_backtest()
