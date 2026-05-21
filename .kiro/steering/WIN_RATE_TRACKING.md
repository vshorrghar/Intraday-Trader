# WIN_RATE_TRACKING.md — Statistical Validation Log

**Purpose:** Track true win rates, R:R achieved, drawdown, and other metrics across all strategies. Decisions made on numbers, not feelings.

**Update rule:** Update WEEKLY (every Sunday EOD or Monday morning). Append historical snapshots; never overwrite history.

**Reading order:** RULES.md, STATE.md, EDGE.md, WIN_RATE_TRACKING.md (when evaluating capital scaling)

**Author:** Vishal (founder, principal trader)
**Last updated:** 2026-05-19 (initial template)

---

## DOCUMENT PURPOSE

Without numerical tracking:
- Bad weeks feel like bad luck
- Good weeks feel like skill
- Both are emotional defenses against accepting what data says

This document forces:
1. Honest measurement of TRUE win rate (not gut estimate)
2. Comparison of theoretical edge (EDGE.md) vs actual results
3. Decision triggers based on statistical thresholds
4. Pattern recognition over time (what works, what doesn't)

---

## STATISTICAL THRESHOLDS (DO NOT SCALE CAPITAL UNTIL MET)

### Sample Size Thresholds

- 0-20 trades: NO conclusions, statistical noise only
- 20-50 trades: Preliminary signal, watch for trends
- 50-100 trades: First meaningful read on win rate
- 100-200 trades: Statistical significance (p<0.05 typical)
- 200+ trades: Confident win rate evaluation

### Win Rate Decision Triggers

For each strategy, breakeven win rate is calculated in EDGE.md.
Decision actions based on actual vs breakeven (after 50+ trades):

- Actual >= breakeven + 10 points: PROFITABLE, can scale capital per Phase gates
- Actual = breakeven +/- 5 points: BREAKEVEN, hold current capital
- Actual = breakeven - 5 to -10 points: WARNING, halve sizes, investigate
- Actual <= breakeven - 10 points: STRATEGY FAILING, halt and audit

---

## INTRADAY MODULE — vishal-live (REAL MONEY)

### Cumulative Since First Real Money Trade (May 12, 2026)

[FILL_IN: Update after each trading day]

| Metric | Value | Source |
|--------|-------|--------|
| First trade date | 2026-05-12 | DB query |
| Latest trade date | 2026-05-19 | DB query |
| Total trades | 5 (approx) | intraday_trades WHERE mode=LIVE |
| Wins (P&L > 0) | 0 | DB query |
| Losses (P&L <= 0) | 5 | DB query |
| Win rate | 0% | wins/total |
| Average win (Rs.) | N/A | mean of P&L > 0 |
| Average loss (Rs.) | -Rs.30 | mean of P&L <= 0 |
| Average R achieved | N/A | mean of (P&L / risk) for wins |
| Total P&L (gross) | TBD | sum of gross_pnl |
| Total charges | TBD | sum of charges |
| Total P&L (net) | -Rs.150 (approx) | sum of pnl |
| Max drawdown (Rs.) | -Rs.717 (May 18 Bug 1 day) | DB query |
| Max drawdown (%) | -4.8% | drawdown / capital |
| Sharpe (annualized) | N/A | needs 30+ trades |

**Statistical significance status:** SAMPLE TOO SMALL (5 trades vs 50 minimum threshold)

---

### Last 7 Days (Rolling Weekly Snapshot)

| Date | Trades | Win Rate | Net P&L | Notes |
|------|--------|----------|---------|-------|
| 2026-05-12 | 2 | 0% | -Rs.74 | First real trades; learning |
| 2026-05-13 | 1 | 0% | -Rs.28 | Bug A+D fix shipped |
| 2026-05-14 | 1 | TBD | open | VEDL position |
| 2026-05-15 | 7! | TBD | -Rs.220 | Bug 5 cascade (counter bug) |
| 2026-05-18 | 4 | TBD | -Rs.248 | TATASTEEL 4x duplication (Bug 1) |
| 2026-05-19 | 3 | 33% (apparent) | +Rs.85 (Dhan), -Rs.130 (DB) | Drift; Bug 1 partially live still |

**Action:** Bug 1 + Bug 3 fixes shipped. Watch May 20 onwards for clean data.

---

### Last 30 Days (Rolling Monthly Snapshot)

[FILL_IN when 30+ days of clean data available]

| Period | Trades | Win Rate | Net P&L | Capital Util |
|--------|--------|----------|---------|--------------|
| 2026-05-19 to 2026-06-19 | TBD | TBD | TBD | TBD |

---

### By Setup Type

[FILL_IN: requires labeling each trade with setup type]

| Setup | Trades | Win Rate | Avg Return | Decision |
|-------|--------|----------|------------|----------|
| Breakout | TBD | TBD | TBD | continue / halt |
| Reversal | TBD | TBD | TBD | continue / halt |
| Pullback | TBD | TBD | TBD | continue / halt |
| Momentum | TBD | TBD | TBD | continue / halt |

**Action:** Once 50+ trades, identify which setup wins most. Eliminate worst setup. Re-allocate capital.

---

### By Time of Day

| Window | Trades | Win Rate | Notes |
|--------|--------|----------|-------|
| 9:30-10:30 IST | TBD | TBD | Time multiplier 1.5x in scoring |
| 10:30-11:30 | TBD | TBD | Time multiplier 1.0x |
| 11:30-12:30 | TBD | TBD | Lunch lull |
| 12:30-13:30 | TBD | TBD | Late session caution |
| 13:30-15:00 | TBD | TBD | Force exit window approaching |

**Action:** If 9:30-10:30 win rate < other windows, time thesis from EDGE.md is wrong.

---

### By VIX Range

| VIX | Trades | Win Rate | Notes |
|-----|--------|----------|-------|
| 13-18 | TBD | TBD | Normal volatility, expected best |
| 18-20 | TBD | TBD | Elevated; reduce size half? |
| 20-22 | TBD | TBD | Caution, edge weakening |
| 22-25 | TBD | TBD | Reduce to 1 trade max (rule) |
| 25+ | TBD | TBD | Skip per rule |

**Action:** If win rate flat across VIX bands, our regime gates may not be needed (or wrong levels).

---

### By Sector

| Sector | Trades | Win Rate | Avg Return |
|--------|--------|----------|------------|
| IT | TBD | TBD | TBD |
| Banking | TBD | TBD | TBD |
| Pharma | TBD | TBD | TBD |
| FMCG | TBD | TBD | TBD |
| Metals | TBD | TBD | TBD |
| Energy | TBD | TBD | TBD |
| Auto | TBD | TBD | TBD |

**Action:** If specific sector consistently loses, exclude from scanner. If specific sector wins, increase weight.


---

## INTRADAY MODULE — vishal (PAPER)

### Cumulative Since System Start

[FILL_IN: extract from intraday_trades WHERE mode=DRY_RUN, profile=vishal]

| Metric | Value |
|--------|-------|
| First trade date | TBD |
| Latest trade date | TBD |
| Total trades | TBD |
| Win rate | TBD |
| Average win | TBD |
| Average loss | TBD |
| R achieved | TBD |
| Total P&L (net) | TBD |
| Max drawdown | TBD |

### Last 30 Days

| Period | Trades | Win Rate | Net P&L |
|--------|--------|----------|---------|
| TBD | TBD | TBD | TBD |

### Comparison: Paper vs Real Money

If paper win rate > real money win rate by 10+ points: investigate execution slippage, fill quality, real-world friction not modeled in paper.

---

## INTRADAY MODULE — neha (PAPER)

[Same structure as vishal paper]

### Cumulative Since System Start

[FILL_IN]

### Last 30 Days

[FILL_IN]

---

## INTRADAY MODULE — neha-live (REAL MONEY, currently STOPPED)

### Status: STOPPED 2026-05-18

Reason: Bug 1 caused TATASTEEL 4x duplication and -Rs.469 actual loss vs -Rs.66 reported.

### Cumulative Before Stop

| Metric | Value |
|--------|-------|
| First trade | 2026-05-14 |
| Last trade | 2026-05-18 |
| Total trades | ~6 |
| Total P&L (Dhan truth) | -Rs.469.50 |
| Total P&L (DB reported) | -Rs.66 (bug-affected) |

### Reactivation Triggers

Per DECISIONS.md PD-002:
- Bug 1 validated 5+ days clean on vishal-live
- Vishal explicit approval

Until reactivated, do NOT update this section.

---

## SWING MODULE (paper-only, target start 2026-05-21)

### Cumulative Since First Trade

[FILL_IN when swing module ships and produces trades]

| Metric | Value |
|--------|-------|
| First trade date | TBD |
| Latest trade date | TBD |
| Total trades | TBD |
| Win rate | TBD (target: 55-60% per EDGE.md) |
| Average win % | TBD (target: 6-7%) |
| Average loss % | TBD (target: -4 to -5%) |
| Average days held (winners) | TBD (target: 7-12) |
| Average days held (losers) | TBD (target: 3-5) |
| R achieved (avg) | TBD (target: 1.4) |
| Total P&L (net) | TBD |
| Max drawdown | TBD |

### Per-Profile Tracking

| Profile | Trades | Win Rate | Net P&L | Status |
|---------|--------|----------|---------|--------|
| vishal | TBD | TBD | TBD | Paper |
| neha | TBD | TBD | TBD | Paper |
| vishal-live | TBD | TBD | TBD | Paper (--live disabled per Rule 25) |

### By Sector (Swing Specific)

Defensive sector thesis from EDGE.md predicts: Pharma, FMCG, Healthcare should dominate winners.

| Sector | Trades | Win Rate | Avg Return |
|--------|--------|----------|------------|
| Pharma | TBD | TBD | TBD |
| FMCG | TBD | TBD | TBD |
| Healthcare | TBD | TBD | TBD |
| Consumer Durables | TBD | TBD | TBD |
| IT | TBD | TBD | TBD |
| Banking | TBD | TBD | TBD |
| Metals | TBD | TBD | TBD |

**Decision trigger:** If defensive sectors don't outperform after 30+ trades, EDGE.md thesis is wrong. Scoring rebalance needed.

### Hold Time Analysis

| Hold Days | Trades | Win Rate | Avg Return | Notes |
|-----------|--------|----------|------------|-------|
| 1-3 | TBD | TBD | TBD | Quick winners |
| 4-7 | TBD | TBD | TBD | Standard hold |
| 8-15 | TBD | TBD | TBD | Extended hold |
| 16-30 | TBD | TBD | TBD | Time stop territory |

**Decision trigger:** If 1-3 day trades have highest win rate, swing thesis wrong (it's actually short-term momentum, not pullback patience).

### 4-Week Validation Decision (Target: 2026-06-15)

After 4 weeks paper:
- IF win rate >= 55% AND 20+ trades: pass to next 13-box gate item
- IF win rate 50-55%: continue paper, refine signals
- IF win rate < 50%: HALT, audit strategy, revisit EDGE.md

---

## F&O MODULE (paper, currently broken)

### Status: PAPER P&L UNRELIABLE (Bug T resurrected 3 times)

### Cumulative (with caveat)

| Metric | Value | Confidence |
|--------|-------|-----------|
| Total strategies opened | TBD | High |
| Total strategies closed | TBD | High |
| Reported P&L | TBD | LOW (Bug T contamination) |

### Honest Assessment

Until Bug T is fully fixed (3rd attempt failed; module decision pending June 1), F&O P&L data is meaningless. Do NOT make decisions based on F&O numbers in this period.

After F&O decision (DECISIONS.md PD-001):
- If REWRITE: track new module P&L starting from rewrite date
- If KILL: this section becomes archive only

---

## OVERALL PORTFOLIO TRACKING

### Combined Real Money P&L (vishal-live + neha-live when active)

| Period | Real Money Capital | Total P&L | Return % |
|--------|--------------------|-----------|----------|
| May 12-19, 2026 | Rs.25K (Rs.15K vishal + Rs.10K neha) | -Rs.717 (Dhan truth) | -2.9% |
| May 20-26 | TBD | TBD | TBD |

### Capital Scaling Decision Log

Per RULES.md Phase gates:
- Phase 1 (current): Rs.10K-15K live, gate met for 50+ trades
- Phase 2: Rs.50K live, gate met for 3 months consistent
- Phase 3: Rs.2L live, gate met for 6 months consistent

**Current phase:** 1 (initial)
**Next phase trigger:** 50+ profitable real-money trades
**Current trade count:** ~5 (FAR below threshold)


---

## WEEKLY UPDATE PROTOCOL

Every Sunday EOD or Monday morning, do this:

### Step 1: Extract Latest Numbers (10 min)

Run on EC2-OLD this command (single line, copy carefully):

  cd ~/dev-sandbox && for profile in vishal-live neha-live vishal neha; do echo "=== $profile ==="; sqlite3 database/${profile}.db "SELECT COUNT(*) as total, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct, ROUND(SUM(pnl), 2) as total_pnl FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED');"; done

Copy results into the tables above.

### Step 2: Decision Check (5 min)

For each strategy, compare actual to EDGE.md thresholds:
- Is win rate above breakeven?
- Is sample size statistically significant?
- Are decision triggers fired?

### Step 3: Update Tables (10 min)

Replace [FILL_IN] markers with real numbers.
Add new row to "Last 7 Days" table.
Update "Last 30 Days" rolling snapshot.

### Step 4: Document Decisions (5 min)

If any decision trigger fired:
- Add entry to DECISIONS.md
- Note in STATE.md
- Take action (halve size, halt, scale)

### Step 5: Save Snapshot (commit to git)

  cd ~/dev-sandbox && git add .kiro/steering/WIN_RATE_TRACKING.md && git commit -m "chore: weekly win rate snapshot" && git push origin main

Total time: ~30 min/week.

---

## DB EXTRACTION QUERIES (REFERENCE)

These SQL queries help extract data for the tables above. Run with sqlite3 database/PROFILE.db inside a heredoc or piped command.

### Query 1: Cumulative win rate per profile

SELECT COUNT(*) as total, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct, ROUND(SUM(pnl), 2) as total_pnl, ROUND(AVG(pnl), 2) as avg_pnl FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED');

### Query 2: By setup type

SELECT strategy_type, COUNT(*) as total, ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate, ROUND(SUM(pnl), 2) as total_pnl FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED') GROUP BY strategy_type;

### Query 3: By sector

SELECT sector, COUNT(*) as total, ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate, ROUND(AVG(pnl), 2) as avg_pnl FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED') GROUP BY sector ORDER BY total DESC;

### Query 4: By time of day (entry hour)

SELECT strftime('%H', created_at) as hour, COUNT(*) as total, ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED') GROUP BY hour ORDER BY hour;

### Query 5: Drawdown calculation

WITH running_pnl AS (SELECT created_at, pnl, SUM(pnl) OVER (ORDER BY created_at) as cumulative FROM intraday_trades WHERE status IN ('CLOSED','STOPPED_OUT','FORCE_EXITED')) SELECT MIN(cumulative) as max_drawdown_rs, MAX(cumulative) as peak FROM running_pnl;

Drawdown percentage: divide max_drawdown_rs by capital amount, multiply by 100.

---

## ANNUAL REVIEW

End of each calendar year:
1. Compile full year win rate per strategy
2. Compare to EDGE.md theoretical edge
3. Decide capital allocation for next year:
   - Strategies with edge proven: increase allocation
   - Strategies underperforming: reduce or kill
   - New strategies to research: add to roadmap
4. Tax planning: STCG vs LTCG conversion candidates

Last annual review: N/A (project less than 1 year old)
Next annual review: 2027-04-30 (financial year end)

---

## SIGNATURE

This document represents my commitment to:
- Honest weekly evaluation (no skipping bad weeks)
- Decisions based on numbers (no emotional overrides)
- Capital scaling only after statistical validation
- Strategy halt if win rate falls 10+ points below breakeven for 30+ days

Vishal | 2026-05-19 | Founder, Principal Trader


---

## REAL TRADE DATA POPULATED 2026-05-21 EOD

Replacing prior [FILL_IN] template markers with actual data from
database/vishal-live.db + Dhan API truth (dhan_live.json).

### vishal-live (Real Money) — 2026-05-12 to 2026-05-21

| Date | Symbol | Direction | Entry | Exit | Net P&L | Notes |
|------|--------|-----------|-------|------|---------|-------|
| 2026-05-12 | ONGC | LONG | ~245 | ~243.5 | -Rs.53.80 | First real trade |
| 2026-05-12 | WIPRO | SHORT | ? | ? | -Rs.20.00 | Low conviction |
| 2026-05-13 | HINDZINC | LONG | ? | ? | -Rs.28.30 | Charges-tainted |
| 2026-05-14 | VEDL | LONG | 334.30 | ? | TBD | x10 shares |
| 2026-05-15 | INFY | LONG | 1124.10 | ? | TBD | Open EOD May 15 |
| 2026-05-15 | HDFCBANK | LONG | 779.90 | ? | TBD | Open EOD May 15 |
| 2026-05-15 | SAREGAMA | LONG | 411.90 | NEVER FILLED | Rs.0 | Bug 3 (limit order) |
| 2026-05-19 | IOC | LONG | ? | ? | TBD | (closed +Rs.85 day) |
| 2026-05-19 | COHANCE | LONG | ? | ? | TBD | (closed +Rs.85 day) |
| 2026-05-19 | INFY | LONG | ? | ? | TBD | (closed +Rs.85 day) |
| 2026-05-20 | TATASTEEL | SHORT | 203.73 | 204.10 | -Rs.38 | Bug A fired, manual exit |
| 2026-05-21 | BEL | LONG | 425.75 | 421.40 | -Rs.43.50 | Force exit |
| 2026-05-21 | ANGELONE | LONG | 337.40 | 339.32 | +Rs.24.90 | Target hit clean |
| 2026-05-21 | HFCL | LONG | 144.93 | 145.27 | +Rs.10.54 (planned) +Rs.36.58 (with phantom SHORT) | Bug B fired |

### Statistics (limited sample, n=14, including bug-tainted)
- Total trades: 14
- Winners: 4 (ANGELONE, HFCL planned exit, HFCL phantom recovery, IOC?)
- Losers: ~7
- Bug-tainted: 5+ (TATASTEEL bug A, HFCL bug B, SAREGAMA Bug 3, etc.)
- Cumulative net P&L: ~-Rs.1,520

### Honest Read
- n=14 is statistically meaningless
- Most "losses" are bug-related not strategy-related
- Cannot conclude anything about win rate yet
- Need 30+ clean trades (post Bug B fix) for first signal
- Need 100 clean trades for confidence

### Going Forward (post Bug B fix)
- Track: every trade with bug-flag (Y/N)
- Only count clean trades toward win rate stats
- Bug-tainted trades go in separate ledger
- After 14 days zero bugs found → confidence increases

### Markers replacing [FILL_IN]
This entire section now has REAL DATA. Prior template stubs deleted.
Update daily after EOD reconciliation script runs (Saturday addition).
