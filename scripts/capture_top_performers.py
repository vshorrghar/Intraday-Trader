import sqlite3, sys, os, requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IST = timezone(timedelta(hours=5, minutes=30))

def get_nse_session():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.nseindia.com/'})
    s.get('https://www.nseindia.com', timeout=10)
    return s

def fetch_nifty500(session):
    r = session.get('https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500', timeout=15)
    r.raise_for_status()
    data = r.json().get('data', [])
    stocks = []
    for item in data:
        sym = item.get('symbol', '')
        if not sym or sym == 'NIFTY 500':
            continue
        ltp = float(item.get('lastPrice', 0) or 0)
        open_p = float(item.get('open', 0) or 0)
        change_pct = float(item.get('pChange', 0) or 0)
        volume = int(float(item.get('totalTradedVolume', 0) or 0))
        change_from_open = ((ltp - open_p) / open_p * 100) if open_p > 0 else 0
        industry = item.get('meta', {}).get('industry', '') if isinstance(item.get('meta'), dict) else ''
        stocks.append({'symbol': sym, 'sector': industry, 'open_price': open_p, 'close_price': ltp, 'gain_pct': round(change_pct, 2), 'change_from_open': round(change_from_open, 2), 'volume': volume})
    return stocks

def fetch_vix(session):
    try:
        r = session.get('https://www.nseindia.com/api/allIndices', timeout=15)
        for idx in r.json().get('data', []):
            if 'VIX' in idx.get('index', '').upper():
                return float(idx.get('last', 0) or 0)
    except Exception:
        pass
    return 0.0

def get_market_mood(stocks):
    green = sum(1 for s in stocks if s['gain_pct'] > 0)
    total = len(stocks) if stocks else 1
    pct = green / total * 100
    if pct > 60: return 'BULLISH'
    elif pct < 40: return 'BEARISH'
    return 'NEUTRAL'

def get_our_trades_today(db_path, date_str):
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT tradingsymbol FROM intraday_trades WHERE trade_date=? AND action=?', (date_str, 'BUY')).fetchall()
        conn.close()
        return [r['tradingsymbol'] for r in rows]
    except Exception:
        return []

def store_top_performers(db_path, date_str, top10, vix, mood, our_picks):
    conn = sqlite3.connect(db_path)
    conn.execute('DELETE FROM daily_top_performers WHERE date=?', (date_str,))
    for i, s in enumerate(top10, 1):
        picked = 1 if s['symbol'] in our_picks else 0
        conn.execute('INSERT INTO daily_top_performers (date, rank, symbol, sector, open_price, close_price, gain_pct, change_from_open, volume, vix_that_day, market_mood, was_picked_by_us) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (date_str, i, s['symbol'], s['sector'], s['open_price'], s['close_price'], s['gain_pct'], s['change_from_open'], s['volume'], vix, mood, picked))
    conn.commit()
    conn.close()

def main():
    today = datetime.now(IST).strftime('%Y-%m-%d')
    print(f'=== Top Performers Capture - {today} ===')
    session = get_nse_session()
    stocks = fetch_nifty500(session)
    if not stocks:
        print('ERROR: No stocks fetched'); return
    vix = fetch_vix(session)
    mood = get_market_mood(stocks)
    print(f'VIX: {vix:.2f} | Mood: {mood} | Stocks: {len(stocks)}')
    sorted_stocks = sorted(stocks, key=lambda x: x['gain_pct'], reverse=True)
    top10 = sorted_stocks[:10]
    dbs = ['database/vishal-live.db', 'database/vishal.db', 'database/neha.db', 'database/neha-live.db']
    all_our_picks = set()
    for db in dbs:
        all_our_picks.update(get_our_trades_today(db, today))
    print('Top 10 Gainers:')
    caught = 0
    for i, s in enumerate(top10, 1):
        sym = s['symbol']
        gp = s['gain_pct']
        cfo = s['change_from_open']
        vol = s['volume']
        sec = s['sector'][:18]
        is_picked = 'YES' if sym in all_our_picks else 'no'
        if sym in all_our_picks:
            caught += 1
        print(f'  {i:2d}. {sym:12s} {gp:+6.2f}%  from_open {cfo:+6.2f}%  vol {vol:>10,}  {sec:18s} {is_picked}')
    print(f'Our picks: {list(all_our_picks) if all_our_picks else "None"}')
    print(f'Accuracy: {caught}/10')
    for db in dbs:
        if os.path.exists(db):
            store_top_performers(db, today, top10, vix, mood, all_our_picks)
    print('Stored in DBs. Done.')

if __name__ == '__main__':
    main()
