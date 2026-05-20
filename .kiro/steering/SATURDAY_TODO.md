# SATURDAY 2026-05-24 — DEDICATED SESSION

## Priority 1: Swing Module Rebuild (1-2 hours)

run_swing.py is placeholder skeleton. Real code exists in swing/*.py 
but never called. DB schema missing columns.

Tasks:
a. Fix swing_trades DB schema — add action, target_price, stop_loss_price, confidence_score, strategy_type, rationale
b. Read function signatures of all swing modules
c. Rewrite run_swing.py to call scanner -> selector -> executor -> monitor -> dashboard
d. End-to-end test: paper SHORT/LONG picks, dashboard updates, DB rows
e. Add cron entries via scripts/safe_crontab_edit.sh:
   - 0 11 * * 1-5 daily swing scan
   - 30 4-9 * * 1-5 hourly swing monitor
f. PAPER ONLY — no --live flag

Definition of Done: real swing pick visible in dashboard within 1 cron cycle.

## Priority 2: F&O Cleanup (30 min)

Three issues to fix:
a. F&O config: switch Bedrock from Opus 4-7 to Sonnet 4.6
   grep -rn "claude-opus\|bedrock_model" fno/ config/
b. Add rate-limit backoff to dhan_broker.get_option_chain (sleep 2s between indices)
c. Fix MTM cron fake P&L (scripts/fno_mtm_run.py) — mark STALE instead of zero LTPs

## Priority 3: Daily Audit Dashboard (deferred from May 20)

Original Task 3 from May 20 prompt:
- scripts/build_daily_audit.py merging DB + Dhan + logs
- dashboard/v2/audit.html per-day what-went-right/wrong view
- 4:00 PM IST cron after EOD
- Backfill May 12-20

## Priority 4: F&O Fate Decision

After fixes, evaluate 5 days clean F&O paper P&L.
Iron Condor edge? -> keep + Rs.499/mo subscription justified.
No edge? -> kill F&O, save Rs.499/mo.

## NOT for this Saturday (later)
- Positional module
- Backtest expansion (50+ stock universe)
- Telegram trade alerts
- Capital scaling decisions
