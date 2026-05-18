#!/bin/bash
cd /home/ec2-user/dev-sandbox
echo "=== Backtest v1.2 Status ==="
echo "Time: $(date)"

PID=$(cat logs/backtest_v1.2.pid 2>/dev/null)

if [ -n "$PID" ] && ps -p $PID > /dev/null 2>&1; then
    echo "STATUS: RUNNING (PID: $PID)"
    echo "LLM cache: $(ls cache/backtest_llm/ 2>/dev/null | wc -l)/16"
    echo ""
    echo "Last 25 log lines:"
    tail -25 logs/backtest_v1.2_run.log
else
    echo "STATUS: COMPLETED OR DIED"
    echo "LLM cache: $(ls cache/backtest_llm/ 2>/dev/null | wc -l)/16"
    LATEST=$(ls -t backtest/results/backtest_v1_*.json 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        echo "Result: $LATEST ($(stat -c %s "$LATEST") bytes)"
        .venv/bin/python3 -c "
import json
data = json.load(open('$LATEST'))
print(f'Universe: {data.get(\"universe_size\", \"unknown\")}')
print(f'Days: {len(data.get(\"selected_days\", []))}')
for prof in data.get('results', data.get('profiles', [])):
    name = prof.get('profile')
    days = prof.get('days', [])
    total = sum(d.get('total_net_pnl', 0) for d in days)
    trades = sum(d.get('trades_placed', 0) for d in days)
    wins = sum(d.get('winners', 0) for d in days)
    wr = (wins/trades*100) if trades else 0
    print(f'  {name}: {trades} trades, Rs.{total:.2f}, {wr:.1f}% win')
"
    else
        echo "ERROR: No result file"
        tail -40 logs/backtest_v1.2_run.log
    fi
fi
