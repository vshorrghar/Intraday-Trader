# DECISIONS.md — Strategic Decision Log

**Purpose:** Document major strategic decisions with full reasoning. Future you (and any AI) reads this to understand WHY current choices were made, preventing re-litigation during emotional moments.

**Update rule:** Append-only. Never delete. Add NEW decisions; mark old ones as "SUPERSEDED" if reversed.

**Reading order in steering:** RULES.md → STATE.md → EDGE.md → DECISIONS.md

**Author:** Vishal (founder, principal trader)
**Last updated:** 2026-05-19

---

## DECISION FORMAT

Each decision documented with:
- **Date** — when decided
- **Context** — what triggered the need
- **Options considered** — at least 2-3 alternatives
- **Decision made** — clear chosen path
- **Rationale** — WHY this option vs others
- **Cost / Benefit analysis** — money, time, risk
- **Reversibility** — how hard to undo
- **Status** — ACTIVE | SUPERSEDED | OBSOLETE

---

## DECISION 001: Use Personal AWS Isengard Account, Not Corporate

### Date: ~April 2026 (initial setup)

### Context
Need cloud infrastructure for project. Two options for AWS account:
- Personal Isengard (private, free credits)
- Work corporate AWS (visibility risk)

### Options Considered
A. Use corporate AWS (free, but exposed to manager via IT monitoring)
B. Use personal Isengard (free, hidden, but limited credits)
C. Pay for separate AWS account out of pocket

### Decision Made
**B — Personal Isengard account**

### Rationale
- Side project must stay invisible to corporate IT
- Personal Isengard is FREE for first 1 year ($1000 credits typical)
- AWS profile `vishal-admin` isolates project work
- No work email, no corporate IP, no Mac git pushes (Rule 1)

### Cost / Benefit
- Cost: Time to set up isolation (1 day initial)
- Benefit: Career protection, project freedom
- Risk: Credits run out → must transition to paid tier (estimated Rs.2K/month)

### Reversibility
HIGH — can migrate to paid AWS account in 1 day if needed

### Status: ACTIVE

---

## DECISION 002: One-Way Git Flow (EC2 → GitHub → Mac)

### Date: ~April 2026

### Context
Need to develop on multiple machines (EC2 for execution, Mac for review). Git push from Mac would trigger AWS IT monitoring.

### Options Considered
A. Push from Mac (triggers IT monitoring, exposes project)
B. Push only from EC2 (Mac becomes read-only)
C. Use SSH tunneling to hide pushes (technically complex, easy to break)

### Decision Made
**B — EC2 is source of truth, Mac is read-only mirror**

### Rationale
- Mac corporate machine; push activity visible to AWS IT
- EC2 personal account; any push from there is invisible
- Simpler workflow: edit on EC2 (heredoc per Rule 11), commit on EC2, push on EC2
- Mac just for code review via `git pull`

### Cost / Benefit
- Cost: Less convenient editing (no IDE on EC2)
- Benefit: Career safety, clear separation of concerns
- Time saved: 0 risk of accidental corporate exposure

### Reversibility
EASY — can switch to Mac-pushes if separate from corporate

### Status: ACTIVE (Rule 1 enforces this)

---

## DECISION 003: AI-Augmented, Not AI-Dependent Architecture

### Date: April 2026 (initial design)

### Context
LLMs are powerful but unreliable for trading. Pure rule-based systems are predictable but rigid. Need to choose architectural balance.

### Options Considered
A. Pure rule-based (no LLM, deterministic)
B. Pure LLM-driven (LLM picks stocks, system executes)
C. Hybrid: Python rules pre-filter, LLM ranks final candidates, Python validates

### Decision Made
**C — Hybrid: Python decides 90%, LLM final ranking only**

### Rationale
- LLM hallucinations could cost real money (gives bad rationale, picks bad stock)
- Python rules are deterministic and auditable
- LLM is good at synthesis (combining sector + technicals + news)
- Pre-filtering 30 → 20 candidates by Python ensures LLM doesn't see garbage
- Post-filtering with R:R 2.0 / confidence 7+ catches LLM mistakes
- Safety net: even if LLM fails, only 1-3 trades placed per session per profile

### Cost / Benefit
- Cost: More complex codebase than pure rule-based
- Benefit: Captures LLM upside without LLM downside
- Real cost: Bedrock API ~$5-20/month (~Rs.500-2000)
- Real benefit: Potential edge from synthesis no rule-based system has

### Reversibility
EASY — could disable LLM call, system falls back to top scanner picks

### Status: ACTIVE

---

## DECISION 004: Multi-Profile Architecture (4 Accounts, Not 1)

### Date: ~April-May 2026

### Context
Trading across multiple accounts requires architectural decisions about isolation.

### Options Considered
A. Single profile, multiple capital pools
B. Per-account separate codebases (4 forks)
C. Single codebase, per-profile config (yamls + DBs)

### Decision Made
**C — Single codebase, per-profile YAML + DB isolation**

### Rationale
- One bug fix benefits all profiles (Bug 1 fix was 1 commit, helped all 4)
- Independent capital limits, risk rules per profile
- Different VIX gates: live (20) vs paper (18)
- Per-profile DBs enable independent audit trails
- Profile switcher in dashboard handles UX
- Dhan API rule: separate IP per real-money account → 2 EC2s, but same code

### Cost / Benefit
- Cost: Multi-EC2 complexity (NEW EC2 for neha-live)
- Benefit: Clean isolation, no cross-contamination
- Risk: Profile YAMLs gitignored → manual sync between EC2s

### Reversibility
MEDIUM — would require consolidating 4 DBs into 1

### Status: ACTIVE (Rule 20 enforces multi-EC2 architecture)

---

## DECISION 005: Continuous 15-Min Scanning (vs Fixed Times)

### Date: 2026-05-14

### Context
Original cron: 9:25 AM, 12:00 PM, 1:30 PM (3 fixed scans/day). Missing mid-session breakouts (e.g., NLCINDIA +17% intraday).

### Options Considered
A. Keep 3 fixed times (current)
B. Continuous every 15 minutes (9:30 AM - 1:00 PM)
C. Continuous every 5 minutes (more granular, more noise)

### Decision Made
**B — Every 15 minutes, 9:30 AM to 1:00 PM IST**

### Rationale
- Catches mid-session breakouts that fixed times miss
- 5-min would over-trade and increase charges
- Late-session gates (after 11 AM) prevent revenge trading
- Profile max-trades cap (3/day live) prevents over-trading
- Idempotent: cron checks for active positions, skips if max hit

### Cost / Benefit
- Cost: 4x more cron runs, slightly higher Bedrock/Dhan API calls
- Benefit: Catch SAREGAMA-type mid-session opportunities
- Risk introduced: Bug 5 (max_trades counter not enforced) — found and fixed May 15

### Reversibility
EASY — revert to 3 fixed cron times if needed

### Status: ACTIVE (validated post-Bug 5 fix)

---

## DECISION 006: Subscribe to Dhan Data API (Rs.499/mo)

### Date: 2026-05-17

### Context
F&O option chain access requires paid Data API. Also unlocks historical OHLC for backtest engine. Without it, F&O paper P&L is synthetic.

### Options Considered
A. Continue without Data API (free tier only)
B. Subscribe Rs.499/month
C. Switch to Zerodha Kite Connect (Rs.2000/mo, more robust)

### Decision Made
**B — Subscribe Dhan Data API at Rs.499/month for vishal account only**

### Rationale
- Cheapest path to real option chain prices
- Unlocks historical OHLC for backtest engine
- Same broker, same auth, no migration cost
- Can backtest scanner improvements before deploying
- Real-time order endpoint for DB-vs-Dhan reconciliation

### Cost / Benefit
- Cost: Rs.499/month = Rs.5988/year
- Benefit: F&O has chance of working, backtest possible, broker truth available
- Note: neha account NOT subscribed (would be Rs.499/mo more)

### Reversibility
EASY — cancel subscription anytime

### Status: ACTIVE

### Side Effect Discovered (May 19)
Real-time order API enabled discovery of Bug 1 (8-symptom indent bug). This subscription has already paid for itself many times over by enabling broker reconciliation that exposed the most expensive bug in the project's history.

---

## DECISION 007: Capital Phase 1 — Rs.10K-15K Live Money Only

### Date: 2026-05-12 (first real money), updated 2026-05-14

### Context
Initial real money deployment. How much to risk?

### Options Considered
A. Rs.50K (aggressive, faster validation)
B. Rs.10K-15K (cautious, slower validation)
C. Rs.5K (extremely cautious, charges dominate)

### Decision Made
**B — Rs.10K initially, raised to Rs.15K on May 14**

### Rationale
- Real money mindset different from paper
- Worst case: lose Rs.900/day max (daily loss limit)
- Charges as % of trade size: ~1.1% on Rs.4500 trades — tolerable
- Below Rs.10K: charges destroy any edge
- Need to learn execution, bug discovery, real broker behavior
- Capital scaling rules (Phase 2 → 50K, Phase 3 → 2L, etc.) are proof-gated

### Cost / Benefit
- Cost: Slow income generation
- Benefit: Survival > speed; bug discovery possible without catastrophic loss
- Real cost so far: ~Rs.1500 cumulative loss across 5 trades

### Reversibility
EASY — can scale up or down based on validation data

### Status: ACTIVE (current Rs.15K live, will scale per proof gates)

---

## DECISION 008: Bug Fix Architecture for Bug 1 (Reconcile via get_positions)

### Date: 2026-05-19

### Context
Bug 1 caused duplicate orders + missing DB rows + unprotected positions. Indent bug at executor.py:198 fixed earlier, but second code path still bypassed SL+DB on MARKET retry.

### Options Considered
A. Add cancel-detection only (parse "Order Is Cancelled" message)
B. Reconcile via get_positions before MARKET retry
C. Switch to Dhan SuperOrder (eliminates need for separate SL placement)

### Decision Made
**B + A — Both reconcile AND cancel-detection (defense in depth)**

### Rationale
- get_positions is broker source of truth
- If LIMIT actually filled but wait_for_fill returned 0 (token expired), positions API will show it
- Cancel-detection catches the SECOND signal Dhan gives (error message)
- Two safety nets before duplicate order can fire
- SuperOrder migration is bigger refactor; keep for week 3-4

### Cost / Benefit
- Cost: 2 extra API calls per failed-fill scenario (rare)
- Benefit: Prevents duplicate orders, ETERNAL phantom trades, INFY 3.5x duplications
- Validation needed: 30 days of clean operation before trusting

### Reversibility
EASY — feature flag could disable reconcile, fall back to original

### Status: ACTIVE (commit 8b96b23, deployed 2026-05-19)

---

## DECISION 009: Swing Module — Pure Paper for First 4 Weeks

### Date: 2026-05-19

### Context
Building swing module tonight. Should --live flag be enabled in cron?

### Options Considered
A. Enable --live immediately for vishal-live (real CNC orders day 1)
B. Paper-only for all profiles for 4 weeks, then evaluate
C. Paper for 2 weeks, live for vishal-live week 3

### Decision Made
**B — Paper-only for 4 weeks, all profiles**

### Rationale
- Zero validation data on swing strategy
- Bug 1 just shipped, may have hidden similar bugs
- Investors Way claims 55-65% win rate — need to verify on Indian data
- Swing strategy unproven on our specific scoring
- Paper costs nothing, validates code paths
- Rule 25 (13-box pre-live gate) requires 4 weeks paper minimum

### Cost / Benefit
- Cost: Delayed real-money income from swing
- Benefit: Avoid catastrophic loss from undiscovered swing bugs
- Risk avoided: Day-1 real money on unvalidated edge thesis

### Reversibility
EASY — add --live to cron entry once 13-box gate passes

### Status: ACTIVE

---

## DECISION 010: Stop neha-live Trading (May 18)

### Date: 2026-05-18

### Context
Bug 1 caused TATASTEEL 4x duplication on neha-live, +Rs.469 actual loss vs Rs.66 reported. User direction: stop neha-live until bug fixed.

### Options Considered
A. Continue neha-live, fix bug post-hoc
B. Stop neha-live cron, keep vishal-live running
C. Stop both vishal-live and neha-live (full real money halt)

### Decision Made
**B — Stop neha-live, keep vishal-live**

### Rationale
- vishal-live had smaller exposure pattern, less affected
- neha-live had cleaner Bug 1 manifestation (4x duplication)
- Full halt would lose validation data for vishal-live
- Single-account testing simpler for bug investigation

### Cost / Benefit
- Cost: Lost Rs.10K capital deployment opportunity on neha-live
- Benefit: Reduced exposure during bug investigation
- Time: 2-3 days neha-live offline

### Reversibility
EASY — re-enable neha-live cron after Bug 1 validated

### Status: ACTIVE (neha-live STOPPED as of 2026-05-19)

---

## DECISION 011: F&O Module — Decision Pending

### Date: 2026-05-19

### Context
Bug T resurrected 3 times. BANKNIFTY P&L showing impossible Rs.92,025 (max possible was Rs.216). F&O paper data unreliable.

### Options Under Consideration
A. Rewrite F&O from scratch with different architecture (3 weeks)
B. Continue debugging Bug T (4th attempt, low confidence)
C. Kill F&O module entirely

### Decision Made
**PENDING — to be decided by 2026-06-01**

### Rationale (for delaying)
- Need to focus on intraday Bug 1 validation first
- Need swing module operational first
- F&O has no real money exposure (zero cost of delay)
- Can decide with cleaner head after current crises stabilize

### Status: PENDING DECISION

### Decision Trigger
Decide by June 1 when:
- Intraday Bug 1 validated 10+ days clean
- Swing module operational 1+ weeks paper
- Fresh perspective on architecture

---

## DECISION 012: Documentation Discipline (This Document Itself)

### Date: 2026-05-19

### Context
Without documented decisions, future versions of self (and AI assistants) will re-litigate every choice during emotional moments. War news, big losses, bug discoveries all create pressure to abandon current strategy.

### Options Considered
A. No formal decision log (current state pre-May 19)
B. Decisions in HISTORY.md only (chronological mix)
C. Dedicated DECISIONS.md (this file)

### Decision Made
**C — Dedicated DECISIONS.md, append-only**

### Rationale
- Decisions deserve dedicated structure
- HISTORY.md is for state archives, not strategic choices
- Append-only prevents revisionism
- Future self / AI / IA / RA can audit decision quality

### Cost / Benefit
- Cost: 10 minutes per decision documented
- Benefit: Prevents emotional re-litigation, audit trail, learning compound

### Reversibility
N/A — purely additive

### Status: ACTIVE (this document)

---

## PENDING DECISIONS (TO BE MADE)

### PD-001: F&O Module Future
**Trigger:** 2026-06-01
**Reference:** DECISION 011

### PD-002: neha-live Reactivation
**Trigger:** Bug 1 validated 5+ days clean on vishal-live
**Reference:** DECISION 010

### PD-003: Capital Scaling Rs.15K → Rs.30K
**Trigger:** Per Rule 25 / Phase 2 gates met
**Reference:** Capital Scaling Plan in RULES.md

### PD-004: Backup Broker (Zerodha Account)
**Trigger:** After 3 months of single-broker (Dhan) experience
**Reference:** EDGE.md "What could KILL this edge"

### PD-005: Telegram Alerts Wiring
**Trigger:** After swing module ships, before any --live deployment
**Reference:** Rule 25 gate item 10

---

## DECISION REVIEW PROTOCOL

Quarterly (end of each calendar quarter):
1. Re-read all ACTIVE decisions
2. Mark any as SUPERSEDED if reversed
3. Resolve any PENDING decisions
4. Document new decisions made during quarter
5. Update STATE.md with summary

Last review: 2026-05-19 (initial)
Next review due: 2026-09-30 (Q3 close)
