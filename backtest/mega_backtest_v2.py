#!/usr/bin/env python3
"""
MEGA BACKTEST V2 — Fixed targets, blacklist applied, realistic exits
Key fixes from V1:
1. Targets use fixed % of entry price (not daily ATR which is too wide)
2. SL uses fixed % of entry price
3. Blacklist applied (WIPRO, MPHASIS, RALLIS, etc.)
4. Multiple target variants tested: 1%, 1.5%, 2% target with 0.5%, 0.75%, 1% SL
Data: 15-min (20 days, 330 stocks) + Daily (246 days, 188 stocks)
"""
import json, os, math
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_15 = 'cache/historical_v2'
CACHE_DAILY = 'cache/swing_daily'
RESULTS_DIR = 'backtest/results'

CAPITAL_SIZES = [30000, 100000, 150000, 200000]
MAX_TRADES_PER_DAY = {30000: 1, 100000: 3, 150000: 4, 200000: 5}
CHARGES_PCT = 0.001

# Blacklist from V1 analysis (consistent losers across all strategies)
BLACKLIST = {
    'WIPRO', 'MPHASIS', 'RALLIS', 'INDIANB', 'BEL', 'SBIN',
    'GODREJPROP', 'PAYTM', 'RELIANCE', 'RVNL', 'HDFCBANK',
    'BANDHANBNK', 'POLICYBZR', 'ITC', 'ADANIENT'
}

# Target/SL variants to test
VARIANTS = [
    {'name': 'T1_SL05',  'target_pct': 0.01,  'sl_pct': 0.005},
    {'name': 'T15_SL07', 'target_pct': 0.015, 'sl_pct': 0.007},
    {'name': 'T2_SL1',   'target_pct': 0.02,  'sl_pct': 0.010},
    {'name': 'T25_SL12', 'target_pct': 0.025, 'sl_pct': 0.012},
    {'name': 'T3_SL15',  'target_pct': 0.03,  'sl_pct': 0.015},
]

def load_15min_data():
    data = {}
    for fname in os.listdir(CACHE_15):
        if not fname.endswith('.json'):
            continue
        sym = fname.split('_15min_')[0]
        if sym in BLACKLIST:
            continue
        with open(os.path.join(CACHE_15, fname)) as f:
            raw = json.load(f)
        timestamps = raw.get('timestamp', [])
        if not timestamps:
            continue
        opens = raw.get('open', [])
        highs = raw.get('high', [])
        lows = raw.get('low', [])
        closes = raw.get('close', [])
        volumes = raw.get('volume', [])
        by_date = defaultdict(list)
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts, tz=IST)
            by_date[dt.strftime('%Y-%m-%d')].append({
                'time': dt.strftime('%H:%M'),
                'open': opens[i] if i < len(opens) else 0,
                'high': highs[i] if i < len(highs) else 0,
                'low':  lows[i]  if i < len(lows)  else 0,
                'close':closes[i] if i < len(closes) else 0,
                'volume':volumes[i] if i < len(volumes) else 0,
            })
        data[sym] = dict(by_date)
    return data

def load_daily_data():
    data = {}
    for fname in os.listdir(CACHE_DAILY):
        if not fname.endswith('.json'):
            continue
        sym = fname.replace('_daily.json', '')
        with open(os.path.join(CACHE_DAILY, fname)) as f:
            raw = json.load(f)
        timestamps = raw.get('timestamp', [])
        candles = []
        opens = raw.get('open', [])
        highs = raw.get('high', [])
        lows  = raw.get('low', [])
        closes= raw.get('close', [])
        volumes=raw.get('volume', [])
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts, tz=IST)
            candles.append({
                'date':  dt.strftime('%Y-%m-%d'),
                'open':  opens[i]  if i < len(opens)  else 0,
                'high':  highs[i]  if i < len(highs)  else 0,
                'low':   lows[i]   if i < len(lows)   else 0,
                'close': closes[i] if i < len(closes) else 0,
                'volume':volumes[i] if i < len(volumes) else 0,
            })
        candles.sort(key=lambda x: x['date'])
        data[sym] = candles
    return data

def get_prev_close(daily_candles, date_str):
    prior = [c for c in daily_candles if c['date'] < date_str]
    return prior[-1]['close'] if prior else None

def get_nifty_change(daily_data, date_str):
    for key in ['NIFTY50', 'NIFTY', 'RELIANCE', 'HDFCBANK']:
        nifty = daily_data.get(key)
        if nifty:
            day = [c for c in nifty if c['date'] == date_str]
            prev = [c for c in nifty if c['date'] < date_str]
            if day and prev:
                return ((day[0]['close'] - prev[-1]['close']) / prev[-1]['close']) * 100
    return 0

def calc_avg_volume(daily_candles, date_str, period=20):
    prior = [c for c in daily_candles if c['date'] < date_str]
    if len(prior) < 3:
        return 0
    return sum(c['volume'] for c in prior[-period:]) / min(len(prior), period)

def calc_vwap(candles):
    cum_pv = cum_v = 0
    vwaps = []
    for c in candles:
        typical = (c['high'] + c['low'] + c['close']) / 3
        cum_pv += typical * c['volume']
        cum_v  += c['volume']
        vwaps.append(cum_pv / cum_v if cum_v > 0 else c['close'])
    return vwaps

def simulate_trade_fixed(candles_after, entry, target, sl):
    for c in candles_after:
        if c['time'] >= '15:15':
            return c['close'], c['time'], 'FORCE_EXIT'
        if c['low'] <= sl:
            return sl, c['time'], 'STOP_LOSS'
        if c['high'] >= target:
            return target, c['time'], 'TARGET_HIT'
    last = candles_after[-1] if candles_after else None
    return (last['close'], last['time'], 'FORCE_EXIT') if last else (entry, '15:15', 'FORCE_EXIT')

def calc_pnl(entry, exit_price, qty):
    gross = (exit_price - entry) * qty
    charges = (entry + exit_price) * qty * CHARGES_PCT
    return round(gross - charges, 2), round(gross, 2), round(charges, 2)

def find_orb_signal(sym, date_str, candles_15, daily_data, prev_close):
    """V6 ORB: gap>1.5% + ORB breakout after 9:30 + volume + above VWAP + Nifty up"""
    if not candles_15 or not prev_close or prev_close <= 0:
        return None
    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if '09:15' <= c['time'] <= '09:30']
    if not opening:
        return None
    open_price = opening[0]['open'] or opening[0]['close']
    if not open_price:
        return None
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.5:
        return None
    nifty_chg = get_nifty_change(daily_data, date_str)
    if nifty_chg < 0:
        return None
    orb_high = max(c['high'] for c in opening)
    daily_sym = daily_data.get(sym, [])
    avg_vol = calc_avg_volume(daily_sym, date_str)
    vwaps = calc_vwap(candles)
    post = [c for c in candles if c['time'] > '09:30']
    for idx, c in enumerate(post):
        if c['high'] > orb_high:
            ci = candles.index(c)
            vwap = vwaps[ci] if ci < len(vwaps) else 0
            entry = orb_high
            if vwap > 0 and entry < vwap * 0.997:
                continue
            rs = gap_pct - nifty_chg
            return {
                'entry': entry,
                'entry_time': c['time'],
                'candles_after': post[idx:],
                'gap_pct': round(gap_pct, 2),
                'nifty_chg': round(nifty_chg, 2),
                'rs': round(rs, 2),
                'avg_vol': avg_vol,
                'day_vol': sum(c2['volume'] for c2 in candles),
            }
    return None

def find_vwap_reclaim(sym, date_str, candles_15, daily_data, prev_close):
    """VWAP Reclaim 11:00-13:00: gap>1% + touched VWAP + reclaimed"""
    if not candles_15 or not prev_close or prev_close <= 0:
        return None
    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if c['time'] <= '09:30']
    if not opening:
        return None
    open_price = opening[0]['open'] or opening[0]['close']
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.0:
        return None
    nifty_chg = get_nifty_change(daily_data, date_str)
    if nifty_chg < 0:
        return None
    vwaps = calc_vwap(candles)
    window = [c for c in candles if '11:00' <= c['time'] <= '13:00']
    for c in window:
        ci = candles.index(c)
        if ci < 1 or ci >= len(vwaps):
            continue
        vwap = vwaps[ci]
        prev_c = candles[ci-1]
        if prev_c['low'] <= vwap * 1.003 and c['close'] > vwap:
            if c['close'] < prev_close * 1.005:
                continue
            rs = ((c['close'] - prev_close)/prev_close*100) - nifty_chg
            return {
                'entry': c['close'],
                'entry_time': c['time'],
                'candles_after': candles[ci+1:],
                'gap_pct': round(gap_pct, 2),
                'nifty_chg': round(nifty_chg, 2),
                'rs': round(rs, 2),
            }
    return None

def find_trend_cont(sym, date_str, candles_15, daily_data, prev_close):
    """Trend continuation 13:00-14:30: gap>1% + above VWAP + near high + RS>0.5%"""
    if not candles_15 or not prev_close or prev_close <= 0:
        return None
    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if c['time'] <= '09:30']
    if not opening:
        return None
    open_price = opening[0]['open'] or opening[0]['close']
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.0:
        return None
    nifty_chg = get_nifty_change(daily_data, date_str)
    if nifty_chg < 0.3:
        return None
    vwaps = calc_vwap(candles)
    day_high = max(c['high'] for c in candles)
    window = [c for c in candles if '13:00' <= c['time'] <= '14:30']
    if not window:
        return None
    c = window[0]
    ci = candles.index(c)
    if ci >= len(vwaps):
        return None
    vwap = vwaps[ci]
    if c['close'] < vwap:
        return None
    if c['close'] < day_high * 0.97:
        return None
    rs = ((c['close'] - prev_close)/prev_close*100) - nifty_chg
    if rs < 0.5:
        return None
    return {
        'entry': c['close'],
        'entry_time': c['time'],
        'candles_after': candles[ci+1:],
        'gap_pct': round(gap_pct, 2),
        'nifty_chg': round(nifty_chg, 2),
        'rs': round(rs, 2),
    }

SIGNAL_FNS = [
    ('ORB',        find_orb_signal),
    ('VWAP_RCL',   find_vwap_reclaim),
    ('TREND_CONT', find_trend_cont),
]

def run():
    print("Loading data...")
    d15 = load_15min_data()
    ddaily = load_daily_data()
    print(f"  15-min: {len(d15)} stocks (blacklist applied)")
    print(f"  Daily:  {len(ddaily)} stocks")

    all_dates = sorted(set(
        date for sym_data in d15.values() for date in sym_data
    ))
    print(f"  Trading days: {len(all_dates)} ({all_dates[0]} to {all_dates[-1]})")

    # Results: variant -> strategy -> capital -> [trades]
    results = {}
    for v in VARIANTS:
        results[v['name']] = {
            s: {cap: [] for cap in CAPITAL_SIZES}
            for s in ['ORB','VWAP_RCL','TREND_CONT','COMBINED']
        }

    for date_str in all_dates:
        dow = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')
        # collect all signals this day
        day_signals = []  # (strategy, sym, sig)

        for sym, sym_dates in d15.items():
            if date_str not in sym_dates:
                continue
            candles = sym_dates[date_str]
            daily_sym = ddaily.get(sym, [])
            prev_close = get_prev_close(daily_sym, date_str)
            if not prev_close:
                c_sorted = sorted(candles, key=lambda x: x['time'])
                prev_close = c_sorted[0]['open']*0.985 if c_sorted else None
            if not prev_close:
                continue

            for strat_name, fn in SIGNAL_FNS:
                sig = fn(sym, date_str, candles, ddaily, prev_close)
                if sig:
                    day_signals.append((strat_name, sym, sig, prev_close))

        # For each variant, simulate all signals
        for v in VARIANTS:
            tgt_pct = v['target_pct']
            sl_pct  = v['sl_pct']
            vname   = v['name']

            # Per strategy per capital: limit slots
            day_used = {s: {cap: 0 for cap in CAPITAL_SIZES} for s in ['ORB','VWAP_RCL','TREND_CONT','COMBINED']}

            # Sort by entry time (earlier entries first)
            day_signals_sorted = sorted(day_signals, key=lambda x: x[2]['entry_time'])

            for strat_name, sym, sig, prev_close in day_signals_sorted:
                entry = sig['entry']
                target = entry * (1 + tgt_pct)
                sl     = entry * (1 - sl_pct)
                candles_after = sig['candles_after']
                if not candles_after:
                    continue

                exit_price, exit_time, exit_reason = simulate_trade_fixed(
                    candles_after, entry, target, sl
                )

                for cap in CAPITAL_SIZES:
                    max_t = MAX_TRADES_PER_DAY[cap]
                    cap_per_trade = cap / max_t

                    # Per-strategy slot
                    if day_used[strat_name][cap] < max_t:
                        qty = max(1, int(cap_per_trade / entry))
                        pnl_net, pnl_gross, charges = calc_pnl(entry, exit_price, qty)
                        trade = {
                            'date': date_str, 'dow': dow, 'symbol': sym,
                            'strategy': strat_name, 'variant': vname,
                            'entry_time': sig['entry_time'], 'exit_time': exit_time,
                            'entry': round(entry,2), 'exit': round(exit_price,2),
                            'target': round(target,2), 'sl': round(sl,2),
                            'qty': qty, 'exit_reason': exit_reason,
                            'pnl_net': pnl_net, 'pnl_gross': pnl_gross,
                            'charges': charges, 'win': pnl_net > 0,
                            'gap_pct': sig.get('gap_pct',0),
                            'rs': sig.get('rs',0),
                            'nifty_chg': sig.get('nifty_chg',0),
                            'capital': cap,
                        }
                        results[vname][strat_name][cap].append(trade)
                        day_used[strat_name][cap] += 1

                    # Combined slot (first signal of any type per day)
                    if day_used['COMBINED'][cap] < max_t:
                        qty = max(1, int(cap_per_trade / entry))
                        pnl_net, pnl_gross, charges = calc_pnl(entry, exit_price, qty)
                        trade = {
                            'date': date_str, 'dow': dow, 'symbol': sym,
                            'strategy': 'COMBINED', 'variant': vname,
                            'entry_time': sig['entry_time'], 'exit_time': exit_time,
                            'entry': round(entry,2), 'exit': round(exit_price,2),
                            'target': round(target,2), 'sl': round(sl,2),
                            'qty': qty, 'exit_reason': exit_reason,
                            'pnl_net': pnl_net, 'pnl_gross': pnl_gross,
                            'charges': charges, 'win': pnl_net > 0,
                            'gap_pct': sig.get('gap_pct',0),
                            'rs': sig.get('rs',0),
                            'original_strategy': strat_name,
                            'capital': cap,
                        }
                        results[vname]['COMBINED'][cap].append(trade)
                        day_used['COMBINED'][cap] += 1

    # Report
    print("\n" + "="*100)
    print("MEGA BACKTEST V2 — FIXED % TARGETS")
    print(f"Blacklist applied: {len(BLACKLIST)} stocks removed")
    print("="*100)

    best_configs = []

    hdr = f"{'Variant':<12} {'Strategy':<12} {'Capital':>10} {'Trades':>7} {'WR%':>6} {'PF':>5} {'Net P&L':>10} {'Monthly':>10} {'Charges':>9} {'Status'}"
    print(hdr)
    print("-"*100)

    for v in VARIANTS:
        vname = v['name']
        for strat in ['ORB','VWAP_RCL','TREND_CONT','COMBINED']:
            for cap in CAPITAL_SIZES:
                trades = results[vname][strat][cap]
                if not trades:
                    continue
                wins   = [t for t in trades if t['win']]
                losses = [t for t in trades if not t['win']]
                total_pnl = sum(t['pnl_net'] for t in trades)
                total_charges = sum(t['charges'] for t in trades)
                wr = len(wins)/len(trades)*100
                gw = sum(t['pnl_net'] for t in wins) if wins else 0
                gl = abs(sum(t['pnl_net'] for t in losses)) if losses else 1
                pf = gw/gl if gl > 0 else 99

                dates = sorted(set(t['date'] for t in trades))
                span = (datetime.strptime(dates[-1],'%Y-%m-%d') -
                        datetime.strptime(dates[0],'%Y-%m-%d')).days + 1
                monthly = (total_pnl/span*30) if span > 0 else 0

                exits = Counter(t['exit_reason'] for t in trades)
                hit_rate = exits.get('TARGET_HIT',0)/len(trades)*100

                if wr >= 50 and pf >= 1.2:
                    status = "✅ EDGE"
                    best_configs.append({
                        'variant':vname,'strategy':strat,'capital':cap,
                        'trades':len(trades),'wr':round(wr,1),'pf':round(pf,2),
                        'net_pnl':round(total_pnl,0),'monthly':round(monthly,0),
                        'hit_rate':round(hit_rate,1)
                    })
                elif wr >= 45 and pf >= 1.0:
                    status = "⚠️ WATCH"
                else:
                    status = "❌"

                if status != "❌" or (strat == 'COMBINED' and cap == 100000):
                    print(f"{vname:<12} {strat:<12} {cap:>10,} {len(trades):>7} {wr:>6.1f} {pf:>5.2f} {total_pnl:>10,.0f} {monthly:>10,.0f} {total_charges:>9,.0f} {status}")

    print("\n" + "="*100)
    print("TOP CONFIGS WITH EDGE:")
    print("="*100)
    if best_configs:
        for c in sorted(best_configs, key=lambda x: x['monthly'], reverse=True):
            print(f"  {c['variant']} {c['strategy']} Rs.{c['capital']:,}: "
                  f"{c['trades']}t {c['wr']}%WR PF{c['pf']} "
                  f"Net Rs.{c['net_pnl']:,} Monthly Rs.{c['monthly']:,} "
                  f"TargetHit:{c['hit_rate']}%")
    else:
        print("  No configs met WR>=50% and PF>=1.2 threshold")
        print("  Best configs by monthly P&L (WR>=45%):")
        watch = []
        for v in VARIANTS:
            for strat in ['ORB','VWAP_RCL','TREND_CONT','COMBINED']:
                for cap in CAPITAL_SIZES:
                    trades = results[v['name']][strat][cap]
                    if not trades:
                        continue
                    wins = [t for t in trades if t['win']]
                    losses = [t for t in trades if not t['win']]
                    wr = len(wins)/len(trades)*100
                    gw = sum(t['pnl_net'] for t in wins) if wins else 0
                    gl = abs(sum(t['pnl_net'] for t in losses)) if losses else 1
                    pf = gw/gl if gl > 0 else 99
                    total_pnl = sum(t['pnl_net'] for t in trades)
                    dates = sorted(set(t['date'] for t in trades))
                    span = (datetime.strptime(dates[-1],'%Y-%m-%d') -
                            datetime.strptime(dates[0],'%Y-%m-%d')).days + 1
                    monthly = total_pnl/span*30 if span > 0 else 0
                    if wr >= 42 or pf >= 1.0:
                        watch.append((monthly, v['name'], strat, cap, len(trades), wr, pf, total_pnl))
        for monthly,vn,st,cap,nt,wr,pf,tp in sorted(watch,reverse=True)[:20]:
            print(f"  {vn} {st} Rs.{cap:,}: {nt}t {wr:.1f}%WR PF{pf:.2f} Monthly Rs.{monthly:,.0f}")

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save = {}
    for v in VARIANTS:
        save[v['name']] = {}
        for strat in ['ORB','VWAP_RCL','TREND_CONT','COMBINED']:
            save[v['name']][strat] = {}
            for cap in CAPITAL_SIZES:
                save[v['name']][strat][str(cap)] = results[v['name']][strat][cap]

    with open(f'{RESULTS_DIR}/mega_v2.json','w') as f:
        json.dump(save, f)
    print(f"\nSaved: {RESULTS_DIR}/mega_v2.json")

if __name__ == '__main__':
    run()
