#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# SANITY CHECK — Mandatory after EVERY deploy/code change
# 
# Checks are in SEQUENTIAL order — each layer depends on the previous:
#   Layer 1: Connectivity (can we reach EC2?)
#   Layer 2: File system (are scripts correct on EC2?)
#   Layer 3: Permissions & cron (will things fire?)
#   Layer 4: AWS auth (will Bedrock/LLM work?)
#   Layer 5: Python runtime (do modules load?)
#   Layer 6: Config validation (are values sane?)
#   Layer 7: Data access (can we fetch NSE data?)
#   Layer 8: End-to-end dry run (does the full pipeline work?)
#
# If any layer fails, subsequent layers are SKIPPED (they'd fail anyway).
# ═══════════════════════════════════════════════════════════════════════════

KEY="$HOME/Downloads/wealth-builder-pro.pem"
EC2="ec2-user@13.206.144.6"
REMOTE_DIR="dev-sandbox"
SSH="ssh -i $KEY -o ConnectTimeout=15 -o StrictHostKeyChecking=no $EC2"
FAILURES=0
TOTAL=0
LAYER_FAILED=""

pass() { TOTAL=$((TOTAL+1)); echo "  ✅ $1"; }
fail() { TOTAL=$((TOTAL+1)); FAILURES=$((FAILURES+1)); echo "  ❌ $1"; }
skip() { TOTAL=$((TOTAL+1)); echo "  ⏭️  $1 (skipped — previous layer failed)"; }

layer_check() {
    if [ -n "$LAYER_FAILED" ]; then
        echo ""
        echo "⚠️  Skipping remaining checks — Layer $LAYER_FAILED failed"
        echo ""
        summary
        exit $FAILURES
    fi
}

summary() {
    echo "═══════════════════════════════════════════════════════════════"
    if [ "$FAILURES" -eq 0 ]; then
        echo "  ✅ ALL $TOTAL CHECKS PASSED — safe to run"
        echo "  🚀 Cron will fire correctly tomorrow morning"
    else
        echo "  ❌ $FAILURES/$TOTAL CHECKS FAILED — DO NOT PROCEED"
        echo "  🛑 Fix failures above before going live"
    fi
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  🔍 POST-DEPLOY SANITY CHECK"
echo "  Run at: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Target: $EC2:~/$REMOTE_DIR"
echo "═══════════════════════════════════════════════════════════════"

# ═══════════════════════════════════════════════════════════════
# LAYER 1: CONNECTIVITY
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 1: EC2 Connectivity ━━━"

if $SSH "echo ok" > /dev/null 2>&1; then
    pass "EC2 reachable at 13.206.144.6"
else
    fail "EC2 unreachable — check IP, security group, or key"
    LAYER_FAILED="1"
fi
layer_check

# Check EC2 timezone
EC2_TZ=$($SSH "date +%Z" 2>/dev/null)
if [ "$EC2_TZ" = "UTC" ]; then
    pass "EC2 timezone is UTC (cron times must be in UTC)"
else
    fail "EC2 timezone is '$EC2_TZ' — expected UTC. Cron times will be wrong!"
fi

# ═══════════════════════════════════════════════════════════════
# LAYER 2: FILE SYSTEM — correct paths, no Mac contamination
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 2: File System & Paths ━━━"

# Check for Mac paths in cron scripts (issue #1)
if $SSH "grep -q '/Users/' ~/$REMOTE_DIR/run_daily.sh 2>/dev/null"; then
    fail "run_daily.sh contains Mac paths (/Users/...) — sync overwrote EC2 script!"
else
    pass "run_daily.sh has EC2 paths"
fi

if $SSH "grep -q '/Users/' ~/$REMOTE_DIR/run_fno_daily.sh 2>/dev/null"; then
    fail "run_fno_daily.sh contains Mac paths (/Users/...) — sync overwrote EC2 script!"
else
    pass "run_fno_daily.sh has EC2 paths"
fi

# Check APP_DIR is correct
DAILY_APP_DIR=$($SSH "grep '^APP_DIR=' ~/$REMOTE_DIR/run_daily.sh | head -1" 2>/dev/null)
if echo "$DAILY_APP_DIR" | grep -q "/home/ec2-user/dev-sandbox"; then
    pass "run_daily.sh APP_DIR correct: /home/ec2-user/dev-sandbox"
else
    fail "run_daily.sh APP_DIR wrong: $DAILY_APP_DIR"
fi

# Check lock file mechanism exists (issue #7)
if $SSH "grep -q 'LOCK_FILE' ~/$REMOTE_DIR/run_daily.sh"; then
    pass "run_daily.sh has lock file mechanism"
else
    fail "run_daily.sh missing lock file — duplicates possible"
fi

# Check no stale lock files (issue #8)
LOCKS=$($SSH "ls ~/$REMOTE_DIR/logs/.*.lock 2>/dev/null | wc -l" 2>/dev/null || echo "0")
LOCKS=$(echo "$LOCKS" | tr -d ' ')
if [ "$LOCKS" = "0" ]; then
    pass "No stale lock files"
else
    fail "$LOCKS stale lock file(s) — cron will skip! Remove with: rm ~/dev-sandbox/logs/.*.lock"
fi

# Check scripts are executable (issue #3)
if $SSH "test -x ~/$REMOTE_DIR/run_daily.sh && test -x ~/$REMOTE_DIR/run_fno_daily.sh"; then
    pass "Both cron scripts are executable"
else
    fail "Cron scripts not executable — cron will fail silently"
fi

# ═══════════════════════════════════════════════════════════════
# LAYER 3: CRON & PERMISSIONS
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 3: Cron Configuration ━━━"

# ec2-user crontab exists (issue #6, #22)
CRON_LINES=$($SSH "crontab -l 2>/dev/null" || echo "")
CRON_COUNT=$(echo "$CRON_LINES" | grep -c "$REMOTE_DIR" || echo "0")
if [ "$CRON_COUNT" -ge 2 ]; then
    pass "ec2-user crontab has $CRON_COUNT job entries"
else
    fail "ec2-user crontab has only $CRON_COUNT entries — expected at least 2"
    LAYER_FAILED="3"
fi
layer_check

# Root crontab is empty (issue #7)
# Root crontab is empty (issue #7)
ROOT_CRON=$($SSH "sudo crontab -l 2>&1 | grep -c 'dev-sandbox'" 2>/dev/null || echo "0")
ROOT_CRON=$(echo "$ROOT_CRON" | tr -dc '0-9')
if [ -z "$ROOT_CRON" ] || [ "$ROOT_CRON" -eq 0 ] 2>/dev/null; then
    pass "Root crontab clean — no duplicate processes"
else
    fail "Root has $ROOT_CRON cron entries — WILL CAUSE DUPLICATES"
fi

# Cron times are in UTC (issue #22)
# 9:20 IST = 3:50 UTC, 9:25 IST = 3:55 UTC
if echo "$CRON_LINES" | grep -q "^50 3"; then
    pass "FnO cron at 3:50 UTC (= 9:20 IST) ✓"
else
    fail "FnO cron time wrong — should be '50 3 * * 1-5' for 9:20 IST"
fi
if echo "$CRON_LINES" | grep -q "^55 3"; then
    pass "Intraday morning cron at 3:55 UTC (= 9:25 IST) ✓"
else
    fail "Intraday morning cron time wrong — should be '55 3 * * 1-5' for 9:25 IST"
fi

# Weekday-only check
if echo "$CRON_LINES" | grep "run_daily\|run_fno" | grep -qv "1-5"; then
    fail "Some cron entries run on weekends — markets are closed Sat/Sun"
else
    pass "All cron entries are weekday-only (Mon-Fri)"
fi

# ═══════════════════════════════════════════════════════════════
# LAYER 4: AWS AUTHENTICATION
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 4: AWS & Bedrock Auth ━━━"

# AWS_PROFILE set in scripts (issue #8)
if $SSH "grep -q 'AWS_PROFILE.*vishal-admin' ~/$REMOTE_DIR/run_daily.sh"; then
    pass "run_daily.sh exports AWS_PROFILE=vishal-admin"
else
    fail "run_daily.sh missing AWS_PROFILE — Bedrock will fail in cron!"
    LAYER_FAILED="4"
fi
layer_check

if $SSH "grep -q 'AWS_PROFILE.*vishal-admin' ~/$REMOTE_DIR/run_fno_daily.sh"; then
    pass "run_fno_daily.sh exports AWS_PROFILE=vishal-admin"
else
    fail "run_fno_daily.sh missing AWS_PROFILE"
fi

# Credentials file exists (issue #5, #13)
if $SSH "test -f ~/.aws/credentials"; then
    pass "~/.aws/credentials exists"
else
    fail "~/.aws/credentials missing — Bedrock auth will fail"
    LAYER_FAILED="4"
fi
layer_check

# vishal-admin profile exists in credentials
if $SSH "grep -q 'vishal-admin' ~/.aws/credentials"; then
    pass "vishal-admin profile found in credentials"
else
    fail "vishal-admin profile missing from ~/.aws/credentials"
    LAYER_FAILED="4"
fi
layer_check

# Bedrock actually works (issue #5, #8)
BEDROCK_RESULT=$($SSH "cd ~/$REMOTE_DIR && export AWS_PROFILE=vishal-admin && export AWS_DEFAULT_REGION=us-east-1 && .venv/bin/python -c '
import boto3, json, yaml
with open(\"config/config.yaml\") as f:
    cfg = yaml.safe_load(f)
model = cfg[\"aws\"][\"bedrock_model_id\"]
region = cfg[\"aws\"][\"bedrock_region\"]

# Approved models only
approved = [\"us.anthropic.claude-opus-4-7\", \"us.anthropic.claude-sonnet-4-20250514-v1:0\", \"anthropic.claude-3-5-sonnet-20241022-v2:0\"]
if model not in approved:
    print(f\"FAIL model={model} not in approved list: {approved}\")
else:
    client = boto3.client(\"bedrock-runtime\", region_name=region)
    body = json.dumps({\"anthropic_version\":\"bedrock-2023-05-31\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"1+1\"}]})
    resp = client.invoke_model(modelId=model, body=body, contentType=\"application/json\")
    print(f\"OK model={model} region={region}\")
' 2>&1" || echo "FAIL unknown")

if echo "$BEDROCK_RESULT" | grep -q "^OK"; then
    pass "Bedrock LLM responds: $(echo $BEDROCK_RESULT | sed 's/OK //')"
else
    fail "Bedrock FAILED: $(echo $BEDROCK_RESULT | tail -1 | cut -c1-100)"
    LAYER_FAILED="4"
fi
layer_check

# ═══════════════════════════════════════════════════════════════
# LAYER 5: PYTHON RUNTIME
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 5: Python & Module Imports ━━━"

# Python exists
if $SSH "test -x ~/$REMOTE_DIR/.venv/bin/python"; then
    pass ".venv/bin/python exists and is executable"
else
    fail "Python venv missing or not executable"
    LAYER_FAILED="5"
fi
layer_check

# Critical imports
IMPORT_RESULT=$($SSH "cd ~/$REMOTE_DIR && .venv/bin/python -c '
errors = []
try:
    from intraday.dashboard import write_dashboard_json, _merge_trades
except Exception as e:
    errors.append(f\"intraday.dashboard: {e}\")
try:
    from fno.dashboard import write_fno_dashboard_json
except Exception as e:
    errors.append(f\"fno.dashboard: {e}\")
try:
    from intraday.auth_server import authenticate_broker, DryRunBrokerClient
except Exception as e:
    errors.append(f\"auth_server: {e}\")
try:
    from intraday.scanner import Pre_Market_Scanner
except Exception as e:
    errors.append(f\"scanner: {e}\")
try:
    from intraday.selector import select_trades_llm
except Exception as e:
    errors.append(f\"selector: {e}\")
try:
    from fno.paper_engine import Paper_Trade_Engine
except Exception as e:
    errors.append(f\"paper_engine: {e}\")
try:
    from llm.bedrock_client import BedrockClient
except Exception as e:
    errors.append(f\"bedrock_client: {e}\")
try:
    import pyotp
except Exception as e:
    errors.append(f\"pyotp: {e}\")

if errors:
    print(\"FAIL \" + \"; \".join(errors))
else:
    print(\"OK 8 modules imported\")
' 2>&1" || echo "FAIL python crashed")

if echo "$IMPORT_RESULT" | grep -q "^OK"; then
    pass "All critical modules import: $(echo $IMPORT_RESULT | sed 's/OK //')"
else
    fail "Import errors: $(echo $IMPORT_RESULT | sed 's/FAIL //')"
    LAYER_FAILED="5"
fi
layer_check

# ═══════════════════════════════════════════════════════════════
# LAYER 6: CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 6: Config Validation ━━━"

CONFIG_RESULT=$($SSH "cd ~/$REMOTE_DIR && .venv/bin/python -c '
import yaml
with open(\"config/config.yaml\") as f:
    cfg = yaml.safe_load(f)

errors = []
# AWS
aws = cfg.get(\"aws\", {})
if not aws.get(\"bedrock_model_id\"): errors.append(\"missing bedrock_model_id\")
if not aws.get(\"bedrock_region\"): errors.append(\"missing bedrock_region\")

# Intraday
intra = cfg.get(\"intraday\", {})
if intra.get(\"daily_capital_limit\", 0) < 1000: errors.append(\"intraday capital < 1000\")
if intra.get(\"per_trade_max_capital\", 0) < 1000: errors.append(\"per_trade_max < 1000\")
if intra.get(\"daily_loss_limit\", 0) <= 0: errors.append(\"intraday loss_limit is 0\")
if intra.get(\"max_trades_per_day\", 0) < 1: errors.append(\"max_trades < 1\")

# FnO
fno = cfg.get(\"fno\", {})
if fno.get(\"mode\") not in (\"paper\", \"live\"): errors.append(f\"fno mode={fno.get('mode')} invalid\")
if fno.get(\"paper_capital\", 0) < 1000: errors.append(\"fno capital < 1000\")
if fno.get(\"daily_loss_limit\", 0) <= 0: errors.append(\"fno loss_limit is 0\")

# Dhan creds
dhan = cfg.get(\"dhan\", {})
if not dhan.get(\"client_id\"): errors.append(\"dhan client_id missing\")
if not dhan.get(\"api_key\"): errors.append(\"dhan api_key missing\")
if not dhan.get(\"totp_secret\"): errors.append(\"dhan totp_secret missing\")
if not dhan.get(\"pin\"): errors.append(\"dhan pin missing\")

if errors:
    print(\"FAIL \" + \"; \".join(errors))
else:
    cap_intra = intra[\"daily_capital_limit\"]
    cap_fno = fno[\"paper_capital\"]
    fno_mode = fno[\"mode\"]
    print(f\"OK intra={cap_intra} fno={cap_fno} mode={fno_mode}\")
' 2>&1" || echo "FAIL yaml parse error")

if echo "$CONFIG_RESULT" | grep -q "^OK"; then
    pass "Config valid: $(echo $CONFIG_RESULT | sed 's/OK //')"
else
    fail "Config errors: $(echo $CONFIG_RESULT | sed 's/FAIL //')"
    LAYER_FAILED="6"
fi
layer_check

# ═══════════════════════════════════════════════════════════════
# LAYER 7: DATA ACCESS
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 7: NSE Data Access ━━━"

NSE_RESULT=$($SSH "cd ~/$REMOTE_DIR && .venv/bin/python << 'PYEOF'
from fetchers.nse_market_movers import fetch_market_movers
data = fetch_market_movers()
sectors = data.get('sectors', [])
gainers = data.get('gainers', [])
losers = data.get('losers', [])
active = data.get('most_active', [])
print(f'OK sectors={len(sectors)} gainers={len(gainers)} losers={len(losers)} active={len(active)}')
PYEOF" 2>&1 || echo "FAIL fetch crashed")

if echo "$NSE_RESULT" | grep -q "^OK"; then
    pass "NSE data: $(echo $NSE_RESULT | grep '^OK' | sed 's/OK //')"
else
    fail "NSE fetch failed: $(echo $NSE_RESULT | tail -1 | cut -c1-100)"
fi

# Dhan TOTP auth test (issue #20)
DHAN_RESULT=$($SSH "cd ~/$REMOTE_DIR && .venv/bin/python << 'PYEOF'
import yaml, pyotp, requests
with open('config/config.yaml') as f:
    cfg = yaml.safe_load(f)
dhan = cfg['dhan']
code = pyotp.TOTP(dhan['totp_secret']).now()
url = f\"https://auth.dhan.co/app/generateAccessToken?dhanClientId={dhan['client_id']}&pin={dhan['pin']}&totp={code}\"
resp = requests.post(url, timeout=30)
if resp.status_code == 200:
    data = resp.json()
    token = data.get('accessToken') or data.get('access_token')
    if token:
        print(f'OK token_len={len(token)}')
    else:
        print(f'FAIL no token in response: {list(data.keys())}')
else:
    print(f'FAIL HTTP {resp.status_code}')
PYEOF" 2>&1 || echo "FAIL dhan crashed")

if echo "$DHAN_RESULT" | grep -q "^OK"; then
    pass "Dhan TOTP auth works: $(echo $DHAN_RESULT | sed 's/OK //')"
else
    fail "Dhan auth failed: $(echo $DHAN_RESULT | sed 's/FAIL //')"
fi

# S3 bucket access check (must use vishal-admin, correct bucket)
S3_BUCKET="dev-sandbox-dashboard-176767908884"
S3_RESULT=$($SSH "export AWS_PROFILE=vishal-admin && aws s3 ls s3://$S3_BUCKET/dashboard/ 2>&1 | head -3" 2>/dev/null || echo "FAIL")
if echo "$S3_RESULT" | grep -q "PRE\|json\|html"; then
    pass "S3 bucket accessible: $S3_BUCKET (using vishal-admin)"
else
    fail "S3 bucket '$S3_BUCKET' not accessible — check AWS_PROFILE=vishal-admin"
fi

# Verify no code uses 'default' profile or wrong bucket name
WRONG_BUCKET=$($SSH "grep -r 'wealth-builder-pro-reports' ~/$REMOTE_DIR/scripts/ ~/$REMOTE_DIR/run_*.sh 2>/dev/null | grep -v '.pyc' | head -3" || echo "")
if [ -z "$WRONG_BUCKET" ]; then
    pass "No scripts reference wrong bucket name"
else
    fail "Scripts still reference old bucket 'wealth-builder-pro-reports'"
fi

# S3 bucket must be PRIVATE (no public access) — AWS IT Paladin catches public buckets
S3_PUBLIC=$($SSH "export AWS_PROFILE=vishal-admin && aws s3api get-public-access-block --bucket $S3_BUCKET 2>&1" 2>/dev/null || echo "FAIL")
if echo "$S3_PUBLIC" | grep -q '"BlockPublicAcls": true'; then
    pass "S3 bucket is PRIVATE (public access blocked)"
else
    fail "S3 bucket may be PUBLIC — AWS IT Paladin will flag this! Run: aws s3api put-public-access-block"
fi

# ═══════════════════════════════════════════════════════════════
# LAYER 8: END-TO-END DRY RUN (quick — no monitoring loop)
# ═══════════════════════════════════════════════════════════════
echo ""
echo "━━━ Layer 8: End-to-End Pipeline Test ━━━"

E2E_RESULT=$($SSH "cd ~/$REMOTE_DIR && export AWS_PROFILE=vishal-admin && export AWS_DEFAULT_REGION=us-east-1 && timeout 120 .venv/bin/python -c '
import sys, os
os.environ[\"AWS_PROFILE\"] = \"vishal-admin\"
os.environ[\"AWS_DEFAULT_REGION\"] = \"us-east-1\"

from config.config_loader import load_config, load_intraday_config
from database.db_manager import DBManager
from intraday.auth_server import DryRunBrokerClient
from intraday.scanner import Pre_Market_Scanner
from intraday.selector import pre_filter_candidates

# Load config
app_config = load_config(\"config/config.yaml\")
intra_config = load_intraday_config(\"config/config.yaml\")

# DB
db = DBManager(app_config.db_path)

# Scan
scanner = Pre_Market_Scanner()
scan = scanner.scan()
if scan is None:
    print(\"FAIL scan returned None\")
    sys.exit(1)

# Pre-filter
filtered = pre_filter_candidates(scan.candidates, intra_config, scan.sectors)

print(f\"OK candidates={len(scan.candidates)} filtered={len(filtered)} vix={scan.vix_value:.1f}\")
db.close()
' 2>&1" || echo "FAIL e2e crashed")

if echo "$E2E_RESULT" | grep -q "^OK"; then
    pass "E2E pipeline: $(echo $E2E_RESULT | sed 's/OK //')"
else
    # Show last meaningful line
    ERROR_LINE=$(echo "$E2E_RESULT" | grep -E "FAIL|Error|error" | tail -1 | cut -c1-120)
    fail "E2E failed: ${ERROR_LINE:-unknown error}"
fi

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
echo ""
summary
exit $FAILURES
