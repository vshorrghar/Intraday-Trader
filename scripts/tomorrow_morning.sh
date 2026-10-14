#!/bin/bash
# tomorrow_morning.sh — validate single-auth + Monday-readiness on a COOLED account.
# Run ONCE in the morning. Does exactly ONE pre_auth. Do NOT run repeatedly.
cd /home/ec2-user/dev-sandbox
echo "=== STEP 1: single pre_auth (the ONLY auth of the day) ==="
.venv/bin/python scripts/pre_auth_dhan.py 2>&1 | tail -4

echo ""
echo "=== STEP 2: preflight go/no-go ==="
bash scripts/preflight_live.sh
PF=$?

echo ""
echo "=== STEP 3: if GO, one dry orchestrator cycle — must reuse token, NOT re-auth ==="
if [ $PF -eq 0 ]; then
  .venv/bin/python - <<'PY' 2>&1 | grep -iE "SHARED token|SINGLE-AUTH|valid_data|trades_placed|RAISED"
import logging; logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
from intraday.v3.orchestrator import run_v3_cycle
try: print("RESULT:", run_v3_cycle("vishal-live-v2", dry_run=False))
except Exception as e: print("RAISED:", type(e).__name__, str(e)[:80])
PY
else
  echo "PREFLIGHT NO-GO — do not trade. Fix FAILs above first."
fi

echo ""
echo "=== STEP 4: confirm only 1 auth happened today (proves single-auth holds) ==="
grep "$(date +%Y-%m-%d)" logs/pre_auth.log | grep -c "SUCCESS\|generated code"
echo "^ should be small (1-2 per client), NOT hundreds"
