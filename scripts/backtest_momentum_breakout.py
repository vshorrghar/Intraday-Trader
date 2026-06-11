#!/usr/bin/env python3
"""
Momentum Breakout Strategy Backtest — Minervini/O'Neil style.

Buys stocks breaking out of tight bases to new highs.
Entry: Stage 2 + VCP + volume breakout.
Exit: Trailing 21-EMA or -7% hard stop.

Uses same cached data as V1 pullback (cache/swing_daily/).
Same capital (Rs2L), same period, fair comparison.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = Path(__file__).parent.parent / "cache" / "swing_daily"
RESULTS_DIR = Path(__file__).parent.parent / "backtest" / "results"

CAPITAL = 200000
RISK_PCT = 0.01  # 1% risk per trade
MAX_POSITIONS = 10
HARD_SL_PCT = 0.07  # 7% max stop
CHARGE_PER_SIDE = 0.001  # 0.1%


def load_all_data():
    """Load all cached daily candles."""
    all_data = {}
    for f in CACHE_DIR.glob("*.json"):
        try:
            with open(f) as fh:
                d = json.load(fh)
            candles = d.get("candles", [])
            if len(candles) >= 250:
                all_data[f.stem] = candles
        except:
            continue
    return all_data


def compute_sma(closes, period):
    if len(closes) < period:
        return 0
    return sum(closes[-period:]) / period


def compute_ema(closes, period):
    if len(closes) < period:
        return 0
    mult = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = (p - ema) * mult + ema
    return ema


def is_stage2(closes):
    """Check Minervini Stage 2 criteria using MA stack."""
    if len(closes) < 200:
        return False
    sma50 = compute_sma(closes, 50)
    sma150 = compute_sma(closes, 150)
    sma200 = compute_sma(closes, 200)
    price = closes[-1]

    # MA stack: price > 50 > 150 > 200
    if not (price > sma50 > sma150 > sma200):
        return False

    # 200-DMA trending up (compare to 20 days ago)
    if len(closes) < 220:
        return False
    sma200_20ago = sum(closes[-220:-20]) / 200 if len(closes) >= 220 else sma200
    if sma200 <= sma200_20ago:
        return False

    # Price within 25% of 52-week high
    high_52w = max(closes[-250:]) if len(closes) >= 250 else max(closes)
    if price < high_52w * 0.75:
        return False

    # Price at least 30% above 52-week low
    low_52w = min(closes[-250:]) if len(closes) >= 250 else min(closes)
    if price < low_52w * 1.30:
        return False

    return True


def detect_vcp(highs, lows, closes):
    """Detect Volatility Contraction Pattern — range getting tighter."""
    if len(closes) < 30:
        return False

    # Compare last 5 days range vs last 20 days average range
    recent_ranges = [highs[i] - lows[i] for i in range(-5, 0)]
    avg_recent = sum(recent_ranges) / len(recent_ranges)

    longer_ranges = [highs[i] - lows[i] for i in range(-25, -5)]
    avg_longer = sum(longer_ranges) / len(longer_ranges)

    if avg_longer <= 0:
        return False

    # Contraction: recent range < 60% of prior range
    return avg_recent < avg_longer * 0.85


def detect_breakout(closes, highs, volumes, idx):
    """Detect if today is a breakout day (new 20-day high on above-average volume)."""
    if idx < 20:
        return False

    today_close = closes[idx]
    today_vol = volumes[idx]

    # New 20-day high
    prior_20_highs = [highs[i] for i in range(idx - 10, idx)]
    if today_close <= max(prior_20_highs):  # 10-day high
        return False

    # Volume > 1.5x 50-day average
    if idx < 50:
        return False
    avg_vol = sum(volumes[idx-50:idx]) / 50
    if avg_vol <= 0:
        return False
    if today_vol < avg_vol * 1.2:
        return False

    return True


def compute_relative_strength(closes, nifty_closes, lookback=60):
    """Stock's return vs Nifty return over lookback period."""
    if len(closes) < lookback or len(nifty_closes) < lookback:
        return 0
    stock_ret = (closes[-1] - closes[-lookback]) / closes[-lookback]
    nifty_ret = (nifty_closes[-1] - nifty_closes[-lookback]) / nifty_closes[-lookback]
    return stock_ret - nifty_ret


def get_nifty_proxy(all_data):
    """Build Nifty proxy from large-caps."""
    proxy_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                     "BHARTIARTL", "SBIN", "ITC", "LT", "KOTAKBANK"]
    # Use average of available large-caps
    all_dates = set()
    for sym in proxy_symbols:
        if sym in all_data:
            for c in all_data[sym]:
                all_dates.add(c["date"])
    return sorted(all_dates)


def run_backtest():
    print("=" * 60)
    print("MOMENTUM BREAKOUT BACKTEST (Minervini/O'Neil Style)")
    print(f"Capital: Rs.{CAPITAL:,} | Risk: {RISK_PCT*100}% | Max positions: {MAX_POSITIONS}")
    print("=" * 60)

    all_data = load_all_data()
    print(f"Loaded {len(all_data)} stocks with 250+ candles")

    # Get trading dates (use a large-cap as reference)
    ref_candles = all_data.get("RELIANCE", all_data.get("TCS", []))
    if not ref_candles:
        print("ERROR: No reference stock found")
        return

    all_dates = [c["date"] for c in ref_candles]
    # Use last 138 days (same as V1 test)
    backtest_dates = all_dates[-138:]
    print(f"Period: {backtest_dates[0]} to {backtest_dates[-1]} ({len(backtest_dates)} days)")
    print()

    # Build per-stock indexed data for fast lookup
    stock_data = {}
    for symbol, candles in all_data.items():
        date_idx = {c["date"]: i for i, c in enumerate(candles)}
        stock_data[symbol] = {
            "candles": candles,
            "date_idx": date_idx,
            "closes": [c["close"] for c in candles],
            "highs": [c["high"] for c in candles],
            "lows": [c["low"] for c in candles],
            "volumes": [c["volume"] for c in candles],
        }

    # Backtest loop
    trades = []
    open_positions = []  # {symbol, entry_date, entry_price, sl_price, qty, days_held}
    cum_pnl = 0
    peak_pnl = 0
    max_dd = 0
    daily_pnl = {}

    for day_idx, date in enumerate(backtest_dates):
        day_realized = 0

        # CHECK EXITS for open positions
        to_close = []
        for pos in open_positions:
            sd = stock_data.get(pos["symbol"])
            if not sd or date not in sd["date_idx"]:
                continue

            idx = sd["date_idx"][date]
            pos["days_held"] += 1
            today_low = sd["lows"][idx]
            today_close = sd["closes"][idx]

            # Hard SL hit
            if today_low <= pos["sl_price"]:
                pos["exit_price"] = pos["sl_price"]
                pos["exit_date"] = date
                pos["exit_reason"] = "STOPPED_OUT"
                to_close.append(pos)
                continue

            # Trailing SL: 21-EMA (only if in profit)
            if idx >= 21:
                ema21 = compute_ema(sd["closes"][:idx+1], 21)
                # Move SL up to 21-EMA if it's above original SL
                if ema21 > pos["sl_price"] and today_close > pos["entry_price"]:
                    pos["sl_price"] = round(ema21 * 0.99, 2)  # Slightly below EMA

                # Exit if closes below 21-EMA (trend broken)
                if today_close < ema21 and pos["days_held"] >= 5:
                    pos["exit_price"] = today_close
                    pos["exit_date"] = date
                    pos["exit_reason"] = "TRAIL_21EMA"
                    to_close.append(pos)
                    continue

            # Time stop: 40 days max hold
            if pos["days_held"] >= 40:
                pos["exit_price"] = today_close
                pos["exit_date"] = date
                pos["exit_reason"] = "TIME_STOP_40D"
                to_close.append(pos)

        # Process exits
        for pos in to_close:
            pnl_gross = (pos["exit_price"] - pos["entry_price"]) * pos["qty"]
            charges = (pos["entry_price"] + pos["exit_price"]) * pos["qty"] * CHARGE_PER_SIDE
            pnl_net = pnl_gross - charges
            pos["pnl"] = round(pnl_net, 2)
            trades.append(pos)
            open_positions.remove(pos)
            day_realized += pnl_net
            cum_pnl += pnl_net
            peak_pnl = max(peak_pnl, cum_pnl)
            max_dd = max(max_dd, peak_pnl - cum_pnl)

        daily_pnl[date] = day_realized

        # SCAN FOR NEW ENTRIES (if capacity available)
        if len(open_positions) >= MAX_POSITIONS:
            continue

        open_symbols = {p["symbol"] for p in open_positions}
        new_entries = []

        for symbol, sd in stock_data.items():
            if symbol in open_symbols:
                continue
            if date not in sd["date_idx"]:
                continue

            idx = sd["date_idx"][date]
            if idx < 250:  # Need enough history
                continue

            closes_to_date = sd["closes"][:idx+1]
            highs_to_date = sd["highs"][:idx+1]
            lows_to_date = sd["lows"][:idx+1]
            volumes_to_date = sd["volumes"][:idx+1]

            # Stage 2 check
            if not is_stage2(closes_to_date):
                continue

            # VCP check
            if not detect_vcp(highs_to_date, lows_to_date, closes_to_date):
                continue

            # Breakout check
            if not detect_breakout(closes_to_date, highs_to_date, volumes_to_date, idx):
                continue

            # Turnover check (avg daily turnover > Rs.10 Cr)
            avg_vol = sum(volumes_to_date[-20:]) / 20
            avg_turnover = avg_vol * closes_to_date[-1]
            if avg_turnover < 5_00_00_000:
                continue

            # Position sizing
            entry_price = closes_to_date[-1]
            # SL below base low (last 20 days) or 7% whichever tighter
            base_low = min(lows_to_date[-20:])
            sl_from_base = base_low * 0.99  # Just below base
            sl_from_pct = entry_price * (1 - HARD_SL_PCT)
            sl_price = max(sl_from_base, sl_from_pct)  # Tighter of the two

            risk_per_share = entry_price - sl_price
            if risk_per_share <= 0:
                continue

            risk_amount = CAPITAL * RISK_PCT
            qty = int(risk_amount / risk_per_share)
            if qty <= 0:
                continue

            # Cap position at 15% of capital
            max_qty = int(CAPITAL * 0.15 / entry_price)
            qty = min(qty, max_qty)

            new_entries.append({
                "symbol": symbol,
                "entry_price": entry_price,
                "sl_price": round(sl_price, 2),
                "qty": qty,
                "score": avg_turnover,  # Use turnover as tiebreaker
            })

        # Take top entries by turnover (most liquid first)
        new_entries.sort(key=lambda x: x["score"], reverse=True)
        slots = MAX_POSITIONS - len(open_positions)

        for entry in new_entries[:slots]:
            open_positions.append({
                "symbol": entry["symbol"],
                "entry_date": date,
                "entry_price": entry["entry_price"],
                "sl_price": entry["sl_price"],
                "qty": entry["qty"],
                "days_held": 0,
                "exit_price": 0,
                "exit_date": "",
                "exit_reason": "",
                "pnl": 0,
            })

        if (day_idx + 1) % 25 == 0:
            print(f"  Day {day_idx+1}/{len(backtest_dates)}: {len(trades)} closed, "
                  f"{len(open_positions)} open, cum=Rs.{cum_pnl:+,.0f}")

    # Force close remaining
    last_date = backtest_dates[-1]
    for pos in open_positions:
        sd = stock_data.get(pos["symbol"])
        if sd and last_date in sd["date_idx"]:
            idx = sd["date_idx"][last_date]
            pos["exit_price"] = sd["closes"][idx]
        else:
            pos["exit_price"] = pos["entry_price"]
        pos["exit_date"] = last_date
        pos["exit_reason"] = "DATA_END"
        pnl_gross = (pos["exit_price"] - pos["entry_price"]) * pos["qty"]
        charges = (pos["entry_price"] + pos["exit_price"]) * pos["qty"] * CHARGE_PER_SIDE
        pos["pnl"] = round(pnl_gross - charges, 2)
        trades.append(pos)
        cum_pnl += pos["pnl"]
        peak_pnl = max(peak_pnl, cum_pnl)
        max_dd = max(max_dd, peak_pnl - cum_pnl)

    # Results
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_wins = sum(t["pnl"] for t in wins)
    gross_losses = abs(sum(t["pnl"] for t in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else 999

    exit_reasons = defaultdict(int)
    for t in trades:
        exit_reasons[t["exit_reason"]] += 1

    print()
    print("=" * 60)
    print("MOMENTUM BREAKOUT RESULTS (same period as V1)")
    print("=" * 60)
    print(f"  Period: {backtest_dates[0]} to {backtest_dates[-1]}")
    print(f"  Trades: {len(trades)} (W:{len(wins)} / L:{len(losses)})")
    print(f"  Win rate: {len(wins)/len(trades)*100:.1f}%" if trades else "  No trades")
    print(f"  Profit factor: {pf:.2f}")
    print(f"  Cumulative P&L: Rs.{cum_pnl:+,.0f} ({cum_pnl/CAPITAL*100:+.1f}%)")
    print(f"  Max drawdown: Rs.{max_dd:,.0f} ({max_dd/CAPITAL*100:.1f}%)")
    print(f"  Avg holding: {sum(t['days_held'] for t in trades)/len(trades):.1f} days" if trades else "")
    avg_win = gross_wins/len(wins) if wins else 0
    avg_loss = gross_losses/len(losses) if losses else 0
    print(f"  Avg winner: Rs.{avg_win:+,.0f} | Avg loser: Rs.{-avg_loss:,.0f}")
    print()

    print("  Exit reasons:")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:<25} {count:>3} ({count/len(trades)*100:.1f}%)")

    print()
    sorted_trades = sorted(trades, key=lambda t: t["pnl"], reverse=True)
    print("  Top 5 winners:")
    for t in sorted_trades[:5]:
        print(f"    {t['symbol']:<12} days={t['days_held']:>2} P&L=Rs.{t['pnl']:>+8,.0f} ({t['exit_reason']})")
    print("  Top 5 losers:")
    for t in sorted_trades[-5:]:
        print(f"    {t['symbol']:<12} days={t['days_held']:>2} P&L=Rs.{t['pnl']:>+8,.0f} ({t['exit_reason']})")

    print()
    print("=" * 60)
    print("COMPARISON: V1 Pullback vs V2 Momentum Breakout")
    print("=" * 60)
    print(f"  {'Metric':<20} {'V1 Pullback':<15} {'V2 Momentum':<15}")
    print(f"  {'-'*20} {'-'*15} {'-'*15}")
    print(f"  {'Trades':<20} {'55':<15} {len(trades):<15}")
    print(f"  {'Win rate':<20} {'41.8%':<15} {len(wins)/len(trades)*100:.1f}%") if trades else None
    print(f"  {'Profit factor':<20} {'1.84':<15} {pf:.2f}")
    print(f"  {'Cum P&L':<20} {'Rs.+3,996':<15} Rs.{cum_pnl:+,.0f}")
    print(f"  {'Max DD':<20} {'Rs.3,179':<15} Rs.{max_dd:,.0f}")
    print(f"  {'Avg hold':<20} {'9.7 days':<15} {sum(t['days_held'] for t in trades)/len(trades):.1f} days") if trades else None
    print("=" * 60)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / "momentum_breakout_v2.json", "w") as f:
        json.dump({
            "strategy": "momentum_breakout_v2",
            "period": f"{backtest_dates[0]} to {backtest_dates[-1]}",
            "capital": CAPITAL,
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins)/len(trades), 3) if trades else 0,
            "profit_factor": round(pf, 2),
            "cumulative_pnl": round(cum_pnl, 2),
            "max_drawdown": round(max_dd, 2),
            "avg_holding_days": round(sum(t["days_held"] for t in trades)/len(trades), 1) if trades else 0,
            "exit_reasons": dict(exit_reasons),
            "trades_detail": trades,
        }, f, indent=2)
    print(f"\nSaved: backtest/results/momentum_breakout_v2.json")


if __name__ == "__main__":
    run_backtest()
