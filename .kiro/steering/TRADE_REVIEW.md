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

