#!/usr/bin/env bash
# deploy.sh — Wealth Builder Pro EC2 deployment script
# For Amazon Linux 2 EC2 in ap-south-1
# Run from: ~/wealth-builder-pro/
set -euo pipefail

APP_DIR="$HOME/wealth-builder-pro"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="${APP_DIR}/logs"
CACHE_DIR="${APP_DIR}/cache"
CRON_FILE="/etc/cron.d/wealth-builder-pro"

echo "=== Wealth Builder Pro Deployment ==="
echo "  App dir: ${APP_DIR}"
echo "  User: $(whoami)"

# 1. Install system dependencies (Amazon Linux 2)
echo "[1/6] Installing system dependencies..."
sudo yum install -y python3 python3-pip cronie nginx 2>/dev/null || true
sudo systemctl enable crond
sudo systemctl start crond

# 2. Create directories
echo "[2/6] Creating directories..."
mkdir -p "${LOG_DIR}" "${CACHE_DIR}" "${APP_DIR}/output/reports"

# 3. Set up Python virtual environment
echo "[3/6] Setting up Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${APP_DIR}/requirements.txt"

# 4. Install cron jobs
echo "[4/6] Installing cron jobs..."
cat > /tmp/wbp-cron << CRON
# Wealth Builder Pro scheduled pipelines (weekdays only)
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
HOME=${HOME}
WBP_CONFIG=${APP_DIR}/config/config.yaml

# Morning Brief: 8:45 AM IST = 3:15 UTC
15 3 * * 1-5 $(whoami) cd ${APP_DIR} && ${VENV_DIR}/bin/python ${APP_DIR}/scripts/run_morning_brief.py >> ${LOG_DIR}/cron.log 2>&1

# Midday Snapshot: 12:30 PM IST = 7:00 UTC
0 7 * * 1-5 $(whoami) cd ${APP_DIR} && ${VENV_DIR}/bin/python ${APP_DIR}/scripts/run_midday_snapshot.py >> ${LOG_DIR}/cron.log 2>&1

# EOD Report: 4:15 PM IST = 10:45 UTC
45 10 * * 1-5 $(whoami) cd ${APP_DIR} && ${VENV_DIR}/bin/python ${APP_DIR}/scripts/run_eod_report.py >> ${LOG_DIR}/cron.log 2>&1
CRON
sudo cp /tmp/wbp-cron "${CRON_FILE}"
sudo chmod 644 "${CRON_FILE}"
rm /tmp/wbp-cron

# 5. Verify cron installed
echo "[5/6] Verifying..."
echo "  Cron file:"
cat "${CRON_FILE}"
echo ""
echo "  Cron service:"
sudo systemctl status crond --no-pager -l 2>/dev/null | head -5 || echo "  crond status check skipped"

# 6. Test run (dry)
echo "[6/6] Testing pipeline imports..."
cd "${APP_DIR}"
${VENV_DIR}/bin/python -c "
import sys; sys.path.insert(0,'.')
from config.config_loader import load_config
from reports.ses_sender import send_email
from reports.html_builder import build_morning_brief
print('  ✅ All imports OK')
" 2>&1 || echo "  ⚠️ Import test failed — check dependencies"

echo ""
echo "=== Deployment Complete ==="
echo "  Cron: ${CRON_FILE}"
echo "  Logs: ${LOG_DIR}/cron.log"
echo "  Schedule (IST, weekdays):"
echo "    8:45 AM  → Morning Brief"
echo "    12:30 PM → Midday Snapshot"
echo "    4:15 PM  → EOD Report"
echo ""
echo "  To test manually:"
echo "    cd ${APP_DIR} && ${VENV_DIR}/bin/python scripts/run_morning_brief.py"
