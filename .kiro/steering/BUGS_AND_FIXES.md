# BUGS_AND_FIXES.md — Production Bug Catalog

**Purpose:** Document every production bug discovered, its symptoms, root cause, fix applied, and prevention measures. Prevents repeat bugs from same architectural blind spots.

**Update rule:** Append-only. Every bug discovered gets an entry within 24 hours of identification.

**Reading order:** RULES.md, STATE.md, STRATEGY.md, BUGS_AND_FIXES.md (when investigating issues)

**Author:** Vishal (founder, principal trader)
**Last updated:** 2026-05-19

---

## DOCUMENT PURPOSE

Bugs in trading code cost real money. Bug T came back 3 times because it was never fully understood. Bug 1 hid for unknown duration before discovery cost Rs.220+ direct losses.

This document forces:
1. Full documentation of each bug (symptoms, cause, fix, cost)
2. Pattern recognition across bugs (same root cause categories)
3. Prevention rules added to RULES.md from each lesson
4. Audit trail for any future RA/IA reviewing system

If a bug class returns 3+ times, the architecture is wrong. We rewrite, not patch.

---

## BUG CLASSIFICATION

### Severity Levels

- CRITICAL: Real money lost, position safety compromised, or data integrity broken
- HIGH: Paper money affected significantly, or could escalate to critical
- MEDIUM: Logic flaw with workaround available
- LOW: Cosmetic, dashboard, non-trading-path issues

### Categories

- EXECUTION: Order placement, fill, cancellation
- MONITORING: Position tracking, exit triggers
- DATA: DB writes, JSON output, broker reconciliation
- AUTH: TOTP, session management, API tokens
- CALCULATION: P&L math, charges, R:R
- SCANNER: Stock filtering, scoring, ranking
- INFRASTRUCTURE: Cron, EC2, S3, CloudFront


---

## ACTIVE BUGS (Open as of 2026-05-19)

### Bug HH: 0 Orders Placed at 12:03 PM neha-live (May 14)

**Status:** OPEN, root cause unknown
**Severity:** HIGH
**Category:** EXECUTION

**Symptoms:**
- May 14, 12:03 PM: scanner picked candidates, LLM selected, BUT zero orders placed
- No error in logs
- Risk manager did not block
- Profile DB has no record of attempted trade

**Suspected causes:**
- Auth issue (silent token expiry)
- Cron environment variable issue
- Risk manager edge case (capital calculation)

**Investigation needed:** Reproduce on demand, add logging at each stage between LLM pick and place_order call.

**Cost so far:** Unknown (one missed trade)

---

### Bug T: F&O Synthetic P&L (Resurrected 3 Times)

**Status:** OPEN, decision pending whether to fix or kill F&O module
**Severity:** HIGH (paper-only, but blocks F&O validation)
**Category:** CALCULATION + DATA

**Symptoms across resurrections:**
- May 19: BANKNIFTY showing Rs.92,025 P&L when max possible was Rs.216
- May 19: NIFTY showing Rs.413.75 (correct)
- May 17: Force exit losing real prices on expiry-day
- May 16: Sub-bugs T-1 (cron broken), T-2 (paper skipped Dhan auth), T-3 (force_exit current_premium=0)
- May 15: Original Bug T fix shipped

**Pattern observed:**
Same bug class returns. Architecture issue, not code issue. Likely:
- Caching layer corruption (stale option chain prices)
- Symbol normalization (NIFTY vs NIFTY24MAYFUT)
- Integer vs string ID confusion
- Greek calculation depending on stale spot price

**Decision pending:** See DECISIONS.md DECISION 011

---

### Bug GG (RESOLVED): Live P&L Stuck at Rs.0

**Status:** RESOLVED 2026-05-14 (commit 23a0261)
**Severity:** was CRITICAL (masked real losses)
**Category:** MONITORING

**Symptoms:**
- May 14: SAIL position lost Rs.63 but monitor showed Rs.0 all day
- Trailing stop never activated (needs P&L)
- Only safety: Dhan SL order placed at entry

**Root cause:** Monitor fetched P&L from broker get_positions, but Dhan returns 0 LTP for some queries. No fallback when broker LTP empty.

**Fix:** Live P&L now fetches from broker, falls back to NSE LTP when broker has no data. File: intraday/monitor.py

**Cost:** ~Rs.63 on SAIL

**Lesson:** Always have data fallback. Single-source data is fragile.

---

### Bug FF (RESOLVED): NSE Losers API Endpoint Dead

**Status:** RESOLVED 2026-05-15 (commit 68e910c)
**Severity:** HIGH (SHORT candidates were 0)
**Category:** SCANNER

**Symptoms:**
- ?index=losers returned "Missing index or key" error string
- Scanner accepted "0 losers" as valid
- Half scanning (SHORT) effectively broken for unknown duration

**Root cause:** NSE API contract changed silently. Endpoint moved data to SecLwr20 key in gainers response.

**Fix:** fetch_top_losers() now calls gainers endpoint, extracts SecLwr20. File: fetchers/nse_market_movers.py

**Cost:** Unknown (missed SHORT opportunities)

**Lesson:** Log and alert on "fetched 0 of expected ~20" responses. Silent degradation is worst kind.

---

### Bug EE (RESOLVED): Bedrock 25-Min Hang at Market Open

**Status:** RESOLVED 2026-05-14 (commit 23a0261)
**Severity:** HIGH (missed best entries)
**Category:** INFRASTRUCTURE

**Symptoms:**
- May 14, 9:26 AM: 25-minute hang on Bedrock call
- Missed entire opening window
- Other times same day: 4-min response acceptable

**Root cause:** boto3 default timeout = 60 seconds, but actually waits indefinitely on certain Bedrock peak-load conditions. No retry config.

**Fix:** Set explicit Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 1})

**Cost:** Missed best 9:30-10:00 entry window on May 14

**Lesson:** Always set explicit timeouts. Defaults aren't reliable for trading-critical paths.


---

### Bug 1: Indent Bug Causing Duplicate Orders + Phantom Trades

**Status:** RESOLVED 2026-05-19 (commits a2e5d66 + 8b96b23)
**Severity:** CRITICAL (real money safety compromised)
**Category:** EXECUTION

**The Bug That Wore 8 Faces:**
- TATASTEEL 4x duplication on May 18 (vishal-live)
- BANDHAN/MOTHERSON/CANBK 2x on May 18
- ETERNAL phantom 38 shares on May 18 (zero DB record)
- INFY 3.5x duplication on May 19
- Bug 5b counter false failures
- Same-symbol block bypass (cron didn't see existing positions)
- DB-vs-Dhan P&L drift 14x (DB said -Rs.66, Dhan said -Rs.469.50)
- 5 of 7 INFY shares unprotected by SL on May 19 afternoon

**Root cause:**
intraday/executor.py line 198: return None at 12-space indent (should have been 16-space).
This made the return statement a sibling of "if filled_qty == 0:" instead of a child.
Function returned None unconditionally after MARKET retry block.

**Flow when bug fired:**
1. LIMIT order placed and REJECTED (Dhan tick size error 16283)
2. MARKET retry placed and FILLED 3 shares
3. Code reached the misindented return None
4. Function exited WITHOUT placing SL
5. Function exited WITHOUT writing to DB
6. Position open on Dhan, zero in our system

**Why it hid for unknown duration:**
- LIMIT first-try fills worked correctly (no MARKET retry needed)
- DryRun broker can't simulate real Dhan tick-size rejections
- MARKET retry only fires on confidence >= 8 setups
- Bug only visible by comparing Dhan API vs DB

**How discovered:**
1. Subscribed Dhan Data API Rs.499/mo (May 17), provided real-time order endpoint
2. Built scripts/sync_dhan_live.py (May 19 morning)
3. Compared dhan_live.json vs intraday_trades, saw missing rows
4. Read executor.py with cat -A, spotted indent mismatch
5. User asked right question: "what did we do differently?"

**First fix (commit a2e5d66):** Indent corrected. ONE path fixed.

**Second fix (commit 8b96b23):** SECOND path discovered. Where wait_for_fill returns 0 due to API failures (token expired, rate limit, network) but order actually filled. Solution: reconcile via get_positions() before MARKET retry.

**Defense in depth:**
- Reconcile #1: Before any retry attempt
- Reconcile #2: After "Order Is Cancelled" message detected
- Both must fail before MARKET retry fires
- Bug 3 fix on monitor.py: fill_status check before recording P&L

**Cost:**
- Direct: Rs.220 (Bug 5 cascade)
- Real money: Rs.717 actual loss vs Rs.66 reported (14x DB drift)
- 5 INFY shares unprotected for entire afternoon (luck saved us)
- Trust: 1 week of paper-mode-only mindset post-fix
- Time: Unknown duration of bug existence + 1 week of investigation

**Prevention rules added:**
- ALL future fixes: cat -A indent verification
- ALL future fixes: AST parse validation
- Real-time broker reconciliation: Rs.499/mo Data API now mandatory
- DB-vs-Dhan comparison: planned daily cron

---

### Bug 2: Scanner Universe Truncated to 169/500 Stocks

**Status:** RESOLVED 2026-05-15 (commit a9df59b)
**Severity:** HIGH (1/3 of intended universe)
**Category:** SCANNER

**Symptoms:**
- May 14: Scanner output showed "169 total" instead of expected ~500
- TDPOWERSYS-type early breakouts (+8.75%) never seen
- 500K volume filter rejected stocks at 9:30 AM

**Root cause:**
Volume filter at 9:30 AM uses unbuilt volume. Most stocks haven't accumulated 500K by then. By 3:30 PM ~500 stocks pass; at 9:30 AM only ~169.

**Fix:** Momentum-aware volume filter:
- Pass if volume >= 500K (original)
- OR pass if change_pct >= 4% AND volume >= 100K (momentum override)

File: intraday/scanner.py

**Cost:** Missed unknown number of early-session breakouts

**Lesson:** Filter thresholds must adapt to time-of-day. Static thresholds at market open exclude valid candidates.

---

### Bug 3: Limit Orders Don't Fill on Fast Movers

**Status:** RESOLVED 2026-05-15 (commit a0ec15e)
**Severity:** HIGH (perfect setups not capturing)
**Category:** EXECUTION

**Symptoms:**
- May 15: SAREGAMA +7% surge, limit order at LTP didn't fill in 10s
- Stock continued to +13%, our cancellation lost the trade
- Confidence 8 setup, R:R 2.2

**Root cause:** Limit order placed at LTP. Stock moves 0.5% in 5 seconds. Limit price stale. No buffer, no MARKET fallback.

**Fix:**
- +0.3% buffer on entry limit (LONG: 1.003x, SHORT: 0.997x)
- Tick aligned to NSE Rs.0.05
- MARKET fallback after 10s timeout if confidence_score >= 8

File: intraday/executor.py

**Cost:** Lost SAREGAMA trade, ~Rs.500-1500 missed profit

**Lesson:** On fast movers, slippage on entry is bounded by SL on exit. MARKET fallback acceptable for high-conviction setups.

---

### Bug 5: max_trades_per_day Counter Bypassed

**Status:** RESOLVED 2026-05-15 (commit 7777382)
**Severity:** CRITICAL (real money over-deployed)
**Category:** EXECUTION + MONITORING

**Symptoms:**
- May 15: vishal-live placed 7 trades when limit was 3
- Lost ~Rs.220 from doubled-down INFY (4x) and HDFCBANK (2x)
- Continuous scan saw "0 trades placed today" and bypassed limit

**Root cause:** risk_manager._restore_daily_state only counted CLOSED trades. OPEN positions were not counted.

**Flow:**
1. 9:30 AM: Place trade #1 (counter was 1, but trade still PENDING)
2. 9:45 AM: Counter looks at CLOSED trades only, sees 0. Place trade #2.
3. 10:00 AM: Same. Trade #3.
4. Continued every 15 min until daily loss limit hit.

**Fix:** Risk manager now counts ALL non-rejected/cancelled BUYs (PENDING + OPEN + CLOSED).

File: intraday/risk_manager.py

**Cost:** Direct Rs.223 on May 15. Bug 1 cascade compounded this.

**Lesson:** When architecture changes (single-scan to continuous), audit every counter and gate. State assumptions break silently.

---

### Bug 6: neha-live Data Invisible from OLD EC2

**Status:** RESOLVED 2026-05-15 (commits abb236e + 7777382)
**Severity:** MEDIUM (operational visibility)
**Category:** INFRASTRUCTURE

**Symptoms:** War Room dashboard on OLD EC2 couldn't see neha-live trades. Two-EC2 architecture meant data fragmented.

**Root cause:** Multi-EC2 setup (Bug-T-related Dhan IP rule) split data. OLD EC2 had vishal+paper data, NEW EC2 had neha-live data. No shared storage.

**Fix:**
- NEW EC2: pushes neha-live DB + dashboard JSONs to S3 every 15 min
- OLD EC2: hourly S3 sync excludes db-sync/* (preserves NEW EC2 data)

Files: scripts/sync_neha_live_db.sh, scripts/sync_neha_live_dashboard.sh

**Cost:** Operational confusion only, no money lost

**Lesson:** When deploying multi-instance, design data unification before splitting.


---

## RECENTLY FIXED (May 12-19, 2026)

### Bug A+D: Dashboard Hiding Charges (Resolved 2026-05-13)

**Severity:** HIGH (false reporting)
**Category:** DATA

Dashboard was showing gross P&L only. Real net P&L (after Rs.50/trade charges) hidden.
neha paper showed +Rs.261 gross but +Rs.57.69 net.

**Fix:** Dashboard now shows gross P&L, charges, net P&L separately.

**Lesson:** Always display NET. Gross is marketing.

---

### Bug H: NSE Tick Size Rejection (Resolved 2026-05-13)

**Severity:** HIGH (orders rejected silently)
**Category:** EXECUTION

Dhan rejected orders with prices not aligned to Rs.0.05 tick (omsErrorCode 16283).
Our code rounded to Rs.0.01, causing all rejections.

**Fix:** Tick alignment formula: round(round(price / 0.05) * 0.05, 2)

**Lesson:** Broker quirks must be documented. Read broker docs for tick size rules.

---

### Bug J: Force Exit Logging Wrong P&L (Resolved 2026-05-13)

**Severity:** HIGH (P&L misreported)
**Category:** MONITORING + DATA

Force exit at 15:15 IST logged P&L using cached price, not actual fill.
Stale price could be Rs.5+ off, distorting reported P&L.

**Fix:** Place broker order FIRST, wait for actual fill price, then log P&L.

**Lesson:** Real fill price > cached price. Always.

---

### Bug K: SL/Target Hit Not Placing Broker Orders (Resolved 2026-05-13)

**Severity:** CRITICAL (positions not actually closed)
**Category:** EXECUTION

When monitor detected SL or target hit, only updated DB. Did NOT place broker SELL.
Position remained open on Dhan while DB said CLOSED.

**Fix:** Monitor now places broker SELL order on SL/target hit before updating DB.

**Lesson:** DB updates without broker action = lying to yourself.

---

### SHORT-RR Bug: R:R Math Always 0 for SHORT Trades (Resolved 2026-05-14)

**Severity:** HIGH (SHORT trades blocked)
**Category:** CALCULATION

Risk manager calculated risk = entry - stop_loss (correct for LONG only).
For SHORT trades, this gave negative risk, R:R = 0, ALL SHORT trades rejected.

**Fix:** Direction-aware R:R math:
- LONG: rr = (target - entry) / (entry - sl)
- SHORT: rr = (entry - target) / (sl - entry)

**Lesson:** Direction-agnostic formulas silently break for non-default direction. Audit every formula for direction symmetry.

---

## BUG PATTERN ANALYSIS

### Pattern 1: "Architecture Change Without Counter Audit"
**Examples:** Bug 5 (continuous scan to counter wrong)
**Lesson:** When architecture shifts, every counter, gate, and stateful element must be re-validated.

### Pattern 2: "Silent External API Degradation"
**Examples:** Bug FF (NSE losers), Bug EE (Bedrock timeout), Bug GG (broker LTP empty)
**Lesson:** External APIs change without notice. Always have monitoring + fallback.

### Pattern 3: "Wrong Source of Truth"
**Examples:** Bug 1 (DB vs Dhan drift), Bug J (cached vs real fill price)
**Lesson:** Broker is source of truth. Internal DB is convenience. Reconcile constantly.

### Pattern 4: "Direction-Agnostic Formula Breaking on Non-Default"
**Examples:** SHORT-RR bug
**Lesson:** When supporting LONG and SHORT, every formula needs explicit direction handling.

### Pattern 5: "Indent / Whitespace Causing Logic Drift"
**Examples:** Bug 1 (the indent bug)
**Lesson:** Critical paths need cat -A verification + AST parse validation post-edit.

### Pattern 6: "Cache Layer Corruption"
**Examples:** Bug T (3 resurrections, likely option chain cache issue)
**Lesson:** Caching is hard. When it breaks 3 times, redesign or remove cache.

---

## PREVENTION CHECKLIST (Post-Bug Discovery)

When ANY new bug discovered, run through:

1. Document in this file within 24 hours
2. Identify category (EXECUTION / MONITORING / DATA / AUTH / CALCULATION / SCANNER / INFRASTRUCTURE)
3. Classify severity (CRITICAL / HIGH / MEDIUM / LOW)
4. Calculate cost (real money lost, paper P&L impact, missed opportunities)
5. Trace root cause to specific file/line
6. Match to existing patterns above (or create new pattern)
7. Apply fix with verification (cat -A + AST parse + import test)
8. Add prevention rule to RULES.md if pattern is novel
9. Plan validation period (5+ trading days minimum)
10. Update STATE.md with bug status

---

## OPEN BUG SUMMARY (as of 2026-05-19)

| Bug ID | Severity | Category | Status |
|--------|----------|----------|--------|
| HH | HIGH | EXECUTION | Open, investigation needed |
| T | HIGH | CALCULATION | Open, module decision pending |
| 1 (validation) | CRITICAL | EXECUTION | Fix shipped, 30-day validation in progress |
| 3 (validation) | HIGH | MONITORING | Fix shipped (exit honesty), 30-day validation |

**Action items:**
- Bug HH: Add detailed logging at every executor stage
- Bug T: Decide F&O fate by 2026-06-01 (DECISIONS.md PD-001)
- Bug 1: Daily DB-vs-Dhan reconciliation cron (planned)

---

## NEXT REVIEW

Quarterly bug review (end of each calendar quarter):
1. Re-read all entries
2. Verify "RESOLVED" bugs haven't returned (especially Bug T pattern)
3. Update PATTERN ANALYSIS with new patterns observed
4. Promote PATTERNS to RULES.md if recurring

Last review: 2026-05-19 (initial)
Next review due: 2026-09-30 (Q3 close)

