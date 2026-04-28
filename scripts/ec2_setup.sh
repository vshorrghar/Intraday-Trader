#!/bin/bash
set -e
APP_DIR="/home/ec2-user/dev-sandbox"

# Create FnO daily script
cat > ${APP_DIR}/run_fno_daily.sh << 'EOF'
#!/bin/bash
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/fno_${DATE}.log"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox FnO — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"
${PYTHON} run_fno.py --force >> "${LOG_FILE}" 2>&1 || true
echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
EOF

# Create Intraday daily script
cat > ${APP_DIR}/run_daily.sh << 'EOF'
#!/bin/bash
APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"
mkdir -p "${LOG_DIR}"
DATE=$(date +%Y-%m-%d)
LOG_FILE="${LOG_DIR}/intraday_${DATE}.log"
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION 2>/dev/null || true
export AWS_PROFILE="vishal-admin"
export AWS_DEFAULT_REGION="us-east-1"
cd "${APP_DIR}"
echo "=== Dev Sandbox Intraday — ${DATE} ===" >> "${LOG_FILE}"
echo "Started at: $(date)" >> "${LOG_FILE}"
${PYTHON} run_intraday.py --force >> "${LOG_FILE}" 2>&1 || true
echo "Finished at: $(date)" >> "${LOG_FILE}"
echo "=== END ===" >> "${LOG_FILE}"
EOF

chmod +x ${APP_DIR}/run_fno_daily.sh ${APP_DIR}/run_daily.sh

# Set up cron — 09:20 IST = 03:50 UTC, 09:25 IST = 03:55 UTC
echo "50 3 * * 1-5 /home/ec2-user/dev-sandbox/run_fno_daily.sh
55 3 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh" | crontab -

echo "--- Cron ---"
crontab -l
echo ""
echo "--- Scripts ---"
ls -la ${APP_DIR}/run_daily.sh ${APP_DIR}/run_fno_daily.sh
echo ""
echo "DONE"
