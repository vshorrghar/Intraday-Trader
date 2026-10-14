#!/bin/bash
# preflight_live.sh — GO/NO-GO check before trusting vishal-live-v2 real-money crons.
# Run before market open (and Friday dry-run). Any FAIL = do not trade today.
cd /home/ec2-user/dev-sandbox
P=vishal-live-v2
CID=1110941563
FAIL=0
echo "=== PREFLIGHT $(date '+%Y-%m-%d %H:%M') ==="

# 1. clock (TOTP depends on it)
timedatectl | grep -q "synchronized: yes" && echo "OK  clock synced" || { echo "FAIL clock not synced"; FAIL=1; }

# 2. shared token fresh + works
TOK=config/.dhan_token_${CID}.json
if [ -f "$TOK" ] && grep -q "$(date +%Y-%m-%d)" "$TOK"; then
  echo "OK  shared token dated today"
else
  echo "FAIL shared token missing/stale — run pre_auth_dhan.py"; FAIL=1
fi
HTTP=$(.venv/bin/python - <<PY
import json,requests
try:
    d=json.load(open("config/.dhan_token_${CID}.json"))
    r=requests.get("https://api.dhan.co/v2/orders",headers={"access-token":d["access_token"],"client-id":"${CID}","Content-Type":"application/json"},timeout=10)
    print(r.status_code)
except Exception as e:
    print("ERR",e)
PY
)
[ "$HTTP" = "200" ] && echo "OK  /v2/orders = 200 (token valid)" || { echo "FAIL /v2/orders = $HTTP (DH-906? token dead)"; FAIL=1; }

# 3. caps correct
CAP=$(grep -A6 "^intraday:" config/profiles/${P}.yaml)
echo "$CAP" | grep -q "daily_capital_limit: 10000" && echo "OK  capital 10000" || { echo "FAIL capital != 10000"; FAIL=1; }
echo "$CAP" | grep -q "max_trades_per_day: 2" && echo "OK  max_trades 2" || { echo "FAIL max_trades != 2"; FAIL=1; }
echo "$CAP" | grep -q "daily_loss_limit: 1000" && echo "OK  loss_limit 1000" || { echo "FAIL loss_limit != 1000"; FAIL=1; }

# 4. live crons installed? (warn only pre-Monday)
crontab -l | grep -q "run_v3_cycle('vishal-live-v2'" && echo "OK  live entry cron installed" || echo "WARN live entry cron NOT installed (expected until Monday)"

echo "=== $([ $FAIL -eq 0 ] && echo 'GO — safe to trade' || echo 'NO-GO — fix FAILs above') ==="
exit $FAIL
