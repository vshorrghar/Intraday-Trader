#!/bin/bash
# Evidence collector for SYSTEM_AUDIT_PLAN.md Stage 1
set -e
cd /home/ec2-user/dev-sandbox

DATE=$(date +%Y-%m-%d)
OUT="audit/evidence_${DATE}.txt"
mkdir -p audit
> "$OUT"

log() {
    echo "" >> "$OUT"
    echo "================================================================" >> "$OUT"
    echo "$1" >> "$OUT"
    echo "================================================================" >> "$OUT"
}

log "EVIDENCE DUMP — $DATE $(date +%H:%M:%S) IST"

log "GIT STATE"
git log --oneline -30 >> "$OUT"
echo "HEAD: $(git rev-parse HEAD)" >> "$OUT"
echo "Branch: $(git rev-parse --abbrev-ref HEAD)" >> "$OUT"
echo "Status:" >> "$OUT"
git status --short >> "$OUT"

log "REPO TREE (code only)"
find . -type f $ -name "*.py" -o -name "*.yaml" -o -name "*.md" $ \
    -not -path "*/.venv/*" -not -path "*/.git/*" \
    -not -path "*/node_modules/*" -not -path "*/dashboard/api/*" \
    -not -path "*/.kiro/*" \
    | sort >> "$OUT"

log "CRON SCHEDULE"
crontab -l 2>/dev/null >> "$OUT" || echo "(no crontab)" >> "$OUT"

for f in \
    intraday/scanner.py \
    intraday/selector.py \
    intraday/risk_manager.py \
    intraday/executor.py \
    intraday/monitor.py \
    intraday/dhan_broker.py \
    intraday/auth_server.py \
    intraday/broker_base.py \
    intraday/charges.py \
    config/profiles/vishal-live.yaml \
    config/profiles/vishal.yaml \
    scripts/check_dhan_orders.py \
    scripts/reconcile_dhan_db.py \
    scripts/sync_dhan_live.py \
    scripts/build_audit_narrative.py \
    scripts/compute_daily_pnl.py \
    scripts/validate_narrative.py
do
    if [ -f "$f" ]; then
        log "FILE: $f ($(wc -l < $f) lines)"
        cat "$f" >> "$OUT"
    else
        log "FILE: $f — NOT FOUND"
    fi
done

for f in .kiro/steering/*.md; do
    if [ -f "$f" ]; then
        log "STEERING: $f"
        cat "$f" >> "$OUT"
    fi
done

log "DB SCHEMA — vishal-live"
sqlite3 database/vishal-live.db ".schema" >> "$OUT"

log "LAST 50 TRADES — vishal-live"
sqlite3 -header -column database/vishal-live.db \
"SELECT id, trade_date, symbol, action, status, entry_price, exit_price, stop_loss_price, target_price, quantity, pnl, confidence_score, strategy_type, mode FROM intraday_trades ORDER BY id DESC LIMIT 50" >> "$OUT"

log "STATS BY STRATEGY — vishal-live"
sqlite3 -header -column database/vishal-live.db \
"SELECT strategy_type, COUNT(*) as n, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1) as win_pct, ROUND(SUM(pnl),2) as total_pnl, ROUND(AVG(pnl),2) as avg_pnl, ROUND(AVG(CASE WHEN pnl>0 THEN pnl END),2) as avg_win, ROUND(AVG(CASE WHEN pnl<0 THEN pnl END),2) as avg_loss FROM intraday_trades WHERE pnl IS NOT NULL GROUP BY strategy_type" >> "$OUT"

log "STATS BY OUTCOME — vishal-live"
sqlite3 -header -column database/vishal-live.db \
"SELECT status, COUNT(*) as n, ROUND(SUM(pnl),2) as total_pnl, ROUND(AVG(pnl),2) as avg_pnl FROM intraday_trades WHERE pnl IS NOT NULL GROUP BY status" >> "$OUT"

log "TOP 20 SYMBOLS BY FREQUENCY — vishal-live"
sqlite3 -header -column database/vishal-live.db \
"SELECT symbol, COUNT(*) as n, ROUND(AVG(entry_price),2) as avg_px, ROUND(SUM(pnl),2) as net_pnl FROM intraday_trades GROUP BY symbol ORDER BY n DESC LIMIT 20" >> "$OUT"

log "DAILY P&L LAST 14 DAYS — vishal-live"
sqlite3 -header -column database/vishal-live.db \
"SELECT trade_date, COUNT(*) as n, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, ROUND(SUM(pnl),2) as net_pnl FROM intraday_trades WHERE pnl IS NOT NULL AND trade_date >= date('now','-14 days') GROUP BY trade_date ORDER BY trade_date DESC" >> "$OUT"

for prof in vishal neha; do
    if [ -f "database/${prof}.db" ]; then
        log "PAPER STATS — $prof (last 50 trades)"
        sqlite3 -header -column "database/${prof}.db" \
        "SELECT id, trade_date, symbol, action, status, entry_price, exit_price, stop_loss_price, target_price, quantity, pnl, confidence_score, strategy_type FROM intraday_trades ORDER BY id DESC LIMIT 50" >> "$OUT"

        log "PAPER AGGREGATE — $prof"
        sqlite3 -header -column "database/${prof}.db" \
        "SELECT COUNT(*) as total, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, ROUND(100.0*SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END)/COUNT(*),1) as win_pct, ROUND(SUM(pnl),2) as total_pnl, ROUND(AVG(CASE WHEN pnl>0 THEN pnl END),2) as avg_win, ROUND(AVG(CASE WHEN pnl<0 THEN pnl END),2) as avg_loss FROM intraday_trades WHERE pnl IS NOT NULL" >> "$OUT"
    fi
done

log "BEDROCK COST LOG"
[ -f logs/bedrock_costs.log ] && cat logs/bedrock_costs.log >> "$OUT"

log "RECENT EXECUTOR LOGS — vishal-live (last 200 lines per day)"
for f in $(ls -t logs/intraday_vishal-live_*.log 2>/dev/null | head -3); do
    echo "" >> "$OUT"
    echo "--- $f ---" >> "$OUT"
    tail -200 "$f" >> "$OUT"
done

log "DAILY PNL BACKFILL — sample"
for prof in vishal-live vishal neha; do
    f="dashboard/api/v2/${prof}/daily_pnl/2026-05-21.json"
    if [ -f "$f" ]; then
        echo "" >> "$OUT"
        echo "--- $f ---" >> "$OUT"
        cat "$f" >> "$OUT"
    fi
done

log "DONE"
echo "" >> "$OUT"
echo "Lines: $(wc -l < $OUT)" >> "$OUT"
echo "Bytes: $(wc -c < $OUT)" >> "$OUT"

echo "Evidence dump complete: $OUT"
echo "Lines: $(wc -l < $OUT)"
echo "Size: $(du -h $OUT | cut -f1)"
