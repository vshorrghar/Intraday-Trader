#!/bin/bash
# Wealth Builder Pro — Local Mac Runner
# Usage: ./run_local.sh [morning|midday|eod]
#
# Before running:
# 1. Get temp AWS creds from Isengard/ada
# 2. Export them:
#    export AWS_ACCESS_KEY_ID=...
#    export AWS_SECRET_ACCESS_KEY=...
#    export AWS_SESSION_TOKEN=...
# 3. Run: ./run_local.sh eod

set -e

MODE="${1:-eod}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check AWS creds are set
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo "❌ AWS credentials not set."
    echo ""
    echo "Get temp creds from Isengard, then:"
    echo "  export AWS_ACCESS_KEY_ID=..."
    echo "  export AWS_SECRET_ACCESS_KEY=..."
    echo "  export AWS_SESSION_TOKEN=..."
    echo ""
    echo "Or run without Bedrock/SES (parsers + fetchers only):"
    echo "  ./run_local.sh test"
    exit 1
fi

cd "$SCRIPT_DIR"

case "$MODE" in
    morning)
        echo "🌅 Running Morning Brief..."
        python3 scripts/run_morning_brief.py
        ;;
    midday)
        echo "📊 Running Midday Snapshot..."
        python3 scripts/run_midday_snapshot.py
        ;;
    eod)
        echo "💼 Running EOD Report..."
        python3 scripts/run_eod_report.py
        ;;
    test)
        echo "🧪 Running parsers + fetchers only (no AWS needed)..."
        python3 -c "
from parsers.groww_stocks_parser import parse_stocks_xlsx
from parsers.groww_mf_parser import parse_mf_xlsx

stocks = parse_stocks_xlsx('input/Stocks_Holdings_Statement.xlsx')
mfs = parse_mf_xlsx('input/Mutual_Funds.xlsx')

print(f'✅ Stocks: {len(stocks)} holdings parsed')
print(f'   Stocks: {len([h for h in stocks if h.holding_type==\"stock\"])}')
print(f'   ETFs:   {len([h for h in stocks if h.holding_type==\"etf\"])}')
print(f'   InvITs: {len([h for h in stocks if h.holding_type==\"invit\"])}')
print(f'✅ MFs: {len(mfs)} schemes parsed')

total_inv = sum(h.buy_value for h in stocks) + sum(h.invested_value for h in mfs)
total_cur = sum(h.groww_closing_value for h in stocks) + sum(h.current_value for h in mfs)
pnl = total_cur - total_inv
print(f'')
print(f'💰 Combined Portfolio:')
print(f'   Invested:  ₹{total_inv:,.0f}')
print(f'   Current:   ₹{total_cur:,.0f}')
print(f'   P&L:       ₹{pnl:,.0f} ({pnl/total_inv*100:.1f}%)')
"
        ;;
    *)
        echo "Usage: ./run_local.sh [morning|midday|eod|test]"
        exit 1
        ;;
esac

echo ""
echo "✅ Done! Check output/ for generated reports."
