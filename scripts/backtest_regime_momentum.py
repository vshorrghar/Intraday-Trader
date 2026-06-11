#!/usr/bin/env python3
"""Regime-filtered momentum breakout. Quick inline backtest."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.backtest_momentum_breakout import (
    load_all_data, is_stage2, compute_sma, compute_ema, CAPITAL, CHARGE_PER_SIDE
)

RISK_PCT = 0.01
MAX_POS = 10
HARD_SL = 0.07

all_data = load_all_data()
proxy = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","ITC","LT","KOTAKBANK","HINDUNILVR"]

ref = all_data["RELIANCE"]
dates = [c["date"] for c in ref]

# Build nifty proxy
nifty_by_date = {}
for d in dates:
    vals = []
    for s in proxy:
        if s in all_data:
            for c in all_data[s]:
                if c["date"] == d:
                    vals.append(c["close"])
                    break
    if vals:
        nifty_by_date[d] = sum(vals)/len(vals)

nifty_closes = [nifty_by_date.get(d, 0) for d in dates]

def get_regime(idx):
    if idx < 200: return "CASH"
    nc = nifty_closes[:idx+1]
    sma50 = sum(nc[-50:])/50
    sma200 = sum(nc[-200:])/200
    price = nc[-1]
    if price > sma50 and sma50 > sma200: return "BULL"
    if price > sma200: return "HALF"
    return "CASH"

# Index data
stock_idx = {}
for sym, candles in all_data.items():
    stock_idx[sym] = {c["date"]:i for i,c in enumerate(candles)}

trades = []
open_pos = []
cum_pnl = 0; peak = 0; max_dd = 0
regime_days = {"BULL":0,"HALF":0,"CASH":0}
backtest_start = 200

for day_i in range(backtest_start, len(dates)):
    date = dates[day_i]
    regime = get_regime(day_i)
    regime_days[regime] += 1

    # EXITS
    to_close = []
    for pos in open_pos:
        if pos["sym"] not in stock_idx: continue
        si = stock_idx[pos["sym"]]
        if date not in si: continue
        idx = si[date]
        sd = all_data[pos["sym"]]
        pos["days"] += 1
        low = sd[idx]["low"]; close = sd[idx]["close"]

        if low <= pos["sl"]:
            pos["exit"] = pos["sl"]; pos["reason"] = "SL"; to_close.append(pos); continue

        pnl_pct = (close - pos["entry"])/pos["entry"]
        if pnl_pct > 0.05 and pos["sl"] < pos["entry"]:
            pos["sl"] = pos["entry"]

        if idx >= 21:
            cs = [sd[j]["close"] for j in range(idx+1)]
            ema21 = compute_ema(cs, 21)
            if close < ema21 and pos["days"] >= 5:
                pos["exit"] = close; pos["reason"] = "TRAIL"; to_close.append(pos); continue

        if pos["days"] >= 40:
            pos["exit"] = close; pos["reason"] = "TIME"; to_close.append(pos)

    for pos in to_close:
        pnl = (pos["exit"]-pos["entry"])*pos["qty"] - (pos["entry"]+pos["exit"])*pos["qty"]*CHARGE_PER_SIDE
        pos["pnl"] = round(pnl,2)
        trades.append(pos); open_pos.remove(pos)
        cum_pnl += pnl; peak = max(peak, cum_pnl); max_dd = max(max_dd, peak-cum_pnl)

    # ENTRIES (only BULL or HALF regime)
    if regime == "CASH" or len(open_pos) >= MAX_POS:
        continue
    max_slots = MAX_POS if regime == "BULL" else 5
    if len(open_pos) >= max_slots:
        continue

    open_syms = {p["sym"] for p in open_pos}
    entries = []

    for sym, candles in all_data.items():
        if sym in open_syms: continue
        si = stock_idx[sym]
        if date not in si: continue
        idx = si[date]
        if idx < 250: continue

        cs = [candles[j]["close"] for j in range(idx+1)]
        hs = [candles[j]["high"] for j in range(idx+1)]
        ls = [candles[j]["low"] for j in range(idx+1)]
        vs = [candles[j]["volume"] for j in range(idx+1)]

        if not is_stage2(cs): continue
        if cs[-1] <= max(hs[-11:-1]): continue
        avg_v = sum(vs[-50:])/50
        if avg_v <= 0 or vs[-1] < avg_v * 1.2: continue
        if sum(vs[-20:])/20 * cs[-1] < 5_00_00_000: continue

        entry = cs[-1]
        sl = max(min(ls[-10:]) * 0.99, entry * (1-HARD_SL))
        risk = entry - sl
        if risk <= 0: continue
        qty = min(int(CAPITAL*RISK_PCT/risk), int(CAPITAL*0.15/entry))
        if qty <= 0: continue
        entries.append({"sym":sym,"entry":entry,"sl":round(sl,2),"qty":qty,"score":avg_v*cs[-1]})

    entries.sort(key=lambda x: x["score"], reverse=True)
    slots = max_slots - len(open_pos)
    for e in entries[:slots]:
        open_pos.append({**e, "date":date, "days":0, "exit":0, "reason":"", "pnl":0})

# Force close
for pos in open_pos:
    pos["exit"] = pos["entry"]; pos["reason"] = "END"
    if pos["sym"] in stock_idx and dates[-1] in stock_idx[pos["sym"]]:
        idx = stock_idx[pos["sym"]][dates[-1]]
        pos["exit"] = all_data[pos["sym"]][idx]["close"]
    pnl = (pos["exit"]-pos["entry"])*pos["qty"] - (pos["entry"]+pos["exit"])*pos["qty"]*CHARGE_PER_SIDE
    pos["pnl"] = round(pnl,2); trades.append(pos)
    cum_pnl += pnl; peak = max(peak,cum_pnl); max_dd = max(max_dd, peak-cum_pnl)

wins = [t for t in trades if t["pnl"]>0]
losses = [t for t in trades if t["pnl"]<=0]
gw = sum(t["pnl"] for t in wins)
gl = abs(sum(t["pnl"] for t in losses))
pf = gw/gl if gl>0 else 999

print("="*60)
print("REGIME-FILTERED MOMENTUM BREAKOUT")
print("="*60)
print(f"Period: {dates[backtest_start]} to {dates[-1]} ({len(dates)-backtest_start} days)")
print(f"Regime: BULL={regime_days['BULL']}, HALF={regime_days['HALF']}, CASH={regime_days['CASH']}")
print(f"Trades: {len(trades)} (W:{len(wins)} L:{len(losses)})")
wr = len(wins)/len(trades)*100 if trades else 0
print(f"Win rate: {wr:.1f}%")
print(f"Profit factor: {pf:.2f}")
print(f"Cum P&L: Rs.{cum_pnl:+,.0f} ({cum_pnl/CAPITAL*100:+.1f}%)")
print(f"Max DD: Rs.{max_dd:,.0f} ({max_dd/CAPITAL*100:.1f}%)")
if wins and losses:
    print(f"Avg win: Rs.{gw/len(wins):+,.0f} | Avg loss: Rs.{-gl/len(losses):,.0f}")
print()
print("COMPARISON (same period, Rs.2L capital):")
print(f"  V1 Pullback (no regime):  P&L Rs.+3,996   PF 1.84  DD Rs.3,179 (1.6%)")
print(f"  V2 Momentum (no regime):  P&L Rs.+5,093   PF 1.20  DD Rs.22,448 (11.2%)")
print(f"  V2+REGIME FILTER:         P&L Rs.{cum_pnl:+,.0f}  PF {pf:.2f}  DD Rs.{max_dd:,.0f} ({max_dd/CAPITAL*100:.1f}%)")
print()
st = sorted(trades, key=lambda t: t["pnl"], reverse=True)
print("Top 5 winners:")
for t in st[:5]: print(f"  {t['sym']:12} days={t['days']:>2} P&L=Rs.{t['pnl']:>+8,.0f} ({t['reason']})")
print("Top 5 losers:")
for t in st[-5:]: print(f"  {t['sym']:12} days={t['days']:>2} P&L=Rs.{t['pnl']:>+8,.0f} ({t['reason']})")
