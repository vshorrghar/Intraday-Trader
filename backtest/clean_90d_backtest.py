#!/usr/bin/env python3
"""
CLEAN 90-DAY BACKTEST
- 280 stocks, 58 trading days
- Blacklist applied (same as live V2)
- Tests: V6 ORB, VWAP Reclaim, Trend Continuation
- Fixed % targets (not ATR — learned from V1 mistake)
- Capital: 30K, 1L, 1.5L, 2L
- 1 trade per day per capital size (quality over quantity)
"""
import json, os
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

IST = timezone(timedelta(hours=5, minutes=30))
CACHE = 'cache/historical_90d'
RESULTS = 'backtest/results'
CHARGES_PCT = 0.001

BLACKLIST = {
    'WIPRO','MPHASIS','RALLIS','INDIANB','BEL','SBIN',
    'GODREJPROP','PAYTM','RELIANCE','RVNL','HDFCBANK',
    'BANDHANBNK','POLICYBZR','ITC','ADANIENT','MRF',
    'SAIL','LAURUSLABS','IPCALAB','CONCOR','PRESTIGE',
    'GNFC','BSE','SONACOMS','ANGELONE','PVRINOX',
    'PIIND','MCDOWELL-N','GODREJCP','UBL','TATASTEEL',
    'BPCL','ASIANPAINT','HINDUNILVR','TATACONSUM',
    'HDFCLIFE','ADANIPOWER','COFORGE','IREDA','NAUKRI',
    'BDL','CANBK','MAZDOCK','ASTRAL','FEDERALBNK',
    'OFSS','BAJAJFINSV','BAJFINANCE','HEROMOTOCO',
    'BAJAJ-AUTO','JSWSTEEL','INDIGO','COCHINSHIP',
}

CAPITAL_SIZES = [30000, 100000, 150000, 200000]

# Target/SL combos to test
VARIANTS = [
    {'name': 'T1_SL05',  'tgt': 0.010, 'sl': 0.005},
    {'name': 'T15_SL07', 'tgt': 0.015, 'sl': 0.007},
    {'name': 'T2_SL1',   'tgt': 0.020, 'sl': 0.010},
    {'name': 'T25_SL12', 'tgt': 0.025, 'sl': 0.012},
    {'name': 'T3_SL15',  'tgt': 0.030, 'sl': 0.015},
]

def load_data():
    data = {}
    for fname in os.listdir(CACHE):
        if not fname.endswith('.json'):
            continue
        sym = fname.split('_15min_')[0]
        if sym in BLACKLIST:
            continue
        with open(os.path.join(CACHE, fname)) as f:
            raw = json.load(f)
        ts = raw.get('timestamp', [])
        if not ts:
            continue
        opens   = raw.get('open', [])
        highs   = raw.get('high', [])
        lows    = raw.get('low', [])
        closes  = raw.get('close', [])
        volumes = raw.get('volume', [])
        by_date = defaultdict(list)
        for i, t in enumerate(ts):
            dt = datetime.fromtimestamp(t, tz=IST)
            by_date[dt.strftime('%Y-%m-%d')].append({
                'time':   dt.strftime('%H:%M'),
                'open':   opens[i]   if i < len(opens)   else 0,
                'high':   highs[i]   if i < len(highs)   else 0,
                'low':    lows[i]    if i < len(lows)    else 0,
                'close':  closes[i]  if i < len(closes)  else 0,
                'volume': volumes[i] if i < len(volumes) else 0,
            })
        data[sym] = dict(by_date)
    return data

def calc_vwap(candles):
    cpv = cv = 0
    out = []
    for c in candles:
        tp = (c['high'] + c['low'] + c['close']) / 3
        cpv += tp * c['volume']
        cv  += c['volume']
        out.append(cpv / cv if cv else c['close'])
    return out

def get_prev_close(data, sym, date_str):
    all_dates = sorted(d for d in data.get(sym, {}) if d < date_str)
    if not all_dates:
        return None
    last_day = data[sym][all_dates[-1]]
    last_day_sorted = sorted(last_day, key=lambda x: x['time'])
    return last_day_sorted[-1]['close'] if last_day_sorted else None

def get_nifty_change(data, date_str):
    for key in ['NIFTY50', 'NIFTY', 'RELIANCE']:
        if key in data and date_str in data[key]:
            prev_dates = sorted(d for d in data[key] if d < date_str)
            if not prev_dates:
                continue
            prev_day = sorted(data[key][prev_dates[-1]], key=lambda x: x['time'])
            today_day = sorted(data[key][date_str], key=lambda x: x['time'])
            if prev_day and today_day:
                pc = prev_day[-1]['close']
                tc = today_day[-1]['close']
                return ((tc - pc) / pc) * 100
    return 0.5  # assume slight positive if no Nifty data

def simulate(candles_after, entry, target, sl):
    for c in candles_after:
        if c['time'] >= '15:15':
            return c['close'], c['time'], 'FORCE_EXIT'
        if c['low'] <= sl:
            return sl, c['time'], 'STOP_LOSS'
        if c['high'] >= target:
            return target, c['time'], 'TARGET_HIT'
    if candles_after:
        last = candles_after[-1]
        return last['close'], last['time'], 'FORCE_EXIT'
    return entry, '15:15', 'FORCE_EXIT'

def pnl(entry, exit_p, qty):
    gross = (exit_p - entry) * qty
    charges = (entry + exit_p) * qty * CHARGES_PCT
    return round(gross - charges, 2), round(gross, 2), round(charges, 2)

# ── SIGNALS ────────────────────────────────────────────────────────────────

def sig_v6(sym, date_str, candles, data, prev_close):
    """V6: gap>1.5% + ORB breakout after 9:30 + above VWAP + Nifty up"""
    if not prev_close or prev_close <= 0:
        return None
    cs = sorted(candles, key=lambda x: x['time'])
    opening = [c for c in cs if '09:15' <= c['time'] <= '09:30']
    if not opening:
        return None
    op = opening[0]['open'] or opening[0]['close']
    if not op:
        return None
    gap = ((op - prev_close) / prev_close) * 100
    if gap < 1.5:
        return None
    nifty = get_nifty_change(data, date_str)
    if nifty < 0:
        return None
    orb_high = max(c['high'] for c in opening)
    vwaps = calc_vwap(cs)
    post = [c for c in cs if c['time'] > '09:30']
    for idx, c in enumerate(post):
        if c['high'] > orb_high:
            ci = cs.index(c)
            vwap = vwaps[ci] if ci < len(vwaps) else 0
            entry = orb_high
            if vwap > 0 and entry < vwap * 0.997:
                continue
            return {
                'strategy': 'V6_ORB',
                'entry': entry,
                'entry_time': c['time'],
                'candles_after': post[idx:],
                'gap_pct': round(gap, 2),
                'nifty_chg': round(nifty, 2),
                'rs': round(gap - nifty, 2),
            }
    return None

def sig_vwap_reclaim(sym, date_str, candles, data, prev_close):
    """VWAP Reclaim 11-13: gap>1% + touched VWAP + reclaimed + gap held"""
    if not prev_close or prev_close <= 0:
        return None
    cs = sorted(candles, key=lambda x: x['time'])
    opening = [c for c in cs if c['time'] <= '09:30']
    if not opening:
        return None
    op = opening[0]['open'] or opening[0]['close']
    gap = ((op - prev_close) / prev_close) * 100
    if gap < 1.0:
        return None
    nifty = get_nifty_change(data, date_str)
    if nifty < 0:
        return None
    vwaps = calc_vwap(cs)
    window = [c for c in cs if '11:00' <= c['time'] <= '13:00']
    for c in window:
        ci = cs.index(c)
        if ci < 1 or ci >= len(vwaps):
            continue
        vwap = vwaps[ci]
        prev_c = cs[ci - 1]
        touched   = prev_c['low'] <= vwap * 1.003
        reclaimed = c['close'] > vwap
        gap_held  = c['close'] > prev_close * 1.005
        if touched and reclaimed and gap_held:
            rs = ((c['close'] - prev_close)/prev_close*100) - nifty
            return {
                'strategy': 'VWAP_RCL',
                'entry': c['close'],
                'entry_time': c['time'],
                'candles_after': cs[ci + 1:],
                'gap_pct': round(gap, 2),
                'nifty_chg': round(nifty, 2),
                'rs': round(rs, 2),
            }
    return None

def sig_trend_cont(sym, date_str, candles, data, prev_close):
    """Trend Cont 13-14:30: gap>1% + above VWAP + near high + RS>0.5%"""
    if not prev_close or prev_close <= 0:
        return None
    cs = sorted(candles, key=lambda x: x['time'])
    opening = [c for c in cs if c['time'] <= '09:30']
    if not opening:
        return None
    op = opening[0]['open'] or opening[0]['close']
    gap = ((op - prev_close) / prev_close) * 100
    if gap < 1.0:
        return None
    nifty = get_nifty_change(data, date_str)
    if nifty < 0.3:
        return None
    vwaps = calc_vwap(cs)
    day_high = max(c['high'] for c in cs)
    window = [c for c in cs if '13:00' <= c['time'] <= '14:30']
    if not window:
        return None
    c = window[0]
    ci = cs.index(c)
    if ci >= len(vwaps):
        return None
    vwap = vwaps[ci]
    if c['close'] < vwap:
        return None
    if c['close'] < day_high * 0.97:
        return None
    rs = ((c['close'] - prev_close)/prev_close*100) - nifty
    if rs < 0.5:
        return None
    return {
        'strategy': 'TREND_CONT',
        'entry': c['close'],
        'entry_time': c['time'],
        'candles_after': cs[ci + 1:],
        'gap_pct': round(gap, 2),
        'nifty_chg': round(nifty, 2),
        'rs': round(rs, 2),
    }

SIGNAL_FNS = [
    ('V6_ORB',    sig_v6),
    ('VWAP_RCL',  sig_vwap_reclaim),
    ('TREND_CONT',sig_trend_cont),
]

# ── MAIN ───────────────────────────────────────────────────────────────────
def run():
    print("Loading 90-day data...")
    data = load_data()
    all_dates = sorted(set(
        d for sym_data in data.values() for d in sym_data
    ))
    print(f"Stocks: {len(data)} | Trading days: {len(all_dates)}")
    print(f"Range: {all_dates[0]} to {all_dates[-1]}")

    # results[variant][strategy][capital] = [trades]
    results = {
        v['name']: {
            s: {cap: [] for cap in CAPITAL_SIZES}
            for s in ['V6_ORB','VWAP_RCL','TREND_CONT','COMBINED']
        }
        for v in VARIANTS
    }

    for date_str in all_dates:
        dow = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')
        day_sigs = []

        for sym, sym_dates in data.items():
            if date_str not in sym_dates:
                continue
            candles = sym_dates[date_str]
            pc = get_prev_close(data, sym, date_str)
            if not pc:
                # estimate from first candle
                cs = sorted(candles, key=lambda x: x['time'])
                pc = cs[0]['open'] * 0.985 if cs else None
            if not pc:
                continue

            for strat_name, fn in SIGNAL_FNS:
                sig = fn(sym, date_str, candles, data, pc)
                if sig:
                    day_sigs.append((strat_name, sym, sig))

        # Sort by entry time — earlier = priority
        day_sigs.sort(key=lambda x: x[2]['entry_time'])

        for v in VARIANTS:
            tgt_pct = v['tgt']
            sl_pct  = v['sl']
            vname   = v['name']
            used = {s: {cap: 0 for cap in CAPITAL_SIZES}
                    for s in ['V6_ORB','VWAP_RCL','TREND_CONT','COMBINED']}

            for strat_name, sym, sig in day_sigs:
                entry = sig['entry']
                if entry <= 0:
                    continue
                target = entry * (1 + tgt_pct)
                sl_p   = entry * (1 - sl_pct)
                ca     = sig['candles_after']
                if not ca:
                    continue
                ep, et, er = simulate(ca, entry, target, sl_p)

                for cap in CAPITAL_SIZES:
                    # 1 trade per day per strategy
                    if used[strat_name][cap] < 1:
                        qty = max(1, int(cap / entry))
                        net, gross, ch = pnl(entry, ep, qty)
                        t = {
                            'date': date_str, 'dow': dow, 'symbol': sym,
                            'strategy': strat_name, 'variant': vname,
                            'entry_time': sig['entry_time'],
                            'exit_time': et, 'exit_reason': er,
                            'entry': round(entry,2), 'exit': round(ep,2),
                            'target': round(target,2), 'sl': round(sl_p,2),
                            'qty': qty, 'win': net > 0,
                            'pnl_net': net, 'pnl_gross': gross,
                            'charges': ch,
                            'gap_pct': sig.get('gap_pct',0),
                            'rs': sig.get('rs',0),
                            'nifty_chg': sig.get('nifty_chg',0),
                            'capital': cap,
                        }
                        results[vname][strat_name][cap].append(t)
                        used[strat_name][cap] += 1

                    # Combined: first signal of any type
                    if used['COMBINED'][cap] < 1:
                        qty = max(1, int(cap / entry))
                        net, gross, ch = pnl(entry, ep, qty)
                        t2 = dict(t) if used[strat_name][cap] == 1 else {
                            'date': date_str, 'dow': dow, 'symbol': sym,
                            'strategy': 'COMBINED', 'variant': vname,
                            'entry_time': sig['entry_time'],
                            'exit_time': et, 'exit_reason': er,
                            'entry': round(entry,2), 'exit': round(ep,2),
                            'target': round(target,2), 'sl': round(sl_p,2),
                            'qty': qty, 'win': net > 0,
                            'pnl_net': net, 'pnl_gross': gross,
                            'charges': ch,
                            'gap_pct': sig.get('gap_pct',0),
                            'rs': sig.get('rs',0),
                            'nifty_chg': sig.get('nifty_chg',0),
                            'original_strategy': strat_name,
                            'capital': cap,
                        }
                        t2['strategy'] = 'COMBINED'
                        results[vname]['COMBINED'][cap].append(t2)
                        used['COMBINED'][cap] += 1

    # ── REPORT ─────────────────────────────────────────────────────────────
    print("\n" + "="*110)
    print("CLEAN 90-DAY BACKTEST — BLACKLIST APPLIED — 1 TRADE/DAY")
    print(f"Stocks: {len(data)} | Days: {len(all_dates)} | Blacklist: {len(BLACKLIST)} stocks removed")
    print("="*110)
    print(f"{'Variant':<12} {'Strategy':<12} {'Capital':>10} {'Days':>5} {'Trades':>7} {'WR%':>6} {'PF':>5} {'Net P&L':>10} {'Monthly':>10} {'Status'}")
    print("-"*110)

    best = []
    all_rows = []

    for v in VARIANTS:
        vname = v['name']
        for strat in ['V6_ORB','VWAP_RCL','TREND_CONT','COMBINED']:
            for cap in CAPITAL_SIZES:
                trades = results[vname][strat][cap]
                if not trades:
                    continue
                wins   = [t for t in trades if t['win']]
                losses = [t for t in trades if not t['win']]
                total  = sum(t['pnl_net'] for t in trades)
                wr     = len(wins)/len(trades)*100
                gw     = sum(t['pnl_net'] for t in wins) if wins else 0
                gl     = abs(sum(t['pnl_net'] for t in losses)) if losses else 1
                pf     = gw/gl if gl > 0 else 99
                fire_days = len(set(t['date'] for t in trades))
                dates  = sorted(set(t['date'] for t in trades))
                span   = (datetime.strptime(dates[-1],'%Y-%m-%d') -
                          datetime.strptime(dates[0],'%Y-%m-%d')).days + 1
                monthly = total/span*30 if span > 0 else 0
                exits  = Counter(t['exit_reason'] for t in trades)
                hit    = exits.get('TARGET_HIT',0)/len(trades)*100

                if wr >= 52 and pf >= 1.2:
                    status = "✅ EDGE"
                    best.append((monthly, vname, strat, cap, len(trades),
                                 fire_days, wr, pf, total, monthly, hit))
                elif wr >= 47 and pf >= 1.0:
                    status = "⚠️ WATCH"
                else:
                    status = "❌"

                row = (vname, strat, cap, fire_days, len(trades),
                       wr, pf, total, monthly, status, hits=hit)

                # Print non-losers and combined
                if status != "❌" or (strat == 'COMBINED' and cap in [30000,100000]):
                    print(f"{vname:<12} {strat:<12} {cap:>10,} {fire_days:>5} "
                          f"{len(trades):>7} {wr:>6.1f} {pf:>5.2f} "
                          f"{total:>10,.0f} {monthly:>10,.0f} {status}")

    print("\n" + "="*110)
    if best:
        print("✅ CONFIGS WITH EDGE (WR>=52%, PF>=1.2):")
        for b in sorted(best, key=lambda x: x[0], reverse=True):
            monthly,vn,st,cap,nt,fd,wr,pf_,tot,mo,hit = b
            print(f"  {vn} {st} Rs.{cap:,}: {nt} trades on {fd} days | "
                  f"{wr:.1f}%WR PF{pf_:.2f} | Net Rs.{tot:,.0f} | "
                  f"Monthly Rs.{mo:,.0f} | TargetHit {hit:.0f}%")
    else:
        print("No configs hit WR>=52% and PF>=1.2")
        print("Best by monthly P&L:")
        all_rows2 = []
        for v in VARIANTS:
            for strat in ['V6_ORB','VWAP_RCL','TREND_CONT','COMBINED']:
                for cap in CAPITAL_SIZES:
                    trades = results[v['name']][strat][cap]
                    if not trades:
                        continue
                    wins = [t for t in trades if t['win']]
                    losses = [t for t in trades if not t['win']]
                    total = sum(t['pnl_net'] for t in trades)
                    wr = len(wins)/len(trades)*100
                    gw = sum(t['pnl_net'] for t in wins) if wins else 0
                    gl = abs(sum(t['pnl_net'] for t in losses)) if losses else 1
                    pf_ = gw/gl if gl > 0 else 99
                    dates = sorted(set(t['date'] for t in trades))
                    span = (datetime.strptime(dates[-1],'%Y-%m-%d') -
                            datetime.strptime(dates[0],'%Y-%m-%d')).days + 1
                    monthly = total/span*30 if span > 0 else 0
                    fire_days = len(set(t['date'] for t in trades))
                    all_rows2.append((monthly,v['name'],strat,cap,
                                      len(trades),fire_days,wr,pf_,total))
        for r in sorted(all_rows2, reverse=True)[:15]:
            mo,vn,st,cap,nt,fd,wr,pf_,tot = r
            print(f"  {vn} {st} Rs.{cap:,}: {nt}t/{fd}days "
                  f"{wr:.1f}%WR PF{pf_:.2f} Net Rs.{tot:,.0f} Monthly Rs.{mo:,.0f}")

    # Save
    os.makedirs(RESULTS, exist_ok=True)
    save = {v['name']: {s: {str(c): results[v['name']][s][c]
            for c in CAPITAL_SIZES}
            for s in ['V6_ORB','VWAP_RCL','TREND_CONT','COMBINED']}
            for v in VARIANTS}
    with open(f'{RESULTS}/clean_90d.json','w') as f:
        json.dump(save, f)
    print(f"\nSaved: {RESULTS}/clean_90d.json")

if __name__ == '__main__':
    run()
