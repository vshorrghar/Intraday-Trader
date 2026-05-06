#!/bin/bash
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"

# Parse --profile argument
PROFILE=""
PROFILE_FLAG=""
for arg in "$@"; do
    case $arg in
        --profile) shift; PROFILE="$1"; PROFILE_FLAG="--profile $1"; shift;;
        --profile=*) PROFILE="${arg#*=}"; PROFILE_FLAG="--profile ${arg#*=}";;
    esac
done

LOCK_SUFFIX="${PROFILE:-default}"
LOCK_FILE="${LOG_DIR}/.fno_${LOCK_SUFFIX}.lock"
LOCK_MAX_AGE=21600  # 6 hours
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/fno_${LOCK_SUFFIX}_${DATE}.log"

# Duplicate prevention (per-profile lock)
if [ -f "${LOCK_FILE}" ]; then
    lock_age=$(( $(date +%s) - $(stat -c %Y "${LOCK_FILE}" 2>/dev/null || echo 0) ))
    if [ "${lock_age}" -gt "${LOCK_MAX_AGE}" ]; then
        echo "$(date): Removing stale lock (age: ${lock_age}s)" >> "${LOG_FILE}"
        rm -f "${LOCK_FILE}"
    else
        echo "$(date): SKIPPED — another instance is running (lock age: ${lock_age}s, PID: $(cat ${LOCK_FILE}))" >> "${LOG_FILE}"
        exit 0
    fi
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox FnO [${LOCK_SUFFIX}] — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date), PID: $$, User: $(whoami)" >> "${LOG_FILE}"
${PYTHON} run_fno.py --force ${PROFILE_FLAG} >> "${LOG_FILE}" 2>&1 || true
echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
