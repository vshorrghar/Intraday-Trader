#!/usr/bin/env python3
"""VWAP_REVERT Stress Test — does it buy falling knives on DOWN days?

Tests VWAP_REVERT alone (relaxed) and the GAP_ORB+VWAP_REVERT combo.
Tags every trade by regime. Answers the killer questions.
"""
import json, glob, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backtest.rule_engine import generate_orb_signals, get_candles_for_date, get_prev_close

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = ROOT / "cache" / "historical_90d"
CHARGES = 60
SLIPPAGE = 0.05
PER_TRADE = 10000  # Rs5K for VWAP_REVERT per spec

def load_data():
    data = {}
    for f in CACHE_DIR.glob("*.json"):
        sym = f.name.split("_15min_")[0]
        data[sym] = json.load(open(f))
    return data

def get_dates(data):
    dates = set()
    sample = list(data.values())[0]
    for ts in sample.get("timestamp", []):
        dt = datetime.fromtimestamp(ts, tz=IST)
        if dt.weekday() < 5:
            dates.add(dt.strftime("%Y-%m-%d"))
    return sorted(dates)

def classify_day_regime(data, date):
    """Classify day regime from Nifty proxy (top 50 stocks)."""
    changes = []
    highs, lows, opens_list = [], [], []
    for sym, ohlc in list(data.items())[:80]:
        candles = get_candles_for_date(ohlc, date)
        if not candles or len(candles) < 4:
            continue
        prev = get_prev_close(ohlc, date)
        if prev <= 0:
            continue
        day_close = candles[-1]["close"]
        day_high = max(c["high"] for c in candles)
        day_low = min(c["low"] for c in candles)
        day_open = candles[0]["open"]
        changes.append((day_close - prev) / prev * 100)
        if day_open > 0:
            highs.append(day_high)
            lows.append(day_low)
            opens_list.append(day_open)

    if not changes:
        return "UNKNOWN"
    avg_change = sum(changes) / len(changes)
    # Day range proxy
    if opens_list:
        avg_range = sum((h-l)/o*100 for h,l,o in zip(highs, lows, opens_list)) / len(opens_list)
    else:
        avg_range = 0

    if avg_range > 2.0:
        return "VOLATILE"
    elif avg_change > 0.4:
        return "UP"
    elif avg_change < -0.4:
        return "DOWN"
    else:
        return "SIDEWAYS"

def find_vwap_revert_signals_relaxed(data, date, min_below=1.0, max_below=4.0):
    """Relaxed VWAP_REVERT: 1-4% below VWAP, any time 10:15-13:00."""
    signals = []
    for sym, ohlc in data.items():
        candles = get_candles_for_date(ohlc, date)
        if not candles or len(candles) < 12:
            continue
        # Compute VWAP
        cum_tp_vol, cum_vol = 0.0, 0
        vwap_values = []
        for c in candles:
            tp = (c["high"] + c["low"] + c["close"]) / 3
            cum_tp_vol += tp * c["volume"]
            cum_vol += c["volume"]
            vwap_values.append(cum_tp_vol / cum_vol if cum_vol > 0 else c["close"])

        # Look for cross-above from 10:15 (idx 4) to 13:00 (idx ~15)
        for i in range(4, min(16, len(candles))):
            if i == 0:
                continue
            prev_close = candles[i-1]["close"]
            curr_close = candles[i]["close"]
            vwap_prev = vwap_values[i-1]
            vwap_curr = vwap_values[i]
            if vwap_prev <= 0:
                continue
            below_pct = (vwap_prev - prev_close) / vwap_prev * 100
            if below_pct < min_below or below_pct > max_below:
                continue
            if curr_close <= vwap_curr:
                continue
            # Signal found
            entry = curr_close
            sl = entry * 0.99  # 1% SL
            target = max(vwap_curr * 1.005, entry + 1.5 * (entry - sl))
            signals.append({
                "symbol": sym, "entry_price": entry, "stop_loss": sl,
                "target": target, "entry_candle_idx": i,
                "strategy": "VWAP_REVERT", "below_pct": below_pct,
            })
            break  # One signal per stock per day
    return signals

def simulate_trade(candles, sig):
    entry_idx = sig["entry_candle_idx"]
    entry = sig["entry_price"] * (1 + SLIPPAGE/100)
    sl = sig["stop_loss"]
    target = sig["target"]
    qty = max(1, int(PER_TRADE / entry))
    # Time stop: 6 candles (90 min)
    for i in range(entry_idx+1, min(entry_idx+7, len(candles))):
        if candles[i]["low"] <= sl:
            exit_p = sl * (1 - SLIPPAGE/100)
            return {"pnl": (exit_p - entry)*qty - CHARGES, "reason": "SL"}
        if candles[i]["high"] >= target:
            exit_p = target * (1 - SLIPPAGE/100)
            return {"pnl": (exit_p - entry)*qty - CHARGES, "reason": "TARGET"}
    # Time stop / force exit
    last_idx = min(entry_idx+6, len(candles)-1)
    exit_p = candles[last_idx]["close"] * (1 - SLIPPAGE/100)
    return {"pnl": (exit_p - entry)*qty - CHARGES, "reason": "TIME_STOP"}

def compute_stats(trades):
    if not trades:
        return {"trades": 0, "wr": 0, "pf": 0, "avg": 0, "worst": 0, "cum": 0}
    wins = sum(1 for t in trades if t["pnl"] > 0)
    gw = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gl = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
    pf = gw/gl if gl > 0 else 0
    cum = sum(t["pnl"] for t in trades)
    worst = min(t["pnl"] for t in trades)
    return {"trades": len(trades), "wr": round(wins/len(trades)*100,1),
            "pf": round(pf,2), "avg": round(cum/len(trades),0),
            "worst": round(worst,0), "cum": round(cum,0)}

def main():
    data = load_data()
    dates = get_dates(data)
    print("="*60)
    print("VWAP_REVERT STRESS TEST")
    print(f"Period: {dates[0]} to {dates[-1]} ({len(dates)} days)")
    print("="*60)

    # === PART 1: VWAP_REVERT ALONE (relaxed) ===
    print("\n--- PART 1: VWAP_REVERT ALONE (relaxed 1-4% dip) ---")
    vwap_by_regime = defaultdict(list)
    for date in dates:
        regime = classify_day_regime(data, date)
        signals = find_vwap_revert_signals_relaxed(data, date)
        for sig in signals[:2]:  # max 2/day
            candles = get_candles_for_date(data.get(sig["symbol"],{}), date)
            if candles and len(candles) > sig["entry_candle_idx"]:
                result = simulate_trade(candles, sig)
                result["regime"] = regime
                result["date"] = date
                vwap_by_regime[regime].append(result)

    print(f"\n{'Regime':<12} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Avg':>8} {'Worst':>8} {'Cum':>9}")
    print("-"*60)
    all_vwap = []
    for regime in ["UP", "DOWN", "SIDEWAYS", "VOLATILE"]:
        trades = vwap_by_regime[regime]
        all_vwap.extend(trades)
        s = compute_stats(trades)
        print(f"{regime:<12} {s['trades']:>7} {s['wr']:>5.0f}% {s['pf']:>5.2f} {s['avg']:>7,.0f} {s['worst']:>7,.0f} {s['cum']:>8,.0f}")
    s_all = compute_stats(all_vwap)
    print(f"{'ALL':<12} {s_all['trades']:>7} {s_all['wr']:>5.0f}% {s_all['pf']:>5.2f} {s_all['avg']:>7,.0f} {s_all['worst']:>7,.0f} {s_all['cum']:>8,.0f}")

    # === PART 2: COMBO (GAP_ORB + VWAP_REVERT) ===
    print("\n\n--- PART 2: COMBO (GAP_ORB + VWAP_REVERT, V4 OFF) ---")
    universe = {sym: sym for sym in data}
    config = {"per_trade_max_capital": 25000}
    combo_by_regime = defaultdict(list)
    daily_pnl = {}

    for date in dates:
        regime = classify_day_regime(data, date)
        day_trades = []
        # GAP_ORB
        v6_signals = generate_orb_signals(date, data, universe, config, "V6", None)
        for sig in v6_signals[:2]:
            candles = get_candles_for_date(data.get(sig["symbol"],{}), date)
            if candles and len(candles) >= 5:
                entry_idx = sig.get("entry_candle_idx", 3)
                if entry_idx < len(candles):
                    entry = sig["entry_price"] * (1+SLIPPAGE/100)
                    sl = sig.get("stop_loss", entry*0.982)
                    target = sig.get("target", entry*1.04)
                    qty = max(1, int(25000/entry))
                    exit_p = None
                    for i in range(entry_idx+1, len(candles)):
                        if candles[i]["low"] <= sl:
                            exit_p = sl*(1-SLIPPAGE/100); break
                        if candles[i]["high"] >= target:
                            exit_p = target*(1-SLIPPAGE/100); break
                    if exit_p is None:
                        exit_p = candles[-1]["close"]*(1-SLIPPAGE/100)
                    pnl = (exit_p-entry)*qty - CHARGES
                    day_trades.append({"pnl": pnl, "regime": regime, "strategy": "GAP_ORB"})

        # VWAP_REVERT (relaxed)
        vwap_signals = find_vwap_revert_signals_relaxed(data, date)
        for sig in vwap_signals[:1]:  # max 1 VWAP per day
            candles = get_candles_for_date(data.get(sig["symbol"],{}), date)
            if candles and len(candles) > sig["entry_candle_idx"]:
                result = simulate_trade(candles, sig)
                result["regime"] = regime
                result["strategy"] = "VWAP_REVERT"
                day_trades.append(result)

        for t in day_trades:
            combo_by_regime[t["regime"]].append(t)
        daily_pnl[date] = sum(t["pnl"] for t in day_trades)

    all_combo = []
    for trades in combo_by_regime.values():
        all_combo.extend(trades)

    s_combo = compute_stats(all_combo)
    # Max drawdown
    running, peak, max_dd = 0, 0, 0
    for d in sorted(daily_pnl):
        running += daily_pnl[d]
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    worst_day = min(daily_pnl.values()) if daily_pnl else 0

    print(f"\nTotal trades: {s_combo['trades']} | WR: {s_combo['wr']}% | PF: {s_combo['pf']} | Cum: Rs{s_combo['cum']:,}")
    print(f"Max DD: Rs{max_dd:,.0f} | Worst day: Rs{worst_day:,.0f}")

    print(f"\n{'Regime':<12} {'Trades':>7} {'WR%':>6} {'PF':>6} {'Avg':>8} {'Worst':>8} {'Cum':>9}")
    print("-"*60)
    for regime in ["UP", "DOWN", "SIDEWAYS", "VOLATILE"]:
        trades = combo_by_regime[regime]
        s = compute_stats(trades)
        print(f"{regime:<12} {s['trades']:>7} {s['wr']:>5.0f}% {s['pf']:>5.2f} {s['avg']:>7,.0f} {s['worst']:>7,.0f} {s['cum']:>8,.0f}")

    # === PART 3: KILLER QUESTIONS ===
    print("\n\n--- PART 3: KILLER QUESTIONS ---")
    down_vwap = vwap_by_regime["DOWN"]
    down_stats = compute_stats(down_vwap)
    print(f"\n1. Does VWAP_REVERT LOSE on DOWN days?")
    if down_vwap:
        print(f"   {down_stats['trades']} trades, WR {down_stats['wr']}%, PF {down_stats['pf']}, Cum Rs{down_stats['cum']:,}")
        if down_stats["pf"] < 0.8:
            print(f"   → YES — FALLING KNIFE. PF {down_stats['pf']} on DOWN days.")
        else:
            print(f"   → NO — holds up (PF {down_stats['pf']})")
    else:
        print(f"   → NO DATA on DOWN days (0 trades)")

    print(f"\n2. Does COMBO beat GAP_ORB-alone (PF 1.03)?")
    if s_combo["pf"] > 1.03:
        print(f"   → YES — Combo PF {s_combo['pf']} > 1.03")
    else:
        print(f"   → NO — Combo PF {s_combo['pf']} <= 1.03 (VWAP_REVERT drags)")

    print(f"\n3. Per-regime money:")
    for regime in ["UP", "DOWN", "SIDEWAYS", "VOLATILE"]:
        s = compute_stats(combo_by_regime[regime])
        flag = "✅ MAKES" if s["cum"] > 0 else "❌ BLEEDS"
        print(f"   {regime}: {flag} Rs{s['cum']:,}")

    # VERDICT
    print("\n" + "="*60)
    if down_vwap and down_stats["pf"] < 0.8:
        print("VERDICT: VWAP_REVERT falling-knife on DOWN — HARD-GATE to RANGING only")
    elif s_combo["pf"] > 1.03:
        print(f"VERDICT: Combo PF {s_combo['pf']} > 1.03 — VWAP_REVERT adds edge")
    elif s_combo["pf"] < 1.03:
        print(f"VERDICT: Combo PF {s_combo['pf']} < 1.03 — VWAP_REVERT drags, consider removing")
    else:
        print("VERDICT: VWAP_REVERT safe across regimes — keep in combo (neutral)")

if __name__ == "__main__":
    main()
