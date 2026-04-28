#!/bin/bash
# Wealth Builder Pro — One-Command Runner
# Usage: ./run.sh
#
# Does everything:
# 1. Checks AWS creds
# 2. Finds latest Groww XLSX from ~/Downloads → copies to input/
# 3. Warns if files are stale (>3 days)
# 4. Runs AI opportunity scanner (Bedrock Claude)
# 5. Builds dashboard
# 6. Starts HTTP server and opens browser

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PORT=8877

echo ""
echo "🚀 Wealth Builder Pro — Full Pipeline"
echo "======================================"
echo ""

# ── Step 1: Check AWS creds ──────────────────────────────────────
echo "🔑 Checking AWS credentials..."

# Try current env first, then vishal-admin profile
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "  No active creds in env, trying vishal-admin profile..."
    export AWS_PROFILE=vishal-admin
    if aws sts get-caller-identity > /dev/null 2>&1; then
        echo "  ✅ Using vishal-admin profile"
    else
        unset AWS_PROFILE
        echo "  ❌ No valid credentials found."
        echo ""
        echo "  Paste your Isengard creds below (all export lines), then press Enter on an empty line:"
        echo ""
        CREDS=""
        while IFS= read -r line; do
            [ -z "$line" ] && break
            CREDS="$CREDS$line"$'\n'
        done
        eval "$(echo "$CREDS" | grep '^export ')"
        
        if ! aws sts get-caller-identity > /dev/null 2>&1; then
            echo "  ❌ Creds still invalid. Check and try again."
            exit 1
        fi
    fi
fi
IDENTITY=$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null)
echo "✅ AWS creds OK: $IDENTITY"
echo ""

# ── Step 2: Find latest Groww files from Downloads ───────────────
echo "📂 Searching ~/Downloads for latest Groww files..."

DOWNLOADS=~/Downloads
STALE_DAYS=3
NOW=$(date +%s)
STALE_WARNING=0

# Find latest Stocks Holdings
LATEST_STOCKS=$(ls -t "$DOWNLOADS"/Stocks_Holdings_Statement_*.xlsx 2>/dev/null | head -1)
if [ -n "$LATEST_STOCKS" ]; then
    cp "$LATEST_STOCKS" input/Stocks_Holdings_Statement.xlsx
    echo "  ✅ Stocks Holdings: $(basename "$LATEST_STOCKS")"
fi

# Find latest Mutual Funds
LATEST_MF=$(ls -t "$DOWNLOADS"/Mutual_Funds_5440360876_*.xlsx 2>/dev/null | head -1)
if [ -n "$LATEST_MF" ]; then
    cp "$LATEST_MF" input/Mutual_Funds.xlsx
    echo "  ✅ Mutual Funds: $(basename "$LATEST_MF")"
fi

# Find latest P&L Report
LATEST_PNL=$(ls -t "$DOWNLOADS"/Stocks_PnL_Report_*.xlsx 2>/dev/null | head -1)
if [ -n "$LATEST_PNL" ]; then
    cp "$LATEST_PNL" input/Stocks_PnL_Report.xlsx
    echo "  ✅ P&L Report: $(basename "$LATEST_PNL")"
fi

# Find latest Order History
LATEST_OH=$(ls -t "$DOWNLOADS"/Stocks_Order_History_*.xlsx 2>/dev/null | head -1)
if [ -n "$LATEST_OH" ]; then
    cp "$LATEST_OH" input/Stocks_Order_History.xlsx
    echo "  ✅ Stocks Order History: $(basename "$LATEST_OH")"
fi

# Find latest MF Order History
LATEST_MOH=$(ls -t "$DOWNLOADS"/Mutual_Funds_Order_History_*.xlsx 2>/dev/null | head -1)
if [ -n "$LATEST_MOH" ]; then
    cp "$LATEST_MOH" input/MF_Order_History.xlsx
    echo "  ✅ MF Order History: $(basename "$LATEST_MOH")"
fi

echo ""

# ── Step 3: Check file freshness ─────────────────────────────────
echo "📅 Checking file freshness..."
for f in input/*.xlsx; do
    if [ -f "$f" ]; then
        FMOD=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null)
        AGE=$(( (NOW - FMOD) / 86400 ))
        NAME=$(basename "$f")
        if [ "$AGE" -gt "$STALE_DAYS" ]; then
            echo "  ⚠️  $NAME: ${AGE} days old (STALE)"
            STALE_WARNING=1
        else
            echo "  ✅ $NAME: ${AGE} day(s) old"
        fi
    fi
done

if [ "$STALE_WARNING" -eq 1 ]; then
    echo ""
    echo "⚠️  Some files are older than ${STALE_DAYS} days."
    read -p "Continue anyway? (y/n): " REPLY
    if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
        echo "Aborted. Download fresh files from Groww first."
        exit 0
    fi
fi

echo ""

# ── Step 4: Run AI Opportunity Scanner ───────────────────────────
echo "🤖 Running AI Opportunity Scanner (Bedrock Claude)..."
echo "   This takes 60-90 seconds..."
python3 run_opportunities.py
echo ""

# ── Step 5: Build Dashboard ──────────────────────────────────────
echo "📊 Building dashboard..."
python3 build_dashboard.py
echo ""

# ── Step 6: Start server and open browser ────────────────────────
# Kill any existing server on the port
kill $(lsof -ti:$PORT) 2>/dev/null || true
sleep 1

echo "🌐 Starting dashboard server on port $PORT..."
cd output/reports
python3 -m http.server $PORT &
SERVER_PID=$!
sleep 1

echo ""
echo "======================================"
echo "✅ Dashboard ready!"
echo ""
echo "   👉 http://localhost:$PORT/dashboard.html"
echo ""
echo "   Press Ctrl+C to stop the server"
echo "======================================"

# Open in browser
open "http://localhost:$PORT/dashboard.html" 2>/dev/null || true

# Wait for Ctrl+C
wait $SERVER_PID
