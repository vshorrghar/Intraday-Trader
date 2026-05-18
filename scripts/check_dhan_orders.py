#!/usr/bin/env python3
"""Helper: Pull Dhan orders/positions, detect duplicates, compare to DB."""
import sys
sys.path.insert(0, '/home/ec2-user/dev-sandbox')

import yaml
import requests
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from intraday.auth_server import authenticate_broker

IST = timezone(timedelta(hours=5, minutes=30))
PROFILE = 'vishal-live'

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'full'
    
    # Auth
    with open(f'config/profiles/{PROFILE}.yaml') as f:
        profile = yaml.safe_load(f)
    
    try:
        broker = authenticate_broker('dhan', profile.get('dhan', {}), dry_run=False, profile=PROFILE)
    except Exception as e:
        print(f"AUTH_FAIL:{e}")
        sys.exit(1)
    
    headers = {
        'access-token': broker.access_token,
        'client-id': broker.client_id,
        'Content-Type': 'application/json',
    }
    
    # Fetch orders
    r = requests.get('https://api.dhan.co/v2/orders', headers=headers, timeout=15)
    if r.status_code != 200:
        print(f"ORDERS_FAIL:HTTP {r.status_code}")
        sys.exit(1)
    
    orders = r.json()
    today_str = datetime.now(IST).strftime('%Y-%m-%d')
    
    # Filter to today's TRADED orders only
    traded = [o for o in orders if o.get('orderStatus') in ('TRADED', 'FILLED', 'COMPLETE')]
    
    # === DUPLICATE DETECTION (within 5 seconds) ===
    grouped = defaultdict(list)
    for o in traded:
        key = (o.get('tradingSymbol'), o.get('transactionType'))
        grouped[key].append(o)
    
    duplicates = []
    for (sym, txn), group in grouped.items():
        if len(group) <= 1:
            continue
        # Check if any pair is within 5 seconds
        times = []
        for o in group:
            et = o.get('exchangeTime', '')
            try:
                dt = datetime.fromisoformat(et.replace('Z', '+00:00')) if et and '1980' not in et else None
                if dt:
                    times.append((dt, o.get('orderId')))
            except:
                pass
        times.sort()
        for i in range(len(times) - 1):
            diff = (times[i+1][0] - times[i][0]).total_seconds()
            if diff <= 5:
                duplicates.append({
                    'symbol': sym,
                    'txn': txn,
                    'time_diff_sec': diff,
                    'order1': times[i][1],
                    'order2': times[i+1][1],
                    'time1': times[i][0].strftime('%H:%M:%S'),
                    'time2': times[i+1][0].strftime('%H:%M:%S'),
                })
    
    # === DB COMPARISON ===
    db_path = f'database/{PROFILE}.db'
    con = sqlite3.connect(db_path)
    db_rows = con.execute(
        "SELECT tradingsymbol, action, SUM(quantity) FROM intraday_trades WHERE trade_date = ? GROUP BY tradingsymbol, action",
        (today_str,)
    ).fetchall()
    con.close()
    
    db_qty = {(r[0], r[1]): r[2] for r in db_rows}
    dhan_qty = defaultdict(int)
    for o in traded:
        key = (o.get('tradingSymbol'), o.get('transactionType'))
        dhan_qty[key] += o.get('quantity', 0)
    
    mismatches = []
    all_keys = set(db_qty.keys()) | set(dhan_qty.keys())
    for key in all_keys:
        db_q = db_qty.get(key, 0)
        dhan_q = dhan_qty.get(key, 0)
        if db_q != dhan_q:
            mismatches.append({
                'symbol': key[0],
                'txn': key[1],
                'db_qty': db_q,
                'dhan_qty': dhan_q,
            })
    
    # === POSITIONS CHECK ===
    r2 = requests.get('https://api.dhan.co/v2/positions', headers=headers, timeout=15)
    positions = r2.json() if r2.status_code == 200 else []
    open_positions = [p for p in positions if p.get('netQty', 0) != 0]
    
    # === OUTPUT ===
    result = {
        'total_orders_today': len(orders),
        'traded_orders': len(traded),
        'duplicate_pairs': duplicates,
        'duplicate_count': len(duplicates),
        'db_vs_dhan_mismatches': mismatches,
        'mismatch_count': len(mismatches),
        'open_positions': len(open_positions),
        'unique_symbols_traded': len(set(o.get('tradingSymbol') for o in traded)),
    }
    
    # Compute total P&L from positions
    total_pnl = sum(float(p.get('realizedProfit', 0)) + float(p.get('unrealizedProfit', 0)) for p in positions)
    result['dhan_total_pnl'] = round(total_pnl, 2)
    
    # DB total P&L
    con = sqlite3.connect(db_path)
    db_pnl_row = con.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM intraday_trades WHERE trade_date = ?", (today_str,)
    ).fetchone()
    con.close()
    result['db_total_pnl'] = round(float(db_pnl_row[0]), 2) if db_pnl_row else 0
    
    print(json.dumps(result))

if __name__ == '__main__':
    main()
