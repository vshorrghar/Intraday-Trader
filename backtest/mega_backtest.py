#!/usr/bin/env python3
"""
MEGA BACKTEST — All strategies, all capital sizes, full trade details
Data: 15-min (20 days, 330 stocks) + Daily (246 days, 188 stocks)
Output: backtest/results/mega_backtest.json + mega_backtest_report.txt
"""
import json, os, math
from datetime import datetime, timedelta, timezone
from collections import defaultdict

IST = timezone(timedelta(hours=5, minutes=30))

# ── CONSTANTS ──────────────────────────────────────────────────────────────
CACHE_15 = 'cache/historical_v2'
CACHE_DAILY = 'cache/swing_daily'
RESULTS_DIR = 'backtest/results'
CHARGES_PCT = 0.001  # 0.1% round trip (STT + brokerage + exchange)
CAPITAL_SIZES = [30000, 100000, 150000, 200000]
MAX_TRADES_PER_DAY = {30000: 1, 100000: 3, 150000: 4, 200000: 5}

# ── DATA LOADERS ───────────────────────────────────────────────────────────
def load_15min_data():
    """Load all 15-min cached data. Returns {symbol: {date: [candles]}}"""
    data = {}
    for fname in os.listdir(CACHE_15):
        if not fname.endswith('.json'):
            continue
        sym = fname.split('_15min_')[0]
        with open(os.path.join(CACHE_15, fname)) as f:
            raw = json.load(f)
        opens = raw.get('open', [])
        highs = raw.get('high', [])
        lows = raw.get('low', [])
        closes = raw.get('close', [])
        volumes = raw.get('volume', [])
        timestamps = raw.get('timestamp', [])
        if not timestamps:
            continue
        by_date = defaultdict(list)
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts, tz=IST)
            date_str = dt.strftime('%Y-%m-%d')
            by_date[date_str].append({
                'time': dt.strftime('%H:%M'),
                'open': opens[i] if i < len(opens) else 0,
                'high': highs[i] if i < len(highs) else 0,
                'low': lows[i] if i < len(lows) else 0,
                'close': closes[i] if i < len(closes) else 0,
                'volume': volumes[i] if i < len(volumes) else 0,
                'ts': ts
            })
        data[sym] = dict(by_date)
    return data

def load_daily_data():
    """Load all daily cached data. Returns {symbol: [candles sorted by date]}"""
    data = {}
    for fname in os.listdir(CACHE_DAILY):
        if not fname.endswith('.json'):
            continue
        sym = fname.replace('_daily.json', '')
        with open(os.path.join(CACHE_DAILY, fname)) as f:
            raw = json.load(f)
        opens = raw.get('open', [])
        highs = raw.get('high', [])
        lows = raw.get('low', [])
        closes = raw.get('close', [])
        volumes = raw.get('volume', [])
        timestamps = raw.get('timestamp', [])
        candles = []
        for i, ts in enumerate(timestamps):
            dt = datetime.fromtimestamp(ts, tz=IST)
            candles.append({
                'date': dt.strftime('%Y-%m-%d'),
                'open': opens[i] if i < len(opens) else 0,
                'high': highs[i] if i < len(highs) else 0,
                'low': lows[i] if i < len(lows) else 0,
                'close': closes[i] if i < len(closes) else 0,
                'volume': volumes[i] if i < len(volumes) else 0,
            })
        candles.sort(key=lambda x: x['date'])
        data[sym] = candles
    return data

# ── TECHNICAL INDICATORS ───────────────────────────────────────────────────
def calc_atr(candles, period=14):
    """ATR from list of candles with high/low/close"""
    if len(candles) < 2:
        return 0
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            candles[i]['high'] - candles[i]['low'],
            abs(candles[i]['high'] - candles[i-1]['close']),
            abs(candles[i]['low'] - candles[i-1]['close'])
        )
        trs.append(tr)
    if not trs:
        return 0
    return sum(trs[-period:]) / min(len(trs), period)

def calc_vwap(candles):
    """VWAP from intraday candles"""
    cum_pv = cum_v = 0
    vwaps = []
    for c in candles:
        typical = (c['high'] + c['low'] + c['close']) / 3
        cum_pv += typical * c['volume']
        cum_v += c['volume']
        vwaps.append(cum_pv / cum_v if cum_v > 0 else c['close'])
    return vwaps

def calc_sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period

def calc_rsi2(closes):
    """RSI(2) for swing strategy"""
    if len(closes) < 3:
        return 50
    gains = losses = 0
    for i in range(len(closes)-2, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def calc_avg_volume(daily_candles, date_str, period=20):
    """20-day average volume before date"""
    prior = [c for c in daily_candles if c['date'] < date_str]
    if len(prior) < 5:
        return 0
    vols = [c['volume'] for c in prior[-period:]]
    return sum(vols) / len(vols)

def get_prev_close(daily_candles, date_str):
    prior = [c for c in daily_candles if c['date'] < date_str]
    return prior[-1]['close'] if prior else None

def get_nifty_change(daily_data, date_str):
    """Get Nifty % change for the day"""
    nifty = daily_data.get('NIFTY50') or daily_data.get('NIFTY') or daily_data.get('RELIANCE')
    if not nifty:
        return 0
    day_candles = [c for c in nifty if c['date'] == date_str]
    prev = [c for c in nifty if c['date'] < date_str]
    if not day_candles or not prev:
        return 0
    return ((day_candles[0]['close'] - prev[-1]['close']) / prev[-1]['close']) * 100

# ── TRADE SIMULATOR ────────────────────────────────────────────────────────
def simulate_trade(candles_after_entry, entry_price, sl, target, entry_time):
    """Walk candles after entry, return exit details"""
    for c in candles_after_entry:
        if c['time'] >= '15:15':
            # Force exit
            exit_price = c['close']
            return exit_price, c['time'], 'FORCE_EXIT'
        if c['low'] <= sl:
            return sl, c['time'], 'STOP_LOSS'
        if c['high'] >= target:
            return target, c['time'], 'TARGET_HIT'
    # End of day
    last = candles_after_entry[-1] if candles_after_entry else None
    if last:
        return last['close'], last['time'], 'FORCE_EXIT'
    return entry_price, entry_time, 'NO_EXIT'

def calc_pnl(entry, exit_price, qty, exit_reason):
    gross = (exit_price - entry) * qty
    charges = (entry + exit_price) * qty * CHARGES_PCT
    return gross - charges, gross, charges

def calc_qty(capital_per_trade, entry_price):
    if entry_price <= 0:
        return 0
    return max(1, int(capital_per_trade / entry_price))

# ── STRATEGY 1: V6 ORB GAP ─────────────────────────────────────────────────
def strategy_v6_orb(sym, date_str, candles_15, daily_data, prev_close):
    """
    Rules:
    1. Gap > 1.5% from prev close
    2. ORB breakout after 9:30 (price > max of 9:15-9:30 candles)
    3. Volume > 1.5x 20-day avg
    4. Price above VWAP at breakout
    5. Nifty up on the day
    """
    if not candles_15 or not prev_close or prev_close <= 0:
        return None

    # Sort candles by time
    candles = sorted(candles_15, key=lambda x: x['time'])

    # Opening candles (9:15-9:30)
    opening = [c for c in candles if '09:15' <= c['time'] <= '09:30']
    if not opening:
        return None

    open_price = opening[0]['open'] if opening[0]['open'] > 0 else opening[0]['close']
    if open_price <= 0:
        return None

    # Gap check
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.5:
        return None

    # Nifty direction
    nifty_change = get_nifty_change(daily_data, date_str)
    if nifty_change < 0:
        return None

    # ORB high
    orb_high = max(c['high'] for c in opening)

    # Volume avg
    daily_sym = daily_data.get(sym, [])
    avg_vol = calc_avg_volume(daily_sym, date_str, 20)
    day_vol = sum(c['volume'] for c in candles)
    if avg_vol > 0 and day_vol < avg_vol * 0.5:
        return None

    # VWAP
    vwaps = calc_vwap(candles)

    # ATR from daily
    daily_candles = daily_data.get(sym, [])
    prior_daily = [c for c in daily_candles if c['date'] < date_str]
    atr = calc_atr(prior_daily[-20:]) if len(prior_daily) >= 14 else open_price * 0.015

    # Find breakout candle AFTER 9:30
    post_opening = [c for c in candles if c['time'] > '09:30']
    for idx, c in enumerate(post_opening):
        if c['high'] > orb_high:
            entry_price = orb_high  # enter at ORB high
            # Volume check at breakout
            if avg_vol > 0 and c['volume'] < avg_vol * 0.05:
                continue
            # VWAP check
            candle_idx = candles.index(c)
            vwap_at_entry = vwaps[candle_idx] if candle_idx < len(vwaps) else 0
            if entry_price < vwap_at_entry * 0.998:
                continue

            sl = entry_price - (1.5 * atr)
            target = entry_price + (3.0 * atr)

            if target <= entry_price or sl >= entry_price:
                continue
            rr = (target - entry_price) / (entry_price - sl)
            if rr < 1.8:
                continue

            return {
                'strategy': 'V6_ORB',
                'entry_price': round(entry_price, 2),
                'entry_time': c['time'],
                'sl': round(sl, 2),
                'target': round(target, 2),
                'gap_pct': round(gap_pct, 2),
                'atr': round(atr, 2),
                'nifty_change': round(nifty_change, 2),
                'candles_after': post_opening[idx:]
            }
    return None

# ── STRATEGY 2: V6 + RELATIVE STRENGTH ─────────────────────────────────────
def strategy_v6_rs(sym, date_str, candles_15, daily_data, prev_close):
    """V6 + RS filter: stock must outperform Nifty by 0.5%+"""
    sig = strategy_v6_orb(sym, date_str, candles_15, daily_data, prev_close)
    if not sig:
        return None
    # RS check: stock gap vs Nifty change
    nifty_change = sig['nifty_change']
    if sig['gap_pct'] - nifty_change < 0.5:
        return None
    sig['strategy'] = 'V6_RS'
    return sig

# ── STRATEGY 3: GAP AND HOLD ───────────────────────────────────────────────
def strategy_gap_hold(sym, date_str, candles_15, daily_data, prev_close):
    """
    Stock gapped > 2% and held above 50% of gap by 11:00 AM
    Entry: 11:00 AM candle if still above gap midpoint
    """
    if not candles_15 or not prev_close or prev_close <= 0:
        return None

    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if c['time'] <= '09:30']
    if not opening:
        return None

    open_price = opening[0]['open'] if opening[0]['open'] > 0 else opening[0]['close']
    if open_price <= 0:
        return None

    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 2.0:
        return None

    nifty_change = get_nifty_change(daily_data, date_str)
    if nifty_change < 0.3:
        return None

    gap_midpoint = prev_close + (open_price - prev_close) * 0.5

    # Check 11:00 candle
    eleven = [c for c in candles if '10:45' <= c['time'] <= '11:15']
    if not eleven:
        return None

    entry_candle = eleven[0]
    if entry_candle['close'] < gap_midpoint:
        return None

    entry_price = entry_candle['close']
    daily_candles = daily_data.get(sym, [])
    prior_daily = [c for c in daily_candles if c['date'] < date_str]
    atr = calc_atr(prior_daily[-20:]) if len(prior_daily) >= 14 else entry_price * 0.015

    sl = entry_price - (1.5 * atr)
    target = entry_price + (2.5 * atr)

    if target <= entry_price or sl >= entry_price:
        return None

    candles_after = [c for c in candles if c['time'] > entry_candle['time']]

    return {
        'strategy': 'GAP_HOLD',
        'entry_price': round(entry_price, 2),
        'entry_time': entry_candle['time'],
        'sl': round(sl, 2),
        'target': round(target, 2),
        'gap_pct': round(gap_pct, 2),
        'atr': round(atr, 2),
        'nifty_change': round(nifty_change, 2),
        'candles_after': candles_after
    }

# ── STRATEGY 4: VWAP RECLAIM ───────────────────────────────────────────────
def strategy_vwap_reclaim(sym, date_str, candles_15, daily_data, prev_close):
    """
    11:00-13:00 window
    Stock was up >1% at open, pulled back to VWAP, now reclaiming
    """
    if not candles_15 or not prev_close or prev_close <= 0:
        return None

    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if c['time'] <= '09:30']
    if not opening:
        return None

    open_price = opening[0]['open'] if opening[0]['open'] > 0 else opening[0]['close']
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.0:
        return None

    nifty_change = get_nifty_change(daily_data, date_str)
    if nifty_change < 0:
        return None

    vwaps = calc_vwap(candles)

    # Look for VWAP reclaim between 11:00-13:00
    window = [c for c in candles if '11:00' <= c['time'] <= '13:00']
    for idx, c in enumerate(window):
        candle_idx = candles.index(c)
        if candle_idx < 1 or candle_idx >= len(vwaps):
            continue
        vwap = vwaps[candle_idx]
        prev_vwap = vwaps[candle_idx - 1]
        prev_c = candles[candle_idx - 1]

        # Previous candle touched VWAP (low near VWAP)
        touched = prev_c['low'] <= vwap * 1.003
        # Current candle is above VWAP (reclaim)
        reclaimed = c['close'] > vwap

        if not (touched and reclaimed):
            continue

        # Gap still held (price > 0.5% above prev close)
        if c['close'] < prev_close * 1.005:
            continue

        entry_price = c['close']
        daily_candles = daily_data.get(sym, [])
        prior_daily = [c2 for c2 in daily_candles if c2['date'] < date_str]
        atr = calc_atr(prior_daily[-20:]) if len(prior_daily) >= 14 else entry_price * 0.015

        sl = vwap - (0.5 * atr)
        target = entry_price + (2.0 * atr)

        if target <= entry_price or sl >= entry_price:
            continue

        candles_after = candles[candle_idx + 1:]

        return {
            'strategy': 'VWAP_RECLAIM',
            'entry_price': round(entry_price, 2),
            'entry_time': c['time'],
            'sl': round(sl, 2),
            'target': round(target, 2),
            'gap_pct': round(gap_pct, 2),
            'atr': round(atr, 2),
            'vwap': round(vwap, 2),
            'nifty_change': round(nifty_change, 2),
            'candles_after': candles_after
        }
    return None

# ── STRATEGY 5: TREND CONTINUATION ────────────────────────────────────────
def strategy_trend_cont(sym, date_str, candles_15, daily_data, prev_close):
    """
    13:00-14:30 window
    Stock up >1% AND above VWAP AND near day high AND RS vs Nifty > 0.5%
    """
    if not candles_15 or not prev_close or prev_close <= 0:
        return None

    candles = sorted(candles_15, key=lambda x: x['time'])
    opening = [c for c in candles if c['time'] <= '09:30']
    if not opening:
        return None

    open_price = opening[0]['open'] if opening[0]['open'] > 0 else opening[0]['close']
    gap_pct = ((open_price - prev_close) / prev_close) * 100
    if gap_pct < 1.0:
        return None

    nifty_change = get_nifty_change(daily_data, date_str)
    if nifty_change < 0.3:
        return None

    vwaps = calc_vwap(candles)
    day_high = max(c['high'] for c in candles)

    # Check 13:00-14:30 candles
    window = [c for c in candles if '13:00' <= c['time'] <= '14:30']
    if not window:
        return None

    entry_candle = window[0]
    candle_idx = candles.index(entry_candle)
    if candle_idx >= len(vwaps):
        return None

    vwap = vwaps[candle_idx]
    price = entry_candle['close']

    # Above VWAP
    if price < vwap:
        return None

    # Within 3% of day high
    if price < day_high * 0.97:
        return None

    # RS filter
    stock_change = ((price - prev_close) / prev_close) * 100
    rs = stock_change - nifty_change
    if rs < 0.5:
        return None

    entry_price = price
    daily_candles = daily_data.get(sym, [])
    prior_daily = [c for c in daily_candles if c['date'] < date_str]
    atr = calc_atr(prior_daily[-20:]) if len(prior_daily) >= 14 else entry_price * 0.015

    sl = entry_price - (0.8 * atr)
    target = entry_price + (1.5 * atr)

    if target <= entry_price or sl >= entry_price:
        return None

    candles_after = candles[candle_idx + 1:]

    return {
        'strategy': 'TREND_CONT',
        'entry_price': round(entry_price, 2),
        'entry_time': entry_candle['time'],
        'sl': round(sl, 2),
        'target': round(target, 2),
        'gap_pct': round(gap_pct, 2),
        'atr': round(atr, 2),
        'rs': round(rs, 2),
        'nifty_change': round(nifty_change, 2),
        'candles_after': candles_after
    }

# ── STRATEGY 6: SWING CRABEL RSI2 (DAILY) ────────────────────────────────
def strategy_swing_crabel(sym, daily_candles, as_of_date):
    """
    RSI(2) < 5 + above 200-DMA + Nifty above 200-DMA
    Uses daily candles only
    """
    if len(daily_candles) < 205:
        return None

    prior = [c for c in daily_candles if c['date'] < as_of_date]
    if len(prior) < 205:
        return None

    closes = [c['close'] for c in prior]
    sma200 = calc_sma(closes, 200)
    if not sma200:
        return None

    current_close = closes[-1]
    if current_close < sma200:
        return None  # Below 200-DMA

    rsi = calc_rsi2(closes[-10:])
    if rsi >= 5:
        return None

    atr = calc_atr(prior[-20:])
    if atr <= 0:
        return None

    entry_price = current_close
    sl = entry_price - (1.0 * atr)
    target = entry_price + (2.0 * atr)

    return {
        'strategy': 'SWING_CRABEL',
        'entry_price': round(entry_price, 2),
        'entry_date': prior[-1]['date'],
        'sl': round(sl, 2),
        'target': round(target, 2),
        'rsi2': round(rsi, 2),
        'sma200': round(sma200, 2),
        'atr': round(atr, 2),
    }

# ── MAIN BACKTEST ENGINE ───────────────────────────────────────────────────
def run_backtest(data_15, data_daily):
    print("Loading trading dates...")

    # Get all trading dates from 15-min data
    all_dates = set()
    for sym_data in data_15.values():
        all_dates.update(sym_data.keys())
    trading_dates = sorted(all_dates)
    print(f"Trading dates (15-min): {len(trading_dates)} — {trading_dates[0]} to {trading_dates[-1]}")

    # Get all trading dates from daily data
    daily_dates = set()
    for candles in data_daily.values():
        daily_dates.update(c['date'] for c in candles)
    daily_trading_dates = sorted(daily_dates)
    print(f"Trading dates (daily): {len(daily_trading_dates)} — {daily_trading_dates[0]} to {daily_trading_dates[-1]}")

    # ── INTRADAY STRATEGIES (15-min data) ──────────────────────────────────
    INTRADAY_STRATEGIES = [
        ('V6_ORB', strategy_v6_orb),
        ('V6_RS', strategy_v6_rs),
        ('GAP_HOLD', strategy_gap_hold),
        ('VWAP_RECLAIM', strategy_vwap_reclaim),
        ('TREND_CONT', strategy_trend_cont),
    ]

    # Results store: {strategy: {capital: [trades]}}
    results = {}
    for strat_name, _ in INTRADAY_STRATEGIES:
        results[strat_name] = {cap: [] for cap in CAPITAL_SIZES}
    results['SWING_CRABEL'] = {cap: [] for cap in CAPITAL_SIZES}
    results['COMBINED_INTRADAY'] = {cap: [] for cap in CAPITAL_SIZES}

    # ── RUN INTRADAY ──────────────────────────────────────────────────────
    print(f"\nRunning intraday strategies on {len(trading_dates)} days x {len(data_15)} stocks...")
    for date_str in trading_dates:
        day_of_week = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')

        # Per-day per-capital slot tracking
        day_trades = {cap: [] for cap in CAPITAL_SIZES}

        for sym, sym_dates in data_15.items():
            if date_str not in sym_dates:
                continue

            candles_15 = sym_dates[date_str]
            if not candles_15:
                continue

            # Get prev close from daily data
            daily_sym = data_daily.get(sym, [])
            prev_close = get_prev_close(daily_sym, date_str)
            if not prev_close:
                # Estimate from first candle open
                candles_sorted = sorted(candles_15, key=lambda x: x['time'])
                if candles_sorted:
                    prev_close = candles_sorted[0]['open'] * 0.985  # approximate
                else:
                    continue

            for strat_name, strat_fn in INTRADAY_STRATEGIES:
                sig = strat_fn(sym, date_str, candles_15, data_daily, prev_close)
                if not sig:
                    continue

                entry_price = sig['entry_price']
                sl = sig['sl']
                target = sig['target']
                entry_time = sig['entry_time']
                candles_after = sig.get('candles_after', [])

                if not candles_after:
                    continue

                exit_price, exit_time, exit_reason = simulate_trade(
                    candles_after, entry_price, sl, target, entry_time
                )

                for cap in CAPITAL_SIZES:
                    max_trades = MAX_TRADES_PER_DAY[cap]
                    # Check if slot available for this strategy on this day
                    strat_trades_today = [t for t in day_trades[cap] if t['strategy'] == strat_name]
                    if len(strat_trades_today) >= max_trades:
                        continue

                    cap_per_trade = cap / max_trades
                    qty = calc_qty(cap_per_trade, entry_price)
                    if qty <= 0:
                        continue

                    pnl_net, pnl_gross, charges = calc_pnl(entry_price, exit_price, qty, exit_reason)

                    trade = {
                        'date': date_str,
                        'day_of_week': day_of_week,
                        'symbol': sym,
                        'strategy': strat_name,
                        'entry_time': entry_time,
                        'exit_time': exit_time,
                        'entry_price': entry_price,
                        'exit_price': round(exit_price, 2),
                        'sl': sl,
                        'target': target,
                        'qty': qty,
                        'exit_reason': exit_reason,
                        'pnl_gross': round(pnl_gross, 2),
                        'charges': round(charges, 2),
                        'pnl_net': round(pnl_net, 2),
                        'win': pnl_net > 0,
                        'gap_pct': sig.get('gap_pct', 0),
                        'atr': sig.get('atr', 0),
                        'nifty_change': sig.get('nifty_change', 0),
                        'capital': cap,
                    }

                    results[strat_name][cap].append(trade)
                    day_trades[cap].append(trade)

    # ── RUN COMBINED INTRADAY ─────────────────────────────────────────────
    print("Building combined intraday (first signal per day per capital)...")
    combined_by_date_cap = defaultdict(lambda: defaultdict(list))
    for strat_name, _ in INTRADAY_STRATEGIES:
        for cap in CAPITAL_SIZES:
            for t in results[strat_name][cap]:
                combined_by_date_cap[t['date']][cap].append(t)

    for date_str, cap_dict in combined_by_date_cap.items():
        for cap, trades in cap_dict.items():
            max_trades = MAX_TRADES_PER_DAY[cap]
            # Sort by entry time, take first max_trades
            trades_sorted = sorted(trades, key=lambda x: x['entry_time'])
            for t in trades_sorted[:max_trades]:
                t2 = dict(t)
                t2['strategy'] = 'COMBINED'
                results['COMBINED_INTRADAY'][cap].append(t2)

    # ── RUN SWING CRABEL ─────────────────────────────────────────────────
    print(f"Running Swing CRABEL on {len(daily_trading_dates)} days x {len(data_daily)} stocks...")
    swing_day_trades = defaultdict(lambda: defaultdict(int))

    for sym, daily_candles in data_daily.items():
        dates_in_range = [c['date'] for c in daily_candles]
        for date_str in daily_trading_dates[200:]:  # Need 200 days history
            if date_str not in dates_in_range:
                continue
            sig = strategy_swing_crabel(sym, daily_candles, date_str)
            if not sig:
                continue

            entry_price = sig['entry_price']
            sl = sig['sl']
            target = sig['target']

            # Swing: hold up to 5 days
            future = [c for c in daily_candles if c['date'] > date_str][:5]
            exit_price = entry_price
            exit_date = date_str
            exit_reason = 'FORCE_EXIT'

            for fc in future:
                if fc['low'] <= sl:
                    exit_price = sl
                    exit_date = fc['date']
                    exit_reason = 'STOP_LOSS'
                    break
                if fc['high'] >= target:
                    exit_price = target
                    exit_date = fc['date']
                    exit_reason = 'TARGET_HIT'
                    break
                exit_price = fc['close']
                exit_date = fc['date']

            for cap in CAPITAL_SIZES:
                max_trades = MAX_TRADES_PER_DAY.get(cap, 3)
                if swing_day_trades[date_str][cap] >= max_trades:
                    continue

                cap_per_trade = cap / max_trades
                qty = calc_qty(cap_per_trade, entry_price)
                if qty <= 0:
                    continue

                pnl_net, pnl_gross, charges = calc_pnl(entry_price, exit_price, qty, exit_reason)
                swing_day_trades[date_str][cap] += 1

                trade = {
                    'date': date_str,
                    'exit_date': exit_date,
                    'day_of_week': datetime.strptime(date_str, '%Y-%m-%d').strftime('%A'),
                    'symbol': sym,
                    'strategy': 'SWING_CRABEL',
                    'entry_price': entry_price,
                    'exit_price': round(exit_price, 2),
                    'sl': sl,
                    'target': target,
                    'qty': qty,
                    'exit_reason': exit_reason,
                    'pnl_gross': round(pnl_gross, 2),
                    'charges': round(charges, 2),
                    'pnl_net': round(pnl_net, 2),
                    'win': pnl_net > 0,
                    'rsi2': sig.get('rsi2', 0),
                    'capital': cap,
                }
                results['SWING_CRABEL'][cap].append(trade)

    return results

# ── REPORT GENERATOR ──────────────────────────────────────────────────────
def generate_report(results):
    lines = []
    lines.append("=" * 80)
    lines.append("MEGA BACKTEST REPORT")
    lines.append("=" * 80)

    summary_rows = []

    for strat_name, cap_results in results.items():
        lines.append(f"\n{'='*60}")
        lines.append(f"STRATEGY: {strat_name}")
        lines.append(f"{'='*60}")

        for cap in CAPITAL_SIZES:
            trades = cap_results[cap]
            if not trades:
                lines.append(f"  Rs.{cap//1000}K: NO TRADES")
                continue

            wins = [t for t in trades if t['win']]
            losses = [t for t in trades if not t['win']]
            total_pnl = sum(t['pnl_net'] for t in trades)
            total_charges = sum(t['charges'] for t in trades)
            wr = len(wins) / len(trades) * 100

            avg_win = sum(t['pnl_net'] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t['pnl_net'] for t in losses) / len(losses) if losses else 0
            gross_wins = sum(t['pnl_net'] for t in wins) if wins else 0
            gross_losses = abs(sum(t['pnl_net'] for t in losses)) if losses else 0
            pf = gross_wins / gross_losses if gross_losses > 0 else 999

            # Monthly projection (annualize based on data period)
            dates = sorted(set(t['date'] for t in trades))
            if len(dates) > 1:
                start = datetime.strptime(dates[0], '%Y-%m-%d')
                end = datetime.strptime(dates[-1], '%Y-%m-%d')
                days_span = (end - start).days + 1
                monthly_proj = (total_pnl / days_span) * 30 if days_span > 0 else 0
            else:
                monthly_proj = 0

            # Per stock analysis
            by_stock = defaultdict(list)
            for t in trades:
                by_stock[t['symbol']].append(t)
            best_stocks = sorted(by_stock.items(), key=lambda x: sum(t['pnl_net'] for t in x[1]), reverse=True)[:5]
            worst_stocks = sorted(by_stock.items(), key=lambda x: sum(t['pnl_net'] for t in x[1]))[:3]

            # Per day-of-week
            by_dow = defaultdict(list)
            for t in trades:
                by_dow[t['day_of_week']].append(t)

            # Exit reason breakdown
            by_exit = defaultdict(int)
            for t in trades:
                by_exit[t['exit_reason']] += 1

            verdict = "✅ EDGE" if wr >= 50 and pf >= 1.2 else ("⚠️ WEAK" if wr >= 45 else "❌ NO EDGE")

            lines.append(f"\n  Capital: Rs.{cap:,}")
            lines.append(f"  Trades: {len(trades)} | WR: {wr:.1f}% | PF: {pf:.2f} | Net P&L: Rs.{total_pnl:,.0f} {verdict}")
            lines.append(f"  Avg Win: Rs.{avg_win:,.0f} | Avg Loss: Rs.{avg_loss:,.0f} | Charges: Rs.{total_charges:,.0f}")
            lines.append(f"  Monthly Projection: Rs.{monthly_proj:,.0f}")
            lines.append(f"  Exit: {dict(by_exit)}")

            lines.append(f"  Top Stocks: " + ", ".join(f"{s}(Rs.{sum(t['pnl_net'] for t in ts):,.0f})" for s,ts in best_stocks))
            lines.append(f"  Worst Stocks: " + ", ".join(f"{s}(Rs.{sum(t['pnl_net'] for t in ts):,.0f})" for s,ts in worst_stocks))

            dow_str = " | ".join(f"{d[:3]}:{len(ts)}t/{sum(1 for t in ts if t['win'])}w" for d,ts in sorted(by_dow.items()))
            lines.append(f"  By Day: {dow_str}")

            summary_rows.append({
                'strategy': strat_name,
                'capital': cap,
                'trades': len(trades),
                'wr': round(wr, 1),
                'pf': round(pf, 2),
                'net_pnl': round(total_pnl, 0),
                'monthly_proj': round(monthly_proj, 0),
                'verdict': verdict
            })

    # Summary table
    lines.append("\n\n" + "=" * 80)
    lines.append("SUMMARY TABLE")
    lines.append("=" * 80)
    lines.append(f"{'Strategy':<20} {'Capital':>10} {'Trades':>7} {'WR%':>6} {'PF':>5} {'Net P&L':>12} {'Monthly':>12} {'Verdict'}")
    lines.append("-" * 90)
    for r in summary_rows:
        lines.append(f"{r['strategy']:<20} {r['capital']:>10,} {r['trades']:>7} {r['wr']:>6.1f} {r['pf']:>5.2f} {r['net_pnl']:>12,.0f} {r['monthly_proj']:>12,.0f} {r['verdict']}")

    return "\n".join(lines)

# ── ENTRY POINT ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Loading 15-min data...")
    data_15 = load_15min_data()
    print(f"  {len(data_15)} stocks loaded")

    print("Loading daily data...")
    data_daily = load_daily_data()
    print(f"  {len(data_daily)} stocks loaded")

    results = run_backtest(data_15, data_daily)

    # Save full trade log
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_data = {}
    for strat, cap_dict in results.items():
        save_data[strat] = {}
        for cap, trades in cap_dict.items():
            # Remove candles_after from saved data (too large)
            save_data[strat][str(cap)] = [
                {k: v for k, v in t.items() if k != 'candles_after'}
                for t in trades
            ]

    with open(f'{RESULTS_DIR}/mega_backtest.json', 'w') as f:
        json.dump(save_data, f, indent=2)
    print(f"Full trade log saved to {RESULTS_DIR}/mega_backtest.json")

    report = generate_report(results)
    with open(f'{RESULTS_DIR}/mega_backtest_report.txt', 'w') as f:
        f.write(report)
    print(report)
