#!/bin/bash
# Sync code from Mac to EC2 (no creds needed, just SSH)
# Usage: ./sync_code.sh

EC2_IP="3.108.156.101"
KEY="$HOME/Downloads/wealth-builder-pro.pem"
PROJECT="$( cd "$( dirname "$0" )" && pwd )"

cd "$PROJECT"

echo "📤 Syncing code to EC2..."

tar czf /tmp/wb_code.tar.gz \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    --exclude='venv' --exclude='.kiro' --exclude='.vscode' \
    --exclude='output' --exclude='cache' --exclude='database/*.db' \
    --exclude='input' .

scp -i "$KEY" -o StrictHostKeyChecking=no /tmp/wb_code.tar.gz ec2-user@$EC2_IP:~/
ssh -i "$KEY" -o StrictHostKeyChecking=no ec2-user@$EC2_IP "cd ~/wealth-builder-pro && tar xzf ~/wb_code.tar.gz 2>/dev/null"

# Also sync XLSX if present
if ls input/*.xlsx > /dev/null 2>&1; then
    scp -i "$KEY" -o StrictHostKeyChecking=no input/*.xlsx ec2-user@$EC2_IP:~/wealth-builder-pro/input/
    echo "✅ Code + XLSX synced"
else
    echo "✅ Code synced (no XLSX files found in input/)"
fi
