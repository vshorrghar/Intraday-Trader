#!/bin/bash
# Upload Groww XLSX files to EC2
# Usage: ./upload_portfolio.sh
#
# Looks for files in two places:
# 1. input/ folder (if you already copied them there)
# 2. ~/Downloads/ (finds latest Groww files automatically)

EC2_IP="3.108.156.101"
KEY="$HOME/Downloads/wealth-builder-pro.pem"
PROJECT="$( cd "$( dirname "$0" )" && pwd )"
SCP="scp -i $KEY -o StrictHostKeyChecking=no"

echo ""
echo "📤 Upload Portfolio Files to EC2"
echo "================================"
echo ""

# Find latest Groww files in Downloads
STOCKS=$(ls -t ~/Downloads/Stocks_Holdings_Statement_*.xlsx 2>/dev/null | head -1)
MF=$(ls -t ~/Downloads/Mutual_Funds_*_*_*.xlsx 2>/dev/null | head -1)
PNL=$(ls -t ~/Downloads/Stocks_PnL_Report_*.xlsx 2>/dev/null | head -1)

# Copy to input/ folder first
mkdir -p "$PROJECT/input"

if [ -n "$STOCKS" ]; then
    cp "$STOCKS" "$PROJECT/input/Stocks_Holdings_Statement.xlsx"
    echo "  ✅ Found: $(basename $STOCKS)"
else
    echo "  ⚠️  No Stocks Holdings file in Downloads"
fi

if [ -n "$MF" ]; then
    cp "$MF" "$PROJECT/input/Mutual_Funds.xlsx"
    echo "  ✅ Found: $(basename $MF)"
else
    echo "  ⚠️  No Mutual Funds file in Downloads"
fi

if [ -n "$PNL" ]; then
    cp "$PNL" "$PROJECT/input/Stocks_PnL_Report.xlsx"
    echo "  ✅ Found: $(basename $PNL)"
else
    echo "  ⚠️  No P&L Report in Downloads (optional)"
fi

# Upload to EC2
echo ""
echo "📡 Uploading to EC2..."
$SCP "$PROJECT/input/"*.xlsx ec2-user@$EC2_IP:~/wealth-builder-pro/input/ 2>/dev/null

if [ $? -eq 0 ]; then
    echo "  ✅ Files uploaded to EC2"
    echo ""
    echo "Now run: ./go.sh"
else
    echo "  ❌ Upload failed. Is EC2 running?"
fi
