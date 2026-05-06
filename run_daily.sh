#!/bin/bash
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"

# Parse --profile argument
PROFILE=""
PROFILE_FLAG=""
LIVE_FLAG=""
for arg in "$@"; do
    case $arg in
        --profile) shift; PROFILE="$1"; PROFILE_FLAG="--profile $1"; shift;;
        --profile=*) PROFILE="${arg#*=}"; PROFILE_FLAG="--profile ${arg#*=}";;
        --live) LIVE_FLAG="--live";;
    esac
done

LOCK_SUFFIX="${PROFILE:-default}"
# Per-session lock: includes hour so morning/midday/afternoon don't block each other
SESSION_HOUR=$(date +%H)
LOCK_FILE="${LOG_DIR}/.intraday_${LOCK_SUFFIX}_${SESSION_HOUR}.lock"
LOCK_MAX_AGE=7200  # 2 hours (single session max)
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/intraday_${LOCK_SUFFIX}_${DATE}.log"

# Duplicate prevention (only blocks SAME hour re-run, not different sessions)
if [ -f "${LOCK_FILE}" ]; then
    lock_age=$(( $(date +%s) - $(stat -c %Y "${LOCK_FILE}" 2>/dev/null || echo 0) ))
    if [ "${lock_age}" -gt "${LOCK_MAX_AGE}" ]; then
        echo "$(date): Removing stale lock (age: ${lock_age}s)" >> "${LOG_FILE}"
        rm -f "${LOCK_FILE}"
    else
        echo "$(date): SKIPPED — same-hour instance running (lock age: ${lock_age}s, PID: $(cat ${LOCK_FILE}))" >> "${LOG_FILE}"
        exit 0
    fi
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox Intraday [${LOCK_SUFFIX}] session=${SESSION_HOUR} — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date), PID: $$, User: $(whoami)" >> "${LOG_FILE}"
${PYTHON} run_intraday.py --force ${PROFILE_FLAG} ${LIVE_FLAG} >> "${LOG_FILE}" 2>&1 || true
echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
