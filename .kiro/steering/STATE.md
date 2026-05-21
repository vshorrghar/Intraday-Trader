# STATE.md — Current Project State

**Last Updated**: 2026-05-18, ~13:30 CET (post-duplicate-order-bug discovery)
**Update Protocol**: Replace TODAY section at end of each session.

---

**Last Updated**: 2026-05-19 EOD - duplicate order ROOT CAUSE FOUND + FIXED
**Update Protocol**: Replace TODAY section at end of each session.

---

**Last Updated**: 2026-05-19 EOD — bugs found + dashboard Phase 1 shipped + Telegram live
**Update Protocol**: Replace TODAY section at end of each session.

---

---

---

## TODAY (2026-05-21 EOD) — BUG B FIRED IN PRODUCTION + VALIDATION DAY

### Real Money Today (vishal-live) — 3 trades, all bug-tainted in some way

| Stock | Entry | Exit | Qty | Net | Notes |
|-------|-------|------|-----|-----|-------|
| BEL | 425.75 | 421.40 | 10 | -Rs.43.50 | Force exit at 15:15 IST, planned |
| ANGELONE | 337.40 | 339.32 | 13 | +Rs.24.90 | Target hit, clean trade |
| HFCL | 143.17 | 143.76 | 62 (!) | +Rs.36.58 | Bug B fired - see below |

Total realized: +Rs.17.98
Estimated charges: ~Rs.20-25
Net after charges: ~Rs.0 to -Rs.5

### BUG B CONFIRMED IN PRODUCTION

Sequence on HFCL:
- 10:30:43 IST: BUY 31 HFCL @ 144.93 (planned entry)
- 10:30:45 IST: SL placed SELL 31 STOP_LOSS trigger 142.25 (planned)
- 11:46:52 IST: Target hit - SELL 31 @ 145.27 closed long position (planned)
- 11:46:52 IST: Original SL at 142.25 NOT CANCELLED by our code (Bug B)
- ~14:30 IST: HFCL drifted to 142.25, orphan SL triggered, Dhan executed SELL 31
- Created phantom SHORT 31 HFCL with no SL protection
- ~15:00 IST: User noticed on Dhan app, manually squared off (BUY 31 @ 142.55)

Lucky outcome: HFCL stayed range-bound, phantom SHORT closed at +Rs.0.93.
Real risk had HFCL spiked: -Rs.150 to -Rs.300 unprotected.

### Bug A (May 20 fix) - VALIDATED
- 3 trades placed today, all LONG, no rogue duplicates
- No [LONG] mislabel events
- Fix from commit 5131cd6 confirmed working for entry path
- SHORT direction validation still pending (no SHORT picks today)

### Validation Status
- vishal-live --live: continues uninterrupted (no pause, partner directive)
- Bug A entry-path fix: VALIDATED on 3 LONG trades today
- Bug B exit-path: CONFIRMED firing on HFCL - fix tonight
- Trailing SL fakeness: confirmed in logs (only memory, not Dhan modify)
- F&O paper: working, deferred to weekend cleanup

### Tonight's Bug Fix Marathon (Thu May 21 evening)
- Fix Bug B-1: cancel SL on target hit
- Fix Bug B-2: cancel SL on force exit
- Fix Bug B-3: trailing SL must modify Dhan order, not just memory
- Test on paper end-to-end before commit
- vishal-live ready for Friday with bug-free exit path

## TODAY (2026-05-20 EOD) — TATASTEEL BUG + CRONTAB SAFETY + vishal-live RE-ENABLED

### Real Money Today (vishal-live)
- TATASTEEL SHORT trade — Bug A exposed (rogue monitor double-SHORT)
- Position: 22 intended, 44 actual on Dhan, 22 unprotected by SL
- User manually closed via Dhan app at 10:18 IST
- Net: -Rs.38 after charges (within Rs.500 daily cap)
- Capital intact: ~Rs.13,580
- Daily loss limit NOT breached

### Two Critical Bugs Found and Fixed (commits today)

#### Bug 1: Bedrock Opus 4-7 timeouts (commit 5131cd6)
- config/config.yaml had bedrock_model_id = us.anthropic.claude-opus-4-7
- Opus consistently timed out 120s
- Result: ZERO trades placed at 9:30 AM and 9:45 AM crons
- Fix: Changed to us.anthropic.claude-sonnet-4-6
- Pre-flight tested: Sonnet 4.6 returns OK in ~1 second
- Also fixed in config/config_neha.yaml (gitignored, manual edit)

#### Bug A: Rogue monitor double-SHORT (commit 5131cd6)
- intraday/executor.py line 313: added "action": entry_side to record dict
- intraday/monitor.py line 86: defensive warning if action field missing
- Bug existed since SHORT support added (commit 23a0261 May 14)
- 6 days silent before TATASTEEL exposed it on real money
- Validation: pending tomorrow's first SHORT pick on fresh code

### Crontab Safety Guard (commit 7843628)
- scripts/safe_crontab_edit.sh — defensive editor with backup + validate + diff + confirm
- scripts/crontab.canonical — known-good restore source
- RULES.md Rule 25 — never pipe transformed crontab to crontab -
- Prevents wipes like May 18, May 20

### vishal-live --live RE-ENABLED for May 21
- Cron line uncommented via safe editor
- Bug A fix validates on first SHORT trade tomorrow
- Daily loss cap Rs.500 bounds real money exposure
- Per-trade Rs.4,500, max 3 trades

### F&O Paper — Actually Working
- 2 IRON_CONDORs opened (NIFTY + BANKNIFTY) at 9:33 IST
- Force exited at 15:15 IST
- Net: -Rs.1.14 (50% win rate)
- 3 issues identified for Saturday cleanup:
  - F&O Bedrock config still uses Opus 4-7 (13-min strategy selection)
  - Dhan HTTP 429 rate limits on BANKNIFTY/FINNIFTY
  - MTM cron produces fake P&L from stale option chain LTPs

### Intraday Paper Today
- vishal: HINDPETRO LONG +Rs.470.87 (winner)
- neha: BPCL LONG +Rs.331.48 (winner)
- Plus 5+ paper SHORT exits with [LONG] mislabel (Bug A fired in paper)
- Combined paper: ~+Rs.605

### Swing Module Truth Discovered
- run_swing.py is placeholder skeleton, imports only SwingConfig + is_paused
- 1,300 lines of real code in swing/*.py orphaned (never called)
- swing_trades DB schema missing action column
- Status: 30% complete (was claimed 60-90% in prior STATE.md)
- Saturday: dedicated rebuild session

### Tomorrow May 21 — vishal-live Watch Plan
- Whenever user wakes (Denmark CET, no 5 AM alarm needed)
- Rs.500 daily loss cap = sleep insurance
- Check dashboard https://d2q1cy3ph7jbd0.cloudfront.net/?profile=vishal-live
- Pull Dhan truth: scripts/sync_dhan_live.py
- Verify: SHORT trade exits with [SHORT] label (not [LONG])
- Verify: monitor places BUY (not SELL) on SHORT exit
- If buggy: emergency disable cron via safe editor

### Today's Commits
- 5131cd6 fix: Bedrock Sonnet 4.6 + rogue monitor double-SHORT bug
- 7843628 feat: crontab safety guard + Rule 25 + vishal-live re-enabled

## TODAY (2026-05-19 EOD) — 3 BUGS + PHASE 1 DASHBOARD + TELEGRAM ACTIVE

### Real Money Today (vishal-live)

- Dhan API truth P&L: +Rs.85.16
- Our DB-reported P&L: -Rs.129.97 (WRONG by Rs.215)
- Available balance EOD: Rs.13,632.80
- 3 trades executed (IOC, COHANCE, INFY)
- Daily loss limit Rs.500 NOT breached
- All positions auto-squared by Dhan at 15:30 IST

### Dashboard Phase 1 — SHIPPED (commit 96c8770)

7 files committed by Kiro:
- dashboard/v2/css/design.css (color palette, typography, spacing)
- dashboard/v2/css/components.css (cards, pills, badges)
- dashboard/v2/components/header.html (template fragment)
- dashboard/v2/universe.html (4-tier Indian universe with staleness timestamps)
- dashboard/v2/risk.html (profile config + risk gates + capital scaling)
- alerts/telegram_bot.py (skeleton: /ping, /status only)
- config/telegram.yaml.example (template, no secrets)

Live URLs verified working:
- https://d2q1cy3ph7jbd0.cloudfront.net (old dashboard, still 200)
- https://d2q1cy3ph7jbd0.cloudfront.net/v2/universe.html (200)
- https://d2q1cy3ph7jbd0.cloudfront.net/v2/risk.html (200)

### Telegram Bot — ACTIVE (running on EC2-OLD)

- Bot username: created via @BotFather
- Token: stored in config/telegram.yaml (gitignored)
- Allowed chat_id: 5422811137 (vishal)
- Process PID: 204601 (background, started today)
- Tested: /ping returned Pong successfully
- Available: /ping, /status, /help
- NOT WIRED: trade alerts, P&L alerts (Phase 4)

### Three Bugs Discovered Today (NOT fixed)

#### Bug 1 (CRITICAL): MARKET retry skips SL placement + DB write
- Yesterday's commit a2e5d66 (return None indent) is in code at correct indent
- BUT logs show MARKET retry STILL bypasses SL+DB after fill
- Pattern: 04:00:23 "MARKET retry filled 3 INFY" -> immediately "BUY IOC" (next stock)
- 5 INFY shares + 1 ADANIGREEN share unprotected all day
- There is a SECOND code path the indent fix didn't reach
- Need to read place_orders() function to find it

#### Bug 2: Cross-process token sharing
- Cron session 05 auth'd Dhan at 05:00 (PID 185464)
- Cron session 07 detected stale 3.7-hour session, re-authed
- But OLD monitor process kept running with OLD invalid token
- get_positions returned HTTP 400 from 07:30 to 09:45 (2+ hours)
- INFY position monitoring blind for entire afternoon

#### Bug 3: Force exit logs success on failed order
- Code: place_order returned HTTP 400 'Invalid Token'
- Same flow logged "OK INFY exit order placed"
- Recorded synthetic P&L -Rs.13.93
- Reality: Dhan auto-square-off closed position
- Our system told a lie

### Capital Plan Agreed Today

User goal: Rs.1 lakh/month income by June 20 (32 days from today).
Capital source: Rs.5 lakh own savings (confirmed not loan).

Math:
- Rs.5L × 0.9% daily = Rs.4,500/day = Rs.1L/month (achievable)
- Requires 60%+ win rate (unproven yet — bugs hide truth)

Staged deployment plan agreed:
- Days 1-5 (May 20-24): Fix bugs, validate clean DB-vs-Dhan
- Days 6-15 (May 27-Jun 6): Scale Rs.15K → Rs.50K → Rs.2L
- Days 16-25 (Jun 8-19): Scale to Rs.5L
- Day 26+ (Jun 20+): Income phase, Rs.5L deployed

Honest probability estimate:
- 25% chance hit Rs.1L/month by Jun 20
- 35% chance hit Rs.50-80K/month
- 25% chance hit Rs.20-40K/month
- 15% chance net loss for the month

Strict gate: NO scale up if any day shows DB-vs-Dhan drift > Rs.5.

### F&O Findings (paper, deferred)

vishal F&O paper today:
- Strategy 15 NIFTY: P&L Rs.413.75 (correct)
- Strategy 16 BANKNIFTY: P&L Rs.92,025 (FAKE — max possible was Rs.216)
- Strategy 17 FINNIFTY: P&L Rs.10 (force exit lost real prices)

Root cause: BANKNIFTY current_price has garbage values (5849, 11972).
Same Bug T resurrection (third or fourth time).
Deferred — not blocking real money.

neha F&O: HTTP 401 confirmed (no Data API on neha account, by design).

### Validation Script Status

CHECK 1 PASS — Cron fired correctly
CHECK 2 PASS — No 5-second duplicates on Dhan
CHECK 3 PASS — Trade counter at 3 (correct)
CHECK 4 PASS — Same-symbol block working
CHECK 5 FAIL — DB-vs-Dhan: 7 mismatches (Bug 1 effect)

### What's Working

- Indent fix yesterday DID work for ONE path (verified in code)
- Auth fix per-profile sessions still working
- Same-symbol block functional when DB has rows
- Trade counter holds at 3/3
- Dashboard Phase 1 v2 ready for Phase 2 wiring
- Telegram bot active, ready for Phase 4 alert wiring
- Dhan API truth source (sync_dhan_live.py) reliable
- Real money capital intact

### What's Broken

- Bug 1: MARKET retry second code path (real money unprotected)
- Bug 2: Cross-process token contamination (causes Bug 3)
- Bug 3: Force exit lies on failed orders
- F&O P&L calculation (paper-only, deferred)
- Dashboard old version P&L wrong (DB-derived, fixable in Phase 2)
- Validate_tomorrow.sh false-positives on Check 5 (compares wrong fields)

### Tomorrow's Priority (one bug at a time, no plan jumps)

1. Read place_orders() function structure
2. Find Bug 1 second path
3. Propose one-block patch
4. User approves
5. Apply to executor.py
6. Test on paper for one day
7. THEN consider scaling capital

Decision pending tomorrow:
- Old dashboard P&L fix (read from dhan_live.json instead of DB)
  → Safe display-only fix
  → Can be done without lifting intraday freeze

### Don't Touch (working)

- intraday/executor.py line 198 (yesterday fix correct)
- intraday/auth_server.py
- config/profile.py
- scripts/sync_dhan_live.py
- alerts/telegram_bot.py (active, leave running)
- dashboard/v2/* (Phase 1 done)

### Cron Status

OLD EC2: vishal-live LIVE + paper + F&O all running
NEW EC2: empty (neha-live STOPPED)

### Today's Session Architecture

Three parallel tracks worked:
1. Trading: bug discovery + capital plan (vishal + Claude)
2. Dashboard Phase 1: Kiro fresh session (succeeded after SCP workaround)
3. Telegram bot: setup + activation

All three tracks landed in single commit 96c8770.

### Cumulative Real Money May 12-19

- Total real-money trades closed: ~6
- Real cumulative P&L (Dhan truth): -Rs.700 to -Rs.1,500 estimate
- Charges burden: Rs.50-70 per round-trip on small positions

---

## PREVIOUS SESSION (2026-05-19 morning) — EXECUTOR.PY INDENT FIX (a2e5d66)


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

---

## TODAY (2026-05-19 LATE NIGHT) — BUG 1 FIX + SWING SKELETON + 6 INSTITUTIONAL DOCS

### Real Money Status
- vishal-live: Rs.15K live, Bug 1 fix shipped, awaiting validation
- neha-live: STOPPED (since May 18, awaiting Bug 1 validation 5+ days clean)
- Total real money exposure: Rs.15K
- Cumulative real P&L May 12-19: -Rs.1,200 to -Rs.1,500 (Dhan truth)

### Commits Tonight
- 8b96b23: Bug 1 reconcile + Bug 3 exit honesty (CRITICAL fix)
- 646705c: Dashboard v2 swing tab (danish-eq UI ported, Indian markets)
- f84be10: Swing paper-mode skeleton (60% built)
- 5bc4cb3: 6 new institutional steering docs

### Bug 1 Fix Status
SHIPPED via commit 8b96b23. Tomorrow morning May 20 first market test.
Defense in depth: get_positions reconcile #1 + cancel-detection #2 + reconcile #3.
Validation gate: 30 trading days clean before any capital scaling per Rule 25 precedent.

### Swing Module Status — 60% Complete
DONE (commit f84be10):
- swing/sector_map.py (12 sector classifications)
- swing/models.py (SwingTradeSetup + SwingConfig dataclasses)
- swing/risk_manager.py (1% sizing, sector cap, regime, daily/weekly loss)
- swing/monitor.py (smart time stop, NEVER auto-sells winners, EXIT_FAILED audit)
- swing/manual_override.py (pause/resume/exit/status)
- fetchers/swing_earnings_list.py (manual list)
- run_swing.py (orchestrator skeleton)
- run_swing_daily.sh + run_swing_monitor.sh (wrappers)
- scripts/swing_control.py (CLI)
- scripts/swing_schema.sql (applied to all 4 DBs)
- vishal profile YAML updated with swing config

NOT BUILT YET (Phases 2, 3, 4, 13, 16):
- swing/scanner.py — 20-DMA pullback scoring (currently placeholder)
- swing/selector.py — LLM prompt for swing (currently placeholder)
- swing/executor.py — CNC product_type swap (currently intraday MIS code)
- swing/dashboard.py — JSON writer (currently placeholder)
- Cron entries (Phase 13)
- Rule 25 in RULES.md (Phase 16)
- Profile YAMLs for neha, vishal-live, neha-live (only vishal done)

### Test Results
- AST parse all swing files: OK
- Pipeline dry-run: runs, prints "placeholder" messages, writes empty JSONs
- Manual override: pause/resume/exit/status all working
- DB schema applied: swing_trades + swing_audit on all 4 DBs

### 6 New Institutional Steering Docs
1. EDGE.md (387 lines) — Why each strategy should make money
2. DECISIONS.md (472 lines) — Strategic decision log, append-only
3. BUGS_AND_FIXES.md (479 lines) — Bug catalog with patterns
4. WIN_RATE_TRACKING.md (436 lines) — Statistical validation log (has [FILL_IN] markers)
5. REGIME_LOG.md (261 lines) — Daily regime template (entries start May 20)
6. TRADE_REVIEW.md (251 lines) — Daily post-mortem template (entries start May 20)

### Tomorrow's Priority (May 20)
1. Pre-market: verify Bug 1 fix at HEAD on both EC2s
2. 9:30 AM IST: tail intraday log, watch for RECONCILE: messages
3. Update WIN_RATE_TRACKING.md with REAL data extracted from intraday DBs
4. EOD: write first REGIME_LOG.md and TRADE_REVIEW.md entries
5. NO new code building tomorrow (validation day)

### Saturday/Sunday Plan
1. Run Prompt 2C: complete swing Phases 2, 3, 4, 13, 16
2. End-to-end test before Monday cron
3. Monday May 26: paper swing trading begins

### Pending Decisions
- F&O fate (REWRITE/KILL) — decide by June 1
- Capital scaling Rs.15K → Rs.30K — gated by 50+ trades + Bug 1 30-day clean
- neha-live reactivation — after Bug 1 5-day clean validation

### Don't Touch
- intraday/executor.py (Bug 1 fix is delicate, 16-space indent + reconcile logic)
- intraday/monitor.py (Bug 3 fix is in 3 locations)
- swing/* skeleton (working, awaiting Phases 2-4)
- dashboard/v2/swing/ (UI works, awaiting real swing data)

### Cumulative Stats
- Codebase: ~22,000 lines (estimated)
- Trading strategies: 4 designed, 1 live, 0 statistically validated
- Steering docs: 16 total (RULES, STATE, HISTORY, STRATEGY, LEARNING, GLOSSARY, BUSINESS_DOC, TECHNICAL_DOC, FNO_STRATEGY, CONTEXT, EDGE, DECISIONS, BUGS_AND_FIXES, WIN_RATE_TRACKING, REGIME_LOG, TRADE_REVIEW)
- Real money trades to date: ~5 closed
- Real money cumulative loss: Rs.1,200-1,500

### How To Resume Tomorrow
1. Open EC2-OLD via SSM
2. cd ~/dev-sandbox && bash scripts/build_context.sh
3. Copy CONTEXT.md to new Bedrock chat
4. Type: "Continue from 2026-05-19 EOD. Either run option C (extract real win rate) or option B (write Prompt 2C-FAST/NARROW for Kiro to complete swing)."


---

## RECONCILIATION SCRIPT BUILT (2026-05-20 03:00 IST)

### scripts/reconcile_dhan_db.py — DONE

Detects DB-vs-Dhan drift per trade. Classifies issues:
- PHANTOM_TRADE — in Dhan, missing from DB
- ORPHAN_DB — in DB, missing from Dhan
- PNL_DRIFT — P&L off by > Rs.5
- QTY_DRIFT — quantity mismatch
- OK — within threshold

Output: dashboard/api/{profile}/reconciliation_report.json
Exit code: 0 if PASS (drift <= Rs.5), 1 if FAIL

### First test result on May 19

VERDICT: FAIL (Rs.215.13 drift)

| Symbol | Issue | Drift |
|--------|-------|-------|
| ADANIGREEN | PHANTOM_TRADE (Bug 1) | -Rs.45.60 |
| COHANCE | PNL_DRIFT (Bug 1 — half qty) | +Rs.214.49 |
| INFY | PNL_DRIFT (Bug 3 — Invalid Token) | +Rs.48.03 |
| IOC | OK (Rs.1.79 minor) | within threshold |

True May 19 P&L: +Rs.85.16
DB-reported May 19 P&L: -Rs.129.97
Drift: Rs.215.13

### Cron added (OLD EC2)

10 10 * * 1-5 — sync + reconcile every weekday 3:40 PM IST

### Saturday cleanup tasks

1. Manually correct DB rows for May 12-19 corruption period
2. Update WIN_RATE_TRACKING.md with cleaned cumulative P&L
3. Verify cron firing and report appearing daily


---

## SESSION CLOSE (2026-05-20 03:35 IST) — TONIGHT'S WINS

### Code shipped (8 commits)
1. 8b96b23 — Bug 1 reconcile + Bug 3 exit honesty
2. 646705c — Dashboard v2 swing UI (danish-eq port)
3. f84be10 — Swing skeleton (60%)
4. 5bc4cb3 — 6 institutional docs
5. 6cb431d — STATE + critical Bug 1 finding
6. ed18e89 — Swing scanner + selector + executor (BRAIN)
7. (this commit) — reconcile_dhan_db.py + show_today_truth.py + cron

### Tonight's biggest discovery
True May 19 P&L: +Rs.85.16 (PROFIT)
DB-reported: -Rs.129.97 (FALSE LOSS)
Drift: Rs.215.13 corruption from Bug 1 + Bug 3

True May 19 win rate: 75% (3W / 1L)
DB-reported: 33% (1W / 2L)

System might genuinely have edge. Sample too small (4 trades) but encouraging.

### Verification tools built
- scripts/sync_dhan_live.py (was built earlier)
- scripts/reconcile_dhan_db.py (NEW tonight)
- scripts/show_today_truth.py (NEW tonight)
- Daily cron: 10 10 * * 1-5 — sync + reconcile

### Daily ritual going forward
EOD (after 3:35 PM IST):
  1. cron auto-runs sync + reconcile
  2. Open dashboard/api/vishal-live/reconciliation_report.json
  3. Status PASS = trust DB; Status FAIL = investigate

Anytime check:
  .venv/bin/python scripts/show_today_truth.py --profile vishal-live

### Outstanding for Saturday
- Swing cron entries (Phase 13)
- Rule 25 in RULES.md (Phase 16)
- Add swing config to neha, vishal-live, neha-live YAMLs
- Manually correct DB rows for May 12-19 corruption period
- Build unified dashboard (one URL all modules)

### Tomorrow's first market test
9:30 AM IST: Bug 1 fix first live test
3:40 PM IST: Reconciliation cron auto-runs
3:45 PM IST: Verify status PASS (drift < Rs.5)

If PASS: Day 1 of 30-day Bug 1 validation begins.
If FAIL: Pause real money. Investigate before next day.

### Project status snapshot
- Real money: vishal-live Rs.15K (Bug 1 fix shipped, awaiting validation)
- neha-live: STOPPED (per May 18 decision)
- F&O: paper only (Bug T pending decision June 1)
- Swing: 95% built, paper mode, cron NOT active yet
- Dashboard: working but DB-derived (lying); truth available via reconciliation
- Documentation: 16 steering docs (institutional grade)


---

## SWING MODULE TRUTH (2026-05-20 EOD discovery)

Despite commit messages claiming swing is built:
- 6c2... feat(swing): paper-mode swing trading module
- ed18e89 feat(swing): scanner + selector + executor — full trading logic

REALITY: run_swing.py is a placeholder skeleton. It imports only
SwingConfig and is_paused. It does NOT call scanner/selector/executor/monitor.
Logs print "(placeholder)" and pipeline writes empty dashboard JSONs.

Real code exists (~1,300 lines across swing/scanner.py, swing/selector.py,
swing/executor.py, swing/monitor.py) but is ORPHANED — nothing calls them.

DB schema also broken — swing_trades table missing 'action' column.

Status: TRULY 30% complete (code exists, integration missing).
Next: Saturday weekend session — rewrite run_swing.py to wire real modules.
First real swing trade: earliest Monday May 25 (paper only).

