# V3 Intraday — Next Session: wire the exit monitor cron

STATUS as of 2026-10-14:
- V3 entry (orchestrator) + exit (intraday/v3/monitor.py) BOTH work. Proven live-paper.
- First closed trade: ICICIPRULI +132.59 (vishal-s3), via run_v3_monitor.
- Monitor is NOT yet cronned — positions only close when run manually.

ONE JOB NEXT SESSION: add monitor cron (vishal-s3 PAPER only).

Do it SAFELY (crontab was wiped twice before — May 18/20):
  1. bash scripts/safe_crontab_edit.sh   # backs up first; OR:
  2. crontab -l > /tmp/cron_bk_$(date +%s).txt   # manual backup, verify non-empty
  3. Add these two lines:

# V3 intraday exit monitor — every 15 min during market (9:30-15:00 IST = 4:00-9:30 UTC)
*/15 4-9 * * 1-5 cd /home/ec2-user/dev-sandbox && .venv/bin/python -c "from intraday.v3.monitor import run_v3_monitor; print(run_v3_monitor('vishal-s3', dry_run=False))" >> logs/cron_s3_monitor.log 2>&1
# V3 force-exit at 15:15 IST (09:45 UTC)
45 9 * * 1-5 cd /home/ec2-user/dev-sandbox && .venv/bin/python -c "from intraday.v3.monitor import run_v3_monitor; print(run_v3_monitor('vishal-s3', dry_run=False))" >> logs/cron_s3_monitor.log 2>&1

  4. Verify: crontab -l | grep s3_monitor   (expect 2 lines)
  5. Watch logs/cron_s3_monitor.log next market day for HOLD/EXIT lines.

GOTCHAS:
- Monitor shares client_id 1110941563 (rate-limited). The */15 entry cron also
  fetches LTP — stagger if 429s get bad (monitor at :07/:22/:37/:52 e.g.).
- PAPER ONLY. Do NOT add --live or wire to vishal-live-v2 until many clean days.
- JSWENERGY + KPITTECH are OPEN now; they'll close once this cron runs (or run
  the monitor manually before then).

OPEN POSITIONS awaiting exit (as of 2026-10-14):
  JSWENERGY  ORB_V4  entry 474.85  T 490.27  SL 467.14
  KPITTECH   ORB_V4  entry 529.20  T 545.44  SL 521.08  (close to SL)
