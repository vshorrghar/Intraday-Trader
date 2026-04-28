#!/bin/bash
# F&O Auto-Trader — Daily Cron Runner
# Runs at 9:20 AM IST (3:50 AM UTC)
# Paper mode by default. Change --force to --live for real money.
# Logs to logs/fno_YYYY-MM-DD.log

APP_DIR="/Users/vshorgha/kiro/websites/intraday-trader"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"

# Create log directory
mkdir -p "${LOG_DIR}"

DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/fno_${DATE}.log"

# AWS credentials for Bedrock LLM — ALWAYS unset first to avoid stale env vars
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"

cd "${APP_DIR}"

echo "=== F&O Auto-Trader — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"
echo "Python: ${PYTHON}" >> "${LOG_FILE}"

# Run F&O auto-trader in paper mode
${PYTHON} run_fno.py --force >> "${LOG_FILE}" 2>&1 || true

echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "Exit code: $?" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
