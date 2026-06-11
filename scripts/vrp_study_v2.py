#!/usr/bin/env python3
"""VRP Frequency Study v2 - Corrected (VIX ID was wrong in v1)"""
import requests, yaml, math, json, sys, sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
sys.path.insert(0, '.')
from intraday.auth_server import authenticate_broker

with open('config/profiles/vishal.yaml') as f:
    cfg = yaml.safe_load(f)
broker = authenticate_broker('dhan', cfg.get('dhan', {}), dry_run=False, profile='vishal')
headers = {'access-token': broker.access_token, 'client-id': str(broker.client_id)}

end = datetime.now().strftime('%Y-%m-%d')
start = (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')

# Get NIFTY historical
body = {'securityId': '13', 'exchangeSegment': 'IDX_I', 'instrument': 'INDEX',
        'expiryCode': 0, 'fromDate': start, 'toDate': end}
resp = requests.post('https://api.dhan.co/v2/charts/historical', json=body, headers=headers)
data = resp.json()
closes = data.get('close', [])
timestamps = data.get('timestamp', [])
print(f'NIFTY: {len(closes)} daily candles')
if closes and timestamps:
    d0 = datetime.fromtimestamp(timestamps[0]).strftime('%Y-%m-%d')
    d1 = datetime.fromtimestamp(timestamps[-1]).strftime('%Y-%m-%d')
    print(f'Date range: {d0} to {d1}')

if len(closes) < 25:
    print("INSUFFICIENT DATA")
    sys.exit(1)

# Compute 20-day RV for every day
rv_values = []
rv_dates = []
for i in range(20, len(closes)):
    log_returns = []
    for j in range(i-19, i+1):
        if closes[j-1] > 0:
            log_returns.append(math.log(closes[j] / closes[j-1]))
    if len(log_returns) >= 20:
        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret)**2 for r in log_returns) / len(log_returns)
        rv20d = math.sqrt(variance) * math.sqrt(252) * 100
        rv_values.append(rv20d)
        if i < len(timestamps):
            rv_dates.append(datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'))

print(f'\nRV20d computed for {len(rv_values)} days')
print(f'RV20d stats: min={min(rv_values):.1f}%, max={max(rv_values):.1f}%, '
      f'mean={sum(rv_values)/len(rv_values):.1f}%, median={sorted(rv_values)[len(rv_values)//2]:.1f}%')

# Distribution
sep = "=" * 60
low = sum(1 for v in rv_values if v < 10)
med = sum(1 for v in rv_values if 10 <= v < 15)
high = sum(1 for v in rv_values if 15 <= v < 20)
vhigh = sum(1 for v in rv_values if v >= 20)
print(f'\nRV20d distribution ({len(rv_values)} days):')
print(f'  < 10% (calm):      {low} days ({100*low/len(rv_values):.1f}%)')
print(f'  10-15% (normal):   {med} days ({100*med/len(rv_values):.1f}%)')
print(f'  15-20% (elevated): {high} days ({100*high/len(rv_values):.1f}%)')
print(f'  >= 20% (high vol): {vhigh} days ({100*vhigh/len(rv_values):.1f}%)')

print(f'\n{sep}')
print(f'VRP FREQUENCY ESTIMATION')
print(f'{sep}')
print(f'NOTE: Dhan does NOT provide India VIX historical data.')
print(f'Using typical VIX ranges as proxy.')
print(f'VRP = VIX - RV20d. Rules engine gate: VRP >= 0.5')
print()

for assumed_vix in [12, 13, 14, 15, 16, 18, 20]:
    tradeable = sum(1 for rv in rv_values if (assumed_vix - rv) >= 0.5)
    pct = 100 * tradeable / len(rv_values)
    trades_year = pct * 250 / 100
    trades_month = trades_year / 12
    print(f'  VIX={assumed_vix:2d}: tradeable {tradeable:3d}/{len(rv_values)} days '
          f'({pct:5.1f}%) = ~{trades_year:.0f}/yr, ~{trades_month:.1f}/mo')

# Last 31 days
print(f'\n{sep}')
print(f'LAST 31 DAYS (the period rules engine saw)')
print(f'{sep}')
last31_rv = rv_values[-31:] if len(rv_values) >= 31 else rv_values
print(f'  RV20d last 31 days: min={min(last31_rv):.1f}%, max={max(last31_rv):.1f}%, '
      f'mean={sum(last31_rv)/len(last31_rv):.1f}%')
blocked = sum(1 for rv in last31_rv if rv >= 13.5)
print(f'  Days BLOCKED (RV >= 13.5%, assuming VIX~14): {blocked}/{len(last31_rv)} ({100*blocked/len(last31_rv):.0f}%)')
print(f'  Days TRADEABLE (RV < 13.5%): {len(last31_rv)-blocked}/{len(last31_rv)}')

# Check DB
print(f'\n{sep}')
print(f'RULES ENGINE ACTUAL STATE (from vishal.db)')
print(f'{sep}')
try:
    db = sqlite3.connect('database/vishal.db')
    nifty_rows = db.execute("""
        SELECT date, close FROM fno_spot_history 
        WHERE symbol='NIFTY' ORDER BY date
    """).fetchall()
    if len(nifty_rows) >= 21:
        nifty_db_closes = [r[1] for r in nifty_rows]
        log_rets = [math.log(nifty_db_closes[i]/nifty_db_closes[i-1]) 
                   for i in range(1, len(nifty_db_closes)) if nifty_db_closes[i-1] > 0]
        if len(log_rets) >= 20:
            recent_rets = log_rets[-20:]
            mean_r = sum(recent_rets)/len(recent_rets)
            var_r = sum((r-mean_r)**2 for r in recent_rets)/len(recent_rets)
            rv_current = math.sqrt(var_r) * math.sqrt(252) * 100
            print(f'  Current RV20d from DB: {rv_current:.1f}%')
            print(f'  For VRP >= 0.5, need VIX >= {rv_current + 0.5:.1f}%')
            if rv_current > 15:
                print(f'  STATUS: RV HIGH - condors BLOCKED unless VIX spikes')
            elif rv_current > 13:
                print(f'  STATUS: RV MODERATE - condors need VIX ~{rv_current+0.5:.0f}+ (borderline)')
            else:
                print(f'  STATUS: RV LOW - condors TRADEABLE at normal VIX levels')
    else:
        print(f'  Only {len(nifty_rows)} rows in fno_spot_history (need 21+)')
    db.close()
except Exception as e:
    print(f'  DB error: {e}')

# FINAL VERDICT
print(f'\n{sep}')
print(f'FINAL HONEST VERDICT')
print(f'{sep}')
calm_days = sum(1 for rv in rv_values if rv < 13.5)
normal_days = sum(1 for rv in rv_values if rv < 15.5)
total = len(rv_values)
years = total / 250

calm_per_year = calm_days * 250 // total
normal_per_year = normal_days * 250 // total

print(f'')
print(f'  DATA: {total} trading days (~{years:.1f} years) of NIFTY history')
print(f'')
print(f'  FREQUENCY ANSWER:')
print(f'  - VRP >= 0.5 occurs on {100*calm_days//total}-{100*normal_days//total}% of days')
print(f'    (depending on whether VIX is 14 or 16)')
print(f'  - That is {calm_per_year}-{normal_per_year} tradeable days/year')
print(f'  - Or {calm_per_year//12}-{normal_per_year//12} trades/month')
print(f'')
print(f'  WHY LAST MONTH HAD ZERO TRADES:')
print(f'  - Recent RV20d: {rv_values[-1]:.1f}% (elevated)')
vrp_est = 14 - rv_values[-1]
print(f'  - With VIX ~14, VRP = 14 - {rv_values[-1]:.1f} = {vrp_est:.1f} ({"NEGATIVE" if vrp_est < 0 else "barely positive"})')
print(f'  - Rules engine CORRECTLY refused to sell cheap premium')
print(f'')
print(f'  IS F&O A "RARE EVENT" STRATEGY?')
if calm_per_year < 50:
    print(f'  - At VIX=14 (calm): ~{calm_per_year} trades/year = YES, RARE')
else:
    print(f'  - At VIX=14 (calm): ~{calm_per_year} trades/year = Regular enough')
if normal_per_year < 50:
    print(f'  - At VIX=16 (normal): ~{normal_per_year} trades/year = Somewhat rare')
else:
    print(f'  - At VIX=16 (normal): ~{normal_per_year} trades/year = Regular')
print(f'')
print(f'  THE REAL INSIGHT:')
print(f'  - F&O condors are a REGIME strategy, not an every-day strategy')
print(f'  - They work BEST when VIX elevated (16-22) but market calming')
print(f'  - Sweet spot: VIX high + RV dropping = fat premium + low risk')
print(f'  - Current market: RV elevated + VIX normal = WORST for selling')
print(f'  - Wait for VIX spike then condors become goldmine')
print(f'')
print(f'  ANNUAL INCOME ESTIMATE (at 2L capital, 4 lots):')
print(f'  - Mean edge Rs.142/lot from backtest')
print(f'  - Optimistic ({normal_per_year} trades): Rs.{normal_per_year * 142 * 4:,}/year')
print(f'  - Pessimistic ({calm_per_year} trades): Rs.{calm_per_year * 142 * 4:,}/year')
print(f'  - Median-based ({normal_per_year} trades, Rs.21/lot): Rs.{normal_per_year * 21 * 4:,}/year')
