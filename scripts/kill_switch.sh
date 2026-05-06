#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# KILL SWITCH — Stop all trades immediately
#
# Usage:
#   bash scripts/kill_switch.sh              # Stop all profiles
#   bash scripts/kill_switch.sh vishal       # Stop vishal only
#   bash scripts/kill_switch.sh neha         # Stop neha only
#
# What it does:
#   1. Creates a KILL file that the monitoring loop checks every cycle
#   2. Kills any running trading processes
#   3. Logs the kill event
#
# To resume trading after a kill:
#   bash scripts/resume_trading.sh
# ═══════════════════════════════════════════════════════════════

KEY="$HOME/Downloads/wealth-builder-pro.pem"
EC2="ec2-user@13.206.144.6"
SSH="ssh -i $KEY -o ConnectTimeout=15 -o StrictHostKeyChecking=no $EC2"
PROFILE="${1:-all}"

echo ""
echo "🚨 KILL SWITCH ACTIVATED"
echo "   Profile: ${PROFILE}"
echo "   Time: $(date)"
echo ""

$SSH "
cd ~/dev-sandbox

# Create kill file (monitoring loop checks this)
if [ '$PROFILE' = 'all' ]; then
    touch logs/.KILL_ALL
    echo 'KILL ALL at $(date)' >> logs/.KILL_ALL
    echo '  ✅ Kill file created: logs/.KILL_ALL'
else
    touch logs/.KILL_$PROFILE
    echo 'KILL $PROFILE at $(date)' >> logs/.KILL_$PROFILE
    echo '  ✅ Kill file created: logs/.KILL_$PROFILE'
fi

# Kill running trading processes
echo '  🔪 Killing running processes...'
pkill -f 'run_intraday.py.*--profile $PROFILE' 2>/dev/null && echo '    Killed intraday' || echo '    No intraday running'
pkill -f 'run_fno.py.*--profile $PROFILE' 2>/dev/null && echo '    Killed fno' || echo '    No fno running'

if [ '$PROFILE' = 'all' ]; then
    pkill -f 'run_intraday.py' 2>/dev/null && echo '    Killed all intraday' || true
    pkill -f 'run_fno.py' 2>/dev/null && echo '    Killed all fno' || true
fi

# Remove lock files so nothing restarts
rm -f logs/.intraday_*.lock logs/.fno_*.lock
echo '  ✅ Lock files cleared'

# Log the kill
echo \"\$(date): KILL SWITCH activated for $PROFILE\" >> logs/kill_switch.log
echo ''
echo '🛑 ALL TRADING STOPPED'
echo '   To resume: bash scripts/resume_trading.sh'
"
