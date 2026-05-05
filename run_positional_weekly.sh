#!/bin/bash
# Positional Trader — Weekly Runner (Fridays)
# Scan + Monitor on Friday after market close (15:35 IST = 10:05 UTC)
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/positional_${DATE}.log"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox Positional — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"

# Monitor existing positions first
${PYTHON} run_positional.py monitor >> "${LOG_FILE}" 2>&1 || true

# Then scan for new setups
${PYTHON} run_positional.py scan >> "${LOG_FILE}" 2>&1 || true

echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
