#!/usr/bin/env python3
"""S3 Combined Backtest — V6 + Claude replay TOGETHER, as they'll run live.

PART A: V6 (GAP_ORB) deterministic backtest on 90d Dhan cache, TRENDING_UP only.
PART B: Claude replay from V1's REAL historical picks (no look-ahead).
PART C: Blend by date — up to 3 V6 + 3 Claude = 6/day, capped at Rs4L.
"""
import json, glob, sqlite3, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backtest.rule_engine import generate_orb_signals, get_candles_for_date, get_prev_close
from intraday.v3.regime import classify_regime, TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, UNCLEAR

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = ROOT / "cache" / "historical_90d"

# Config (LOCKED)
CAPITAL = 400000
PER_TRADE = 65000
MAX_V6_DAY = 3
MAX_CLAUDE_DAY = 3
CHARGES = 60
SLIPPAGE = 0.05

def load_cache():
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

def get_regime(data, date):
    changes, total, up = [], 0, 0
    for sym, ohlc in list(data.items())[:80]:
        candles = get_candles_for_date(ohlc, date)
        if not candles or len(candles) < 4: continue
        prev = get_prev_close(ohlc, date)
        if prev <= 0: continue
        c = candles[min(3, len(candles)-1)]["close"]
        changes.append((c-prev)/prev*100)
        if c > prev: up += 1
        total += 1
    if total == 0: return UNCLEAR
    return classify_regime(sum(changes)/len(changes), 0.5, up/total*100, 16.0)["regime"]

def sim_v6_trade(candles, sig):
    idx = sig.get("entry_candle_idx", 3)
    if idx >= len(candles): return None
    entry = sig["entry_price"] * (1+SLIPPAGE/100)
    sl = sig.get("stop_loss", entry*0.982)
    target = sig.get("target", entry*1.04)
    qty = max(1, int(PER_TRADE/entry))
    for i in range(idx+1, len(candles)):
        if candles[i]["low"] <= sl:
            return {"pnl": (sl*(1-SLIPPAGE/100)-entry)*qty - CHARGES, "reason": "SL"}
        if candles[i]["high"] >= target:
            return {"pnl": (target*(1-SLIPPAGE/100)-entry)*qty - CHARGES, "reason": "TARGET"}
    exit_p = candles[-1]["close"]*(1-SLIPPAGE/100)
    return {"pnl": (exit_p-entry)*qty - CHARGES, "reason": "FORCE_EXIT"}

def load_claude_trades():
    """Load V1 Claude picks from vishal paper DB."""
    db = str(ROOT / "database" / "vishal.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT trade_date, symbol, tradingsymbol, entry_price, exit_price, "
        "target_price, stop_loss_price, quantity, pnl, strategy_type, status "
        "FROM intraday_trades WHERE status NOT IN ('REJECTED','CANCELLED','PENDING','OPEN') "
        "AND entry_price > 0 AND exit_price > 0 ORDER BY id"
    ).fetchall()
    conn.close()
    trades = [dict(r) for r in rows]
    return trades

def sim_claude_trade(t):
    """Re-simulate a Claude pick with standard charges/slippage."""
    entry = t["entry_price"] * (1+SLIPPAGE/100)
    exit_p = t["exit_price"] * (1-SLIPPAGE/100)
    qty = min(t["quantity"], max(1, int(PER_TRADE/entry)))
    gross = (exit_p - entry) * qty
    return {"pnl": gross - CHARGES, "reason": t["status"], "symbol": t["symbol"]}

def compute_stats(trades):
    if not trades: return {"trades":0,"wr":0,"pf":0,"cum":0,"max_dd":0,"worst_day":0}
    wins = sum(1 for t in trades if t["pnl"]>0)
    gw = sum(t["pnl"] for t in trades if t["pnl"]>0)
    gl = abs(sum(t["pnl"] for t in trades if t["pnl"]<=0))
    pf = gw/gl if gl>0 else 0
    cum = sum(t["pnl"] for t in trades)
    # Max DD
    r,p,dd = 0,0,0
    for t in trades:
        r += t["pnl"]; p = max(p,r); dd = max(dd, p-r)
    return {"trades":len(trades),"wins":wins,"wr":round(wins/len(trades)*100,1),
            "pf":round(pf,2),"cum":round(cum,0),"max_dd":round(dd,0)}

def main():
    data = load_cache()
    dates = get_dates(data)
    print("="*65)
    print("S3 COMBINED BACKTEST — V6 + Claude TOGETHER")
    print(f"Capital: Rs{CAPITAL:,} | Per trade: Rs{PER_TRADE:,} | Max 6/day")
    print(f"Period: {dates[0]} to {dates[-1]} ({len(dates)} days)")
    print("="*65)

    # PART A: V6
    universe = {sym: sym for sym in data}
    config = {"per_trade_max_capital": PER_TRADE}
    v6_trades = []
    v6_by_regime = defaultdict(list)

    for date in dates:
        regime = get_regime(data, date)
        if regime != TRENDING_UP:
            continue
        signals = generate_orb_signals(date, data, universe, config, "V6", None)
        for sig in signals[:MAX_V6_DAY]:
            candles = get_candles_for_date(data.get(sig["symbol"],{}), date)
            if not candles or len(candles) < 5: continue
            result = sim_v6_trade(candles, sig)
            if result:
                result["date"] = date
                result["symbol"] = sig["symbol"]
                result["source"] = "V6"
                result["regime"] = regime
                v6_trades.append(result)
                v6_by_regime[regime].append(result)

    # PART B: Claude replay
    claude_raw = load_claude_trades()
    claude_trades = []
    claude_by_date = defaultdict(list)

    for t in claude_raw:
        result = sim_claude_trade(t)
        result["date"] = t["trade_date"]
        result["source"] = "CLAUDE"
        result["regime"] = get_regime(data, t["trade_date"]) if t["trade_date"] in dates else "UNKNOWN"
        claude_trades.append(result)
        claude_by_date[t["trade_date"]].append(result)

    # Cap Claude to 3/day
    claude_capped = []
    for date, trades in claude_by_date.items():
        claude_capped.extend(trades[:MAX_CLAUDE_DAY])

    print(f"\n--- PART A: V6 (TRENDING_UP only) ---")
    s_v6 = compute_stats(v6_trades)
    print(f"  Trades: {s_v6['trades']} | WR: {s_v6['wr']}% | PF: {s_v6['pf']} | Cum: Rs{s_v6['cum']:,}")

    print(f"\n--- PART B: Claude Replay ---")
    print(f"  V1 DB range: {claude_raw[0]['trade_date'] if claude_raw else '?'} to {claude_raw[-1]['trade_date'] if claude_raw else '?'}")
    print(f"  Total V1 picks (closed, with exit): {len(claude_raw)}")
    print(f"  After 3/day cap: {len(claude_capped)}")
    s_cl = compute_stats(claude_capped)
    print(f"  Trades: {s_cl['trades']} | WR: {s_cl['wr']}% | PF: {s_cl['pf']} | Cum: Rs{s_cl['cum']:,}")

    # PART C: Blend by date
    print(f"\n--- PART C: COMBINED (V6 + Claude, by date) ---")
    # Find overlap dates
    v6_dates = set(t["date"] for t in v6_trades)
    claude_dates = set(t["date"] for t in claude_capped)
    all_dates_used = sorted(v6_dates | claude_dates)
    overlap_dates = sorted(v6_dates & claude_dates)
    print(f"  V6 active dates: {len(v6_dates)}")
    print(f"  Claude active dates: {len(claude_dates)}")
    print(f"  Overlap dates: {len(overlap_dates)}")

    # Combine
    combined = []
    daily_pnl = defaultdict(float)
    combo_by_regime = defaultdict(list)

    # V6 trades (already regime-gated)
    for t in v6_trades:
        combined.append(t)
        daily_pnl[t["date"]] += t["pnl"]
        combo_by_regime[t["regime"]].append(t)

    # Claude trades (all regimes)
    for t in claude_capped:
        # Dedupe: if same symbol same day already in V6, skip
        v6_syms_today = set(x["symbol"] for x in v6_trades if x["date"] == t["date"])
        if t.get("symbol") in v6_syms_today:
            continue  # Dedupe
        combined.append(t)
        daily_pnl[t["date"]] += t["pnl"]
        combo_by_regime[t.get("regime", UNCLEAR)].append(t)

    s_combo = compute_stats(combined)
    # Max DD from daily
    r,p,dd = 0,0,0
    for d in sorted(daily_pnl):
        r += daily_pnl[d]; p = max(p,r); dd = max(dd, p-r)
    worst_day = min(daily_pnl.values()) if daily_pnl else 0

    v6_count = sum(1 for t in combined if t["source"]=="V6")
    cl_count = sum(1 for t in combined if t["source"]=="CLAUDE")

    print(f"\n  OVERALL (Rs{CAPITAL:,} capital):")
    print(f"    Total trades: {s_combo['trades']} (V6={v6_count}, Claude={cl_count})")
    print(f"    Win Rate: {s_combo['wr']}%")
    print(f"    Profit Factor: {s_combo['pf']}")
    print(f"    Cumulative P&L: Rs{s_combo['cum']:,} ({s_combo['cum']/CAPITAL*100:.1f}%)")
    print(f"    Max Drawdown: Rs{dd:,.0f}")
    print(f"    Worst Day: Rs{worst_day:,.0f}")

    print(f"\n  BY REGIME:")
    print(f"    {'Regime':<15} {'Trades':>7} {'WR%':>6} {'PF':>6} {'P&L':>10}")
    print(f"    {'-'*45}")
    for regime in [TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, UNCLEAR, "UNKNOWN"]:
        trades = combo_by_regime.get(regime, [])
        if not trades: continue
        s = compute_stats(trades)
        print(f"    {regime:<15} {s['trades']:>7} {s['wr']:>5.0f}% {s['pf']:>5.2f} {s['cum']:>9,}")

    print(f"\n  BY SOURCE:")
    print(f"    V6-only:    PF {compute_stats(v6_trades)['pf']} | Cum Rs{compute_stats(v6_trades)['cum']:,}")
    print(f"    Claude-only: PF {compute_stats(claude_capped)['pf']} | Cum Rs{compute_stats(claude_capped)['cum']:,}")
    print(f"    Combined:   PF {s_combo['pf']} | Cum Rs{s_combo['cum']:,}")
    claude_adds = s_combo['pf'] > compute_stats(v6_trades)['pf']
    print(f"    Claude adds edge: {'YES' if claude_adds else 'NO'} (combo PF {s_combo['pf']} vs V6-alone {compute_stats(v6_trades)['pf']})")

    # Friction-honest
    friction_pnl = s_combo['cum'] * 0.80  # 20% haircut
    print(f"\n  FRICTION-HONEST:")
    print(f"    Backtest P&L:  Rs{s_combo['cum']:,}")
    print(f"    After 20% haircut: Rs{friction_pnl:,.0f}")

    # Verdict
    print(f"\n{'='*65}")
    if s_combo['pf'] >= 1.5:
        print(f"VERDICT: Combined PF {s_combo['pf']} >= 1.5 → S3 has real edge, worth paper-forward + tiny-live")
    else:
        print(f"VERDICT: Combined PF {s_combo['pf']} < 1.5 → S3 thin, V6+Claude doesn't beat break-even")

    print(f"\nHONESTY CAVEATS:")
    print(f"  - V6 = true backtest on 90d Dhan cache (deterministic, reproducible)")
    print(f"  - Claude = replay of REAL V1 picks from vishal paper DB (no look-ahead)")
    print(f"  - Overlap window: V6 cache {dates[0]}-{dates[-1]}, Claude DB {claude_raw[0]['trade_date'] if claude_raw else '?'}-{claude_raw[-1]['trade_date'] if claude_raw else '?'}")
    print(f"  - Deduped: same stock same day counted once (V6 priority)")
    print(f"  - Backtest proves EDGE, not execution safety")

if __name__ == "__main__":
    main()
