#!/bin/bash
# Setup cron jobs for auto-trader on EC2
# Run ONCE on EC2: bash scripts/setup_cron.sh

set -e

echo "🔧 Setting up auto-trader cron jobs..."

# Install cron if missing
if ! command -v crontab &> /dev/null; then
    echo "  📦 Installing cronie..."
    sudo yum install -y cronie
    sudo systemctl enable crond
    sudo systemctl start crond
    echo "  ✅ Cronie installed"
fi

# Create output dir
mkdir -p ~/wealth-builder-pro/output/trades

# Set cron jobs
# 9:15 AM IST = 3:45 AM UTC — morning pick
# 3:45 PM IST = 10:15 AM UTC — EOD check
cat << 'CRON' | crontab -
# Auto-trader: morning pick at 9:15 AM IST (weekdays only)
45 3 * * 1-5 cd /home/ec2-user/wealth-builder-pro && /home/ec2-user/wealth-builder-pro/venv/bin/python3 -m llm.auto_trader >> /home/ec2-user/wealth-builder-pro/output/trades/cron.log 2>&1

# Auto-trader: EOD check at 3:45 PM IST (weekdays only)
15 10 * * 1-5 cd /home/ec2-user/wealth-builder-pro && /home/ec2-user/wealth-builder-pro/venv/bin/python3 -m llm.check_trade >> /home/ec2-user/wealth-builder-pro/output/trades/cron.log 2>&1
CRON

echo "  ✅ Cron jobs set:"
crontab -l
echo ""

# Quick test — run auto_trader now to verify it works
echo "🧪 Quick test run..."
cd ~/wealth-builder-pro
source venv/bin/activate
python3 -m llm.auto_trader

echo ""
echo "✅ Setup complete! Cron will run automatically:"
echo "   9:15 AM IST — Pick intraday stock (dry run)"
echo "   3:45 PM IST — Check if pick was a win/loss"
echo ""
echo "To check results anytime:"
echo "   cat ~/wealth-builder-pro/output/trades/cron.log"
