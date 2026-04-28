#!/bin/bash
# Intraday Auto-Trader — Daily Cron Runner
# Runs at 9:25 AM IST (3:55 AM UTC)
# Dry-run by default. Add --live for real money.
# Logs to logs/intraday_YYYY-MM-DD.log

APP_DIR="/Users/vshorgha/kiro/websites/intraday-trader"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"

# Create log directory
mkdir -p "${LOG_DIR}"

DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/intraday_${DATE}.log"

# AWS credentials for Bedrock LLM — ALWAYS unset first to avoid stale env vars
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"

cd "${APP_DIR}"

echo "=== Intraday Auto-Trader — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"
echo "Python: ${PYTHON}" >> "${LOG_FILE}"

# Run intraday auto-trader (dry-run by default, add --live for real money)
${PYTHON} run_intraday.py --force >> "${LOG_FILE}" 2>&1 || true

echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "Exit code: $?" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
