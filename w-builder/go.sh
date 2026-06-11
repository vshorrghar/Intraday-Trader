#!/bin/bash
# Wealth Builder Pro — ONE COMMAND
# Usage: ./go.sh
#
# Needs: Isengard creds (for SSH from Mac to EC2)
# EC2 uses IAM role for Bedrock (no creds needed on EC2)

set -e

EC2_INSTANCE_ID="i-0a31ad57170cbfd0c"
EC2_REGION="ap-south-1"
KEY="$HOME/Downloads/wealth-builder-pro.pem"
PROJECT="$( cd "$( dirname "$0" )" && pwd )"
EC2_PATH="~/wealth-builder-pro"

cd "$PROJECT"

echo ""
echo "💼 Wealth Builder Pro"
echo "====================="
echo ""

# ── Step 1: AWS Creds (only for SSH/SCP from Mac) ───────────────
echo "📋 Paste your Isengard credentials (for SSH access)."
echo "   Paste ALL export lines, then press Enter on empty line:"
echo ""

CREDS=""
while IFS= read -r line; do
    [ -z "$line" ] && break
    CREDS="$CREDS$line"$'\n'
done

AWS_KEY=$(echo "$CREDS" | grep AWS_ACCESS_KEY_ID | sed 's/.*AWS_ACCESS_KEY_ID=//' | tr -d ' "'"'")
AWS_SECRET=$(echo "$CREDS" | grep AWS_SECRET_ACCESS_KEY | sed 's/.*AWS_SECRET_ACCESS_KEY=//' | tr -d ' "'"'")
AWS_TOKEN=$(echo "$CREDS" | grep AWS_SESSION_TOKEN | sed 's/.*AWS_SESSION_TOKEN=//' | tr -d ' "'"'")

if [ -z "$AWS_KEY" ] || [ -z "$AWS_SECRET" ] || [ -z "$AWS_TOKEN" ]; then
    echo "❌ Could not parse credentials."; exit 1
fi
echo "  ✅ Creds parsed"

export AWS_ACCESS_KEY_ID="$AWS_KEY"
export AWS_SECRET_ACCESS_KEY="$AWS_SECRET"
export AWS_SESSION_TOKEN="$AWS_TOKEN"

# ── Step 2: Get EC2 IP ───────────────────────────────────────────
echo ""
echo "🔍 Looking up EC2 IP..."
EC2_IP=$(aws ec2 describe-instances \
    --instance-ids "$EC2_INSTANCE_ID" \
    --region "$EC2_REGION" \
    --query "Reservations[0].Instances[0].PublicIpAddress" \
    --output text 2>/dev/null)

if [ -z "$EC2_IP" ] || [ "$EC2_IP" = "None" ]; then
    echo "❌ EC2 has no public IP. Is it running?"; exit 1
fi
echo "  ✅ EC2 IP: $EC2_IP"

SSH="ssh -i $KEY -o ConnectTimeout=15 -o StrictHostKeyChecking=no ec2-user@$EC2_IP"
SCP="scp -i $KEY -o StrictHostKeyChecking=no"

# ── Step 3: Pick latest XLSX from Downloads ──────────────────────
echo ""
echo "📂 Picking latest Groww files..."
python3 pick_latest_files.py

# ── Step 4: Check EC2 reachable ──────────────────────────────────
echo ""
echo "🔌 Checking EC2..."
if ! $SSH "echo ok" > /dev/null 2>&1; then
    echo "❌ EC2 unreachable. Check security group in Console (SSH 0.0.0.0/0)."
    exit 1
fi
echo "  ✅ EC2 is up"

# ── Step 5: Sync code + XLSX to EC2 ─────────────────────────────
echo ""
echo "📤 Syncing code + files to EC2..."
tar czf /tmp/wb_code.tar.gz \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='venv' --exclude='.kiro' --exclude='.vscode' \
    --exclude='output' --exclude='cache' --exclude='database/*.db' \
    --exclude='input' .
$SCP /tmp/wb_code.tar.gz ec2-user@$EC2_IP:~/
$SSH "cd $EC2_PATH && tar xzf ~/wb_code.tar.gz 2>/dev/null"
echo "  ✅ Code synced"

if ls input/*.xlsx > /dev/null 2>&1; then
    $SCP input/*.xlsx ec2-user@$EC2_IP:$EC2_PATH/input/
    echo "  ✅ XLSX files synced"
fi

# ── Step 6: Run analysis on EC2 (uses IAM role, no creds!) ──────
echo ""
echo "🤖 Running portfolio analysis on EC2 (uses IAM role)..."
$SSH "
cd $EC2_PATH && source venv/bin/activate
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export BEDROCK_MODEL_ID='us.anthropic.claude-sonnet-4-20250514-v1:0'
python3 run_analysis.py 2>&1 | tail -8
"

echo ""
echo "📡 Running market scan on EC2..."
$SSH "
cd $EC2_PATH && source venv/bin/activate
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export BEDROCK_MODEL_ID='us.anthropic.claude-sonnet-4-20250514-v1:0'
python3 run_market_scan.py 2>&1 | tail -8
"

echo ""
echo "🔧 Building dashboard on EC2..."
$SSH "
cd $EC2_PATH && source venv/bin/activate
python3 build_dashboard.py 2>&1 | tail -5
"

# ── Step 7: Pull results to Mac ─────────────────────────────────
echo ""
echo "📥 Pulling results to Mac..."
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M")
mkdir -p output/reports

$SCP "ec2-user@$EC2_IP:$EC2_PATH/output/reports/data.json" output/reports/data.json
$SCP "ec2-user@$EC2_IP:$EC2_PATH/output/latest_analysis.json" "output/reports/analysis_${TIMESTAMP}.json"
ln -sf "analysis_${TIMESTAMP}.json" output/reports/latest.json
echo "  ✅ Report: output/reports/analysis_${TIMESTAMP}.json"

# ── Step 8: Open dashboard ──────────────────────────────────────
if ! lsof -i :8877 > /dev/null 2>&1; then
    cd output/reports && python3 -m http.server 8877 > /dev/null 2>&1 &
    cd "$PROJECT"
    sleep 1
fi

echo ""
echo "🌐 Opening dashboard..."
open http://localhost:8877/dashboard.html

echo ""
echo "=============================="
echo "✅ ALL DONE!"
echo "=============================="
echo "Dashboard: http://localhost:8877/dashboard.html"
echo "Report:    output/reports/analysis_${TIMESTAMP}.json"
echo ""
