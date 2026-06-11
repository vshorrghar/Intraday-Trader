#!/usr/bin/env python3
"""F&O VRP Frequency Study: How often does VRP >= 0.5 occur over 1-2 years?"""
import requests, yaml, math, json, time, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from intraday.auth_server import authenticate_broker

IST = timezone(timedelta(hours=5, minutes=30))

with open("config/profiles/vishal.yaml") as f:
    cfg = yaml.safe_load(f)
broker = authenticate_broker("dhan", cfg.get("dhan", {}), dry_run=False, profile="vishal")
headers = {"access-token": broker.access_token, "client-id": str(broker.client_id)}

end = datetime.now().strftime("%Y-%m-%d")

# Pull max NIFTY history
for days_back in [500, 365, 200]:
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    body = {"securityId": "13", "exchangeSegment": "IDX_I", "instrument": "INDEX", "expiryCode": 0, "fromDate": start, "toDate": end}
    resp = requests.post("https://api.dhan.co/v2/charts/historical", json=body, headers=headers)
    data = resp.json()
    closes = data.get("close", [])
    timestamps = data.get("timestamp", [])
    print(f"NIFTY {days_back}d back: {len(closes)} candles (HTTP {resp.status_code})")
    if len(closes) >= 100:
        break

if len(closes) < 25:
    print("INSUFFICIENT DATA")
    sys.exit(1)

# Try to get India VIX historical
time.sleep(2)
# India VIX security ID on Dhan: try common IDs
vix_closes = []
for vix_id in ["26017", "26", "17"]:
    vix_body = {"securityId": vix_id, "exchangeSegment": "IDX_I", "instrument": "INDEX", "expiryCode": 0, "fromDate": start, "toDate": end}
    vix_resp = requests.post("https://api.dhan.co/v2/charts/historical", json=vix_body, headers=headers)
    vix_data = vix_resp.json()
    vix_closes = vix_data.get("close", [])
    if vix_closes and len(vix_closes) > 10:
        print(f"India VIX found (ID={vix_id}): {len(vix_closes)} candles")
        break
    time.sleep(1)

if not vix_closes:
    print("No VIX historical data available. Using FIXED IV=15% as proxy.")
    print("NOTE: This underestimates VRP. Real VIX averages 12-18% in calm markets.")

# Compute VRP for each day
print(f"\n{'='*70}")
print(f"VRP FREQUENCY STUDY — NIFTY ({len(closes)} trading days)")
print(f"{'='*70}")
iv_source = "India VIX" if vix_closes else "Fixed 15%"
print(f"IV proxy: {iv_source}")
print(f"RV: 20-day realized volatility from NIFTY daily closes")
print()

vrp_values = []
for i in range(20, len(closes)):
    # RV20d
    log_returns = []
    for j in range(i-19, i+1):
        if closes[j-1] > 0:
            log_returns.append(math.log(closes[j] / closes[j-1]))
    if len(log_returns) < 20:
        continue
    mean_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_ret)**2 for r in log_returns) / len(log_returns)
    rv20d = math.sqrt(variance) * math.sqrt(252) * 100

    # IV
    if vix_closes and i < len(vix_closes):
        iv = vix_closes[i]
    else:
        iv = 15.0

    vrp = iv - rv20d
    ts = timestamps[i] if i < len(timestamps) else 0
    dt = datetime.fromtimestamp(ts, tz=IST) if ts else None
    vrp_values.append({"day": i, "rv20d": rv20d, "iv": iv, "vrp": vrp, "date": dt})

print(f"VRP computed for {len(vrp_values)} days")

vrps = [v["vrp"] for v in vrp_values]
total = len(vrps)

# Distribution
strongly_pos = sum(1 for v in vrps if v >= 3.0)
positive = sum(1 for v in vrps if v >= 0.5)
near_zero = sum(1 for v in vrps if -0.5 <= v < 0.5)
slightly_neg = sum(1 for v in vrps if -5 <= v < -0.5)
deeply_neg = sum(1 for v in vrps if v < -5)

print(f"\nVRP DISTRIBUTION ({total} days):")
print(f"  VRP >= 3.0 (strong sell premium): {strongly_pos:>4} days ({strongly_pos/total*100:.1f}%)")
print(f"  VRP >= 0.5 (tradeable):           {positive:>4} days ({positive/total*100:.1f}%)")
print(f"  VRP -0.5 to 0.5 (neutral):        {near_zero:>4} days ({near_zero/total*100:.1f}%)")
print(f"  VRP -5 to -0.5 (options cheap):    {slightly_neg:>4} days ({slightly_neg/total*100:.1f}%)")
print(f"  VRP < -5 (very cheap, dont sell):  {deeply_neg:>4} days ({deeply_neg/total*100:.1f}%)")

print(f"\nTRADE FREQUENCY (VRP >= 0.5 gate):")
print(f"  Tradeable days: {positive}/{total} = {positive/total*100:.1f}%")
trading_days_year = 250
trades_year = int(positive / total * trading_days_year)
trades_month = trades_year / 12
print(f"  Projected trades/year:  ~{trades_year}")
print(f"  Projected trades/month: ~{trades_month:.1f}")

# When does VRP go positive?
print(f"\nWHEN IS VRP POSITIVE?")
pos_days = [v for v in vrp_values if v["vrp"] >= 0.5]
neg_days = [v for v in vrp_values if v["vrp"] < 0.5]
if pos_days:
    avg_rv_pos = sum(v["rv20d"] for v in pos_days) / len(pos_days)
    avg_iv_pos = sum(v["iv"] for v in pos_days) / len(pos_days)
    print(f"  Positive VRP days: avg IV={avg_iv_pos:.1f}%, avg RV20d={avg_rv_pos:.1f}%")
if neg_days:
    avg_rv_neg = sum(v["rv20d"] for v in neg_days) / len(neg_days)
    avg_iv_neg = sum(v["iv"] for v in neg_days) / len(neg_days)
    print(f"  Negative VRP days: avg IV={avg_iv_neg:.1f}%, avg RV20d={avg_rv_neg:.1f}%")
print(f"  VRP positive when: market CALMS DOWN (RV drops below IV)")
print(f"  Typically: after a volatility spike subsides, IV stays elevated")
print(f"  while realized vol drops = premium sellers get paid for old fear")

# Last 31 days vs full
last_31 = vrps[-31:] if len(vrps) >= 31 else vrps
last_31_pos = sum(1 for v in last_31 if v >= 0.5)
print(f"\nLAST 31 DAYS vs FULL HISTORY:")
print(f"  Last 31 days VRP>=0.5: {last_31_pos}/{len(last_31)} ({last_31_pos/len(last_31)*100:.1f}%)")
print(f"  Full history VRP>=0.5: {positive}/{total} ({positive/total*100:.1f}%)")
if len(last_31) > 0 and positive > 0:
    ratio = (last_31_pos/len(last_31)) / (positive/total)
    if ratio < 0.5:
        print(f"  VERDICT: Last 31 days is UNUSUALLY negative VRP (below historical norm)")
    elif ratio > 1.5:
        print(f"  VERDICT: Last 31 days is UNUSUALLY positive VRP (above norm)")
    else:
        print(f"  VERDICT: Last 31 days is NORMAL")

# Honest verdict
print(f"\n{'='*70}")
print("HONEST VERDICT")
print(f"{'='*70}")
if trades_month >= 15:
    print(f"  F&O is a REGULAR strategy: ~{trades_month:.0f} trades/month")
    print(f"  Enough volume to matter as a business.")
elif trades_month >= 5:
    print(f"  F&O is a MODERATE-frequency strategy: ~{trades_month:.0f} trades/month")
    print(f"  Meaningful but not daily. Need per-trade edge to be significant.")
elif trades_month >= 1:
    print(f"  F&O is a LOW-frequency strategy: ~{trades_month:.1f} trades/month")
    print(f"  Rare-event strategy. Only worth it if per-trade edge is large.")
else:
    print(f"  F&O is EFFECTIVELY DEAD at VRP>=0.5 gate: <1 trade/month")
    print(f"  The gate is too tight for current market conditions.")
    print(f"  Options: lower gate to VRP>=0 or VRP>=-2, or accept near-zero frequency.")
