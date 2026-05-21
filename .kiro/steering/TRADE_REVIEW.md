# TRADE_REVIEW.md — Daily Trade Post-Mortem

**Purpose:** Daily review of every closed trade. Forces honest evaluation: was setup correct, was execution clean, what to learn.

**Update rule:** Daily after market close (15 min). Append-only.

**Reading order:** RULES.md, STATE.md, WIN_RATE_TRACKING.md, TRADE_REVIEW.md (when reviewing recent trade quality)

**Author:** Vishal
**Last updated:** 2026-05-19 (template)

---

## DOCUMENT PURPOSE

After 60 days you have 60 entries showing patterns YOU don't see in real-time:
- Which setups you actually execute well
- Where slippage hurts more than expected
- Which sectors truly fit your scanner

Code optimization without trade-level review is guessing.

---

## DAILY TEMPLATE

### YYYY-MM-DD (DAY)

#### Trade Count Today

- vishal-live trades: _____
- swing-vishal-live trades: _____
- Paper trades: _____
- Total real money trades: _____

---

#### Per-Trade Review

##### Trade 1: SYMBOL DIRECTION

- Profile: _____
- Entry: _____ at _____ IST
- Exit: _____ at _____ IST
- Quantity: _____
- Net P&L: _____
- Confidence: _____
- Setup type: _____

WHY DID I PICK THIS?
- Score: _____ (out of 17 for intraday)
- Sector context: _____
- LLM rationale: _____

WHAT WENT RIGHT/WRONG?
- _____
- _____

WAS THE STOP CORRECT?
- YES / NO. Reason: _____

WAS EXECUTION CLEAN?
- Order fill: _____ (slippage Rs._____)
- Bug 1 reconcile triggered: YES/NO
- Bug 3 fill_status: _____
- DB matches Dhan: YES/NO

LESSONS:
- _____
- _____

GRADE: A / B / C / D
- A: Setup matched, execution perfect, won money
- B: Setup matched, execution OK, lost money (acceptable)
- C: Setup wrong OR execution slipped
- D: Should not have taken this trade

---

#### EOD Summary

- Total real money trades: _____
- Wins: _____
- Losses: _____
- Net P&L: _____
- Capital used: Rs. _____ of Rs. _____
- Daily loss limit status: __ % of Rs.900
- Bug events today: 0 / list
- System grade: A / B / C / D

#### Tomorrow Plan

- Continue cron unchanged: YES/NO
- Code change needed: YES (what?) / NO
- Watch list for tomorrow: _____

---

## SAMPLE FILLED DAY (REFERENCE)

### 2026-05-20 (Tuesday)

Trade Count: 2 vishal-live, 0 swing, 0 paper

##### Trade 1: INFY LONG

- Profile: vishal-live
- Entry: Rs.1194.05 at 9:32 IST
- Exit: Rs.1192.80 at 14:23 IST (SL hit)
- Quantity: 3 shares
- Net P&L: -Rs.4.50 after charges
- Confidence: 8
- Setup: BREAKOUT (RS-First v3)

WHY: Score 14/17. IT was top 3 sector pre-market. LLM cited "strong sector rotation play."

WHAT WENT WRONG:
- IT sector reversed at 11 AM (broader sentiment shift)
- INFY broke 1194 support at 14:00
- SL hit at 14:23

LESSONS:
- LLM didn't catch mid-session sector reversal
- Need: sector momentum re-check at 11 AM cron cycle
- Trade was valid at entry; market changed

WAS STOP CORRECT? YES (-1.8% from entry)

EXECUTION: Clean. LIMIT filled first try. SL placed. Bug 1 reconcile NOT triggered. Bug 3 fill_status: filled.

GRADE: B+ (rules followed, market disagreed, small loss acceptable)

##### Trade 2: IOC LONG

(Same structure)

---

#### EOD Summary

- Total real money: 2 trades
- Wins: 0, Losses: 2
- Net P&L: -Rs.45
- Capital used: Rs.8500 of Rs.15000
- Daily loss: 5% of Rs.900 limit
- Bug events: 0
- System grade: B+ (executed rules, no bugs)

---

## WEEKLY REVIEW (every Sunday)

### Week of YYYY-MM-DD

#### Trade Quality Distribution

- Grade A trades: _____ ( __ %)
- Grade B trades: _____ ( __ %)
- Grade C trades: _____ ( __ %)
- Grade D trades: _____ ( __ %)

#### Common Lessons This Week

- _____
- _____
- _____

#### Patterns Spotted

- _____

#### Action For Next Week

- _____
- _____

---

## MONTHLY REVIEW (end of month)

### Month: YYYY-MM

#### Total Trades & Quality

- Total: _____
- A grades: __ %
- B grades: __ %
- C grades: __ %
- D grades: __ %

#### Most Common Lesson Pattern

- _____

#### Setups That Worked

- _____ (___ % win rate, _____ trades)

#### Setups That Failed

- _____ (___ % win rate, _____ trades)

#### Decision Implications

- Continue: _____
- Reduce frequency: _____
- Eliminate: _____

#### Update To EDGE.md Required?

YES / NO. If yes: _____

#### Update To Scanner Required?

YES / NO. If yes: _____

---

## TIPS FOR EFFICIENT DAILY REVIEW

1. **5-min trade review max per trade** — be concise
2. **Be brutally honest in grading** — D trades teach more than A trades
3. **Skip if no real-money trades that day** — paper-only days are optional
4. **Use phone notes during day, transcribe at EOD** — don't rely on memory
5. **Don't perfect, document** — messy daily entry beats missing entry

---

## ANNUAL REVIEW

End of each year:
1. Re-read all monthly summaries
2. Identify your top 3 strategy strengths and weaknesses
3. Update EDGE.md based on lessons
4. Document in HISTORY.md

Last review: N/A
Next review due: 2026-12-31

---

## SIGNATURE

I commit to daily trade reviews because:
- Real money deserves honest evaluation
- Patterns hide in plain sight without documentation
- Future me cannot remember why I took trades from 90 days ago
- This is what real fund managers do

Vishal | 2026-05-19 | Founder, Principal Trader


---

## 2026-05-20 — TATASTEEL Post-Mortem

### Trade
- Symbol: TATASTEEL
- Direction: SHORT
- Entry: Rs.203.73 (intended 22 shares)
- Actual filled on Dhan: 44 shares (Bug A doubled)
- Manual exit: Rs.204.10 via Dhan app at 10:18 IST
- Net P&L: -Rs.38 after charges

### What Went Right
- LLM picked correctly: Metal sector weak (-0.53%), TATASTEEL momentum down -2.66%
- R:R 2.0, confidence 7, all gates passed
- User caught the bug within 18 minutes
- Daily loss cap Rs.500 NOT breached
- Manual close locked in bounded loss

### What Went Wrong
- Bug A: monitor opened SECOND SHORT (44 vs intended 22)
- 22 shares unprotected (only 22 covered by SL @ 207.80)
- System lied in logs: labeled SHORT trade as [LONG]
- Without manual intervention, loss could have been Rs.300+ if TATASTEEL spiked

### Process Lessons
- Real money exposes bugs paper hides
- User vigilance saved capital today
- Telegram alert for unexpected position would have helped
- Same pattern as upcoming Bug B (orphan SL) — exit/cleanup paths underbuild

### Strategy Lessons
- Pick was sound, execution was buggy
- Don't blame strategy when infrastructure fails
- This trade does NOT count toward win rate stats (bug-tainted)

### Action Taken
- Bug A patched same day (commit 5131cd6)
- Defensive warning added in monitor.py
- vishal-live continued trading after fix

---

## 2026-05-21 — HFCL Post-Mortem

### Trade
- Symbol: HFCL
- Direction: LONG (intended), then phantom SHORT (bug)
- Entry: Rs.144.93 x 31
- Target hit exit: Rs.145.27
- Phantom SHORT created at: ~Rs.143.76 x 31
- Manual close phantom: Rs.142.55 x 31
- Net P&L combined: +Rs.36.58 (lucky outcome)

### What Went Right
- LLM picked correctly: Infrastructure sector +0.78%, HFCL momentum +2.31%
- Volume 19.9M, exceptional liquidity
- R:R 2.0, target hit cleanly
- Bug A entry fix worked perfectly (no rogue duplicate at entry)
- Lucky direction on phantom SHORT (HFCL drifted down)
- User noticed phantom position via Dhan app

### What Went Wrong
- Bug B: original SL not cancelled when target hit
- Orphan SL fired at 142.25, created phantom SHORT
- 31 shares phantom SHORT had ZERO stop loss
- Trailing SL was fake — only updated memory, not Dhan order
- Could have lost Rs.150-300 if HFCL had spiked instead of drifted

### Process Lessons
- Two bugs in two days = pattern (entry then exit)
- Every order lifecycle must be code-traced (create → cancel/modify/fill)
- Don't trust Dhan auto-cleanup (slow, unreliable)
- EOD reconciliation script is now P0 priority

### Strategy Lessons
- LONG MOMENTUM with sector confirmation works (consistent with HINDPETRO, BPCL)
- Fast targets at 0.3-0.5% above entry hit reliably in NEUTRAL/bullish regimes
- Charges still eating most profit at Rs.4,500/trade scale
- Need bigger per-trade size or higher win rate to be net positive

### Action Taken
- Logged in BUGS_AND_FIXES.md
- Bug B fix scheduled tonight Thursday evening
- vishal-live continues uninterrupted
