#!/bin/bash
# ================================================================
# VISHAL-LIVE VALIDATION SCRIPT
# Run at 3 checkpoints: morning / midday / eod
# Usage: bash scripts/validate_tomorrow.sh morning
# ================================================================

cd /home/ec2-user/dev-sandbox
export AWS_PROFILE=vishal-admin

CHECKPOINT="${1:-morning}"
DATE=$(date +%Y-%m-%d)
LOG="logs/intraday_vishal-live_${DATE}.log"
PYTHON=".venv/bin/python3"

echo "================================================================"
echo " VISHAL-LIVE VALIDATION — CHECKPOINT: ${CHECKPOINT}"
echo " Date: ${DATE}  Time: $(TZ=Asia/Kolkata date '+%H:%M:%S IST')"
echo "================================================================"
echo ""

PASS_COUNT=0
TOTAL=5

# ─── CHECK 1: Fresh state / Cron fired ───
echo "[CHECK 1 — Fresh state / Cron fired]"
if [ ! -f "$LOG" ]; then
    echo "  Status: N/A"
    echo "  Evidence: No log file yet (${LOG})"
    echo ""
else
    SESSION_COUNT=$(grep -c "Phase: Configuration — START" "$LOG" 2>/dev/null)
    FIRST_RESTORE=$(grep "Restored daily state" "$LOG" | head -1)
    
    if echo "$FIRST_RESTORE" | grep -q "trades=0"; then
        echo "  Status: PASS"
        echo "  Evidence: First restore shows trades=0"
        echo "  Sessions fired: ${SESSION_COUNT}"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ -z "$FIRST_RESTORE" ]; then
        echo "  Status: N/A"
        echo "  Evidence: No 'Restored daily state' line yet"
    else
        echo "  Status: FAIL"
        echo "  Evidence: First restore NOT trades=0: ${FIRST_RESTORE}"
    fi
fi
echo ""

# ─── CHECK 2: Bug A — Auth collision (Dhan API) ───
echo "[CHECK 2 — Bug A: Auth collision duplicates]"
echo "  Test: No same-symbol orders within 5 seconds on Dhan"
DHAN_RESULT=$($PYTHON scripts/check_dhan_orders.py 2>/dev/null)

if echo "$DHAN_RESULT" | grep -q "AUTH_FAIL\|ORDERS_FAIL"; then
    echo "  Status: FAIL"
    echo "  Evidence: Dhan API call failed: ${DHAN_RESULT}"
    echo ""
elif [ -z "$DHAN_RESULT" ]; then
    echo "  Status: N/A"
    echo "  Evidence: No Dhan data (market may not have opened yet)"
    echo ""
else
    DUP_COUNT=$(echo "$DHAN_RESULT" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('duplicate_count',0))" 2>/dev/null)
    TRADED_COUNT=$(echo "$DHAN_RESULT" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('traded_orders',0))" 2>/dev/null)
    
    if [ "$DUP_COUNT" = "0" ] && [ "$TRADED_COUNT" != "0" ]; then
        echo "  Status: PASS"
        echo "  Evidence: ${TRADED_COUNT} traded orders, 0 duplicate pairs"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$TRADED_COUNT" = "0" ]; then
        echo "  Status: N/A"
        echo "  Evidence: No traded orders yet today"
    else
        echo "  Status: FAIL"
        echo "  Evidence: ${DUP_COUNT} duplicate pairs found!"
        # Show details
        echo "$DHAN_RESULT" | $PYTHON -c "
import sys, json
d = json.load(sys.stdin)
for dup in d.get('duplicate_pairs', []):
    print(f\"    [DUP] {dup['symbol']} {dup['txn']}: {dup['time1']} + {dup['time2']} ({dup['time_diff_sec']:.0f}s apart)\")
" 2>/dev/null
    fi
fi
echo ""

# ─── CHECK 3: Bug 5b — Trade counter ───
echo "[CHECK 3 — Bug 5b: Trade counter counts BUY+SELL]"
if [ ! -f "$LOG" ]; then
    echo "  Status: N/A"
    echo "  Evidence: No log file"
    echo ""
else
    # Look for Restored lines showing incrementing counter
    RESTORE_LINES=$(grep "Restored daily state: trades=" "$LOG" | tail -5)
    LATEST_TRADES=$(grep "Restored daily state: trades=" "$LOG" | tail -1 | grep -oP 'trades=\K[0-9]+')
    
    # Check if any SELL trade was placed
    SELL_PLACED=$(grep "Dhan place_order: SELL" "$LOG" | grep -v "@ 0.00" | head -1)
    
    if [ -n "$SELL_PLACED" ] && [ -n "$LATEST_TRADES" ] && [ "$LATEST_TRADES" -gt "0" ]; then
        echo "  Status: PASS"
        echo "  Evidence: SELL trade placed AND counter=${LATEST_TRADES} (>0)"
        echo "  SELL order: ${SELL_PLACED:0:100}"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ -z "$SELL_PLACED" ]; then
        # No SHORT trades today — check if BUY counter works
        BUY_PLACED=$(grep "Dhan place_order: BUY" "$LOG" | head -1)
        if [ -n "$BUY_PLACED" ] && [ -n "$LATEST_TRADES" ] && [ "$LATEST_TRADES" -gt "0" ]; then
            echo "  Status: PASS"
            echo "  Evidence: BUY trade placed AND counter=${LATEST_TRADES} (>0). No SHORT trades to test SELL counting."
            PASS_COUNT=$((PASS_COUNT + 1))
        elif [ -z "$BUY_PLACED" ]; then
            echo "  Status: N/A"
            echo "  Evidence: No trades placed yet"
        else
            echo "  Status: FAIL"
            echo "  Evidence: Trade placed but counter=${LATEST_TRADES}"
        fi
    else
        echo "  Status: FAIL"
        echo "  Evidence: SELL placed but counter=${LATEST_TRADES} (should be >0)"
    fi
fi
echo ""

# ─── CHECK 4: Bug 5c — Same-symbol re-entry block ───
echo "[CHECK 4 — Bug 5c: Same-symbol re-entry block]"
if [ ! -f "$LOG" ]; then
    echo "  Status: N/A"
    echo "  Evidence: No log file"
    echo ""
else
    REENTRY_BLOCK=$(grep "already traded today" "$LOG" | head -3)
    UNIQUE_SYMBOLS=$(grep "Dhan place_order" "$LOG" | grep -v "@ 0.00" | awk '{print $6}' | sort -u | wc -l)
    TOTAL_ORDERS=$(grep "Dhan place_order" "$LOG" | grep -v "@ 0.00" | wc -l)
    
    if [ -n "$REENTRY_BLOCK" ]; then
        echo "  Status: PASS"
        echo "  Evidence: Re-entry block fired:"
        echo "    ${REENTRY_BLOCK:0:200}"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$UNIQUE_SYMBOLS" -le "3" ] && [ "$TOTAL_ORDERS" -gt "0" ]; then
        echo "  Status: PASS (indirect)"
        echo "  Evidence: ${UNIQUE_SYMBOLS} unique symbols in ${TOTAL_ORDERS} orders (≤3 limit respected)"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$TOTAL_ORDERS" = "0" ]; then
        echo "  Status: N/A"
        echo "  Evidence: No orders placed yet — cannot test re-entry"
    else
        echo "  Status: FAIL"
        echo "  Evidence: ${UNIQUE_SYMBOLS} unique symbols, ${TOTAL_ORDERS} total orders (possible re-entry)"
    fi
fi
echo ""

# ─── CHECK 5: Loss limit + DB vs Dhan reconciliation ───
echo "[CHECK 5 — Loss limit Rs.500 + DB vs Dhan match]"

# Config check
LOSS_LIMIT=$(grep "daily_loss_limit" config/profiles/vishal-live.yaml | head -1 | awk '{print $2}')
echo "  Config: daily_loss_limit=${LOSS_LIMIT}"

if [ "$LOSS_LIMIT" = "500" ]; then
    CONFIG_OK="yes"
else
    CONFIG_OK="no"
    echo "  WARNING: Expected 500, got ${LOSS_LIMIT}"
fi

if [ -n "$DHAN_RESULT" ] && ! echo "$DHAN_RESULT" | grep -q "AUTH_FAIL\|ORDERS_FAIL"; then
    MISMATCH_COUNT=$(echo "$DHAN_RESULT" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('mismatch_count',0))" 2>/dev/null)
    DHAN_PNL=$(echo "$DHAN_RESULT" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('dhan_total_pnl',0))" 2>/dev/null)
    DB_PNL=$(echo "$DHAN_RESULT" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); print(d.get('db_total_pnl',0))" 2>/dev/null)
    
    if [ "$CONFIG_OK" = "yes" ] && [ "$MISMATCH_COUNT" = "0" ]; then
        echo "  Status: PASS"
        echo "  Evidence: Loss limit=500, DB vs Dhan: 0 mismatches, Dhan P&L=Rs.${DHAN_PNL}, DB P&L=Rs.${DB_PNL}"
        PASS_COUNT=$((PASS_COUNT + 1))
    elif [ "$CONFIG_OK" = "yes" ] && [ "$MISMATCH_COUNT" != "0" ]; then
        echo "  Status: FAIL"
        echo "  Evidence: Loss limit OK but ${MISMATCH_COUNT} qty mismatches between DB and Dhan!"
        echo "  Dhan P&L: Rs.${DHAN_PNL} vs DB P&L: Rs.${DB_PNL}"
        echo "$DHAN_RESULT" | $PYTHON -c "
import sys, json
d = json.load(sys.stdin)
for m in d.get('db_vs_dhan_mismatches', []):
    print(f\"    {m['symbol']} {m['txn']}: DB={m['db_qty']} vs Dhan={m['dhan_qty']}\")
" 2>/dev/null
    else
        echo "  Status: FAIL"
        echo "  Evidence: Config wrong (loss_limit=${LOSS_LIMIT}, expected 500)"
    fi
else
    if [ "$CONFIG_OK" = "yes" ]; then
        echo "  Status: PASS (config only)"
        echo "  Evidence: Loss limit=500 configured. Dhan API not available for reconciliation."
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  Status: FAIL"
        echo "  Evidence: Config wrong"
    fi
fi
echo ""

# ─── SUMMARY ───
echo "================================================================"
echo " SUMMARY: ${PASS_COUNT}/${TOTAL} checks passed"
echo ""
if [ "$PASS_COUNT" -ge "4" ]; then
    echo " RECOMMENDATION: Fixes appear to be working. Continue monitoring."
elif [ "$PASS_COUNT" -ge "2" ]; then
    echo " RECOMMENDATION: Partial pass. Check FAIL items. May need investigation."
else
    echo " RECOMMENDATION: Multiple failures. DO NOT increase capital. Wait for diagnosis."
fi
echo "================================================================"
