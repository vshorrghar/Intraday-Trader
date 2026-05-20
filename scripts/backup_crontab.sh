#!/bin/bash
# Daily crontab backup with verification + auto-prune
# Reason: crontab wiped twice this week (May 18, May 20) — defense in depth

set -euo pipefail

BACKUP_DIR="$HOME/.crontab_backups"
mkdir -p "$BACKUP_DIR"

BACKUP="$BACKUP_DIR/crontab_$(date +%Y%m%d_%H%M%S).txt"

# Capture current crontab
crontab -l > "$BACKUP" 2>/dev/null || true

# Verify backup is non-empty
if [ ! -s "$BACKUP" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') WARN: backup empty — crontab may already be wiped" >&2
    exit 1
fi

LINES=$(wc -l < "$BACKUP")
echo "$(date '+%Y-%m-%d %H:%M:%S') OK: backed up $LINES lines to $BACKUP"

# Also update canonical (always points to latest known-good state)
cp "$BACKUP" /home/ec2-user/dev-sandbox/scripts/crontab.canonical

# Prune backups older than 30 days
find "$BACKUP_DIR" -name "crontab_*.txt" -mtime +30 -delete 2>/dev/null || true

# Show summary
COUNT=$(ls -1 "$BACKUP_DIR"/crontab_*.txt 2>/dev/null | wc -l)
echo "$(date '+%Y-%m-%d %H:%M:%S') Total backups retained: $COUNT (max 30 days)"
