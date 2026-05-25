#!/usr/bin/env python3
"""
Multi-strategy swing backtest — tests 6 proven approaches from swing trading legends.

Strategies tested:
1. CRABEL (Larry Connors): RSI(2) < 5 on stocks above 200-DMA. Aggressive oversold.
2. PULLBACK_TIGHT: 20-DMA pullback with tight SL (ATR-based), wide target (3:1)
3. PULLBACK_WIDE: Same but wider SL (2×ATR), moderate target (2:1), higher WR
4. DEFENSIVE_ONLY: Only pharma/FMCG/IT stocks (proven winners from backtest)
5. HIGH_SCORE_ONLY: Score >= 10 (very selective, highest quality setups)
6. VOLUME_SURGE: Relative volume > 2x + near 20-DMA (institutional interest)

All use the same scanner but different selector parameters.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.run_swing_backtest import _load_cached_data, _compute_charges, _compute_stats
from swing.scanner import score_swing_candidate
from swing.models import SwingConfig, SwingTradeSetup

IST = timezone(timedelta(hours=5, minutes=30))

# Strategy configurations
STRATEGIES = {
    "CRABEL_RSI2": {
        "description": "Larry Connors RSI(2) < 5 — extreme oversold bounce",
        "min_score": 6,
        "rsi2_max": 5,
        "delta_min": -3.0,
        "delta_max": 0.5,
        "sl_multiplier": 1.5,  # 1.5 × ATR
        "target_multiplier": 3.0,  # 3:1 R:R
        "max_sl_pct": 0.06,
        "min_sl_pct": 0.03,
        "max_target_pct": 0.12,
        "max_holding_days": 5,  # Short hold — mean reversion
    },
    "PULLBACK_TIGHT": {
        "description": "Tight SL (1×ATR), wide target (3:1), selective",
        "min_score": 8,
        "rsi2_max": 30,
        "delta_min": -2.0,
        "delta_max": 1.0,
        "sl_multiplier": 1.0,
        "target_multiplier": 3.0,
        "max_sl_pct": 0.05,
        "min_sl_pct": 0.02,
        "max_target_pct": 0.15,
        "max_holding_days": 10,
    },
    "PULLBACK_WIDE": {
        "description": "Wide SL (2×ATR), moderate target (2:1), higher WR",
        "min_score": 7,
        "rsi2_max": 40,
        "delta_min": -3.0,
        "delta_max": 2.0,
        "sl_multiplier": 2.0,
        "target_multiplier": 2.0,
        "max_sl_pct": 0.08,
        "min_sl_pct": 0.04,
        "max_target_pct": 0.16,
        "max_holding_days": 15,
    },
    "DEFENSIVE_SECTORS": {
        "description": "Only PHARMA/FMCG/IT/HEALTHCARE — proven winners",
        "min_score": 6,
        "rsi2_max": 50,
        "delta_min": -3.0,
        "delta_max": 2.0,
        "sl_multiplier": 1.5,
        "target_multiplier": 2.5,
        "max_sl_pct": 0.06,
        "min_sl_pct": 0.03,
        "max_target_pct": 0.15,
        "max_holding_days": 15,
        "sectors_allowed": {"PHARMA", "FMCG", "HEALTHCARE", "IT", "CONSUMER_DURABLE"},
    },
    "HIGH_SCORE": {
        "description": "Score >= 10 only — highest quality setups",
        "min_score": 10,
        "rsi2_max": 50,
        "delta_min": -2.0,
        "delta_max": 1.0,
        "sl_multiplier": 1.5,
        "target_multiplier": 2.5,
        "max_sl_pct": 0.06,
        "min_sl_pct": 0.03,
        "max_target_pct": 0.15,
        "max_holding_days": 12,
    },
    "VOLUME_SURGE": {
        "description": "High turnover (>20Cr) + near DMA — institutional interest",
        "min_score": 6,
        "rsi2_max": 50,
        "delta_min": -2.0,
        "delta_max": 1.5,
        "sl_multiplier": 1.5,
        "target_multiplier": 2.5,
        "max_sl_pct": 0.06,
        "min_sl_pct": 0.03,
        "max_target_pct": 0.15,
        "max_holding_days": 12,
        "min_turnover_cr": 20,
    },
}


def select_for_strategy(candidates: list, strategy: dict, capital: float, per_trade: float) -> list:
    """Select trades using strategy-specific parameters."""
    filtered = candidates.copy()

    # Score filter
    filtered = [c for c in filtered if c["score"] >= strategy["min_score"]]

    # RSI2 filter
    filtered = [c for c in filtered if c.get("rsi2", 100) < strategy["rsi2_max"]]

    # Delta from 20-DMA filter
    filtered = [c for c in filtered
                if strategy["delta_min"] <= c.get("delta_from_20dma", 99) <= strategy["delta_max"]]

    # Sector filter (if specified)
    if "sectors_allowed" in strategy:
        filtered = [c for c in filtered if c.get("sector", "") in strategy["sectors_allowed"]]

    # Turnover filter (if specified)
    min_turnover = strategy.get("min_turnover_cr", 5)
    filtered = [c for c in filtered if c.get("avg_turnover_cr", 0) >= min_turnover]

    # Last 5d return > -8% (falling knife)
    filtered = [c for c in filtered if c.get("last_5d_return", -99) > -8.0]

    # Rank by score
    filtered.sort(key=lambda x: x["score"], reverse=True)

    # Take top 5
    filtered = filtered[:5]

    # Build trade setups
    trades = []
    for c in filtered:
        entry = c["latest_close"]
        atr_pct = c.get("atr_pct", 3.0) / 100

        sl_pct = max(strategy["min_sl_pct"], atr_pct * strategy["sl_multiplier"])
        sl_pct = min(sl_pct, strategy["max_sl_pct"])
        stop_loss = entry * (1 - sl_pct)

        target_pct = sl_pct * strategy["target_multiplier"]
        target_pct = min(target_pct, strategy["max_target_pct"])
        target = entry * (1 + target_pct)

        rr = (target - entry) / (entry - stop_loss) if entry > stop_loss else 0
        if rr < 2.0:
            continue

        risk_amount = capital * 0.01
        qty = int(risk_amount / (entry - stop_loss)) if (entry - stop_loss) > 0 else 0
        qty = min(qty, int(per_trade / entry)) if entry > 0 else 0
        if qty <= 0:
            continue

        trades.append({
            "symbol": c["symbol"],
            "entry_price": entry,
            "target_price": round(target, 2),
            "stop_loss_price": round(stop_loss, 2),
            "quantity": qty,
            "score": c["score"],
            "rr": round(rr, 2),
            "strategy_type": "PULLBACK",
        })

    return trades


def run_strategy_backtest(strategy_name: str, strategy: dict, universe_data: dict, months: int = 2):
    """Run backtest for one strategy variant."""
    capital = 300000
    per_trade = 30000
    max_holding = strategy["max_holding_days"]

    min_candles = min(len(d["close"]) for d in universe_data.values())
    backtest_days = min(months * 22, min_candles - 200)
    if backtest_days <= 0:
        return {"strategy": strategy_name, "error": "insufficient_data"}

    all_trades = []
    open_positions = []

    for day_offset in range(backtest_days):
        day_idx = -(backtest_days - day_offset)

        # Score candidates
        candidates = []
        for symbol, ohlc in universe_data.items():
            end_idx = len(ohlc["close"]) + day_idx
            if end_idx < 200:
                continue
            daily_slice = {k: v[:end_idx] for k, v in ohlc.items()}
            result = score_swing_candidate(symbol, daily_slice)
            if result:
                candidates.append(result)

        # Check exits
        to_close = []
        for pos in open_positions:
            ohlc = universe_data.get(pos["symbol"])
            if not ohlc:
                continue
            end_idx = len(ohlc["close"]) + day_idx
            if end_idx >= len(ohlc["close"]):
                continue
            pos["days_held"] += 1
            high = ohlc["high"][end_idx]
            low = ohlc["low"][end_idx]
            close = ohlc["close"][end_idx]

            if high >= pos["target_price"]:
                pos["exit_price"] = pos["target_price"]
                pos["exit_reason"] = "TARGET_HIT"
                to_close.append(pos)
            elif low <= pos["stop_loss_price"]:
                pos["exit_price"] = pos["stop_loss_price"]
                pos["exit_reason"] = "STOPPED_OUT"
                to_close.append(pos)
            elif pos["days_held"] >= max_holding:
                pos["exit_price"] = close
                pos["exit_reason"] = "TIME_EXIT"
                to_close.append(pos)

        for pos in to_close:
            open_positions.remove(pos)
            buy_val = pos["entry_price"] * pos["quantity"]
            sell_val = pos["exit_price"] * pos["quantity"]
            gross = (pos["exit_price"] - pos["entry_price"]) * pos["quantity"]
            charges = _compute_charges(buy_val, sell_val)
            all_trades.append({
                "symbol": pos["symbol"],
                "entry_price": pos["entry_price"],
                "exit_price": pos["exit_price"],
                "quantity": pos["quantity"],
                "days_held": pos["days_held"],
                "gross_pnl": round(gross, 2),
                "charges": round(charges, 2),
                "net_pnl": round(gross - charges, 2),
                "exit_reason": pos["exit_reason"],
                "score": pos["score"],
                "rr": pos["rr"],
                "strategy_type": "PULLBACK",
            })

        # New entries
        available = 5 - len(open_positions)
        if available > 0 and candidates:
            selected = select_for_strategy(candidates, strategy, capital, per_trade)
            for trade in selected[:available]:
                if any(p["symbol"] == trade["symbol"] for p in open_positions):
                    continue
                ohlc = universe_data.get(trade["symbol"])
                if not ohlc:
                    continue
                next_idx = len(ohlc["close"]) + day_idx + 1
                if next_idx >= len(ohlc["open"]):
                    continue
                entry = ohlc["open"][next_idx]
                if entry <= 0:
                    continue
                # Recalc SL/target from actual entry
                sl_dist_pct = (trade["entry_price"] - trade["stop_loss_price"]) / trade["entry_price"]
                sl = entry * (1 - sl_dist_pct)
                tgt = entry * (1 + sl_dist_pct * strategy["target_multiplier"])
                open_positions.append({
                    "symbol": trade["symbol"],
                    "entry_price": round(entry, 2),
                    "target_price": round(tgt, 2),
                    "stop_loss_price": round(sl, 2),
                    "quantity": trade["quantity"],
                    "days_held": 0,
                    "score": trade["score"],
                    "rr": trade["rr"],
                })

    # Close remaining
    for pos in open_positions:
        ohlc = universe_data.get(pos["symbol"])
        if ohlc:
            gross = (ohlc["close"][-1] - pos["entry_price"]) * pos["quantity"]
            charges = _compute_charges(pos["entry_price"] * pos["quantity"], ohlc["close"][-1] * pos["quantity"])
            all_trades.append({
                "symbol": pos["symbol"], "entry_price": pos["entry_price"],
                "exit_price": ohlc["close"][-1], "quantity": pos["quantity"],
                "days_held": pos["days_held"], "gross_pnl": round(gross, 2),
                "charges": round(charges, 2), "net_pnl": round(gross - charges, 2),
                "exit_reason": "BACKTEST_END", "score": pos["score"],
                "rr": pos["rr"], "strategy_type": "PULLBACK",
            })

    stats = _compute_stats(all_trades, SwingConfig())
    return {"strategy": strategy_name, "description": strategy["description"], "stats": stats}


def main():
    logging.basicConfig(level=logging.WARNING)
    data = _load_cached_data()
    if not data:
        print("ERROR: No cached data. Run fetch_swing_data.py first.")
        return

    print(f"Loaded {len(data)} stocks")
    print(f"Testing 6 strategy variants on 2 months of data...")
    print(f"Capital: Rs.3,00,000 | Per trade: Rs.30,000 | Max positions: 5")
    print("=" * 70)

    results = []
    for name, strategy in STRATEGIES.items():
        result = run_strategy_backtest(name, strategy, data, months=2)
        results.append(result)
        s = result.get("stats", {})
        trades = s.get("total_trades", 0)
        wr = s.get("win_rate_pct", 0)
        pf = s.get("profit_factor", 0)
        net = s.get("total_net_pnl", 0)
        verdict = s.get("verdict", "NO_DATA")
        print(f"\n  {name}: {strategy['description']}")
        print(f"    Trades: {trades} | WR: {wr}% | PF: {pf} | Net: Rs.{net:,.0f} | {verdict}")

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'Strategy':<20} {'Trades':>6} {'WR%':>5} {'PF':>5} {'Net P&L':>10} {'Verdict':<15}")
    print("-" * 70)
    for r in results:
        s = r.get("stats", {})
        print(f"{r['strategy']:<20} {s.get('total_trades',0):>6} {s.get('win_rate_pct',0):>5.1f} "
              f"{s.get('profit_factor',0):>5.2f} {s.get('total_net_pnl',0):>10,.0f} {s.get('verdict','?'):<15}")

    # Save results
    out_path = Path("backtest/results/swing_multi_strategy.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
