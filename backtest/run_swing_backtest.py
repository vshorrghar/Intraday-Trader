"""
Swing backtest — tests 20-DMA pullback strategy on 6 months of daily data.

Uses:
- swing/scanner.py score_swing_candidate() for signal generation
- swing/rules_selector.py select_swing_trades() for deterministic selection
- Daily OHLC from cache/swing_daily/ (fetched via Dhan Data API)

Per Rule 26: Backtest BEFORE deploy. Data from Dhan. Proof first.

Usage:
    python -m backtest.run_swing_backtest
    python -m backtest.run_swing_backtest --months 3
    python -m backtest.run_swing_backtest --output backtest/results/swing_backtest.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from swing.scanner import score_swing_candidate
from swing.rules_selector import select_swing_trades
from swing.models import SwingConfig

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = Path(__file__).parent.parent / "cache" / "swing_daily"
RESULTS_DIR = Path(__file__).parent / "results"


def _compute_charges(buy_value: float, sell_value: float) -> float:
    """Compute CNC delivery charges for swing trade.

    Breakdown:
    - Brokerage: Rs.20 per leg x 2 = Rs.40
    - STT: 0.1% on sell value
    - Exchange: 0.003% on both sides
    - GST: 18% of brokerage
    - Stamp: 0.015% on buy value
    """
    brokerage = 40.0
    stt = sell_value * 0.001
    exchange = (buy_value + sell_value) * 0.00003
    gst = brokerage * 0.18
    stamp = buy_value * 0.00015
    return round(brokerage + stt + exchange + gst + stamp, 2)


def _load_cached_data() -> dict[str, dict]:
    """Load all cached daily OHLC data from disk."""
    data = {}
    if not CACHE_DIR.exists():
        return data
    for f in CACHE_DIR.glob("*_daily.json"):
        symbol = f.stem.replace("_daily", "")
        try:
            with open(f) as fh:
                ohlc = json.load(fh)
            if len(ohlc.get("close", [])) >= 200:
                data[symbol] = ohlc
        except (json.JSONDecodeError, KeyError):
            continue
    return data


def run(
    months: int = 6,
    config: SwingConfig | None = None,
    output_file: str | None = None,
) -> dict:
    """Run swing backtest on cached daily data.

    Simulates the 20-DMA pullback strategy over the specified period.

    Args:
        months: number of months to backtest (default 6)
        config: SwingConfig (uses defaults if None)
        output_file: path to save results JSON

    Returns:
        dict with backtest results and statistics
    """
    if config is None:
        config = SwingConfig(
            swing_capital_limit=100000,
            swing_per_trade_max=10000,
            swing_max_open_positions=5,
            swing_min_score=8,
            swing_min_confidence=6,
            swing_min_rr=2.0,
            swing_max_holding_days=15,
        )

    # Load data
    universe_data = _load_cached_data()
    if not universe_data:
        print("ERROR: No cached swing data found. Run fetch_swing_data.py first.")
        return {"error": "no_data"}

    print(f"Loaded {len(universe_data)} stocks from cache")

    # Determine backtest period
    # Use the shortest data series to find common date range
    min_candles = min(len(d["close"]) for d in universe_data.values())
    backtest_days = min(months * 22, min_candles - 250)  # Need 250 for lookback

    if backtest_days <= 0:
        print("ERROR: Insufficient data for backtest. Need > 250 + backtest_days candles.")
        return {"error": "insufficient_data"}

    print(f"Backtest period: {backtest_days} trading days (~{backtest_days // 22} months)")
    print(f"Lookback: 250 days for indicators")
    print()

    # Simulate
    all_trades = []
    open_positions = []  # Track concurrent positions

    for day_offset in range(backtest_days):
        # Current day index (counting from end of data)
        day_idx = -(backtest_days - day_offset)

        # Score all stocks using data up to this day
        candidates = []
        for symbol, ohlc in universe_data.items():
            # Slice data up to current day
            end_idx = len(ohlc["close"]) + day_idx
            if end_idx < 250:
                continue

            daily_slice = {
                "open": ohlc["open"][:end_idx],
                "high": ohlc["high"][:end_idx],
                "low": ohlc["low"][:end_idx],
                "close": ohlc["close"][:end_idx],
                "volume": ohlc["volume"][:end_idx],
            }

            result = score_swing_candidate(symbol, daily_slice)
            if result and result["score"] >= config.swing_min_score:
                candidates.append(result)

        # Check open positions for exit
        positions_to_close = []
        for pos in open_positions:
            pos_symbol = pos["symbol"]
            if pos_symbol not in universe_data:
                continue
            ohlc = universe_data[pos_symbol]
            end_idx = len(ohlc["close"]) + day_idx
            if end_idx >= len(ohlc["close"]):
                continue

            today_high = ohlc["high"][end_idx]
            today_low = ohlc["low"][end_idx]
            today_close = ohlc["close"][end_idx]
            pos["days_held"] += 1

            # Check target hit
            if today_high >= pos["target_price"]:
                pos["exit_price"] = pos["target_price"]
                pos["exit_reason"] = "TARGET_HIT"
                positions_to_close.append(pos)
            # Check stop loss hit
            elif today_low <= pos["stop_loss_price"]:
                pos["exit_price"] = pos["stop_loss_price"]
                pos["exit_reason"] = "STOPPED_OUT"
                positions_to_close.append(pos)
            # Check time stop
            elif pos["days_held"] >= config.swing_max_holding_days:
                pos["exit_price"] = today_close
                pos["exit_reason"] = "TIME_EXIT"
                positions_to_close.append(pos)

        # Close positions
        for pos in positions_to_close:
            open_positions.remove(pos)
            buy_value = pos["entry_price"] * pos["quantity"]
            sell_value = pos["exit_price"] * pos["quantity"]
            gross_pnl = (pos["exit_price"] - pos["entry_price"]) * pos["quantity"]
            charges = _compute_charges(buy_value, sell_value)
            net_pnl = gross_pnl - charges

            all_trades.append({
                "symbol": pos["symbol"],
                "entry_price": pos["entry_price"],
                "exit_price": pos["exit_price"],
                "quantity": pos["quantity"],
                "days_held": pos["days_held"],
                "gross_pnl": round(gross_pnl, 2),
                "charges": round(charges, 2),
                "net_pnl": round(net_pnl, 2),
                "exit_reason": pos["exit_reason"],
                "score": pos["score"],
                "rr": pos["rr"],
                "strategy_type": pos["strategy_type"],
            })

        # Select new trades (only if we have capacity)
        available_slots = config.swing_max_open_positions - len(open_positions)
        if available_slots > 0 and candidates:
            # Temporarily reduce max_positions to available slots
            temp_config = SwingConfig(
                swing_capital_limit=config.swing_capital_limit,
                swing_per_trade_max=config.swing_per_trade_max,
                swing_max_open_positions=available_slots,
                swing_min_score=config.swing_min_score,
                swing_min_confidence=config.swing_min_confidence,
                swing_min_rr=config.swing_min_rr,
                swing_max_holding_days=config.swing_max_holding_days,
            )
            selected = select_swing_trades(candidates, temp_config)

            for trade in selected:
                # Check not already in position for this symbol
                if any(p["symbol"] == trade.nse_symbol for p in open_positions):
                    continue

                # Entry at next day's open (simulate real execution)
                sym_ohlc = universe_data.get(trade.nse_symbol)
                if sym_ohlc is None:
                    continue
                next_day_idx = len(sym_ohlc["close"]) + day_idx + 1
                if next_day_idx >= len(sym_ohlc["open"]):
                    continue

                entry_price = sym_ohlc["open"][next_day_idx]
                if entry_price <= 0:
                    continue

                # Recalculate SL/target based on actual entry (not close)
                sl_distance = trade.entry_price - trade.stop_loss_price
                sl_pct = sl_distance / trade.entry_price
                stop_loss = entry_price * (1 - sl_pct)
                target = entry_price * (1 + sl_pct * 2.5)

                open_positions.append({
                    "symbol": trade.nse_symbol,
                    "entry_price": round(entry_price, 2),
                    "target_price": round(target, 2),
                    "stop_loss_price": round(stop_loss, 2),
                    "quantity": trade.quantity,
                    "days_held": 0,
                    "score": candidates[0]["score"] if candidates else 0,
                    "rr": round((target - entry_price) / (entry_price - stop_loss), 2) if entry_price > stop_loss else 0,
                    "strategy_type": trade.strategy_type,
                })

    # Force close any remaining open positions at last available price
    for pos in open_positions:
        ohlc = universe_data.get(pos["symbol"])
        if ohlc:
            exit_price = ohlc["close"][-1]
            buy_value = pos["entry_price"] * pos["quantity"]
            sell_value = exit_price * pos["quantity"]
            gross_pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
            charges = _compute_charges(buy_value, sell_value)
            all_trades.append({
                "symbol": pos["symbol"],
                "entry_price": pos["entry_price"],
                "exit_price": round(exit_price, 2),
                "quantity": pos["quantity"],
                "days_held": pos["days_held"],
                "gross_pnl": round(gross_pnl, 2),
                "charges": round(charges, 2),
                "net_pnl": round(gross_pnl - charges, 2),
                "exit_reason": "BACKTEST_END",
                "score": pos["score"],
                "rr": pos["rr"],
                "strategy_type": pos["strategy_type"],
            })

    # Compute statistics
    stats = _compute_stats(all_trades, config)

    # Save results
    if output_file:
        out_path = Path(output_file)
    else:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"swing_backtest_{ts}.json"

    results = {
        "generated_at": datetime.now(IST).isoformat(),
        "config": {
            "months": months,
            "capital": config.swing_capital_limit,
            "per_trade_max": config.swing_per_trade_max,
            "max_positions": config.swing_max_open_positions,
            "min_score": config.swing_min_score,
            "min_rr": config.swing_min_rr,
            "max_holding_days": config.swing_max_holding_days,
        },
        "stats": stats,
        "trades": all_trades,
    }

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Print report
    _print_report(stats, all_trades)

    return results


def _compute_stats(trades: list[dict], config: SwingConfig) -> dict:
    """Compute backtest statistics."""
    if not trades:
        return {"total_trades": 0, "verdict": "NO_DATA"}

    total = len(trades)
    winners = [t for t in trades if t["net_pnl"] > 0]
    losers = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = len(winners) / total * 100 if total > 0 else 0

    total_gross = sum(t["gross_pnl"] for t in trades)
    total_charges = sum(t["charges"] for t in trades)
    total_net = sum(t["net_pnl"] for t in trades)

    avg_win = sum(t["net_pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["net_pnl"] for t in losers) / len(losers) if losers else 0
    avg_days = sum(t["days_held"] for t in trades) / total if total > 0 else 0

    gross_wins = sum(t["net_pnl"] for t in winners)
    gross_losses = abs(sum(t["net_pnl"] for t in losers))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Verdict
    if win_rate >= 45 and profit_factor >= 1.3:
        verdict = "DEPLOY"
    elif win_rate >= 40 and profit_factor >= 1.1:
        verdict = "PAPER_ONLY"
    else:
        verdict = "DO_NOT_DEPLOY"

    # By exit reason
    by_exit = {}
    for t in trades:
        reason = t["exit_reason"]
        if reason not in by_exit:
            by_exit[reason] = {"count": 0, "net_pnl": 0}
        by_exit[reason]["count"] += 1
        by_exit[reason]["net_pnl"] += t["net_pnl"]

    # Top/bottom stocks
    stock_pnl = {}
    for t in trades:
        sym = t["symbol"]
        stock_pnl[sym] = stock_pnl.get(sym, 0) + t["net_pnl"]
    sorted_stocks = sorted(stock_pnl.items(), key=lambda x: x[1], reverse=True)
    top_10 = sorted_stocks[:10]
    bottom_5 = sorted_stocks[-5:]

    return {
        "total_trades": total,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_gross_pnl": round(total_gross, 2),
        "total_charges": round(total_charges, 2),
        "total_net_pnl": round(total_net, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_days_held": round(avg_days, 1),
        "by_exit_reason": {k: {"count": v["count"], "net_pnl": round(v["net_pnl"], 2)} for k, v in by_exit.items()},
        "top_10_stocks": [{"symbol": s, "net_pnl": round(p, 2)} for s, p in top_10],
        "bottom_5_stocks": [{"symbol": s, "net_pnl": round(p, 2)} for s, p in bottom_5],
        "verdict": verdict,
    }


def _print_report(stats: dict, trades: list[dict]):
    """Print human-readable backtest report."""
    print("\n" + "=" * 60)
    print("SWING BACKTEST REPORT — 20-DMA Pullback Strategy")
    print("=" * 60)
    print(f"\n  Total trades:     {stats['total_trades']}")
    print(f"  Win rate:         {stats['win_rate_pct']}%")
    print(f"  Profit factor:    {stats['profit_factor']}")
    print(f"  Avg days held:    {stats['avg_days_held']}")
    print(f"\n  Total gross P&L:  Rs.{stats['total_gross_pnl']:,.2f}")
    print(f"  Total charges:    Rs.{stats['total_charges']:,.2f}")
    print(f"  Total net P&L:    Rs.{stats['total_net_pnl']:,.2f}")
    print(f"\n  Avg winner:       Rs.{stats['avg_win']:,.2f}")
    print(f"  Avg loser:        Rs.{stats['avg_loss']:,.2f}")

    print(f"\n  Exit reasons:")
    for reason, data in stats.get("by_exit_reason", {}).items():
        print(f"    {reason}: {data['count']} trades, Rs.{data['net_pnl']:,.2f}")

    print(f"\n  Top 5 stocks:")
    for item in stats.get("top_10_stocks", [])[:5]:
        print(f"    {item['symbol']}: Rs.{item['net_pnl']:,.2f}")

    print(f"\n  Bottom 5 stocks:")
    for item in stats.get("bottom_5_stocks", []):
        print(f"    {item['symbol']}: Rs.{item['net_pnl']:,.2f}")

    print(f"\n  {'=' * 40}")
    print(f"  VERDICT: {stats['verdict']}")
    print(f"  {'=' * 40}")
    if stats["verdict"] == "DEPLOY":
        print("  Strategy shows edge. Ready for paper trading.")
    elif stats["verdict"] == "PAPER_ONLY":
        print("  Marginal edge. Paper trade for 1 month before live.")
    else:
        print("  No edge detected. Do NOT deploy. Investigate parameters.")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run swing backtest")
    parser.add_argument("--months", type=int, default=6, help="Months to backtest")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)  # Suppress scanner debug logs

    print("Swing Backtest — 20-DMA Pullback Strategy")
    print(f"Period: {args.months} months")
    print()

    run(months=args.months, output_file=args.output)


if __name__ == "__main__":
    main()
