#!/bin/bash
set -e
APP_DIR="/home/ec2-user/dev-sandbox"

# ── Step 0: Remove any root crontab to prevent duplicate processes ──
echo "🔒 Removing root crontab (if any) to prevent duplicate processes..."
sudo crontab -r 2>/dev/null || true
echo "  ✅ Root crontab cleared"

# Create FnO daily script (with lock file for duplicate prevention)
cat > ${APP_DIR}/run_fno_daily.sh << 'EOF'
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
EOF

# Create Intraday daily script (with lock file for duplicate prevention)
cat > ${APP_DIR}/run_daily.sh << 'EOF'
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
${PYTHON} run_intraday.py --force ${PROFILE_FLAG} >> "${LOG_FILE}" 2>&1 || true
echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
EOF

chmod +x ${APP_DIR}/run_fno_daily.sh ${APP_DIR}/run_daily.sh

# Set up cron ONLY for ec2-user — 09:20 IST = 03:50 UTC, 09:25 IST = 03:55 UTC
# Each profile gets its own cron entries with --profile flag
# Midday at 12:00 IST = 06:30 UTC, Afternoon at 13:30 IST = 08:00 UTC
cat << 'CRON' | crontab -
# === VISHAL ===
# FnO: 9:20 AM IST
50 3 * * 1-5 /home/ec2-user/dev-sandbox/run_fno_daily.sh --profile vishal
# Intraday morning: 9:25 AM IST
55 3 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile vishal
# Intraday midday: 12:00 PM IST
30 6 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile vishal
# Intraday afternoon: 1:30 PM IST
0 8 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile vishal

# === NEHA (uncomment when credentials are added) ===
# FnO: 9:22 AM IST (2 min offset to avoid overlap)
#52 3 * * 1-5 /home/ec2-user/dev-sandbox/run_fno_daily.sh --profile neha
# Intraday morning: 9:27 AM IST
#57 3 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
# Intraday midday: 12:02 PM IST
#32 6 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
# Intraday afternoon: 1:32 PM IST
#2 8 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
CRON

echo "--- Cron (ec2-user only) ---"
crontab -l
echo ""
echo "--- Root crontab (should be empty) ---"
sudo crontab -l 2>/dev/null || echo "(empty)"
echo ""
echo "--- Scripts ---"
ls -la ${APP_DIR}/run_daily.sh ${APP_DIR}/run_fno_daily.sh
echo ""
echo "DONE — cron runs ONLY as ec2-user, with lock files to prevent duplicates"
