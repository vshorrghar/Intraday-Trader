#!/bin/bash
# Sync code from Mac to EC2 — preserves EC2's config files
# Usage: ./sync_to_ec2.sh

set -e
KEY="$HOME/Downloads/wealth-builder-pro.pem"
EC2="ec2-user@13.206.144.6"
REMOTE_DIR="dev-sandbox"
PROJECT="$( cd "$( dirname "$0" )" && pwd )"

cd "$PROJECT"

echo "📤 Syncing code to EC2 ($EC2:~/$REMOTE_DIR)..."

# Create tar excluding stuff that shouldn't go to EC2
tar czf /tmp/wb_code.tar.gz \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='venv' --exclude='.venv' --exclude='.kiro' --exclude='.vscode' \
    --exclude='output' --exclude='cache' --exclude='input' \
    --exclude='database/*.db' --exclude='config/groww_api.yaml' \
    --exclude='.git' --exclude='.hypothesis' \
    .

scp -i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=no /tmp/wb_code.tar.gz "$EC2":~/
ssh -i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=no "$EC2" "cd ~/$REMOTE_DIR && tar xzf ~/wb_code.tar.gz 2>/dev/null"

echo "✅ Code synced to EC2"
