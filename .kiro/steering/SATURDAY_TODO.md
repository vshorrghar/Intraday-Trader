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

## Priority 0 (CRITICAL) — Systemic LONG-only audit

May 20 EOD discovered THREE places where code assumed LONG-only direction:

1. intraday/executor.py record dict (FIXED commit 5131cd6)
2. intraday/monitor.py _trade_direction (FIXED commit 5131cd6 + defensive warning)
3. scripts/_status_lib.py fetch_trades query (FIXED commit XXXXX May 20 night)

Saturday TASK 1A: grep entire codebase for similar patterns:

  grep -rn "action = 'BUY'\|action == 'BUY'\|action == "BUY"\|direction = 'LONG'\|direction == 'LONG'" \
    --include="*.py" --include="*.sql" --include="*.sh" .

Any matches: review, decide if SHORT path is handled.

Also audit places that compute P&L:
  buy_price - sell_price       (LONG correct, SHORT wrong)
  exit_price - entry_price     (LONG correct, SHORT inverted)

Look for missing direction-aware math.

This systemic blind spot has produced 3 bugs in 6 days.
Could be 5-10 more places hiding.


---

## UPDATE 2026-05-21 EOD

Bug B fired in production today (HFCL phantom SHORT).
Saturday plan REORDERED — Bug B fix moved to TONIGHT (Thursday May 21 evening).

### Tonight (Thursday May 21 evening, after this doc update)
P0: Fix Bug B variants in intraday/monitor.py
- B-target: cancel SL when target hits
- B-force: cancel SL on force exit
- B-trailing: modify Dhan SL order on trailing SL move (not just memory)
Test on paper end-to-end.
Commit + push.

### Saturday May 24 (revised scope)
P0 (if not finished tonight): finish any remaining Bug B work
P1: Build EOD reconciliation script (scripts/eod_reconcile.py)
- Compare Dhan truth to DB nightly
- Telegram alert if drift > Rs.5 OR orphan orders detected
- Cron at 15:35 IST after market close
P2: Fix other intraday bugs:
- Force-exit-lies (record P&L only after verifying TRADED status)
- Cross-process token (refresh auth at start of every monitor cycle)
P3 (deferred): Swing module rebuild
P4 (deferred): F&O cleanup (Bedrock to Sonnet, rate-limit backoff, MTM fake P&L)

### NOT for this weekend
- Audit dashboard (defer to next weekend)
- Capital scaling discussions
- Telegram trade alerts wiring (only EOD recon alerts)
