#!/bin/bash
# F&O Auto-Trader — Daily Cron Runner
# Runs at 9:20 AM IST (3:50 AM UTC)
# Paper mode by default. Change --force to --live for real money.
# Logs to logs/fno_YYYY-MM-DD.log
#
# DUPLICATE PREVENTION: Uses a lock file so only one instance runs at a time.
# If a previous run is still active (or crashed), the lock is auto-cleaned
# after 6 hours to prevent permanent lockout.

APP_DIR="/Users/vshorgha/kiro/websites/intraday-trader"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"
LOCK_FILE="${APP_DIR}/logs/.fno.lock"
LOCK_MAX_AGE=21600  # 6 hours in seconds

# Create log directory
mkdir -p "${LOG_DIR}"

DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/fno_${DATE}.log"

# ── Duplicate prevention ──
# Clean stale lock (older than 6 hours = crashed previous run)
if [ -f "${LOCK_FILE}" ]; then
    lock_age=$(( $(date +%s) - $(stat -f %m "${LOCK_FILE}" 2>/dev/null || stat -c %Y "${LOCK_FILE}" 2>/dev/null || echo 0) ))
    if [ "${lock_age}" -gt "${LOCK_MAX_AGE}" ]; then
        echo "$(date): Removing stale lock (age: ${lock_age}s)" >> "${LOG_FILE}"
        rm -f "${LOCK_FILE}"
    else
        echo "$(date): SKIPPED — another instance is running (lock age: ${lock_age}s)" >> "${LOG_FILE}"
        exit 0
    fi
fi

# Acquire lock
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

# AWS credentials for Bedrock LLM — ALWAYS unset first to avoid stale env vars
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"

cd "${APP_DIR}"

echo "=== F&O Auto-Trader — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"
echo "Python: ${PYTHON}" >> "${LOG_FILE}"
echo "PID: $$" >> "${LOG_FILE}"

# Run F&O auto-trader in paper mode
${PYTHON} run_fno.py --force >> "${LOG_FILE}" 2>&1 || true

echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "Exit code: $?" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
