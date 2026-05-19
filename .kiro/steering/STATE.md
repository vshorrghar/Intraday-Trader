# STATE.md — Current Project State

**Last Updated**: 2026-05-18, ~13:30 CET (post-duplicate-order-bug discovery)
**Update Protocol**: Replace TODAY section at end of each session.

---

**Last Updated**: 2026-05-19 EOD - duplicate order ROOT CAUSE FOUND + FIXED
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-19) - DUPLICATE ORDER BUG ROOT CAUSE FOUND + FIXED

### THE FIX - Commit a2e5d66

One-line indent fix in intraday/executor.py line 198.

Before: return None at 12-space indent (sibling of if filled_qty == 0)
After: return None at 16-space indent (child of if filled_qty == 0)

The function was returning None unconditionally after MARKET retry block,
regardless of whether the retry succeeded.

### Root Cause (hidden for weeks)

When LIMIT order rejected (tick size error 16283) AND confidence >= 8:
- Code retries with MARKET order
- MARKET retry succeeds, fills on Dhan
- BUT function returns None immediately after retry
- SL order never placed
- DB row never written
- Trailing SL monitor never starts

### Today's Evidence (INFY trifecta)

| Time | Action | Filled on Dhan | Recorded in DB | SL Placed |
|------|--------|----------------|----------------|-----------|
| 09:30:21 | INFY MARKET retry | 3 shares | NO | NO |
| 10:30:22 | INFY MARKET retry | 2 shares | NO | NO |
| 10:45:17 | INFY LIMIT (filled first try) | 2 shares | YES (id=26) | YES (qty=2) |

Net result on Dhan: 7 INFY shares LONG.
Net result in our DB: 1 row, qty=2.
SL coverage: 2 of 7 shares (5 unprotected).

### What This Single Bug Explains

- May 18 TATASTEEL 4x duplication - MARKET retry fired 3 extra times
- May 18 BANDHAN, MOTHERSON, CANBK 2x - same pattern
- May 18 ETERNAL phantom - MARKET retry filled, no DB record
- May 19 INFY 3.5x - same pattern, three sessions
- Bug 5b counter failures - counter reads from DB, but DB rows missing
- Same-symbol block failures - block reads from DB, no rows to see
- DB-vs-Dhan P&L drift (14x off May 18) - half of trades not in our DB

ONE INDENT. SEVEN VISIBLE BUGS.

### Today's Real Money P&L (Dhan truth)

Per dhan_live.json @ 14:32 IST:
- INFY: 7 shares LONG @ Rs.1192.73 (unrealized -Rs.10 mid-session)
- COHANCE: 9 shares SHORT - unrealized +Rs.250
- ADANIGREEN: 1 share LONG @ Rs.1423 (unrealized -Rs.36, phantom trade)
- IOC: closed +Rs.5.76 realized
- Total at 14:32 IST: +Rs.105.61
- Daily realized loss: -Rs.98.19

### Tomorrow Morning Validation

Required before 9:30 AM IST cron fires:
1. git log --oneline -3 shows a2e5d66 at HEAD on BOTH EC2s
2. Line 198 of executor.py shows 16-space indent
3. EC2-NEW pulled the fix
4. validate_tomorrow.sh runs morning checkpoint

### Real Money Trading Status (END OF DAY)

| Profile | Status | Reason |
|---------|--------|--------|
| vishal-live | LIVE (cron active) | Bug fixed for tomorrow |
| neha-live | STOPPED | Decision pending |
| vishal paper | active | DryRun broker |
| neha paper | active | DryRun broker |

### Next Session Priorities

1. Verify cron fires correctly Wednesday morning with patched code
2. Run validate_tomorrow.sh at 9:35 / 11:00 / 15:30 IST
3. EOD Wednesday: pull dhan_live.json, verify DB matches
4. If 5/5 PASS for 3 days: consider re-enabling neha-live cron
5. Then build dashboard improvements (Kiro)
6. Then build Telegram bot

### Don't Touch (working)

- intraday/executor.py (just fixed)
- intraday/auth_server.py (May 18 fix)
- config/profile.py (May 18 fix)
- fno/pnl_calculator.py (May 18 fix)
- scripts/fno_mtm_run.py (May 18 fix)
- scripts/sync_dhan_live.py (built today)
- scripts/check_dhan_orders.py (validation diagnostic)
- scripts/validate_tomorrow.sh (validation orchestrator)

---

## PREVIOUS SESSION (2026-05-19 morning) - CONTEXT AUTOMATION + SSM WORKFLOW DECIDED


### Session Outcome
- Discovered Dhan optionchain code had 3 spec bugs (client-id header, securityId, payload format)
- Patched all 3 per official Dhan v2 docs
- Discovered root cause of HTTP 401: Data API not subscribed (paid add-on Rs.499/month)
- F&O segment activated on Dhan account (client_id 1110941563)
- Data API subscribed Rs.499/month — pre-flight test confirmed 470 strikes returning real data
- Built backtest engine v0.1 (data loader + scanner replay) using Dhan historical OHLC API
- Verified F&O Monday cron path end-to-end (auth + chain fetch + MTM)

### Commits Today (newest first)
- 562030d — feat: backtest engine v0.1 — Dhan historical OHLC + scanner replay
- b714f1d — docs: capture Bug T sub-bugs (T-1/T-2/T-3) + neha-live password fix
- 4ada2c4 — docs: sync STRATEGY active bugs + RULES cron schedule
- 4867ef0 — fix: Bug T-1/T-2/T-3 sub-bugs (cron, paper auth, force_exit)
- 2584676 — fix: neha-live password + login mapping

### What Was Built
**intraday/dhan_broker.py:**
- `get_historical_ohlc()` method — Dhan /v2/charts/intraday endpoint
- Verified: 750 candles for TCS over 11 trading days

**backtest/ (NEW MODULE):**
- `data_loader.py` — fetch + cache historical OHLC (200ms rate limit, 5-min/1-min/15-min/60-min candles)
- `scanner_replay.py` — replay scanner v3 scoring on past data using 9:30 AM snapshot
- `results/` — JSON output per backtest run
- Nifty 50 universe hardcoded (50 symbol→securityId mappings)

### Backtest v0.1 — HONEST SCOPE LIMITATIONS
First test run: 5 stocks (TCS, INFY, HDFCBANK, RELIANCE, ICICIBANK), 4 trading days
Result reported by Kiro: "75% avg hit rate"

**Reality check on the 75% number:**
- Test universe was only 5 stocks
- "Hit rate" comparison fell back to comparing scanner picks vs EOD performers OF THE SAME 5 STOCKS
- daily_top_performers DB lookup failed (table empty for those dates)
- With 5 stocks picking 5 longs, overlap with top performers is trivial
- **Do NOT quote 75% as scanner accuracy. It's noise on a small universe.**

**What backtest CAN tell us right now:**
- Code path works end-to-end (auth → fetch → score → compare → save)
- Historical data structure is correct
- Scoring logic loads without errors

**What backtest CANNOT tell us yet:**
- Real scanner accuracy (need 50+ stock universe)
- Sector rotation impact (signal omitted — needs sector indices)
- 52w high/low impact (signal omitted — needs daily candles)
- Time-of-day variations (hardcoded 1.5x multiplier)

### Bug T Status — CODE FIXED + DATA API LIVE
- 6b8de75 (May 15) — original Bug T fix
- 4867ef0 (May 17) — sub-bugs T-1, T-2, T-3
- Tonight — Dhan v2 spec compliance (client-id, UnderlyingScrip ints, expirylist, response parsing)
- Pre-flight test verified: NIFTY chain returns 470 strikes with spot=23643.5 even off-hours
- Monday F&O paper WILL use real Dhan option chain prices

### Data API Subscription Coverage
| Profiles | client_id | Data API |
|----------|-----------|----------|
| vishal + vishal-live | 1110941563 | ✅ Subscribed Rs.499/mo |
| neha + neha-live | 1111523334 | ❌ NOT subscribed |

Decision pending: separate subscription for neha account (Rs.499/mo more) OR accept synthetic data on neha profiles.

### F&O Monday Verification (no code changes, just verification)
- Auth path: ✅ DhanBrokerClient instantiates correctly
- Option chain: ✅ 470 strikes returned with real spot price
- MTM run: ✅ executes (0 updated = correct, no open strategies after May 15 cleanup)
- Crontab entries verified:
  - 50 3 * * 1-5 — vishal F&O daily (9:20 AM IST)
  - 52 3 * * 1-5 — neha F&O daily (9:22 AM IST)
  - 54 3 * * 1-5 — vishal-live F&O daily paper (9:24 AM IST)
  - */30 4-9 * * 1-5 — F&O MTM updates every 30 min

### Caveat: scripts/fno_mtm_run.py standalone fails
Running `python scripts/fno_mtm_run.py` directly fails with `ModuleNotFoundError: No module named 'fno'`.
The cron wrapper `scripts/fno_mtm_update.sh` does `cd ~/dev-sandbox` first, so cron will work.
Just don't run the .py file directly without cd to project root.

---

## PREVIOUS SESSION (2026-05-17) — BUG T SUB-BUGS + NEHA-LIVE PASSWORD

### Session Outcome
- Bug T fix from May 15 had 3 sub-bugs found by Kiro on May 16-17
- T-1: MTM cron replaced broken one-liner with scripts/fno_mtm_run.py
- T-2: Paper mode now auths real Dhan broker for option chain fetch
- T-3: force_exit_all computes current_premium instead of passing 0
- neha-live dashboard password + login mapping fixed
- Pillar docs synced (STRATEGY active bugs + RULES cron schedule)

### Commits Today (newest first)
- 4ada2c4 — docs: sync STRATEGY active bugs + RULES cron schedule
- 4867ef0 — fix: Bug T-1/T-2/T-3 sub-bugs (May 17, 14:55 IST)
- 2584676 — fix: neha-live password + login mapping (May 16, 21:38 IST)

### Bug T Status — NOW PROPERLY FIXED
Original Bug T fix on May 15 (commit 6b8de75) had 3 holes:
- T-1: cron one-liner broken — wrapper script created
- T-2: paper mode skipped Dhan auth — option chain returned nothing
- T-3: force_exit passed current_premium=0 — synthetic P&L on exits

All 3 patched in commit 4867ef0. Now needs full Monday May 18 validation.

### Pillar Doc Sync (commit 4ada2c4)
- STRATEGY.md: ACTIVE BUGS table updated (removed EE/FF/GG/SHORT-RR/SCANNER as fixed; added Recently Fixed log)
- STRATEGY.md: NEXT TO BUILD updated (Monday validation list, current week tasks)
- RULES.md: Section 6 cron schedule now includes F&O MTM + neha-live S3 syncs

---

## PREVIOUS SESSION (2026-05-15) — TRIPLE-STREAM SESSION

### Session Outcome
- Stream 1: Scanner v3 bugfixes (Bugs 1, 2, 3 from Day 1 production)
- Stream 2: F&O Bug T fix — real Dhan price paper trading
- Stream 3: Bug 6 fix — neha-live data visibility from OLD EC2 (DB + dashboard sync via S3)
- Stream 4: 4 new steering docs added
- Bug 5 discovered EOD: max_trades_per_day not enforced (real cost ~Rs.220 today)

### Commits Today (newest first)
- 6b8de75 — feat: Bug T fix — F&O real-price MTM + exit triggers + option chain cache
- 5d79c29 — docs: add FNO_STRATEGY.md
- 3f3fdbe — docs: add BUSINESS_DOC + TECHNICAL_DOC + GLOSSARY to steering/
- 7777382 — feat: live_status + eod_summary scripts + Bug 5 status fix + Bug 6 neha-live sync
- abb236e — fix: Bug 6 - sync neha-live.db OLD<->NEW via S3
- a0ec15e — fix: buffered limit (+0.3% tick-aligned) + MARKET fallback for conf>=8 (Bug 3)
- 68e910c — fix: NSE losers endpoint dead — use SecLwr20 from gainers (Bug 2)
- a9df59b — fix: momentum-aware volume filter (Bug 1)

### Real Money Trades This Week
| Date | Profile | Stock | Direction | Net P&L |
|------|---------|-------|-----------|---------|
| May 12 | vishal-live | ONGC LONG | -Rs.53.80 |
| May 12 | vishal-live | WIPRO SHORT | -Rs.20.00 |
| May 13 | vishal-live | HINDZINC LONG | -Rs.28.30 |
| May 14 | vishal-live | VEDL x10 @ 334.30 | TBD |
| May 14 | neha-live | SAIL x19 @ 206.42 | -Rs.63 |
| May 15 | vishal-live | INFY x4 @ 1124.10 | TBD (open EOD) |
| May 15 | vishal-live | HDFCBANK x5 @ 779.90 | TBD (open EOD) |
| May 15 | vishal-live | SAREGAMA x10 @ 411.90 | NEVER FILLED — Bug 3 |

Cumulative: ~-Rs.165 closed + Bug 5 cost ~Rs.220 today

---

## STREAM 1: SCANNER/EXECUTOR BUGS — FIXED

### Bug 1 (CRITICAL): Scanner saw only 169/500 stocks — a9df59b
- Root: 500K volume filter rejected stocks at 9:30 AM
- Fix: Pass if change_pct >= 4% AND volume >= 100K
- File: intraday/scanner.py

### Bug 2 (HIGH): NSE losers API dead — 68e910c
- Root: ?index=losers returns "Missing index or key."
- Fix: Use SecLwr20 from gainers response
- File: fetchers/nse_market_movers.py
- Verified: 20 losers (NOIDATOLL 16.55% sample)

### Bug 3 (HIGH): Limit orders fail on fast movers — a0ec15e
- Root: SAREGAMA limit at LTP did not fill in 10s
- Fix: +0.3% buffer (1.003x LONG, 0.997x SHORT) + tick-align + MARKET fallback if conf>=8
- File: intraday/executor.py

### Bug 4: NOT A BUG (cron just hadnt fired)

### Bug 5 (CRITICAL — DISCOVERED EOD): max_trades_per_day bypassed
- Root: _restore_daily_state only counted CLOSED trades. OPEN didnt count.
- Effect: Continuous scan saw "0 trades placed" -> bypassed daily limit
- Real cost: vishal-live placed 7 trades (limit 3). Lost ~Rs.223.
- Fix: Counts all BUY except REJECTED/CANCELLED/FAILED/ABANDONED/PENDING
- File: intraday/risk_manager.py
- Status: Fixed in code, needs Monday validation

---

## STREAM 2: F&O BUG T FIX — REAL DHAN PRICES

### Built (commit 6b8de75)

**fno/option_chain_cache.py** (NEW)
- 5-min TTL cache shared across profiles
- Cache: cache/option_chain__.json
- 2-sec rate limiting
- Graceful failure

**fno/pnl_calculator.py** (NEW)
- Pure logic, accepts get_chain_func callable (data-source agnostic)
- compute_leg_pnl(), compute_strategy_pnl(), update_strategy_pnl_in_db()
- SELL: (entry - current) * qty | BUY: (current - entry) * qty

**fno/monitor.py** (MODIFIED)
- Added update_all_open_strategies(profile)
- Exit triggers per strategy:
  - IRON_CONDOR: 50% max profit OR 1.5x max loss OR <=1 day expiry
  - SHORT_STRADDLE/STRANGLE: 30% credit OR 2x credit loss OR expiry day 3 PM
  - BULL_PUT/BEAR_CALL_SPREAD: 70% credit OR full loss OR <=2 days expiry
  - DIRECTIONAL_*: 50% gain trail OR 30% loss OR before 2 PM if no movement

**DB changes (all 4 DBs)**
- Added current_price column to fno_trades
- Marked 84 stale open trades CLOSED (synthetic):
  - vishal: 48 | neha: 24 | vishal-live: 12 | neha-live: 0

**Cron added (OLD EC2 only)**
*/30 4-9 * * 1-5 update_all_open_strategies for vishal-live, vishal, neha

### Validation BLOCKED until Monday
- Dhan optionchain returned HTTP 401 + 404 fallback (after-hours)
- Dhan auth itself works (positions API returned 4 items)
- Likely: optionchain only available 9:15 AM - 3:30 PM IST
- First real test: Monday May 18 morning

---

## STREAM 3: BUG 6 FIX — NEHA-LIVE VISIBILITY

### Built on NEW EC2

**scripts/sync_neha_live_db.sh**
- Pushes database/neha-live.db -> s3://.../db-sync/neha-live.db
- Cron: */15 4-10 * * 1-5

**scripts/sync_neha_live_dashboard.sh**
- Syncs dashboard/api/neha-live/ -> s3://.../api/neha-live/
- Cron: */15 4-10 * * 1-5

### S3 Architecture
- OLD EC2 sync: aws s3 sync dashboard/ ... --exclude "db-sync/*" (preserves NEW EC2 DB)
- NEW EC2: pushes neha-live DB + dashboard JSON every 15 min
- Verified: /api/neha-live/intraday_latest.json returns 200 OK

### Pending: Dashboard neha-live tab missing in UI nav (HTML update)

---

## STREAM 4: STEERING DOCS EXPANSION

| File | Status |
|------|--------|
| BUSINESS_DOC.md | NEW |
| TECHNICAL_DOC.md | NEW |
| GLOSSARY.md | NEW |
| FNO_STRATEGY.md | NEW |
| STRATEGY.md | UPDATED |
| LEARNING.md | UPDATED |
| STATE.md | UPDATED (this file) |
| HISTORY.md | UNCHANGED |
| RULES.md | UNCHANGED |

Reading order: RULES -> STATE -> STRATEGY -> LEARNING -> GLOSSARY -> BUSINESS_DOC -> TECHNICAL_DOC -> FNO_STRATEGY

---

## LIVE STATUS (2026-05-15, 23:00 IST)

### Both EC2s Running
| EC2 | IP | Profiles |
|-----|----|----------|
| OLD | 13.206.144.6 | vishal-live, vishal, neha paper, F&O (3), F&O MTM cron |
| NEW | 13.202.63.223 | neha-live ONLY + DB sync to S3 + dashboard sync |

### Git Sync Status
- OLD EC2: 6b8de75
- NEW EC2: a0ec15e
- ACTION Monday: ssh ec2-user@13.202.63.223 "cd ~/dev-sandbox && git pull"

### Active Crons OLD EC2
- */15 4-7 * * 1-5 — intraday vishal-live, vishal, neha
- 50/52/54 3 * * 1-5 — F&O daily for vishal/neha/vishal-live
- */30 4-9 * * 1-5 — F&O MTM update (NEW today)
- 5 10 * * 1-5 — Top performers capture
- 0 3-10 * * 1-5 — Dashboard S3 sync + CloudFront invalidation

### Active Crons NEW EC2
- */15 4-7 * * 1-5 — intraday neha-live
- */15 4-10 * * 1-5 — sync neha-live DB to S3
- */15 4-10 * * 1-5 — sync neha-live dashboard JSON to S3

### Capital Limits
| Profile | Capital | Max Trades | Loss Limit | VIX |
|---------|---------|------------|------------|-----|
| vishal-live | Rs.15,000 | 3 | Rs.900 | 20 |
| neha-live | Rs.10,000 | 3 | Rs.900 | 20 |
| vishal paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |
| neha paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |

---

## ACTIVE BUGS / OPEN WORK

### Critical
| ID | Description | Status |
|----|-------------|--------|
| Bug 5 | max_trades_per_day not enforced | FIXED, needs Monday validation |
| Bug T | F&O P&L synthetic | FIXED, needs Monday market-hours validation |
| Bug HH | 0 orders placed at 12:03 PM neha-live (May 14) | OPEN |
| TELEGRAM-WIRE | Module ready, not called from monitor/executor | OPEN |

### High
- Dashboard neha-live tab missing (UI update)
- SL-TIMING: SL placed before BUY confirmed fill
- Dhan optionchain validation blocked until Monday

### Medium / Low / Future
- F&O legs_json expiry_date partial fix
- Dhan + AWS credentials rotation
- Backtest engine
- News + fundamentals fetchers
- Swing live deployment
- Positional module
- Onboarding website

---

## MONDAY MORNING CHECKLIST (2026-05-18)

### Pre-Market
1. timedatectl on both EC2s
2. NEW EC2: cd ~/dev-sandbox && git pull
3. git log --oneline -3 on both

### Market Open 9:30 AM IST
1. tail -f logs/intraday_vishal-live_2026-05-18.log
2. Bug 1: "Nifty500 scan: 250+ total" (was 169)
3. Bug 2: Losers count > 0
4. Bug 3: "buffered" or "MARKET retry" on fast movers
5. Bug 5: trade counter increments correctly across continuous scans

### F&O Open 9:24 AM IST
1. Strategies have real Dhan strike prices in entry_price
2. ls cache/option_chain_*.json

### Mid-Session every 30 min
1. cat logs/fno_pnl_update.log
2. fno_trades.current_price populated
3. fno_strategies P&L updating
4. Exit triggers fire when conditions met

### EOD 3:35 PM IST
1. cat logs/top_performers.log
2. War Room scanner accuracy
3. EOD summary shows real F&O P&L

### Watch For
- Bug 5 trade counter (most important — real money)
- Bug T option chain HTTP status (401 = Dhan API issue)
- Buffer 0.3% slippage acceptable
- F&O exit triggers not firing prematurely

---

## INFRASTRUCTURE

| Item | Value |
|------|-------|
| OLD EC2 | 13.206.144.6 (i-0256713c061011a5f) |
| NEW EC2 | 13.202.63.223 (i-0233c705c9104383e) |
| Dashboard | https://d2q1cy3ph7jbd0.cloudfront.net |
| GitHub | https://github.com/vshorrghar/Intraday-Trader.git |
| Bedrock | Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5) us-east-1 |
| AWS Profile | vishal-admin |
| Latest commit OLD | 6b8de75 |
| Latest commit NEW | a0ec15e (needs pull) |
| S3 db-sync prefix | s3://dev-sandbox-dashboard-176767908884/db-sync/ |
| S3 per-profile prefix | s3://dev-sandbox-dashboard-176767908884/api// |

---

## CAPITAL SCALING REMINDER

Phase 1: Rs.10K-15K live (current).
Phase 2 unlocks at: 50 profitable trades on real money.
Current: ~5 closed real money trades (Bug 5 inflated count today, dont count those).
Wait for 20+ validated trades on RS-First v3 + Bug 5 fix before evaluating.

---

## HOW TO RESUME ANY CHAT

Paste RULES.md + STATE.md + your question. Any AI that lectures without reading both is wasting your time.

End of STATE.md
