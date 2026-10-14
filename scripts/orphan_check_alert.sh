#!/bin/bash
# Orphan-check alert wrapper.
# Runs the read-only orphan-SL detector and sends a Telegram alert when it
# finds an orphan (exit 2) or cannot verify the account (exit 1). On a clean
# run (exit 0) it stays silent. The detector itself never trades; this wrapper
# only reads its exit code and notifies.
#
# Usage (cron): bash scripts/orphan_check_alert.sh [PROFILE]
set -uo pipefail

cd /home/ec2-user/dev-sandbox || exit 3
PROFILE="${1:-vishal-live-v2}"
PY=.venv/bin/python

# Run detector, capture output + exit code (do NOT let set -e abort on 1/2).
OUT="$("$PY" scripts/check_orphan_orders.py "$PROFILE" 2>&1)"
CODE=$?

echo "$OUT"  # still goes to the cron log via redirection

if [ "$CODE" -eq 0 ]; then
    exit 0  # clean, no alert
fi

# Build an alert message by exit code.
if [ "$CODE" -eq 2 ]; then
    HEADER="\xF0\x9F\x9A\xA8 ORPHAN ORDER on ${PROFILE}"
elif [ "$CODE" -eq 1 ]; then
    HEADER="\xE2\x9A\xA0\xEF\xB8\x8F Orphan check COULD NOT VERIFY ${PROFILE} (auth/data fail)"
else
    HEADER="\xE2\x9A\xA0\xEF\xB8\x8F Orphan check error (exit ${CODE}) on ${PROFILE}"
fi

# Send via the existing telegram module (respects enabled flag; silent if off).
"$PY" - "$HEADER" "$OUT" <<'PYEOF'
import sys
sys.path.insert(0, "/home/ec2-user/dev-sandbox")
try:
    from alerts.telegram import _is_enabled, _get_creds, send_alert
    if _is_enabled():
        token, chat_id = _get_creds()
        header, body = sys.argv[1], sys.argv[2]
        send_alert(token, chat_id, f"{header}\n\n{body[:600]}")
        print("[alert] telegram sent")
    else:
        print("[alert] telegram disabled in config — not sent")
except Exception as e:
    print(f"[alert] telegram send failed: {e}")
PYEOF

exit "$CODE"
