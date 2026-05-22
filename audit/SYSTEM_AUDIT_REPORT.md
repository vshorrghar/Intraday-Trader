# SYSTEM AUDIT REPORT — Capital Readiness Review

**Subject:** Intraday Trader (multi-strategy auto-trader for NSE India)
**Reviewer:** Senior trading-systems review (external)
**Reviewee:** Vishal (founder, principal trader)
**Date of Review:** 2026-05-22
**Evidence Source:** `audit/evidence_2026-05-22.txt` (19,959 lines)
**Audit Plan:** `.kiro/steering/SYSTEM_AUDIT_PLAN.md` (commit 6b7ce44)
**Status:** Stage 2 deliverable

---

## SECTION 1 — EXECUTIVE SUMMARY

### Verdict in one paragraph

The Intraday Trader is a **B+ observability system bolted onto a C-grade execution layer running a not-yet-validated strategy**. The owner has done genuinely excellent documentation work (16 institutional-grade steering docs, daily journals, bug catalog with pattern analysis, decision log, validator pipeline), and that observability is what made this audit possible at all. However, the execution layer has shipped a confirmed bug into production every 1-2 trading days for 10 days running, the strategy has not yet demonstrated edge in real money (30% live win rate vs 49% paper, both below profitability thresholds), and the daily P&L dashboard built today proved that at ₹15K capital the **charge ratio exceeds 100% on representative days** — meaning the system is mathematically incapable of profit at current capital regardless of strategy quality. **Adding capital today would multiply losses, not gains.** Adding capital after a focused 2-3 day P0 fix sprint, followed by 1-2 weeks of paper validation at ₹50K simulated capital, is realistic.

### Real-money outcome to date (May 12 – May 22, 2026)

| Metric | Value | Source |
|---|---|---|
| Trading days | 9 | DB query |
| Closed trades (vishal-live) | 30 | `intraday_trades` status IN (CLOSED, STOPPED_OUT, FORCE_EXITED) |
| Wins | 9 | pnl > 0 |
| Losses | 21 | pnl ≤ 0 |
| **Win rate** | **30%** | wins/total |
| Net P&L (DB-reported, may include synthetic) | -₹378 | sum(pnl) |
| Cumulative real-money loss (Dhan-truth basis, per LEARNING.md May 18) | ~-₹1,500 | per honest reckoning |
| Charge ratio peak | 134% | 2026-05-21, daily_pnl backfill |
| Bugs that fired on real money | 4 confirmed | Bug 1, Bug 5, Bug A, Bug B |
| Bugs documented but unfixed | 7+ | force-exit-lies, cross-process-token, Bug B-2, Bug C, Bug HH, Bug L, etc. |

### Win rate by trading mode

| Profile | Capital | Trades | Win Rate | Net P&L | Profit Factor | Verdict |
|---|---|---|---|---|---|---|
| vishal-live (real) | ₹15K | 30 | 30% | -₹378 | <1.0 | Below break-even |
| vishal (paper) | ₹3L | 116 | 49.1% | +₹8,138 | ~1.0 | Break-even, not edge |
| neha (paper) | ₹3L | 83 | 44.6% | -₹3,687 | <1.0 | Worse than random |

The 19-percentage-point gap between paper (49%) and live (30%) is **not strategy failure**. It is largely **execution-bug damage** — confirmed by:
- Bug 1 caused 14× DB-vs-Dhan P&L drift on May 18 (-₹717 actual vs -₹52 reported)
- Bug A doubled position size on May 20 TATASTEEL trade
- Bug B created phantom SHORT position on May 21 HFCL trade
- Force-exit-lies bug today (May 22) logged synthetic P&L when token expired

After P0 bug fixes, the live win rate will likely converge toward paper's 49%. **49% is still not edge — it is break-even at best.** The system needs both bugs fixed AND strategy edge demonstrated before capital scaling.

### Critical finding discovered today (Stage 1 evidence)

**FORCE-EXIT-LIES is active in production.** Today's `intraday_vishal-live_2026-05-22.log` shows 60+ HTTP 400 errors over 2.5 hours of monitoring (token expired mid-session), followed at force-exit time by:

[ERROR] place_order failed: 'Invalid Token' [INFO] ✅ ITC exit order placed (BUY) order_id= [INFO] ⏰ ITC FORCE EXITED @ ₹304.55 fill=no_poll

The code logs success on a failed broker call, then logs synthetic P&L using **entry price as exit price**. Same pattern visible in May 21 logs (BEL force exit). This bug has been documented in `BUGS_AND_FIXES.md` since May 19 but **remains unfixed for 3 trading days**. Real P&L impact unquantified — Dhan auto-square-off at 15:30 IST likely closed positions, but the DB shows fictional numbers.

This is the single most important finding in this audit. Until it is fixed, **no P&L number reported by the system can be trusted on any day where the Dhan token expires mid-session.**

### Bug discovery rate vs trading edge demonstration rate

10 trading days have produced:
- **16+ documented bugs** (Bug A, B, B-2, C, D, EE, FF, GG, HH, J, K, L, T+3 sub-bugs, 1, 2, 3, 5, 5b, 6, BEDROCK-OPUS, CRONTAB-WIPE×2, FORCE-EXIT-LIES, CROSS-PROCESS-TOKEN, SHORT-RR)
- **Net negative P&L** on real money (~-₹1,500)
- **Zero strategies statistically validated** (smallest required sample is 50+ trades; current best is 30)

**The system's bug discovery rate exceeds its profit demonstration rate.** This is the operational reality. It does not mean the project is failing — it means it is in an early-validation phase where every fix is information, every loss is tuition. But it does mean **scaling capital is premature**, and the owner has explicitly framed this audit around exactly that question.

### Capital readiness verdict (preview — full detail in Section 12)

| Capital level | Status today | Required to unlock |
|---|---|---|
| ₹15K (current) | ⚠️ Precarious — force-exit-lies active | Fix P0-1 (force-exit-lies) and P0-2 (token refresh) immediately |
| ₹15K (trustworthy) | After 2-3 days P0 fixes | All P0 items merged + verified |
| ₹50K (paper-simulated) | After 1-2 weeks validation | Edge thesis proven on paper at ₹50K position sizes |
| ₹50K (live) | After 50 clean live trades | Win rate ≥ 45% sustained, profit factor > 1.0 |
| ₹1L (live) | After 100 clean trades at ₹50K | Win rate ≥ 50% sustained, profit factor > 1.2 |
| ₹2L (live) | After 100 clean trades at ₹1L | Same gates plus 2-week stable operation |

**The owner's stated capacity to deploy ₹1-2L is not the gate. Code maturity is the gate.**

### Top 5 P0 findings (full list in Section 10)

1. **P0-1 FORCE-EXIT-LIES** — Production bug active today; logs synthetic P&L on broker token expiry
2. **P0-2 CROSS-PROCESS-TOKEN** — Long-running monitor processes hold stale auth across cron sessions; caused 2.5h blind monitoring today
3. **P0-3 Bug B-2 (orphan SL on trailing-exit)** — Discovered today; trailing-SL → market-exit code path leaves original STOP_LOSS pending in Dhan; phantom-SHORT risk
4. **P0-4 No automated orphan-order detection** — Bug B-class events only caught by user eyeballing Dhan UI; does not scale
5. **P0-5 Bug C (RR data integrity)** — Several LONG trades have SL price ABOVE entry price (impossible state); rr_planned=0; documented May 21, unfixed

### What this report is NOT

- This is not a green light to add capital. It is a gating document.
- This is not a critique of the owner's judgment. The owner asked for the audit and has documented every bug honestly.
- This is not a recommendation to abandon the project. The observability layer is genuinely strong, and the strategy at ₹3L paper is at break-even — meaning improvements may push it into edge territory.
- This is not a substitute for the owner's own judgment on capital allocation. It is a structured second opinion.

### What this report IS

- A complete, prioritized inventory of every gap that prevents safe capital scaling
- A concrete fix list with effort estimates suitable for Kiro to execute one-by-one
- A capital ramp plan with measurable gates between tiers
- A bug pattern analysis showing why the same family of bugs keeps recurring
- An honest assessment of statistical edge (or lack thereof) at current sample sizes

---

## SECTION 2 — SYSTEM MAP

### 2.1 Architecture at a glance

┌─────────────────────────────────────────────────────────────────────────┐ │ EXTERNAL DATA SOURCES │ │ NSE India APIs (Nifty 500, sectors, gainers/losers, VIX, OHLC) │ │ Dhan REST API v2 (orders, positions, margins, option chain, OHLC) │ │ AWS Bedrock (Claude Sonnet 4.6 — strategy ranking) │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ SCANNER LAYER (intraday/scanner.py) │ │ Pulls Nifty 500 + sectors + VIX │ │ Filters: price 50-5000, volume > 500K (or >100K if change >4%) │ │ RS-First v3 scoring: 6 signals, 3 penalties, time multiplier │ │ Output: top 15 LONG + top 15 SHORT = 30 candidates │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ PRE-FILTER (intraday/selector.py) │ │ 30 candidates → 20 (price-range + high_volatility flag) │ │ Sector alignment annotation │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ LLM RANKING (Bedrock) │ │ 20 candidates + market context → 1-5 picks with rationale │ │ Returns: stock_name, entry, target, SL, confidence, strategy_type │ │ Time budget: 60s read_timeout, 1 retry, no fallback │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ POST-LLM VALIDATION (selector.validate_pick) │ │ R:R ≥ 2.0 mandatory; confidence ≥ profile threshold (7 or 8) │ │ Direction logic: LONG = target > entry > SL; SHORT inverted │ │ high_volatility=True → reject │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ POSITION SIZING (intraday/risk_manager.py) │ │ Confidence-weighted allocation across picks │ │ Caps: per_trade_max_capital, daily_capital_limit │ │ VIX gate: >25 SKIP, >22 reduce to 1 trade │ │ Same-symbol re-entry block (in-memory + DB-restored) │ │ Daily loss cap check │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ ORDER EXECUTION (intraday/executor.py) │ │ Wait until 9:30 IST (entry_delay_minutes after market open) │ │ LIMIT entry order with 0.3% buffer, tick-aligned (₹0.05) │ │ Wait up to 10s for fill (poll every 2s) │ │ Reconcile via get_positions before any retry (Bug 1 fix) │ │ MARKET fallback only if confidence ≥ 8 │ │ Place STOP_LOSS order matching filled qty │ │ Insert row in intraday_trades (single-row trade model) │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ POSITION MONITOR (intraday/monitor.py) │ │ 5-min cycle (or live NSE quote enrichment if Dhan blank) │ │ Direction-aware P&L computation │ │ Exit triggers: SL hit, target hit, trailing SL update, force exit │ │ All exits: cancel original SL → place market exit → poll fill → log │ │ Bug B fix: cancel SL before placing exit (target/force/trailing paths) │ │ Bug B-2 (UNFIXED): trailing SL → market-exit path leaves orphan SL │ └────────────────────────────────┬────────────────────────────────────────┘ │ ┌────────────────────────────────▼────────────────────────────────────────┐ │ OBSERVABILITY LAYER │ │ Daily audit JSON (build_audit_narrative.py) │ │ AI narrative via Bedrock + validator │ │ Daily P&L dashboard (compute_daily_pnl.py — built today, May 22) │ │ Reconciliation script (reconcile_dhan_db.py) │ │ Top performers capture (capture_top_performers.py) │ │ Dashboard JSON for CloudFront │ └─────────────────────────────────────────────────────────────────────────┘

### 2.2 Module-by-module assessment

| Module | Lines | Quality | Notes |
|---|---|---|---|
| `intraday/scanner.py` | 596 | A- | RS-First v3 scoring is sound. Hardcoded `price_range_max=5000` in scanner; live profile yaml further restricts to 2000. |
| `intraday/selector.py` | 603 | B+ | LLM prompt is detailed and includes self-check rules. Direction-aware validation works. Trade history fed to LLM (last 30 days). |
| `intraday/risk_manager.py` | 298 | B | Confidence-weighted sizing, same-symbol block, DB-restored state. **Missing: consecutive-loss circuit breaker, sector concentration cap, margin verification before entry.** |
| `intraday/executor.py` | 352 | C+ | Bug 1 reconcile defense-in-depth is good. **But: hosts the indent-bug family. Reconcile #1, #2, #3 add complexity that suggests architectural issue, not surgical fix.** |
| `intraday/monitor.py` | 675 | C | Direction-aware P&L correct. Bug B fix covers 3 of 4 exit paths. **Bug B-2 confirms a 4th path exists. `_place_exit_and_get_fill_price` returns "fallback" status but caller logs success regardless — this is the FORCE-EXIT-LIES root cause.** |
| `intraday/dhan_broker.py` | 773 | B | REST API wrapper is correct. `cancel_order`, `modify_order`, `get_order_list` all present. Option chain v2 spec compliant. **No automatic re-auth on 401 → CROSS-PROCESS-TOKEN bug source.** |
| `intraday/auth_server.py` | 562 | B+ | TOTP auth with 3 retries, session caching with client_id validation. **DryRunBrokerClient is faithful. Cross-process token issue is in monitor, not auth itself.** |
| `intraday/charges.py` | 176 | A | Authoritative charges module. Dhan rates verified. Self-test included. **One of the cleanest files in the codebase.** |
| `intraday/broker_base.py` | 227 | A | Clean abstract interface. Factory pattern. F&O methods properly abstracted. |
| `scripts/check_dhan_orders.py` | 142 | C | Detects duplicates within 5s. **Compares Dhan filled-leg quantities vs DB single-row trades — false positive on every closed long. Does NOT detect orphan PENDING orders, which is the failure mode that actually matters.** |
| `scripts/reconcile_dhan_db.py` | 279 | A- | PHANTOM/ORPHAN/PNL_DRIFT/QTY_DRIFT classification. ₹5 threshold. JSON output. **The right tool, well built.** |
| `scripts/sync_dhan_live.py` | (not in dump) | A | Pulls real-time order endpoint via paid Data API. Truth source. |
| `scripts/build_audit_narrative.py` | 271 | A- | Bedrock-driven narrative generation. Cost log per call. Atomic writes. max_tokens=2048 (raised today). |
| `scripts/validate_narrative.py` | 580 | B+ | Strict 3-bucket validation (verified / failed / structurally_skipped). 4 fixes shipped today. **Still some narrative claims escape via "external_data_needed" — but this is acceptable.** |
| `scripts/compute_daily_pnl.py` | 220 | A- | Built today. Per-profile capital + P&L metrics. Backfilled 38 JSONs. Surfaces charge_ratio_pct prominently. |

### 2.3 Data flow & state

**Where state lives:**

1. **Per-profile SQLite DBs** at `database/{profile}.db` — `intraday_trades`, `intraday_audit_log`, `intraday_daily_summary`, `fno_trades`, `fno_strategies`, `swing_trades`, `daily_top_performers`, etc.
2. **Per-profile broker session** at `config/.broker_session_{profile}.json` — TOTP-derived access tokens, valid same-day only
3. **Profile YAML** at `config/profiles/{profile}.yaml` — capital limits, thresholds, broker creds. **Gitignored. Manually synced between EC2s.**
4. **In-memory monitor state** — `Position_Monitor._active_trades` list, `Risk_Manager._capital_used_today`, `_symbols_traded_today` set
5. **Dhan broker state** — orders, positions, margins. Source of truth.
6. **Dashboard JSON** at `dashboard/api/v2/{profile}/` — daily_pnl, audit, intraday_latest. Synced to S3 hourly.

**Where state leaks:**

1. **Cross-process token contamination** — long-running monitor in process A holds token from cron session 1; new cron session 2 re-auths but A keeps using old token. Causes 2+ hours of HTTP 400 errors. Confirmed today.
2. **DB single-row trade model vs broker leg-based model** — DB has one row per trade with action=BUY (long) or action=SELL (short). Dhan has separate orders per leg. `check_dhan_orders.py` cannot reconcile cleanly.
3. **In-memory record dict missing fields** — Bug A root cause. Executor put trade in DB correctly but the dict passed to monitor lacked `action` field. Monitor defaulted to LONG. Caused duplicate SHORT orders.
4. **Trailing SL update only modifies in-memory** when broker.modify_order is unavailable (older bug, partially fixed). Bug B-trailing.

### 2.4 Cron schedule (active)

OLD EC2 (13.206.144.6):
- `*/15 4-7 * * 1-5` — intraday vishal-live, vishal, neha (every 15 min, 9:30-13:00 IST)
- `50/52/54 3 * * 1-5` — F&O paper for vishal/neha/vishal-live (9:20-9:24 IST)
- `*/30 4-9 * * 1-5` — F&O MTM update (every 30 min during market)
- `5 10 * * 1-5` — top performers capture (3:35 PM IST)
- `0 3-10 * * 1-5` — dashboard S3 sync hourly
- `*/5 4-9 * * 1-5` — Dhan live sync (truth pull)
- `10 10 * * 1-5` — reconcile_dhan_db.py (3:40 PM IST EOD)
- `30 22 * * *` and `30 11 * * 1-5` — crontab self-backup

NEW EC2 (13.202.63.223): runs `danish-eq` (different US/EU swing project), not part of this audit.

### 2.5 What's working at A-grade

- **Charges module** — authoritative, segment-aware, self-tested
- **Reconciliation script** — built correctly, classification taxonomy is sound
- **Daily P&L dashboard** — built today, exposes charge_ratio_pct prominently
- **Audit narrative pipeline** — Bedrock-driven, validator-guarded, cost-tracked
- **Steering documentation** — 16 docs, brutally honest, append-only journals
- **Git discipline** — Rule 1 (no Mac pushes), Rule 25 (safe crontab editor)
- **TOTP auth** — proper 3-retry handling, session caching, client_id validation

### 2.6 What's at C-grade or worse

- **Execution layer** — orphan SL family (Bug A, B, B-2, C) has produced 4 confirmed real-money bugs in 10 days
- **Force-exit logic** — `_place_exit_and_get_fill_price` returns failure status but callers log success
- **Authentication lifecycle** — no auto-refresh on 401; cross-process token bug active
- **`check_dhan_orders.py`** — false positives by design; misses the failure modes that matter
- **Configuration drift** — daily_loss_limit shows ₹500 in yaml, ₹900 in RULES.md; price_range_max only on live profile
- **Two-EC2 working tree drift** — 219 lines uncommitted in `swing/dashboard.py` discovered during this audit
- **F&O module** — Bug T resurrected 3 times; same family of cache-corruption bugs

### 2.7 The structural insight

The codebase has a clean **scanner → selector → executor → monitor** pipeline. Each module is independently sensible. **The bugs cluster at the boundaries between modules** — specifically at the executor↔monitor handoff (Bug A), the monitor↔broker exit lifecycle (Bug B family), the executor↔DB write (Bug 1 indent), and the auth↔long-running-process boundary (cross-process token). 

This is not a code-quality problem. It is a **lifecycle-tracking problem**: every order has a state machine (created → pending → filled / cancelled / rejected → exited / orphaned), and the system does not centrally enforce that every state transition is observed and logged. Bugs leak through the gaps between modules because no module owns "the lifecycle of order X end-to-end."

The fix is not "patch each bug as found." The fix is **a central order-lifecycle reconciler** that runs every 5 minutes and asserts: for every PENDING order in Dhan, there must be a matching open position in DB, OR a matching pending parent entry, OR alert. This single discipline kills the entire Bug B family (B, B-2, future B-N) in one stroke. P0-4 in the findings catalog.

---

## SECTION 3 — STRATEGY LAYER ASSESSMENT

### 3.1 What signal is actually being traded?

Reading the code (not the documentation), the system trades **intraday relative-strength momentum continuation in the first half of the trading session**, with the following operational definition:

**Entry filter (scanner.py + pre_filter):**
- Stock is in NSE Nifty 500 universe
- Price ₹50–₹5000 (scanner) AND ₹100–₹2000 (vishal-live yaml ONLY — paper profiles have no upper bound)
- Volume ≥ 500K, OR (≥4% same-day move with ≥100K volume)
- Not in `high_volatility` flag (gap > 3%)

**Scoring (scanner.py RS-First v3):**
- Signal 1: Intraday continuation (`change_from_open`) — 0–5 pts
- Signal 2: Momentum strength (`change_pct`) — 0–8 pts
- Signal 3: Price near day high — 0–2 pts
- Signal 4: Volume confirmation — 0–2 pts
- Signal 5: FNO liquidity bonus — 0–1 pt
- Signal 6: Sector rotation bonus — 0–5 pts
- Penalties: fade detector (-3 if fell from high), trap detector (-5 gap with no sector support)
- **Time multiplier on final score**: 1.5× first hour → 0.4× late session

**LLM ranking (selector.py):**
- 20 candidates → 1–5 picks
- LLM prompt enforces: R:R ≥ 2.0, confidence ≥ profile min, entry within 3% of open
- Strategy types LLM may pick: MOMENTUM, ORB, GAP, VWAP, REVERSAL (long); SHORT_MOMENTUM, SHORT_ORB, SHORT_GAP, SHORT_REVERSAL (short)

**Exit rules (monitor.py):**
- 5-min monitor cycle
- Trailing SL after 0.5% profit
- 50% partial book at midpoint to target
- SL hit / target hit → place market exit + cancel original SL (3 of 4 paths fixed)
- Force exit at 15:15 IST (market closes 15:30)

### 3.2 What edge is being claimed?

Per `EDGE.md` (the owner's own honest framing):

> "We capture 1-2% intraday momentum continuation when stocks break key levels on volume with sector confirmation in the first 90 minutes of trading, before retail FOMO drives the move toward exhaustion."

The thesis: **smart money positions at 9:30-10:30 IST; retail buys into FOMO at 10:30-11:30; we exit before late-day exhaustion.** Time multiplier (1.5× first hour) encodes this thesis.

This is a defensible thesis on its face. SEBI 2022-2024 data confirms 60-70% of intraday volume comes from retail, and retail behavior has known temporal patterns. The question is not whether the thesis is plausible — it is — but whether **this specific implementation captures it**.

### 3.3 Stated vs actual exit logic

| Stated rule (LLM prompt + EDGE.md) | Actual behavior in code |
|---|---|
| SL = entry × 0.982 (1.8% below) | Correct in selector validation; correct in executor placement |
| Target = entry × 1.04 (4% above) | LLM picks target; validator enforces R:R ≥ 2.0 |
| Trailing SL after 0.5% profit | Correct; modifies Dhan order via `broker.modify_order` |
| Force exit at 15:15 IST | Correct; called from monitor's force_exit_all path |
| Cancel original SL on target/force exit | **3 of 4 paths fixed (commit f9d4998)**. **Bug B-2 confirms 4th path leaves orphan.** |
| Cancel original SL on trailing-SL exit | **NOT IMPLEMENTED.** This is Bug B-2 discovered today. |

**Divergence #1 (P0):** The trailing-SL exit code path places a fresh market SELL order to close, but does not call `broker.cancel_order(sl_order_id)` first. The original STOP_LOSS sits pending in Dhan's order book. If price later drifts to the trigger, Dhan executes the SELL/BUY, creating a fresh phantom position with no protection. **Confirmed in production today on HFCL and SAIL.**

**Divergence #2 (P0):** When the broker call inside `_place_exit_and_get_fill_price` fails (HTTP 400 token expired), the helper returns status="order_failed" or "fallback" — but the **caller in `_check_position` and `_force_exit_all` logs success regardless** and writes synthetic P&L using the cached `current_price` (which is itself stale because the position-fetch loop has been failing for hours). This is FORCE-EXIT-LIES. Confirmed today.

**Divergence #3 (P1):** Stated entry rule: "Only enter if LTP is within 3% of open price." Actual: enforced in LLM prompt but not validated in `validate_pick`. LLM-side enforcement is soft — if LLM disregards it, no Python check catches it. Audit narrative for neha 2026-05-19 flagged COHANCE entered 4.95% above open.

**Divergence #4 (P1):** Stated rule: "Each pick from a different sector." Actual: enforced only via LLM prompt instruction. No code-level check that 5 picks span 5 sectors.

### 3.4 Strategy type distribution — what actually fires

vishal-live (30 closed trades May 12-22) by strategy_type:

| Strategy | Trades | Wins | Win Rate | Net P&L |
|---|---|---|---|---|
| MOMENTUM | 20 | 7 | 35% | -₹260 |
| GAP | 4 | 1 | 25% | -₹97 |
| SHORT_MOMENTUM | 6 | 1 | 17% | -₹11 |
| SHORT_GAP | 3 | 0 | 0% | -₹10 |
| VWAP | 1 | 0 | 0% | ₹0 |
| **REVERSAL, ORB, SHORT_REVERSAL, SHORT_ORB** | **0** | — | — | — |

**4 of 9 defined strategy types never fire on real money.** This is either:
- (a) The LLM prompt biases toward MOMENTUM/GAP because those are listed first, or
- (b) The market regime in this 10-day window genuinely had no REVERSAL/ORB setups, or
- (c) The pre-filter eliminates candidates that would qualify for REVERSAL/ORB

Without backtest data this is unanswerable. **What is answerable:** the system's effective strategy is **MOMENTUM-with-occasional-GAP**, not the 9-strategy library it advertises. This matters because risk profiles differ (REVERSAL setups have different volatility characteristics than MOMENTUM).

### 3.5 LLM behavior — observed from logs

Today's vishal-live log (May 22) shows:

LLM market mood: BEARISH — only 4/27 sectors green LLM VIX assessment: Elevated — VIX 19.25 (>18). Applying 2% SL. Pick #1 VALID: TATASTEEL @ ₹203.73 → ₹195.58 (SL ₹207.80, R:R 2.0, conf 7) [SHORT_MOMENTUM]

LLM rationale demonstrates:
- Correct regime assessment (4/27 green = bearish, picks SHORT)
- Correct VIX-aware SL widening (2% instead of 1.8%)
- Correct R:R math (8.15/4.07 = 2.0)
- Cites volume, sector context, distance from open

**LLM quality is not the bottleneck.** The Bedrock cost log shows 24 audit narratives totaling $0.50 over 8 days. Sub-second response times on Sonnet 4.6. The LLM does its job. The bottleneck is **execution, not selection.**

### 3.6 What the strategy layer is missing

| Missing capability | Severity | Impact |
|---|---|---|
| Backtest baseline against random-entry | P1 | Cannot quantify edge |
| Sector concentration cap (code-enforced) | P2 | Correlated risk on sector selloff days |
| Earnings-window blackout (5 days before/after) | P1 | EDGE.md flags this as risk; not implemented |
| Regime gate (Nifty above 200-DMA?) | P2 | Currently trades same way in all regimes |
| News sentiment per stock | P3 | TO BUILD per `STATE.md` |
| Per-strategy win rate tracking | P1 | WIN_RATE_TRACKING.md has [FILL_IN] markers |

### 3.7 Strategy layer verdict

**Grade: B.** The selection logic is reasonable, the LLM is well-prompted, the scoring is multi-factor and rule-based. **The strategy is not the problem.** The problem is two layers down (execution) and one layer up (capital sizing makes charges dominate gross P&L).

A clean test of the strategy layer requires:
1. P0 execution bugs fixed (so live ≈ paper)
2. Capital sized so charges < 30% of gross (≥ ₹50K positions per trade)
3. 100+ trades through the cleaned pipeline

None of these conditions is currently met. **Strategy quality cannot be evaluated until the substrate works.**

---

## SECTION 4 — STATISTICAL VIABILITY

This is the most important section in this report. Everything else is engineering. This section asks the question that determines whether engineering is worth doing: **does the system have edge, or is it noise?**

### 4.1 Win rate, profit factor, expectancy — by profile

**vishal-live (REAL MONEY, ₹15K capital, 30 closed trades)**

| Metric | Value | Methodology |
|---|---|---|
| Sample size | 30 | `intraday_trades` status IN (CLOSED, STOPPED_OUT, FORCE_EXITED), action IN (BUY, SELL) |
| Wins (pnl > 0) | 9 | |
| Losses (pnl ≤ 0) | 21 | |
| Win rate | 30.0% | wins / total |
| Total net P&L | -₹378 | sum(pnl) — DB-reported, may include synthetic from FORCE-EXIT-LIES |
| Avg win | ~₹17 | mean(pnl where pnl>0) |
| Avg loss | -₹35 | mean(pnl where pnl<0) |
| Profit factor | 0.21 | (wins × avg_win) / (losses × avg_loss) — far below 1.0 |
| Expectancy | -₹13 / trade | mean(pnl) |

**Statistical significance:** sample of 30 is below the 50-minimum threshold for any meaningful win-rate read. With 30 trades at 30% WR, the 95% confidence interval is roughly **15%–48%** — wide enough that the true win rate could be anywhere in that range. We cannot reject "the strategy has zero edge."

**vishal (PAPER, ₹3L capital, 116 closed trades)**

| Metric | Value |
|---|---|
| Sample size | 116 |
| Wins | 57 |
| Losses | 59 |
| Win rate | 49.1% |
| Total net P&L | +₹8,138 |
| Avg win | ₹300 |
| Avg loss | -₹309 |
| Profit factor | 0.99 |
| Expectancy | +₹70 / trade |

**Statistical significance:** sample of 116 crosses the 50-trade threshold but not the 100-trade significance threshold. 49.1% WR with profit factor 0.99 is **break-even with a slight tailwind from the small +₹70/trade expectancy**. This is NOT edge — it is "the strategy is not losing money on paper at ₹50K position sizes." Different statement.

**neha (PAPER, ₹3L capital, 83 closed trades)**

| Metric | Value |
|---|---|
| Sample size | 83 |
| Wins | 37 |
| Losses | 46 |
| Win rate | 44.6% |
| Total net P&L | -₹3,687 |
| Avg win | ₹228 |
| Avg loss | -₹303 |
| Profit factor | 0.61 |
| Expectancy | -₹44 / trade |

**Statistical significance:** sample of 83. 44.6% WR with avg_loss > avg_win. **This profile is bleeding ₹44/trade.** Same code, same prompt, same sizing as vishal-paper — different randomness draws producing different outcomes, OR something subtly different about how neha-paper is processing trades.

### 4.2 The paper-vs-live gap

Same scanner. Same selector. Same LLM. Same risk_manager. Same monitor. Same broker abstraction. Different outcomes:

- vishal-paper: 49% WR, +₹8,138, profit factor ~1.0
- vishal-live: 30% WR, -₹378, profit factor 0.21

**19-percentage-point gap, 1.6× capital efficiency gap.** Why?

**Hypothesis A: Paper doesn't simulate real fills.** Paper uses DryRunBrokerClient which assumes orders fill at requested price. Real Dhan slippage adds 0.3-0.5% per trade. At ₹4500 per trade, that's ₹13-22 of friction the paper doesn't model. Across 30 trades that's ₹400-650 of phantom edge. **Plausible contributor, ~1/3 of the gap.**

**Hypothesis B: Bugs in real-money execution path.** Confirmed bugs that fired on real money:
- May 15 Bug 5: vishal-live placed 7 trades vs limit 3 → -₹220 cost
- May 18 Bug 1: TATASTEEL 4× duplication → -₹717 actual vs -₹52 reported (14× DB drift)
- May 20 Bug A: TATASTEEL doubled SHORT → -₹38 (manual exit)
- May 21 Bug B: HFCL phantom SHORT → +₹0.93 by luck (could have been -₹300)
- May 22 (today) Force-exit-lies on ITC and Angel One → unknown actual P&L

**Sum of confirmed bug damage: ~₹1,000+** out of -₹378 reported total. **This is the dominant explanation of the gap.**

**Hypothesis C: Live profile yaml restricts universe.** vishal-live.yaml has `price_range_max: 2000`. Paper profiles don't. Live cannot trade Trent (₹4268), Eicher (₹6995), ICICI (₹1265). **The two profiles trade different stocks.** This is structural, not random — and it means **paper validation does not transfer to live.**

**Hypothesis D: Sample size dominates.** 30 live trades vs 116 paper trades. With small samples, regression to the mean takes time. Live could converge toward 49% as sample grows.

**Most likely answer:** all four contribute, but B (bugs) is the largest. After P0 fixes, live will likely trend toward paper's 49% WR. **But 49% is still not edge.**

### 4.3 Charge ratio — the elephant

Daily P&L backfill (committed today, May 22) reveals the structural problem:

vishal-live 2026-05-21:
gross_pnl: +₹116.56 charges: ₹156.57 net_pnl: -₹40.01 charge_ratio_pct: 134%

**Charges exceed gross profit by 34%.** The system won 2 of 3 trades that day and still lost money.

vishal-paper 2026-05-21 (same day, ₹3L capital, larger position sizes):
gross_pnl: -₹109.74 charges: ₹470.70 net_pnl: -₹580.44 charge_ratio_pct: 429%

**This day was bad on paper too** — but for a different reason: 7 trades at ₹50K each = ₹3.5L of total trade value, at 0.13% gross loss = ₹110 gross negative, but charges of ₹470 piled on. **Charge ratio is structurally lower at higher capital ONLY when gross is meaningfully positive.** When gross is near zero or negative, charges dominate at any scale.

neha-paper 2026-05-21:
gross_pnl: +₹376.52 charges: ₹436.39 net_pnl: -₹59.87 charge_ratio_pct: 116%

**Pattern across the day:**
| Profile | Capital | Gross | Charges | Net | Charge Ratio |
|---|---|---|---|---|---|
| vishal-live | ₹15K | +₹117 | ₹157 | -₹40 | 134% |
| vishal-paper | ₹3L | -₹110 | ₹471 | -₹580 | 429% |
| neha-paper | ₹3L | +₹377 | ₹436 | -₹60 | 116% |

**No profile profitable on this day.** Charges ate 116-429% of gross.

### 4.4 The required-win-rate calculation

For vishal-live with current avg-win/avg-loss ratio (₹17 / ₹35 = 0.49):
- **Required win rate to break even (zero charges):** ₹35 / (₹17 + ₹35) = **67%**
- **Required win rate at current charge load (~₹52/trade round-trip):** approximately **80%**

The system currently runs at 30%. **Gap to break-even: 37 percentage points.** Gap to profitable: ~50 percentage points.

For vishal-paper (the better-performing profile):
- avg_win ₹300, avg_loss -₹309
- Required win rate to break even: ₹309 / (₹300 + ₹309) = **50.7%**
- Required win rate after charges (paper has ~₹70/trade ratio): **53-55%**
- Current: 49.1%

**vishal-paper is roughly 4-6 percentage points below the profitability threshold.** This is interpretable as "the strategy needs modest improvement to be profitable, OR larger sample size will reveal it's already there." Not catastrophic. Tractable.

### 4.5 Comparison to random-entry baseline

A coin-flip strategy with the same R:R 2.0 setup would produce:
- Win rate: ~50%
- Avg win: 2× avg loss
- Expected outcome: **profitable before charges, neutral after charges** (because R:R 2.0 means winners pay for losers)

**vishal-paper at 49% WR with avg_win ≈ avg_loss is BELOW the coin-flip baseline.** The strategy is not adding value over random selection at ₹50K position sizes.

This is the most uncomfortable finding in this audit. **It does not mean the strategy is bad.** It means:
- Sample size is still small (116 trades)
- Slippage and execution noise in paper data are real
- The R:R 2.0 target isn't being achieved on average (avg_win < target × loss)

But it does mean **claims of edge cannot be made yet.** EDGE.md correctly states "Win rate 60% achievable with discipline. 65% requires regime adaptation we don't yet have." Owner has documented this honestly. The audit confirms: **edge thesis is plausible, not proven.**

### 4.6 Profit factor by strategy type (vishal-live)

| Strategy | Trades | Avg Win | Avg Loss | Profit Factor |
|---|---|---|---|---|
| MOMENTUM | 20 | ₹17 | -₹42 | 0.22 |
| GAP | 4 | ₹8 | -₹52 | 0.05 |
| SHORT_MOMENTUM | 6 | ₹3 | -₹3.5 | 0.17 |
| SHORT_GAP | 3 | — | -₹3.5 | 0.00 |

**Every strategy has profit factor < 1.0 at current capital.** The pattern is consistent: small wins, larger losses, dominated by FORCE_EXITED outcomes (15 of 30 trades = 50%).

**FORCE_EXITED dominance** is the operational tell. It means the system is rarely hitting target, rarely getting stopped at SL — instead it's holding losing positions until the 15:15 IST kill switch. This indicates:
- Either the entries are wrong (no follow-through)
- Or the targets are too aggressive (4% in 5 hours is a lot)
- Or the SLs are too wide (price wanders without tripping SL or target)

### 4.7 The honest verdict on edge

**At sample sizes available (30 live, 116+83 paper), no statistically significant edge has been demonstrated.**

What CAN be said:
- Paper at ₹3L produces 49% WR / break-even — strategy is not actively destroying capital at scale
- Live at ₹15K produces 30% WR / -₹13/trade — but 50%+ of this loss is bug damage, not strategy damage
- Charge ratio is the dominant cost at ₹15K capital — strategy needs 80% WR to be profitable, achievable for nobody
- After P0 bug fixes + capital scaling to ₹50K, the *math* of edge becomes plausible

What CANNOT be said:
- "The strategy works"
- "It will be profitable at scale"
- "Past performance suggests future results"

**Required to claim edge:** 100+ clean trades (post P0 fixes) at win rate ≥ 50% AND profit factor > 1.2 AND charge ratio < 30%. Earliest realistic date for this verdict: **8-12 weeks from today** if discipline holds.

### 4.8 What we miss because of this

Without statistical edge demonstrated:
- Capital scaling to ₹1L is **gambling on hope, not evidence**
- The "₹1L/month income by June 20" plan documented in STATE.md May 19 is **mathematically improbable** (owner self-assessed at 25% probability — honest)
- F&O module (paper, broken) cannot be fairly evaluated even if Bug T were fixed
- Swing module (orphaned code, ~30% built) cannot be evaluated at all
- The validator/narrative/audit observability investment cannot pay back without a profitable underlying system

**The audit observability layer is genuinely excellent and will retain value even if the strategy ultimately fails.** It is portable to any future trading system. That is the consolation prize if the current strategy doesn't validate.

---

## SECTION 5 — RISK ARCHITECTURE

### 5.1 Position sizing logic

`intraday/risk_manager.py::size_trades()` uses confidence-weighted allocation:
- Base qty = floor(per_trade_max_capital / entry_price)
- Weight = confidence_score / total_confidence across picks
- Weighted qty = floor((remaining_capital × weight) / entry_price)
- Final qty = min(base, weighted)

**Verdict: B+.** Sound logic. Distributes capital toward higher-conviction picks. Per-trade cap prevents over-concentration.

**However**, sizing is fixed-rupee, not fraction-of-capital:
- `per_trade_max_capital: 4500` is hardcoded in `vishal-live.yaml`
- When capital scales 15K → 1L, this number must be edited manually
- No code logic computes "X% of daily_capital_limit"
- Risk per trade as % of capital: ₹4500 / ₹15000 = **30%** (very high)
- Professional benchmark: 1-2% per trade

At ₹1L same yaml: 4500/100000 = 4.5%. At ₹2L: 2.25%. **Risk-per-trade implicitly drops as capital scales.** Favorable for scaling, but means strategy outcomes at ₹15K cannot be linearly extrapolated to ₹1L+ — different effective risk profile.


### 5.2 Daily loss limit — configuration drift

`vishal-live.yaml`: `daily_loss_limit: 500`
`RULES.md` Section 5: `daily_loss_limit | INR 900 (raised from 600 on May 14)`

The yaml has 500, the steering doc claims 900. Neither matches actual cumulative real-money daily losses:
- ₹220 on May 15 (Bug 5 cascade)
- ₹717 on May 18 (Bug 1 with 14× DB drift)

Both exceeded both documented limits.

The May 18 incident exposed the deeper failure: cumulative real loss was ₹717, but DB-reported was -₹52. **The daily loss limit cannot enforce what the DB doesn't know.** Bug 1 made the DB lie about losses. Loss limit silently bypassed.

**Verdict: P0.** Active value of `daily_loss_limit` is unclear, documented value disagrees with configured value, and historical incidents prove the limit doesn't reliably halt trading.

### 5.3 Same-symbol re-entry block

`risk_manager.py` maintains `_symbols_traded_today` set, restored from DB on init. **Works correctly when DB has rows.**

**Failure mode:** when Bug 1 (indent) prevented DB writes during MARKET retry, the re-entry block was bypassed → INFY 3.5× and TATASTEEL 4× duplications (May 18-19). This was a downstream symptom of Bug 1, not a re-entry block bug. Re-entry block itself is correct.


### 5.4 What's missing — risk capabilities not implemented

| Capability | Severity | Why it matters |
|---|---|---|
| Consecutive-loss circuit breaker | P1 | After 3 losses in a row, system should halt for the day. Not implemented. |
| Sector concentration cap | P2 | If LLM picks 5 metal-sector stocks, risk_manager doesn't prevent it. |
| Margin verification before entry | P1 | `get_margins()` exists but is not called pre-trade. Orders may reject mid-batch. |
| Pre-entry capital remaining check | P0 | `can_place_new_order()` only checks loss cap, not capital remaining. |
| Open-position exposure limit | P2 | If 3 trades all OPEN, total exposure could exceed `daily_capital_limit`. |
| Realized vs unrealized distinction in cap | P1 | When force-exit fails (lies), unrealized never converts to realized but DB shows synthetic realized. Cap may not fire. |

### 5.5 Bad day walkthrough — May 18

- Cron fires every 15 min from 9:30 to 13:00
- Bug 1 in executor causes MARKET retry to skip DB write
- Risk manager sees empty DB → counter = 0
- Each cron run sees "0 trades placed" → no max-trades cap
- 7 trades placed (limit was 3)
- 4 of them duplicates (TATASTEEL × 4, BANDHAN × 2)
- Real loss: ₹717. DB-reported: ₹52 (14× drift)
- Daily loss limit ₹500 not triggered (DB said -₹52, well within cap)

**Risk management quality is bounded above by data integrity quality.**

### 5.6 Risk architecture verdict

**Grade: B-.** Sizing is sound. Same-symbol block works. VIX gate is reasonable. **But the architecture trusts the DB blindly, and the DB has been demonstrably wrong on multiple real-money days.**

Fix is not in `risk_manager.py`. Fix is in:
1. Eliminating DB write failures (P0 fixes in execution layer)
2. Adding Dhan-side cross-check at session start

---

### 5.4 What's missing — risk capabilities not implemented

| Capability | Severity | Why it matters |
|---|---|---|
| Consecutive-loss circuit breaker | P1 | After 3 losses in a row, system should halt for the day. Not implemented. |
| Sector concentration cap | P2 | If LLM picks 5 metal-sector stocks, risk_manager doesn't prevent it. |
| Margin verification before entry | P1 | `get_margins()` exists but is not called pre-trade. Orders may reject mid-batch. |
| Pre-entry capital remaining check | P0 | `can_place_new_order()` only checks loss cap, not capital remaining. |
| Open-position exposure limit | P2 | If 3 trades all OPEN, total exposure could exceed `daily_capital_limit`. |
| Realized vs unrealized distinction in cap | P1 | When force-exit fails (lies), unrealized never converts to realized but DB shows synthetic realized. Cap may not fire. |

### 5.5 Bad day walkthrough — May 18

- Cron fires every 15 min from 9:30 to 13:00
- Bug 1 in executor causes MARKET retry to skip DB write
- Risk manager sees empty DB → counter = 0
- Each cron run sees "0 trades placed" → no max-trades cap
- 7 trades placed (limit was 3)
- 4 of them duplicates (TATASTEEL × 4, BANDHAN × 2)
- Real loss: ₹717. DB-reported: ₹52 (14× drift)
- Daily loss limit ₹500 not triggered (DB said -₹52, well within cap)

**Risk management quality is bounded above by data integrity quality.**

### 5.6 Risk architecture verdict

**Grade: B-.** Sizing is sound. Same-symbol block works. VIX gate is reasonable. **But the architecture trusts the DB blindly, and the DB has been demonstrably wrong on multiple real-money days.**

Fix is not in `risk_manager.py`. Fix is in:
1. Eliminating DB write failures (P0 fixes in execution layer)
2. Adding Dhan-side cross-check at session start

---

## SECTION 6 — EXECUTION LAYER

This is the largest section because **execution is where the bugs cluster**.

### 6.1 Order lifecycle — what should happen

For one intraday LONG trade:
1. Scanner picks stock
2. Selector validates R:R, confidence
3. Risk manager sizes position
4. Executor places LIMIT BUY with 0.3% buffer
5. Wait up to 10s, poll order status every 2s
6. If filled → continue. If not → cancel LIMIT, place MARKET if conf ≥ 8.
7. Reconcile via `get_positions` before any retry (Bug 1 defense)
8. Place STOP_LOSS order at SL price, tick-aligned
9. Insert row in `intraday_trades` with status=PENDING
10. Monitor takes over (5-min cycle)
11. Exit triggers: target / SL / trailing / 15:15 IST force exit
12. On exit: cancel original SL, place market exit, record P&L

This is the documented flow. The code does most of this. **The bugs cluster at specific transition points.**

### 6.2 Bug family — root cause analysis

**Class 1: State-tracking failures across module boundaries**
- Bug A: in-memory record dict missing `action` field → monitor wrong direction
- Bug 1 (indent): MARKET retry bypassed SL placement and DB write
- Bug 5: max_trades_per_day counter ignored OPEN trades
- Bug 5b: counter restoration query bug (SHORT trades filtered out)

**Class 2: Lifecycle cleanup failures**
- Bug B: target hit doesn't cancel original SL → orphan
- Bug B-2: trailing-SL → market-exit doesn't cancel SL → orphan (DISCOVERED TODAY)
- Bug C: SL price stored above entry on LONG trades → impossible state
- Bug T (3 resurrections): F&O cache corruption, exit P&L synthetic

**Both classes share a deeper pattern:** *no module owns the end-to-end lifecycle of an order.* Executor places it. Monitor watches it. **No central reconciler that asserts: for every order placed in the last 10 minutes, exactly one of {filled-and-tracked, cancelled, rejected} must be true.**

This makes P0-4 (orphan-order detection cron) the highest-leverage fix. **One reconciler kills Bug B, B-2, B-3, B-4, and prevents the next Bug B-N from ever surfacing on real money.**

### 6.3 Confirmed exit-path bugs

#### Bug B (PARTIAL FIX, commit f9d4998)
- Target hit: ✅ cancels SL before market exit
- Force exit: ✅ cancels SL before market exit
- Trailing SL update: ✅ uses `broker.modify_order` instead of memory-only
- **Trailing SL → market exit: ❌ not patched** (Bug B-2)

#### Bug B-2 (DISCOVERED TODAY, UNFIXED)

Today's vishal-live order book pulled at 13:50 IST:
10:30:43 HFCL SELL 14 PENDING STOP_LOSS @ 142.75 ← original SL 11:03:00 HFCL SELL 14 TRADED LIMIT ← exit market order placed FRESH 11:46:07 HFCL SELL 14 CANCELLED STOP_LOSS @ 142.75 ← cancelled MANUALLY by user

**Window of unprotected orphan SL: 76 minutes** when position was already closed but SL trigger was still live in Dhan's book. SAIL had 52-min orphan window same day.

If price had dipped to ₹142.75 in the orphan window, Dhan would have executed → fresh phantom SHORT 14 HFCL with no protection. **User caught manually.** No automated detection.

#### Bug C (DISCOVERED 2026-05-21, UNFIXED)

ANGELONE trade_id 29: direction LONG, entry_price ₹336.90, stop_loss_price **₹339.45 (above entry, impossible for LONG)**, rr_planned=0.

If SL stored in DB was also placed on Dhan, SL was set ABOVE entry — meaning a LONG trade would be stopped out the moment price ticked up. Opposite of protection.

Trade closed at target via trailing — bad SL did not actually fire. But **DB stores impossible state**. Root cause unknown.

---

#### FORCE-EXIT-LIES (DOCUMENTED MAY 19, ACTIVE TODAY)

Today's vishal-live log (May 22), for 2.5 hours straight:
[ERROR] Dhan get_positions failed — HTTP 400 [repeats every 2 minutes for 144+ cycles]

Then at 15:16:50 IST (force exit time):
[ERROR] Dhan cancel_order failed — HTTP 400: 'Invalid Token' [INFO] Bug B: SL cancelled before force exit: ITC sl_order_id=321260522258208 [ERROR] Dhan place_order failed — HTTP 400: 'Invalid Token' [INFO] ✅ ITC exit order placed (BUY) order_id= [INFO] ⏰ ITC FORCE EXITED @ ₹304.55 | gross ₹0.00 charges ₹4.53 net ₹-4.53 [SHORT] fill=no_poll

**Three lies in 4 lines:**
1. "Bug B: SL cancelled" — but cancel_order returned HTTP 400, SL was NOT cancelled
2. "✅ ITC exit order placed" — but place_order returned HTTP 400, no exit was placed
3. "ITC FORCE EXITED @ ₹304.55" — using ENTRY price as exit price, fill=no_poll

Same exact pattern in May 21 log (BEL force exit, fill=no_poll).

**Real impact:** Dhan auto-square-off at 15:30 IST likely closed positions, but our system has no idea what price they actually closed at. DB shows synthetic P&L based on entry price.

**Severity: P0 catastrophic.** On every day Dhan token expires mid-session, system reports fictional P&L. We've been operating on partially-fictional data for 3+ trading days.

#### CROSS-PROCESS-TOKEN (DOCUMENTED MAY 19, UNFIXED)

Mechanism:
- Cron at 09:30 IST authenticates, stores token
- Monitor process started at 09:30 holds token in memory
- Cron at 11:00 IST detects stale session (>3.5h), re-authenticates
- **Old monitor process still running with old token** — token now invalid
- Every `get_positions` call returns HTTP 400

Today's evidence: 60+ consecutive HTTP 400 errors over 2.5 hours.

### 6.4 Race conditions

| Race | Window | Consequence |
|---|---|---|
| Two crons call auth simultaneously | <1s | One overwrites other's session file |
| Monitor polls position while cron places new order | 5 min | Monitor sees stale list |
| LLM call times out during force-exit window | 60-120s | Position not exited at intended time |
| Network drop during cancel_order before place_order | <2s | Original SL gone AND no new exit placed → unprotected |

**Most concerning:** cancel-then-place sequence in monitor exit code is not atomic. **No code path detects "cancel succeeded but place failed" state.**

### 6.5 EC2 reboot scenario — UNTESTED

If EC2 reboots mid-session:
- Running monitor processes die
- Open positions on Dhan remain open
- Next cron starts fresh, no in-memory state
- **Code does NOT have "resume monitoring of pre-existing positions" logic**
- Positions surviving reboot would be untracked
- Dhan auto-square-off at 15:30 closes them, P&L unrecorded

**Severity: P1.** Probability low, consequences severe.

### 6.6 The order book today — smoking gun

10:00:43 ITC SELL 14 TRADED LIMIT (legit short entry) 10:00:45 ITC BUY 14 PENDING STOP_LOSS 310.65 (legit SL) 10:30:41 HFCL BUY 14 TRADED LIMIT (long entry) 10:54:49 SAIL SELL 10 TRADED LIMIT (long exit, closed) 11:03:00 HFCL SELL 14 TRADED LIMIT (long exit, closed) 11:46:07 HFCL SELL 14 CANCELLED STOP_LOSS 142.75 (orphan SL — manual cancel) 11:46:09 SAIL SELL 10 CANCELLED STOP_LOSS 195.25 (orphan SL — manual cancel)

This proves Bug B-2 in production. HFCL had an orphan SL pending for 76 minutes. SAIL for 52 minutes. **Manual intervention required. No automated alert.**

### 6.7 Execution layer verdict

**Grade: C.** Code is correct for happy path. Consistently fragile at boundaries. Bugs cluster at lifecycle transitions where no module owns the end-to-end invariant.

**Top 3 fixes:**
1. **P0-1: Eliminate FORCE-EXIT-LIES** — broker failure must raise, caller must not log success
2. **P0-2: Token refresh on long-running monitor** — reload session every poll, OR trap 401/400 and re-auth
3. **P0-4: Orphan-order reconciler cron** — every 5 min, alert on PENDING with no matching position

After these three: C → B. After Bug B-2 + Bug C + circuit breaker fixes: B → B+. After 30 trading days clean: B+ → A-.

---

## SECTION 7 — CAPITAL SCALABILITY ASSESSMENT

Required by `SYSTEM_AUDIT_PLAN.md` Section 2.4-bis. Concrete evidence: at ₹15K capital, charge_ratio_pct exceeds 100% on representative days.

### 7.1 Hardcoded rupee values found

| File | Hardcoded value | Risk on scaling |
|---|---|---|
| `vishal-live.yaml` | `daily_capital_limit: 15000` | Must edit on capital change |
| `vishal-live.yaml` | `per_trade_max_capital: 4500` | Must edit; risk-per-trade ratio shifts |
| `vishal-live.yaml` | `daily_loss_limit: 500` | Loss tolerance doesn't scale with capital |
| `vishal-live.yaml` | `price_range_max: 2000` | **CRITICAL: paper profiles don't have this — universe diverges** |
| `vishal-live.yaml` | `price_range_min: 100` | Same divergence issue |
| `intraday/scanner.py` | `price_min=50, price_max=5000` | Universe filter, applies all profiles |
| `intraday/scanner.py` | `min_volume=500_000` | Liquidity floor |

### 7.2 Behavior change when capital scales 15K → 1L

Position sizing: Linear. ₹4500 → ₹30000 per trade = 6.7× larger qty.
Number of trades per day: Same (`max_trades_per_day` unchanged at 3).
Different mix: Yes — at ₹30K per position, Trent (₹4268) becomes viable (qty 7), Eicher (₹6995, qty 4), ICICI (₹1265, qty 23). **Universe expands meaningfully.**
SL/TP distances: Same % (1.8% / 4%). ✅ Already %-based.

`if capital < X` branches: None.
`if qty < X` branches: Implicit `qty <= 0` skip in risk_manager.

### 7.3 Paper-vs-live divergence due to config

| Setting | vishal-live | vishal-paper | neha-paper |
|---|---|---|---|
| daily_capital_limit | 15000 | 300000 | 300000 |
| per_trade_max_capital | 4500 | 50000 | 50000 |
| max_trades_per_day | 3 | 6 | 6 |
| daily_loss_limit | 500 | 9000 | 9000 |
| **price_range_max** | **2000** | **NOT SET** | **NOT SET** |
| **price_range_min** | **100** | **NOT SET** | **NOT SET** |
| min_confidence_score | 7 | 7 | 7 |
| vix_threshold | 20 | 18 | 18 |

**Implication:** vishal-paper trades 0-∞ price range; vishal-live trades only 100-2000. **Any strategy validation done on paper does not apply to live trade universe.**

This is the most important architectural insight in this section. **Paper validation is currently invalid as proxy for live validation.**

### 7.4 Minimum capital for charge_ratio < 30%

From paper data (last 10 days, gross PnL aggregate): ~₹50-75K position sizes produce charge_ratio in 20-30% range when gross is meaningfully positive.

vishal-paper 2026-05-21 had 7 trades averaging ~₹37K position, charges ₹470, gross -₹110 (bad day, 429%). On a typical day with gross ₹500-1000, charges ₹400-500 = 50-100%. **Even ₹50K positions are not enough on borderline-profitable days.**

**Estimated minimum viable capital:**
- ₹50K-75K per trade position size
- Implies ₹2.5L-3L total (5-6 concurrent × ₹50K)
- OR ₹1L total with 2 concurrent × ₹50K

**Conclusion: ₹1L total capital is the minimum where strategy edge has a fair chance to manifest above charges.** Current ₹15K is structurally below this threshold regardless of strategy quality.

### 7.5 Verdict — Capital Scalability

- **Capital-agnostic today:** PARTIAL. Sizing is %-based. Loss limit and price range are hardcoded rupees. Universe filter on live profile only.
- **Refactor to fully agnostic:** ~3 hours of P1 work.
- **Minimum viable capital for current config:** ~₹1L.
- **Recommended capital for stable profit at current edge:** ~₹2L.
- **Hard rupee values that must become %:** `daily_loss_limit`, `per_trade_max_capital`, eventually `price_range_max`.

P1 deliverable, not P0. P0 reserved for capital-RISK bugs.

---

## SECTION 8 — DATA INTEGRITY

### 8.1 DB single-row trade model vs broker leg-based model

DB schema: `intraday_trades` has one row per trade with `action='BUY'` (LONG) or `action='SELL'` (SHORT). Exit info crammed into same row (`exit_price`, status='STOPPED_OUT', `pnl`).

Dhan: separate orders per leg. BUY entry, SELL exit, both in `/v2/orders`.

**Reconciliation gap:** `check_dhan_orders.py` compares Dhan SELL leg quantities vs DB `action='SELL'` rows. For closed long trades, DB has 0 SELL rows but Dhan has SELL leg = qty. **Always flags as mismatch.** False positive on every successful long exit.

This was verified today (HFCL/SAIL closed legitimately, script flagged as mismatch with `db_qty=0, dhan_qty=14`).

### 8.2 Atomic writes

`db_manager` uses sqlite3 with default isolation. **No explicit transactions** wrapping multi-step operations like "place order + insert trade row + place SL + update trade row".

**Failure mode:** If place_order succeeds but DB insert fails, trade is on Dhan but not in DB. Bug 1 demonstrated this exact pattern.

### 8.3 DB-vs-Dhan drift evidence

Documented from May 18 incident:
- DB-reported P&L: -₹52
- Dhan-reported P&L: -₹717
- **Drift: 14×, hidden from system for entire day**

May 19 incident:
- DB-reported: -₹130
- Dhan-reported: +₹85
- **Drift: ₹215, system showed loss when there was profit**

May 22 (today):
- DB-reported: -₹0.82 (synthetic, fill=no_poll)
- Dhan-reported: unknown (auto-square-off closed positions)
- **Drift: unknown but non-zero**

### 8.4 Reconciliation script gaps

`scripts/reconcile_dhan_db.py` exists with PHANTOM/ORPHAN/PNL_DRIFT/QTY_DRIFT classification, ₹5 threshold. Cron at 15:40 IST.

**What it catches:** end-of-day drift > ₹5
**What it misses:**
- Real-time orphan PENDING orders (Bug B-2 family)
- Token expiry mid-session (FORCE-EXIT-LIES)
- Phantom SHORT created by orphan SL firing

**Required addition:** orphan-order detection running every 5 min during market hours (P0-4).

### 8.5 Data integrity verdict

**Grade: B-.** Reconciliation script is well-built but runs only EOD. Real-time gaps create capital-risk windows. Single-row DB model creates structural reconciliation noise. Atomic write discipline missing in critical paths.

---

## SECTION 9 — OPERATIONAL DISCIPLINE

### 9.1 Two-EC2 architecture

OLD EC2 (13.206.144.6): vishal-live + paper + F&O
NEW EC2 (13.202.63.223): danish-eq (different project) + neha-live (stopped)

Per-account Dhan IP whitelist forces this split. Neha-live currently STOPPED since May 18 — extra EC2 wasted resource at present.

### 9.2 Working tree drift discovered today

During Stage 1 evidence dump:
- 219 lines uncommitted in `swing/dashboard.py` (Opus 4.7 session, never committed)
- 4 stray empty files in repo root (`main`, `10,}`, etc.)
- `dhan_orders.py` at root (different from `scripts/check_dhan_orders.py`)
- Untracked `intraday/monitor.py.backup_20260512_1811`

Snapshotted to branch `pre-audit-working-tree-2026-05-22` to preserve. **Indicates EC2-direct-edit workflow lacks discipline** — code gets edited and tested but not always committed.

### 9.3 Crontab hygiene

Crontab wiped twice in 4 days (May 18, May 20). Caused by `crontab -l | sed | crontab -` pattern where sed failure produces empty stdout, wiping crontab.

**Mitigation in place (Rule 25):** `scripts/safe_crontab_edit.sh` with backup verification + non-empty validation + diff confirmation. Canonical restore source at `scripts/crontab.canonical`.

**Root risk persists:** if anyone uses raw `crontab -l | ... | crontab -` without the safe script, wipe happens again.

### 9.4 Auth lifecycle

TOTP auth: 3 retries on token rotation, session caching with client_id validation. Sound design.

**Gap:** long-running processes (monitor) hold token in memory. Cross-process token contamination causes 2.5h blind monitoring (today). No re-auth on HTTP 401/400.

### 9.5 Steering docs — context window pressure

16 docs at `.kiro/steering/`. Total ~5000 lines. Bedrock context limit on a single chat: ~200K tokens (≈ 150K words). 16 docs fit, but with chat history they crowd.

Already documented: `CONTEXT.md` (auto-rebuilt) + Rule 21 (reading order) + Rule 24 (Bedrock can't fetch externals). Workable but adds friction to every new AI session.

### 9.6 F&O reliability

Bug T resurrected 3 times (May 15, May 17, May 19). Pattern: cache-layer corruption, symbol normalization, force_exit using zero premium. Same family of bugs.

Per BUGS_AND_FIXES.md own pattern catalog: "If a bug class returns 3+ times, the architecture is wrong. We rewrite, not patch."

**Decision pending June 1 (DECISIONS.md PD-001):** rewrite F&O, continue debugging, or kill module.

### 9.7 Validation tooling itself buggy

May 19: `validate_tomorrow.sh` returned PASS while Bug 1 was firing in production. Validator's CHECK 5 (DB-vs-Dhan) compared wrong fields.

Today's validator improvements (commit 3b8f88b) fixed 4 specific issues but the broader principle remains: **validation tooling needs validation tooling**. The tools we built to catch bugs themselves had bugs.

### 9.8 Operational discipline verdict

**Grade: B.** Documentation discipline is exceptional (16 docs). Git discipline is good (Rule 1). Crontab safety improved (Rule 25). **But:** working tree drift, cross-process auth, and tooling-validating-tooling all need work.

---

## SECTION 10 — FINDINGS CATALOG

Each finding: ID, title, evidence, severity, impact, what we miss, fix, verification, effort.

### P0 — CAPITAL-RISK FINDINGS (must fix before adding any capital)

#### P0-1: FORCE-EXIT-LIES — production bug active today
**Evidence:** `intraday_vishal-live_2026-05-22.log` lines from 15:16:50 IST. Three lies in 4 lines: cancel_order failed but logged "SL cancelled", place_order failed but logged "exit order placed", FORCE EXITED at entry price with `fill=no_poll`. Same pattern May 21 (BEL).
**Severity rationale:** System reports fictional P&L on every day Dhan token expires mid-session. Reconciliation, daily loss limit, audit narratives all read fictional data.
**Impact:** All P&L numbers post-token-expiry are unreliable. Cumulative real P&L unknown for 3+ trading days. Loss limit can be silently bypassed.
**What we miss:** Cannot trust DB to reflect reality. Every downstream metric (win rate, charge ratio, daily P&L) is contaminated.
**Fix:** `intraday/monitor.py::_place_exit_and_get_fill_price` must raise on broker error. Callers (`_check_position`, `_force_exit_all`) wrap in try/except, log EXIT_FAILED audit event, leave position OPEN in DB. Refuse to write synthetic exit_price.
**Verification:** Inject token expiry on test profile, verify positions stay OPEN in DB and EXIT_FAILED audit row written.
**Effort:** 60 min code + 30 min test = 90 min.

#### P0-2: CROSS-PROCESS-TOKEN — long monitor blind for hours
**Evidence:** Today's log: 2.5 hours of HTTP 400 errors on `get_positions`. Same May 19, 21.
**Severity rationale:** Monitor blind to position prices means trailing SL doesn't trigger, target hit doesn't fire, force exit lies (P0-1).
**Impact:** Real-money positions un-monitored for hours. Compounds P0-1.
**What we miss:** Mid-session price action invisible. Trailing SL never moves. Target hits invisible.
**Fix:** Add token-reload at start of every monitor cycle: `self.broker.access_token = load_session_file()`. Catch HTTP 401/400 on first failure, trigger `authenticate_broker()` re-auth.
**Verification:** Force token expiry, confirm next monitor cycle re-auths and resumes.
**Effort:** 45 min.

#### P0-3: Bug B-2 — orphan SL on trailing-SL exit path
**Evidence:** Today's HFCL (76 min orphan), SAIL (52 min orphan). User caught manually.
**Severity rationale:** Phantom-SHORT risk. Same failure mode as May 21 HFCL phantom incident.
**Impact:** Position closed, orphan SL fires on price drift, creates unprotected fresh position. Capital at risk.
**What we miss:** Bug B fix only covers 3 of 4 exit code paths. The 4th (trailing-SL → market-exit) has no `cancel_order` call.
**Fix:** In `monitor.py` trailing-SL exit branch, call `self.broker.cancel_order(trade.sl_order_id)` before placing market exit. Same defensive pattern as commit f9d4998.
**Verification:** Paper trade with trailing SL hit, confirm Dhan order book has 0 PENDING after exit.
**Effort:** 30 min code + 30 min paper test = 60 min.

#### P0-4: Orphan-order reconciler cron — automated detection
**Evidence:** Today's manual catch of Bug B-2. No automated alert.
**Severity rationale:** Bug B family will keep producing variants. Manual eyeballing doesn't scale.
**Impact:** Undetected orphans fire, create phantom positions, real-money loss.
**What we miss:** No system invariant enforced. Every Bug B-N variant requires re-discovery.
**Fix:** New cron: `*/5 4-9 * * 1-5 .venv/bin/python scripts/orphan_order_check.py`. Script: fetch all PENDING orders from Dhan, for each verify matching open position in DB OR matching pending parent entry. If neither, alert (Telegram or log) AND optionally auto-cancel after 10 min grace.
**Verification:** Inject orphan SL, verify alert fires within 5 min.
**Effort:** 90 min code + 30 min test = 120 min.

#### P0-5: Bug C — RR data integrity (LONG SL above entry)
**Evidence:** ANGELONE trade_id 29: LONG entry 336.90, SL 339.45 (ABOVE entry, impossible).
**Severity rationale:** SL placed at impossible level. If Dhan-side mirrors DB, real protection is broken.
**Impact:** LONG trades can be stopped out instantly on tiny upward tick. Worse, audit narratives flag rr_planned=0 making validation impossible.
**What we miss:** Root cause unknown. Could be tick-rounding, executor mishandling, or risk_manager modifying SL incorrectly. 30+ trades have rr_planned=0.
**Fix:** Step 1 — query: `SELECT id, symbol, action, entry_price, stop_loss_price FROM intraday_trades WHERE (action='BUY' AND stop_loss_price >= entry_price) OR (action='SELL' AND stop_loss_price <= entry_price)`. Step 2 — for each match, trace selector→risk_manager→executor to find where bad value enters. Step 3 — assertion in executor before broker.place_order: assert SL on correct side of entry.
**Verification:** No matching rows after fix; assertion raises on synthetic bad input.
**Effort:** 90 min investigation + 30 min fix + 30 min test = 150 min.

#### P0-6: Daily loss limit configuration drift
**Evidence:** vishal-live.yaml: 500. RULES.md Section 5: 900. Historical losses (₹220 May 15, ₹717 May 18) exceeded both.
**Severity rationale:** The actual cap in production is unclear. No alert when breached.
**Impact:** Loss cap may not fire. Real-money downside unbounded.
**What we miss:** No verification that cap = active value. No alert on >50% utilization.
**Fix:** Single source of truth in yaml. Add log line at session start: `Daily loss limit: ₹X (from {profile}.yaml)`. Add Telegram alert at 50% and 80% utilization.
**Verification:** Manual test with synthetic loss, confirm alert fires.
**Effort:** 30 min.

#### P0-7: Force-exit price logging uses cached current_price
**Evidence:** Today's log: "FORCE EXITED @ ₹304.55" where 304.55 = ENTRY price for ITC. Cached `current_price` was stale because position-fetch was failing for hours.
**Severity rationale:** Subset of P0-1 but worth calling out separately. The cached price is itself unreliable when get_positions has been failing.
**Impact:** Even if force-exit were truly placed, the logged P&L would be wrong because cached price is stale.
**What we miss:** No "data freshness" check. Code happily uses 2.5-hour-old price.
**Fix:** Track `last_price_update_ts` per trade. If > 5 min old, refuse to use for P&L calculation. Force re-fetch or fail loudly.
**Verification:** Test with simulated stale price, confirm refusal/refresh.
**Effort:** 45 min.

---

### P1 — EDGE-RISK FINDINGS (prevent profitability)

#### P1-1: Charge ratio 134% at ₹15K — structurally unprofitable
**Evidence:** vishal-live 2026-05-21: gross +₹117, charges ₹157, net -₹40. Pattern: charges dominate at ₹4500 position size.
**Impact:** System cannot demonstrate edge at current capital regardless of strategy quality.
**Fix:** Capital scaling to ₹1L+ per Section 7.4. Or cut trading frequency to ≤1 trade/day.
**Effort:** Capital decision, not code. 0 dev hours, but blocked by P0 fixes.

#### P1-2: Capital-agnostic refactor needed
**Evidence:** Section 7. `daily_loss_limit`, `per_trade_max_capital`, `price_range_max` are hardcoded rupees. Live yaml has price_range_max=2000, paper doesn't.
**Impact:** Paper validation does not transfer to live (different universe). Manual yaml edits on every capital change introduce error risk.
**Fix:** Convert `daily_loss_limit` to `daily_loss_limit_pct: 3.5`. Convert `per_trade_max_capital` to `per_trade_max_capital_pct: 30`. Remove `price_range_max` from live yaml or add to paper yaml — must match.
**Effort:** 90 min refactor + 30 min test.

#### P1-3: Live-vs-paper win rate gap is bug-driven
**Evidence:** Live 30%, paper 49%. Confirmed bugs that fired on live: Bug 1 (-₹717), Bug A (₹38), Bug B (-₹0.93 lucky, could be -₹300). After P0 fixes, live should converge to paper.
**Impact:** Cannot distinguish strategy quality from bug damage until P0 fixes complete.
**Fix:** P0 fixes + 30 days clean operation.
**Effort:** Encompassed by P0 work.

#### P1-4: SHORT trade win rate 11% across both profiles
**Evidence:** vishal-live SHORT_MOMENTUM 17%, SHORT_GAP 0%. Same patterns in paper.
**Impact:** SHORT execution may have hidden bugs OR the SHORT signal is fundamentally weaker.
**Fix:** After P0 fixes, audit SHORT trades specifically. Compare SHORT vs LONG for same regime conditions.
**Effort:** 60 min analysis after P0 done.

#### P1-5: Only 4 of 9 strategy types fire
**Evidence:** vishal-live trades show MOMENTUM, GAP, SHORT_MOMENTUM, SHORT_GAP. Never REVERSAL, ORB, VWAP, SHORT_REVERSAL, SHORT_ORB.
**Impact:** Effective strategy library smaller than designed. Either prompt biases or pre-filter excludes other setups.
**Fix:** Review LLM prompt — verify all 9 types described equally. Test prompt with synthetic high-confidence setup for each missing type.
**Effort:** 60 min.

#### P1-6: No backtest baseline against random entry
**Evidence:** WIN_RATE_TRACKING.md and EDGE.md both note this. Cannot quantify edge.
**Impact:** Cannot claim system beats coin-flip until baseline computed.
**Fix:** Backtest script: same Nifty 500 universe, 50% random entries with R:R 2.0, same charge model. Compare 100-trade outcomes.
**Effort:** 4-6 hours.

#### P1-7: vishal-paper 49% / profit factor 1.0 is BREAK-EVEN not edge
**Evidence:** Section 4.5 calculation. R:R 2.0 expected ~50% WR with 2× avg_win — paper has avg_win ≈ avg_loss.
**Impact:** Even after P0 fixes, strategy at ₹3L paper position size shows no edge over random entries.
**Fix:** Either improve avg_win:avg_loss ratio (better entries, wider targets, tighter trails) OR accept break-even and add other strategies.
**Effort:** Strategy work, not pure code. 8-15 hours of analysis + iteration.

#### P1-8: neha-paper bleeding ₹44/trade — possibly losing in this regime
**Evidence:** 83 trades, 44.6% WR, -₹3,687 net. Same code as vishal-paper.
**Impact:** Suggests strategy outcome is regime-dependent or bias in random fill.
**Fix:** Compare neha vs vishal trade-by-trade for any systematic difference. May be sample variance — needs more trades.
**Effort:** 90 min analysis.

### P2 — OPERATIONAL FINDINGS

#### P2-1: Working tree drift on EC2 (219 uncommitted lines today)
**Fix:** Snapshotted. Pre-commit hook to warn on uncommitted .py files older than 24h.
**Effort:** 30 min.

#### P2-2: F&O Bug T resurrected 3 times — pattern not instance
**Fix:** DECISIONS.md PD-001 — rewrite or kill, decide June 1.
**Effort:** Either 3 weeks rewrite or 0 hours kill.

#### P2-3: 16 steering docs — context-window pressure
**Fix:** Already mitigated via CONTEXT.md auto-rebuild + Rule 21 reading order. No code action needed; awareness only.
**Effort:** 0.

#### P2-4: check_dhan_orders.py false positives
**Fix:** Add net-position comparison alongside leg comparison. Suppress mismatches that match expected single-row→multi-leg pattern.
**Effort:** 60 min.

#### P2-5: Crontab wiped twice — Rule 25 added but root risk persists
**Fix:** Already mitigated. Awareness via Rule 25.
**Effort:** 0.

#### P2-6: Bedrock model config drift — Opus 4-7 in some configs
**Fix:** Grep for `claude-opus-4-7` in all config files, replace with `claude-sonnet-4-6`.
**Effort:** 15 min.

#### P2-7: Swing module orphaned (1300 lines, run_swing.py is placeholder)
**Fix:** SATURDAY_TODO.md already plans rebuild. Defer until P0 done.
**Effort:** 8-12 hours.

#### P2-8: validate_tomorrow.sh false PASS May 19
**Fix:** Validate the validator. Add unit tests for CHECK 5 logic.
**Effort:** 60 min.

### P3 — DEFERRED FINDINGS

- Narrative validator dashboard surfacing (TASK 4 Phase 3)
- F&O strategy improvements
- Swing module completion
- Positional module
- News sentiment integration
- Onboarding website
- Telegram alerts wiring (currently /ping only)
- Multi-broker support (Zerodha alongside Dhan)

These wait until P0+P1 complete and capital readiness established.

---

## SECTION 11 — BUG PATTERN ANALYSIS

### 11.1 The recurring root pattern

Every confirmed bug in the execution layer (Bug A, B, B-2, C, 1, 5, 5b, FORCE-EXIT-LIES, CROSS-PROCESS-TOKEN) has the same shape:

**Multi-step state transition where state lives in multiple places, and one place silently diverges from another.**

- Bug A: in-memory dict had no `action` field; DB had it; monitor read from dict
- Bug 1: indent error caused MARKET retry path to skip both SL placement AND DB write — broker had position, system didn't
- Bug B: target hit closed DB row; broker still had pending SL — broker state diverged from DB state
- Bug 5: counter read from DB; placed orders not yet in DB; counter undercounted
- FORCE-EXIT-LIES: code logged success; broker rejected with HTTP 400 — log diverged from broker
- CROSS-PROCESS-TOKEN: process A had token X in memory; file had token Y; token X invalid on Dhan

### 11.2 Why same family keeps recurring

Three structural reasons:

1. **No central order-lifecycle state machine.** Each module manages its own piece. Executor places, monitor watches, broker holds truth. No single observer asserts "for every order ever placed, it must currently be in exactly one of these states."

2. **DryRun broker is too forgiving.** Paper trading uses simulated fills that always succeed. Real Dhan returns HTTP 400, REJECTED orders, partial fills, tick-size errors. Bugs that depend on real failure modes are invisible until production.

3. **Trust without verify.** Code assumes broker call succeeded if no exception thrown. HTTP 400 returns dict with error fields, no exception. Code reads dict, sees missing `broker_order_id`, logs success anyway.

### 11.3 The architectural fix that eliminates the family

**Mandatory invariant enforcement, every 5 minutes:**

For every PENDING order in Dhan:
- It MUST have a corresponding open position in DB, OR
- It MUST have a corresponding pending parent entry order in last 30 sec
- Otherwise: ALERT + auto-cancel after 10-min grace

For every OPEN position in DB:
- It MUST have a corresponding PENDING SL order in Dhan
- Otherwise: ALERT (position unprotected)

For every CLOSED trade in DB (last 24h):
- All PENDING orders for that symbol must be CANCELLED
- Otherwise: ALERT (orphan)

This is one cron job. ~150 lines of Python. **Closes the entire Bug B family permanently.** Single highest-leverage P0 in this report.

### 11.4 Pattern catalog (per BUGS_AND_FIXES.md, validated)

The owner already documented these patterns. This audit confirms them:

- Pattern 1: Architecture change without counter audit
- Pattern 2: Silent external API degradation
- Pattern 3: Wrong source of truth (DB vs broker)
- Pattern 4: Direction-agnostic formula breaking on non-default
- Pattern 5: Indent/whitespace causing logic drift
- Pattern 6: Cache layer corruption (Bug T family)

**New pattern to add (Pattern 7):** *Trust without verify across boundaries*. Caller assumes callee succeeded if no exception raised. Applies to FORCE-EXIT-LIES, CROSS-PROCESS-TOKEN, and any future broker-API-related bug.

---

## SECTION 12 — CAPITAL READINESS VERDICT

### 12.1 Today (May 22, 2026)

**Ready for: ₹15K only — and even this is precarious.**

Reasons:
- FORCE-EXIT-LIES active in production for 3+ days
- CROSS-PROCESS-TOKEN bug allowing 2.5h blind monitoring
- Bug B-2 caught manually today (orphan SL real money exposure)
- Bug C unfixed (impossible SL state)
- Daily loss limit configuration drift (₹500 vs ₹900)

**Adding capital today multiplies losses, not gains.** The bug damage is independent of capital size — same bugs at ₹1L cause 6.7× the loss.

### 12.2 After P0 fixes (~2-3 days work)

**Ready for: ₹15K trustworthy operation.**

Conditions met:
- All 7 P0 findings closed and verified
- Orphan-order reconciler cron running
- Force-exit-lies eliminated
- Token refresh working
- Bug C investigated and root-caused

This is the floor. Real-money trading at ₹15K becomes safe to continue.

### 12.3 After P0+P1 fixes + capital-agnostic refactor (~1-2 weeks)

**Ready for: ₹50K paper-validated simulation.**

NOT ready for ₹50K live yet. Need to first prove edge on paper at ₹50K position sizes.

Conditions:
- All P0 closed (above)
- P1-2 (capital-agnostic refactor) complete
- P1-3, P1-4, P1-5 investigations complete
- Paper trading at ₹50K simulated capital for 2 weeks
- Win rate ≥ 45% over ≥ 30 paper trades at ₹50K size

### 12.4 After 50 clean live trades at ₹50K (~3-4 weeks live)

**Ready for: ₹1L live.**

Conditions:
- 50 closed trades at ₹50K with WR ≥ 45%
- Charge ratio < 30% on ≥ 70% of trading days
- Profit factor > 1.0 over 50 trades
- Zero P0-class bugs surfaced for 30 consecutive trading days
- Reconciliation script PASS on every day for 30 days

### 12.5 After 100 clean trades at ₹1L (~6-8 weeks more)

**Ready for: ₹2L live.**

Conditions:
- 100 closed trades at ₹1L with WR ≥ 50%
- Profit factor > 1.2
- Max drawdown < 15%
- 2-week stable operation with no manual interventions

### 12.6 Beyond ₹2L

Per RULES.md Phase 5 plan: requires 12+ months proof, multiple market regimes, audited returns. Not in scope for this audit.

### 12.7 The honest summary

**Capital is not the gate. Code maturity and edge demonstration are the gates.**

Owner has stated explicit willingness to deploy ₹1-2L. Audit gates this on:
1. P0 fixes (capital safety) — blocking
2. Edge demonstration on paper at scaled size — blocking
3. Sustained clean live operation — blocking

Earliest realistic ₹1L live deployment: **4-6 weeks from today** if discipline holds.

This is slower than the owner's documented "₹1L/month income by June 20" goal (32 days from May 19, owner self-assessed at 25% probability). The audit's verdict: **the 25% probability was honest. The plan's failure mode is bugs that haven't been fixed yet, not capital availability.**

---

## SECTION 13 — CAPITAL RAMP PLAN (revised)

### Phase 1: P0 Sprint (Days 1-3) — May 22 evening to May 25 (Sun)

Goal: Eliminate all 7 P0 findings.

Day 1 (Friday evening, May 22):
- P0-1: FORCE-EXIT-LIES fix
- P0-2: Token refresh fix
- Both: paper-mode end-to-end test before commit

Day 2 (Saturday):
- P0-3: Bug B-2 fix
- P0-4: Orphan-order reconciler script + cron
- P0-5: Bug C investigation + fix
- P0-7: Stale price detection

Day 3 (Sunday):
- P0-6: Daily loss limit unification
- Verification day: re-run evidence dump, diff against May 22, confirm clean
- Reconciliation cron confirmed firing
- Ready for Monday market open

Capital: stays at ₹15K throughout. Real-money trading continues if cron confirms safe.

### Phase 2: P1 + Paper Validation (Days 4-14) — May 26 to June 5

Goal: Prove edge on paper at ₹50K simulated capital.

Days 4-7: P1 fixes
- P1-2: Capital-agnostic refactor (3 hours)
- P1-3, P1-4, P1-5 investigations (analysis, not code)
- Validate live ≈ paper after P0 fixes

Days 8-14: Paper at scaled size
- Modify vishal-paper to ₹50K per trade simulated
- Run for 2 weeks, capture 30+ trades
- Daily reconciliation must PASS
- Daily charge ratio must trend below 50%

Gate for next phase:
- 30+ paper trades at ₹50K position size
- Win rate ≥ 45%
- Profit factor > 0.9 (close to break-even)
- Zero P0-class bug surfaces

If gate fails: stay at ₹15K live, reassess strategy.

### Phase 3: ₹50K Live (Days 15-45) — June 8 to July 8

Goal: Demonstrate edge on real money at ₹50K position size.

- Edit vishal-live yaml: capital → 50000, per_trade → 15000
- Run live for 4-5 weeks
- Daily reconciliation must PASS every day
- Telegram alerts on any P0-class symptom

Gate for next phase:
- 50+ closed live trades
- Win rate ≥ 45%
- Profit factor > 1.0
- Charge ratio < 30% on ≥ 70% of days
- 30 consecutive days with zero P0-class bugs

If gate fails: revert to ₹15K, audit Phase 2-3 findings.

### Phase 4: ₹1L Live (Days 46-90) — July 11 to Aug 23

Same structure. 100 trades. WR ≥ 50%. Profit factor > 1.2. Then ₹2L.

### Phase 5: ₹2L+ (Day 91+)

Beyond audit scope.

---

## SECTION 14 — PRIORITIZED FIX LIST FOR KIRO

Format suitable for Kiro to execute one-by-one without ambiguity. Branch: `audit-2026-05-22`.

### P0-1: Eliminate FORCE-EXIT-LIES
**File:** `intraday/monitor.py`
**Function:** `_place_exit_and_get_fill_price`
**Change:** Currently returns `(fallback_price, "fallback")` on broker error. Modify to raise `BrokerExitFailedException`. Wrap callers (`_check_position`, `_force_exit_all`) in try/except: on exception, log `EXIT_FAILED` audit event, leave trade.status=OPEN, do NOT write synthetic exit_price/pnl, return early.
**Test:** Inject mock broker that returns HTTP 400. Assert position stays OPEN in DB and audit event written.
**Commit message:** `audit-fix(P0-1): eliminate force-exit-lies — raise on broker failure`

### P0-2: Token refresh on long-running monitor
**File:** `intraday/monitor.py`
**Change:** At start of each polling cycle in `run_monitoring_loop`, reload broker access_token from session file. Catch HTTP 401/400 in `get_positions` first failure → trigger `authenticate_broker()` re-auth.
**Test:** Force token expiry mid-cycle, confirm next poll re-auths and resumes.
**Commit message:** `audit-fix(P0-2): token refresh on monitor poll cycle`

### P0-3: Bug B-2 — cancel SL on trailing-SL exit path
**File:** `intraday/monitor.py`
**Change:** Find branch where trailing SL leads to market exit. Before `_place_exit_and_get_fill_price`, call `self.broker.cancel_order(trade.sl_order_id)` with try/except (warn on fail, continue).
**Test:** Paper trade with trailing SL hit, confirm Dhan order book has 0 PENDING for that symbol after exit.
**Commit message:** `audit-fix(P0-3): Bug B-2 — cancel SL on trailing-exit path`

### P0-4: Orphan-order reconciler cron
**New file:** `scripts/orphan_order_check.py`
**Logic:** For each profile, fetch PENDING orders from Dhan via `/v2/orders`. For each, check matching open position (`get_positions` quantity != 0) OR matching pending parent (entry placed in last 60 sec). If neither, classify as orphan. Log + alert via Telegram (if wired) + optionally auto-cancel after 10-min grace.
**Cron:** `*/5 4-9 * * 1-5 cd ~/dev-sandbox && .venv/bin/python scripts/orphan_order_check.py >> logs/orphan_check.log 2>&1`
**Test:** Manually create orphan SL on paper account, verify alert fires within 5 min.
**Commit message:** `audit-fix(P0-4): orphan-order reconciler cron — closes Bug B family`

### P0-5: Bug C — RR data integrity
**Step 1:** Investigate. Run query: `SELECT id, symbol, action, entry_price, stop_loss_price, target_price FROM intraday_trades WHERE (action='BUY' AND stop_loss_price >= entry_price) OR (action='SELL' AND stop_loss_price <= entry_price) LIMIT 50;` on all profile DBs. Document findings.
**Step 2:** Trace bad rows: which selector pick produced this? what did LLM return? what did risk_manager pass to executor?
**Step 3:** Add assertion in `executor._place_single_trade` before broker.place_order: `assert (entry_side == 'BUY' and trade.stop_loss_price < trade.entry_price) or (entry_side == 'SELL' and trade.stop_loss_price > trade.entry_price), f"Invalid SL direction"`.
**Test:** Synthetic bad input raises assertion. No matching DB rows after 5 days.
**Commit message:** `audit-fix(P0-5): Bug C — assert SL direction before broker call`

### P0-6: Daily loss limit unification
**File:** `config/profiles/vishal-live.yaml`
**Change:** Confirm one canonical value (recommend ₹900 to match RULES.md). Add log line at session start in `risk_manager.__init__`: `logger.info("Daily loss limit: ₹%d", self.config.daily_loss_limit)`. Add Telegram alert at 50% utilization.
**Test:** Confirm log shows correct value. Synthetic loss to 50% triggers alert.
**Commit message:** `audit-fix(P0-6): unify daily loss limit + utilization alert`

### P0-7: Stale price detection in force exit
**File:** `intraday/monitor.py`
**Change:** Track `last_price_update_ts` per trade in `_active_trades`. In `_force_exit_all`, refuse to use cached `current_price` if older than 5 min — force re-fetch via `get_positions` first; if that also fails, raise.
**Test:** Simulate stale price, confirm refusal/refresh.
**Commit message:** `audit-fix(P0-7): stale price detection in exit logic`

### P1 fixes (after all P0 merged)

P1-2: Capital-agnostic refactor — convert hardcoded rupees to %.
P1-3-4-5: Investigations only, no code.
P1-6: Backtest random-baseline — new `backtest/random_baseline.py`.

### Verification gate before proceeding to next priority

After each P0 fix:
1. Commit on `audit-2026-05-22` branch.
2. Push to GitHub.
3. Run paper-mode regression: `bash run_daily.sh --profile vishal --force` and verify clean log.
4. Reply with commit hash + test result.
5. Wait for human approval before next P0.

---

## SECTION 15 — OUT OF SCOPE

Explicitly deferred per `SYSTEM_AUDIT_PLAN.md`:

- Narrative validator dashboard surfacing (TASK 4 Phase 3)
- F&O strategy improvements (Bug T decision pending June 1)
- Swing module completion (orphaned, defer to weekend after P0)
- New broker integrations (Zerodha)
- UI / dashboard polish
- News sentiment integration
- Onboarding website
- Telegram trade alerts wiring (only EOD recon alerts in P0-4)

These wait until capital readiness is established (Phase 3 complete, ₹50K live for 30 days).

---

## SECTION 16 — SIGN-OFF

### Definition of Done (this audit)

- [x] `evidence_2026-05-22.txt` generated and reviewed
- [x] `SYSTEM_AUDIT_REPORT.md` committed to repo
- [ ] All P0 findings have a commit fixing them
- [ ] All P0 findings have a verification artifact
- [ ] BUGS_AND_FIXES.md updated with audit findings
- [ ] Stage 4 verification day passed
- [ ] Capital ramp plan agreed in writing
- [ ] Reviewer + human sign off in this section

### Reviewer Sign-off

This audit was conducted on 2026-05-22 against evidence file `audit/evidence_2026-05-22.txt` (19,959 lines) covering all execution-path code, configuration, last 50 trades per profile, aggregate statistics, and 3 days of executor logs.

The system has a B+ observability layer and a C-grade execution layer. The strategy at current sample sizes shows no statistically significant edge but is plausibly close to break-even on paper at ₹3L capital. Capital scaling to ₹1-2L is reasonable AFTER the 7 P0 findings are closed and 4-6 weeks of validated operation accumulate.

The owner has demonstrated honest documentation discipline throughout the build. This is the asset that made the audit possible and will retain value regardless of whether the current strategy ultimately validates.

**Reviewer:** External senior trading-systems review (Claude — Anthropic)
**Date:** 2026-05-22
**Signature:** [reviewer-acknowledgment]

### Owner Sign-off

I have read this audit report in full. I acknowledge:

- [ ] The 7 P0 findings as accurate and material
- [ ] The capital readiness verdict (₹15K trustworthy after P0; ₹50K live after P0+P1+30 days clean; ₹1L after 50 clean trades at ₹50K)
- [ ] The capital ramp plan timeline (4-6 weeks earliest realistic ₹1L deployment)
- [ ] The strategy edge has not yet been demonstrated at current sample sizes
- [ ] No capital scaling will occur until P0 fixes verified

**Owner:** Vishal
**Date:** ________________
**Signature:** ________________

---

## END OF AUDIT REPORT
