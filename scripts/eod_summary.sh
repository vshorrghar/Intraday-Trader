#!/bin/bash
# EOD P&L Summary — all profiles
# Usage: bash scripts/eod_summary.sh [date]
# Default: today

DATE=${1:-$(date +%Y-%m-%d)}
LOG_DIR=~/dev-sandbox/logs

echo "=============================================="
echo "  EOD SUMMARY — ${DATE}"
echo "=============================================="

summarize_profile() {
    local profile=$1
    local label=$2
    local logfile="${LOG_DIR}/intraday_${profile}_${DATE}.log"

    echo ""
    echo "--- ${label} ---"

    if [ ! -f "$logfile" ]; then
        echo "  No log file found"
        return
    fi

    # Trades placed
    local trades=$(grep -c "Placed.*orders" "$logfile" 2>/dev/null || echo 0)

    # Individual trade exits
    grep -E "FORCE EXITED|TARGET|STOPPED|Total P&L" "$logfile" | \
        sed 's/.*intraday.monitor: /  /' | \
        sed 's/.*intraday: /  /'

    # Session P&L lines
    grep -E "Total P&L|🟢 Total|🔴 Total" "$logfile" | \
        sed 's/.*intraday[^:]*: /  /'

    # If no exits found
    local exits=$(grep -cE "FORCE EXITED|TARGET|STOPPED" "$logfile" 2>/dev/null || echo 0)
    if [ "$exits" -eq 0 ]; then
        echo "  No trades completed"
        # Check if any orders placed
        grep -E "Placed [0-9]+ / [0-9]+ orders" "$logfile" | \
            sed 's/.*intraday[^:]*: /  /' | tail -5
    fi

    # Last unrealized P&L if still open
    grep "unrealized P&L" "$logfile" | tail -1 | \
        sed 's/.*intraday.monitor: /  [Last monitor] /'
}

summarize_profile "vishal-live" "VISHAL-LIVE (Real ₹10K)"
summarize_profile "vishal"      "VISHAL PAPER (₹3L)"
summarize_profile "neha"        "NEHA PAPER (₹3L)"

# Manual runs
echo ""
echo "--- MANUAL RUNS ---"
if ls ${LOG_DIR}/manual_run_${DATE}*.log 2>/dev/null | head -1 | grep -q .; then
    grep -E "FORCE EXITED|TARGET|STOPPED|Total P&L|🟢|🔴" \
        ${LOG_DIR}/manual_run_${DATE}*.log 2>/dev/null | \
        sed 's/.*intraday[^:]*: /  /' | tail -10
else
    echo "  No manual runs today"
fi

# FnO summary
echo ""
echo "--- FnO ---"
for profile in vishal-live vishal neha; do
    local_log="${LOG_DIR}/fno_${profile}_${DATE}.log"
    if [ -f "$local_log" ]; then
        echo "  ${profile}:"
        grep -E "P&L|profit|loss|placed|SKIP" "$local_log" | \
            sed 's/.*fno[^:]*: /    /' | tail -5
    fi
done

echo ""
echo "=============================================="
echo "  Log files today:"
ls ${LOG_DIR}/*${DATE}*.log 2>/dev/null | \
    xargs -I{} basename {} | sed 's/^/  /'
echo "=============================================="
