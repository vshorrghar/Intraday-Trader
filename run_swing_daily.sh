#!/bin/bash
# Swing Trader — Daily Runner
# Scan: 15:35 IST (10:05 UTC) — after market close
# Monitor: 09:35 IST (04:05 UTC) — after market open
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/swing_${DATE}.log"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox Swing — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"

# Determine action based on time (UTC)
HOUR=$(date +%H)
if [ "$HOUR" -ge 9 ]; then
    # After 9 UTC = after 14:30 IST = scan time
    ${PYTHON} run_swing.py scan --force >> "${LOG_FILE}" 2>&1 || true
else
    # Before 9 UTC = morning = monitor time
    ${PYTHON} run_swing.py monitor >> "${LOG_FILE}" 2>&1 || true
fi

echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
