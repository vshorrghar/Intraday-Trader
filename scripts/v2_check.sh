#!/bin/bash
cd ~/dev-sandbox
TODAY=$(date +%Y-%m-%d)
LOG="logs/intraday_vishal-live-v2_$TODAY.log"

echo "=== V2 STATUS — $TODAY ==="
echo ""
echo "Last cron sessions:"
grep "session=" "$LOG" 2>/dev/null | tail -5

echo ""
echo "V6 signals & decisions:"
grep -E "V6=|signals|SIGNAL|placed|market:" "$LOG" 2>/dev/null | tail -10

echo ""
echo "Errors today:"
grep -E "ERROR|FAIL" "$LOG" 2>/dev/null | tail -5

echo ""
echo "Trades in DB:"
sqlite3 database/vishal-live-v2.db "SELECT trade_date, symbol, strategy_type, entry_price, exit_price, pnl, status FROM intraday_trades WHERE trade_date='$TODAY';" 2>/dev/null

echo ""
echo "All-time V2 stats:"
sqlite3 database/vishal-live-v2.db "SELECT COUNT(*) as trades, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, ROUND(SUM(pnl),2) as total_pnl FROM intraday_trades;" 2>/dev/null
