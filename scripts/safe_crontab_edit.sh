#!/bin/bash
set -euo pipefail

# safe_crontab_edit.sh — Defensive crontab editor
# Prevents accidental wipes (May 18, May 20 incidents)
# Usage: bash scripts/safe_crontab_edit.sh

if [ -d /var/backups ] && [ -w /var/backups ]; then
    BACKUP_DIR=/var/backups
else
    BACKUP_DIR=~/.crontab_backups
    mkdir -p "$BACKUP_DIR"
fi
BACKUP="$BACKUP_DIR/crontab_$(date +%Y%m%d_%H%M%S).txt"

crontab -l > "$BACKUP" 2>/dev/null || true

if [ ! -s "$BACKUP" ]; then
    echo "ERROR: Crontab backup is empty."
    echo "If crontab is currently empty, restore from canonical:"
    echo "  crontab scripts/crontab.canonical"
    exit 1
fi

LINES_BEFORE=$(wc -l < "$BACKUP")
echo "✅ Backup saved: $BACKUP ($LINES_BEFORE lines)"

cp "$BACKUP" /tmp/cron_edit.txt
${EDITOR:-vim} /tmp/cron_edit.txt

if [ ! -s /tmp/cron_edit.txt ]; then
    echo "ERROR: Edit produced empty file. Refusing to install."
    echo "Original preserved: $BACKUP"
    exit 1
fi

LINES_AFTER=$(wc -l < /tmp/cron_edit.txt)

if ! grep -q "run_daily.sh" /tmp/cron_edit.txt; then
    echo "WARNING: Crontab does not contain run_daily.sh — strange."
    read -p "Install anyway? (y/N): " confirm
    [ "$confirm" != "y" ] && exit 1
fi

echo ""
echo "=== DIFF ==="
diff "$BACKUP" /tmp/cron_edit.txt || true
echo ""
echo "Lines: $LINES_BEFORE -> $LINES_AFTER"
read -p "Install? (y/N): " confirm
[ "$confirm" != "y" ] && { echo "Aborted. Backup preserved: $BACKUP"; exit 1; }

crontab /tmp/cron_edit.txt
echo "✅ Installed. New crontab: $LINES_AFTER lines."
echo "Backup: $BACKUP"
