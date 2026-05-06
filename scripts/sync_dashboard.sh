#!/usr/bin/env bash
# sync_dashboard.sh — Sync dashboard files to S3 for CloudFront serving
# Same bucket, Neha gets /neha/ prefix
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REGION="ap-south-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="dev-sandbox-dashboard-${ACCOUNT_ID}"

echo "$(date '+%Y-%m-%d %H:%M:%S') — Syncing dashboards to s3://${BUCKET}"

# --- Vishal's dashboard (root path) ---
VISHAL_DIR="${APP_DIR}/dashboard"
if [ -d "${VISHAL_DIR}" ] && [ -f "${VISHAL_DIR}/index.html" ]; then
    echo "  Syncing Vishal → s3://${BUCKET}/"
    aws s3 sync "${VISHAL_DIR}/" "s3://${BUCKET}/" \
        --region "${REGION}" \
        --exclude "neha/*" \
        --delete \
        --cache-control "max-age=300" \
        --quiet
    echo "  ✅ Vishal dashboard synced"
else
    echo "  ⚠️  Skipping Vishal (no dashboard/index.html)"
fi

# --- Neha's dashboard (/neha/ prefix) ---
NEHA_DIR="${APP_DIR}/dashboard_neha"
if [ -d "${NEHA_DIR}" ] && [ -f "${NEHA_DIR}/index.html" ]; then
    echo "  Syncing Neha → s3://${BUCKET}/neha/"
    aws s3 sync "${NEHA_DIR}/" "s3://${BUCKET}/neha/" \
        --region "${REGION}" \
        --delete \
        --cache-control "max-age=300" \
        --quiet
    echo "  ✅ Neha dashboard synced"
else
    echo "  ⚠️  Skipping Neha (no dashboard_neha/index.html)"
fi

# --- Update trading history ---
cd "${APP_DIR}"
source "${APP_DIR}/.venv/bin/activate" 2>/dev/null || source "${APP_DIR}/venv/bin/activate" 2>/dev/null || true

python3 scripts/update_history.py 2>/dev/null || true
python3 scripts/update_history.py --profile neha 2>/dev/null || true

echo "$(date '+%Y-%m-%d %H:%M:%S') — Dashboard sync complete"
echo "  Vishal: https://d2q1cy3ph7jbd0.cloudfront.net"
echo "  Neha:   https://d2q1cy3ph7jbd0.cloudfront.net/neha/"
