# SYSTEM AUDIT — Capital Readiness Review
**Created:** 2026-05-22 (Fri), CET 9:00 AM
**Goal:** Decide go/no-go for scaling capital from 15K → ₹1-2L
**Premise:** Capital is available. Code maturity is the gate, not money.
**Deadline:** All findings + fixes complete before Monday 2026-05-25 market open

---

## Principle
This is not a feature plan. This is a pre-flight inspection. The system runs
real money. Every gap identified is a leak. Every leak is closed before more
capital is added.

The audit produces a single artifact: `SYSTEM_AUDIT_REPORT.md` — a verdict
document with priority-ranked findings. Kiro then executes fixes in priority
order. No deviation, no scope creep.

---

## Stage 0 — Preparation (10 min)
**Owner:** human
**When:** Friday afternoon CET (after Indian market close)

Steps:
1. Confirm Kiro's TASK 4 validator wrap-up is complete and committed
2. Tell Kiro to STOP all dashboard/narrative work
3. Read this plan, confirm scope, approve

Output: clean git state, Kiro idle, plan acknowledged.

---

## Stage 1 — Evidence Collection (15 min)
**Owner:** human runs script, reviewer reads output
**When:** Friday after Stage 0
**No code changes.**

Run: `bash /home/ec2-user/dev-sandbox/audit/run_evidence_dump.sh`

Captures:
- All execution-path Python files (scanner, selector, risk_manager,
  executor, monitor, dhan_broker)
- Config files (vishal-live.yaml + steering docs)
- DB schema for intraday_trades
- Last 50 trades with full fields (vishal-live + vishal paper + neha paper)
- Aggregate stats per strategy / outcome / symbol
- Bedrock costs log
- Last 3 days of executor logs
- Cron schedule

Output: `audit/evidence_.txt`

---

## Stage 2 — Systematic Review (90-120 min, async)
**Owner:** reviewer (no Kiro action)
**When:** Friday afternoon CET

The reviewer reads the evidence dump and produces `SYSTEM_AUDIT_REPORT.md`
with these sections:

### 2.1 System Map
Module-by-module: inputs, outputs, side effects, failure modes.
Include data flow diagram (text-based).

### 2.2 Strategy Layer Assessment
- What signal is being traded? Document the actual entry rule from code,
  not from documentation.
- What is the claimed edge? What independent evidence supports it?
- What is the exit logic? Compare stated vs actual behavior in code.
- Cross-reference last 50 trades: does observed behavior match
  documented strategy? Identify divergence.

### 2.3 Statistical Viability
Compute from last 50 vishal-live + 50 vishal-paper + 50 neha-paper trades:
- Win rate by strategy_type
- Avg win, avg loss, profit factor
- Charge ratio (charges / |gross PnL|)
- Expectancy per trade after charges
- Required win rate at current avg-win/loss to break even after charges
- Comparison vs random-entry baseline (50% WR, same R:R, same charges)

Verdict: does the system have statistical edge or not?

### 2.4 Risk Architecture
- Position sizing logic — fixed %, volatility-aware, or arbitrary?
- Daily loss limit — coded? enforced? tested?
- Per-symbol re-entry limit — coded? enforced?
- Consecutive-loss circuit breaker — present?
- Correlation risk — what happens if 5 LONG trades all in same sector
  during sector selloff?
- Margin/balance verification before entry?
### 2.4-bis Capital Scalability Assessment
Concrete evidence from compute_daily_pnl backfill (committed 38676cc):
At Rs.15K capital, charge_ratio_pct on representative days exceeds 100%
(e.g. vishal-live 2026-05-21: gross +Rs.116.56, charges Rs.156.57 = 134%).
This makes the strategy structurally unprofitable at current capital
regardless of win rate.

Reviewer must answer with evidence from code:

A) Are position sizes computed as a fraction of capital, or based on
   hardcoded rupee floors / qty floors?
   Run: grep -rn "capital|qty.*[0-9]|risk_per_trade" intraday/
   Document every hardcoded rupee or qty value found.

B) If capital is changed in profile YAML from 15K to 1L, what changes
   in observed behavior?
   - Position sizing: linear, capped, or floored?
   - Number of trades per day: same, more, or different mix?
   - SL/TP distances: same % or same rupees?
   - Any branch that says "if capital < X" or "if qty < X"?

C) Is there ANY logic that would behave differently between paper and
   live profiles based on capital alone (not the live/paper flag)?

D) What is the MINIMUM capital at which charge_ratio_pct drops below 30%
   given current position sizing and trade frequency? Compute from
   existing trade data (sum charges across last 14 days, sum gross,
   solve for capital that brings ratio to 30%).

E) What architectural changes are needed to make the system truly
   capital-agnostic? Itemize as P1 fix-list candidates with effort
   estimates in minutes.

Verdict format at end of section:
- "Capital-agnostic today: YES / PARTIAL / NO"
- "Refactor to fully agnostic: N hours of P1 work"
- "Minimum viable capital for current config: Rs.X"
- "Recommended capital for stable profit at current edge: Rs.Y"
- "Hard rupee values found that must become %: [list]"

This becomes a P1 deliverable in SYSTEM_AUDIT_REPORT.md, not P0.
P0 is reserved for capital-RISK bugs (orphan SLs, wrong SL placement).


### 2.5 Execution Layer
- Order lifecycle: every place_order matched to cancel + fill paths
- Race conditions between scanner / executor / monitor
- What happens on:
  - Broker API timeout mid-place
  - EC2 reboot with open positions
  - Network partition during exit
  - Duplicate fills from broker side
- Bug A / B / B-2 / C — find root pattern, not just instances

### 2.6 Data Integrity
- DB single-row trade model vs broker leg model — list every gap
- Atomic writes? Foreign key integrity?
- check_dhan_orders.py false positives — confirm fix path
- Orphan-order detection — how the system would catch a Bug B-N event
  WITHOUT human eyeball

### 2.7 Operational Discipline
- Cron coverage — when does which job run?
- What happens if a job fails silently?
- Backup / recovery — DB corruption scenario?
- Secrets management — Dhan tokens, AWS creds — rotation policy?
- Deployment — how does code reach EC2? Is it auditable?

### 2.8 Findings — by Severity
- **P0 (capital-risk):** must fix before adding any capital
- **P1 (edge-risk):** strategy/risk gaps that prevent profit
- **P2 (operational):** scaling/maintenance issues
- **P3 (nice-to-have):** logged but deferred

Each finding documents:
  - Title
  - Evidence (file:line or query result)
  - Severity rationale
  - Concrete fix description
  - Estimated engineering effort (minutes)

### 2.9 Capital Readiness Verdict
- Current state: ready for X capital
- After P0 fixes: ready for Y capital
- After P0+P1 fixes: ready for Z capital
- Conditions / gates for each tier

### 2.10 Prioritized Fix List for Kiro
Ordered by P0 → P1 → P2.
Each item: title, file(s), exact change, test to verify.
Format suitable for Kiro to execute one-by-one without ambiguity.

---

## Stage 3 — Kiro Execution (Friday evening + Saturday + Sunday)
**Owner:** Kiro, supervised by human

### Rules of execution
1. Kiro reads `SYSTEM_AUDIT_REPORT.md`, executes P0 items first, IN ORDER.
2. After each P0 item: commit, run regression check, report back. Wait for
   human approval before next item.
3. P1 items only start after ALL P0 items are merged and verified.
4. P2 items only start after ALL P1 items merged.
5. NO scope creep. If Kiro finds a new bug during fix work, log it as P-NEW
   in BUGS_AND_FIXES.md, do not fix in this cycle.
6. Every fix has a verification test — either a passing query, a paper trade
   reproducing the scenario, or a unit test if applicable.

### Commit message format
`audit-fix(P0-1):  — verified by <test>`

### Branch strategy
All audit fixes on branch `audit-2026-05-22`. Merged to main only after full
verification. If anything breaks, revert the whole branch.

---

## Stage 4 — Verification Day (Sunday evening)
**Owner:** human + Kiro

1. Re-run evidence dump script — diff against Friday's
2. Re-run statistical viability calculations
3. Confirm all P0 fixes present in main
4. Run a paper-mode end-to-end test (1 trade through full lifecycle)
5. Re-run check_dhan_orders.py — 0 mismatches expected
6. Verify orphan-detection cron fires correctly via injected test scenario

If all green: Monday market open with ₹50K (NOT full ₹1L on day 1).

If anything red: STOP. Stay at 15K. Re-plan.

---

## Stage 5 — Capital Ramp Plan (post-audit)
Only triggered if Stage 4 passes.

- Week 1 (May 26 – May 30): ₹50K live (not full ₹1L). Watch for any
  symptom not seen at 15K. Daily reconciliation.
- Week 2 (June 2 – June 6): If clean, scale to ₹1L. If any P0-class
  symptom appears, halt and patch.
- Week 3+: Hold ₹1L until 50+ trades validate edge. Then consider ₹2L.

---

## Out of Scope (deferred)
- Narrative validator dashboard surfacing (Phase 3 of TASK 4)
- F&O strategy improvements
- Swing strategy optimization
- New broker integrations
- UI / dashboard polish

These wait until capital readiness is established.

---

## Definition of Done (this audit)
- [ ] evidence_<DATE>.txt generated and reviewed
- [ ] SYSTEM_AUDIT_REPORT.md committed to repo
- [ ] All P0 findings have a commit fixing them
- [ ] All P0 findings have a verification artifact
- [ ] BUGS_AND_FIXES.md updated with every finding (closed and deferred)
- [ ] Stage 4 verification day passed
- [ ] Capital ramp plan agreed in writing
- [ ] Reviewer + human sign off in this file at the bottom

---

## Sign-off Log
(Append entries here as stages complete.)

