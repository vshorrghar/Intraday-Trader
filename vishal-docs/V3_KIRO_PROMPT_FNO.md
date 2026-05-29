# KIRO F&O MODULE — PRODUCTION READINESS PROMPT

═══════════════════════════════════════════════════════════════════════

You are fixing critical bugs in the F&O module and making it production-
ready. The infrastructure exists (5,402 lines across 16 files in fno/)
with 96 paper trades placed, but P&L numbers are corrupted and adjustment
logic is missing.

This prompt covers Phases 1-6 to get F&O from "untrustworthy paper" to
"validated paper ready for live graduation."

This prompt is the complete contract. Do not deviate.

═══════════════════════════════════════════════════════════════════════
## PART 1: ANTI-LOOP DISCIPLINE RULES
═══════════════════════════════════════════════════════════════════════

In your previous sessions you have spent 5+ hours stuck in tool retry
loops and pivoted from main task mid-session. THIS WILL NOT HAPPEN.

Hard rules:

1. PHASE GATES are MANDATORY. Complete acceptance criteria, stop, report.
2. NO TOOL LOOPS. If fs_write fails 2 times, switch to heredoc OR scp.
3. NO MID-PHASE PIVOTS. Continue current phase to completion.
4. NO REINVENTION. Reuse existing modules.
5. CHECKPOINT BEFORE EACH PHASE:
   ```
   git status
   .venv/bin/python -m pytest tests/ -q (135 tests must continue passing)
   ```
6. THIS SESSION = F&O ONLY. Do not touch swing/, intraday/v3/, or any V3 build files.

═══════════════════════════════════════════════════════════════════════
## PART 2: LOCKED DECISIONS
═══════════════════════════════════════════════════════════════════════

**KNOWN BUG (Priority 1 to fix):**
- Strategy id=16 shows ₹92,025 P&L on ₹216 premium = 426x impossible
- Root cause: somewhere in fno/pnl_calculator.py OR fno/monitor.py
- All 96 paper trades' P&L numbers are suspect

**LIVE READINESS GATE (LOCKED):**
F&O cannot go live until ALL of these:
- P&L bug fixed and validated
- 30+ paper trades with VERIFIED accurate P&L
- Win rate >= 60% on Iron Condors
- No single trade with > 2× max theoretical loss
- Adjustment logic working OR position size halved

**CAPITAL (LOCKED):**
- Paper capital: ₹50,000 per profile
- Live deployment: NOT in this prompt
- Real money cron stays DISABLED for vishal-live throughout this work

**DO NOT MODIFY:**
- ❌ fno/option_chain.py (works, fetches Dhan chain correctly)
- ❌ fno/greeks.py (Black-Scholes math is correct)
- ❌ fno/symbols.py (Dhan tradingsymbol format works)
- ❌ Real money YAML configs
- ❌ Any cron entry that places live trades
- ❌ Any V3 intraday or swing code

═══════════════════════════════════════════════════════════════════════
## PART 3: PHASES
═══════════════════════════════════════════════════════════════════════

---

### PHASE 1: P&L BUG INVESTIGATION (Budget: 2 hours)

**GOAL:** Find the exact bug causing ₹92K P&L on ₹216 premium.

**DELIVERABLES:**

A) Reproduce the bug:
1. Pull strategy id=16 from DB
2. Pull all leg fills, exit triggers, MTM updates
3. Manually compute correct P&L using Black-Scholes + actual fills
4. Compare to stored P&L → identify where bug enters

B) Document findings in `vishal-docs/FNO_PNL_BUG_DIAGNOSIS.md`
- Exact strategy details (legs, entry/exit prices, qty)
- Stored P&L: ₹92,025
- Correct P&L: [computed value]
- Discrepancy: [magnitude]
- Bug location: [file:line]
- Root cause: [mechanism]

C) Likely suspects (investigate in order):
1. fno/pnl_calculator.py — wrong premium direction (sold credit vs paid debit)
2. fno/monitor.py — exit P&L using stale prices
3. fno/paper_engine.py — simulated theta decay accumulation bug
4. Position sizing × premium multiplier confusion (qty × multiplier × price)
5. Aggregation across legs missing sign flip

**ACCEPTANCE CRITERIA:**
- [ ] Bug reproduced for strategy id=16
- [ ] Manual P&L computation matches reality
- [ ] Root cause file:line identified
- [ ] Fix proposed (not yet applied — that's Phase 2)
- [ ] Diagnosis doc committed

**STOP. Report. Wait for approval to proceed to Phase 2.**

---

### PHASE 2: P&L BUG FIX + VALIDATION (Budget: 2 hours)

**GOAL:** Apply fix. Validate against ALL 96 historical paper trades.

**DELIVERABLES:**

A) Apply fix to identified file(s)

B) Add unit test that fails before fix, passes after:
   `tests/fno/test_pnl_bug_regression.py`
   - Test reproduces strategy id=16 scenario
   - Asserts P&L is computed correctly

C) Backfill validation script: `scripts/fno_revalidate_pnl.py`
   - Iterate all 96 paper trades in DB
   - Recompute P&L using fixed logic
   - Print diff: stored_pnl vs corrected_pnl
   - Flag trades with discrepancy > 5%
   - Output: `vishal-docs/FNO_PNL_REVALIDATION_REPORT.md`

D) Update DB with corrected P&L (separate column to preserve audit trail):
   ```sql
   ALTER TABLE fno_strategies ADD COLUMN corrected_pnl REAL;
   UPDATE fno_strategies SET corrected_pnl = [computed] WHERE id = X;
   ```

**ACCEPTANCE CRITERIA:**
- [ ] Fix applied and committed
- [ ] Regression test passes
- [ ] All 96 trades revalidated
- [ ] Revalidation report shows realistic P&L distribution (no ₹92K outliers; max single-trade should be 1-1.5× premium)
- [ ] Total cumulative P&L now reflects reality
- [ ] All 136+ tests pass (135 existing + 1 new regression)

**STOP. Report. Show before/after cumulative P&L. Wait for approval.**

---

### PHASE 3: REPLACE LLM STRATEGY SELECTION WITH RULES (Budget: 2 hours)

**GOAL:** F&O strategy selection becomes deterministic. No more LLM judgment.

**DELIVERABLES:**

A) `fno/rules_strategy_engine.py` (already exists per ground truth — verify)
   If exists, audit and harden. If not, create.

   Strategy selection rules (deterministic):
   ```
   IF VIX > 22 OR confluence_score < 20:
       → NO TRADE
   ELIF regime == "SIDEWAYS" AND IVP >= 65 AND VRP >= 2.0
        AND DTE between 5-7 AND |spot - max_pain| < 0.8% of spot:
       → IRON_CONDOR
   ELIF regime == "TRENDING_UP" AND IVP >= 55 AND IV_skew bullish
        AND DTE between 7-14:
       → BULL_PUT_SPREAD
   ELIF regime == "TRENDING_DOWN" AND IVP >= 55 AND IV_skew bearish
        AND DTE between 7-14:
       → BEAR_CALL_SPREAD
   ELIF event_day == True AND IVP <= 25 AND VRP <= -1.0:
       → LONG_STRADDLE (cheap vol before expected event)
   ELSE:
       → NO TRADE
   ```

B) Strike selection rules (deterministic, no LLM):
   - Iron Condor: short strikes at 1-sigma each side, wings 200pts away
   - Spreads: short at 0.3 delta, long at 0.15 delta
   - Straddle: ATM strike

C) Update run_fno.py to call rules_strategy_engine instead of LLM
   - Keep LLM code path but disabled by config flag
   - config: `fno.use_rules_engine: true` (default true)

D) Test against last 20 paper trades:
   - Re-run strategy selection on historical option chain snapshots
   - Verify same/similar strategies chosen
   - Document any cases where rules disagree with what was placed

**ACCEPTANCE CRITERIA:**
- [ ] rules_strategy_engine.py implements all 5 rules above
- [ ] No more Bedrock calls in normal F&O flow
- [ ] tests/fno/test_rules_strategy_engine.py shows 8+ passed
- [ ] Backtest against 20 historical days produces sensible strategies
- [ ] All 144+ tests pass

**STOP. Report. Wait for approval.**

---

### PHASE 4: ADJUSTMENT LOGIC (Budget: 3 hours)

**GOAL:** When underlying tests short strike, roll the tested side.

**DELIVERABLES:**

A) `fno/adjustment_engine.py`

   Triggers:
   - Iron Condor: when underlying within 0.5σ of either short strike
   - Short Strangle: same trigger
   - Credit Spread: when underlying within 1.0σ of short strike

   Adjustment actions:
   - Iron Condor tested side: roll tested vertical further OTM (same expiry)
     - Example: NIFTY at 24000, short 24200 CE tested
     - → Buy back 24200/24400 CE spread, sell 24400/24600 CE spread
     - → Lock partial loss, reduce risk
   - Iron Condor far side: collapse the safe vertical (close it)
     - Example: 23700/23500 PE spread is safe → close it for small profit
     - → Frees margin, reduces gamma
   - Single-leg credit spread tested: roll out and down/up by 1 strike

   Limits:
   - Max 1 adjustment per strategy per day
   - Max 2 adjustments per strategy lifetime
   - If adjustment would lock loss > 2× original max profit: just exit instead

B) Add adjustment trigger check to fno/monitor.py
   - Monitor cycle (every 15 min) checks adjustment criteria
   - Calls adjustment_engine if triggered
   - Records adjustment in DB: adjustments table

C) DB schema:
   ```sql
   CREATE TABLE fno_adjustments (
       id INTEGER PRIMARY KEY,
       strategy_id INTEGER,
       adjustment_time TEXT,
       trigger_reason TEXT,
       legs_added TEXT,      -- JSON
       legs_removed TEXT,    -- JSON
       net_pnl_impact REAL,
       FOREIGN KEY(strategy_id) REFERENCES fno_strategies(id)
   );
   ```

D) Tests:
   - test_iron_condor_short_strike_test_triggers_roll
   - test_safe_side_collapse_when_far_otm
   - test_max_2_adjustments_per_strategy
   - test_adjustment_skipped_if_loss_too_large

**ACCEPTANCE CRITERIA:**
- [ ] adjustment_engine.py implements all 3 strategy adjustments
- [ ] monitor.py calls adjustment check each cycle
- [ ] DB schema migrated
- [ ] tests/fno/test_adjustment.py shows 4+ passed
- [ ] Run on 5 simulated tested-strike scenarios — all behave correctly
- [ ] All 148+ tests pass

**STOP. Report. Wait for approval.**

---

### PHASE 5: PAPER MODE PRICING FIX (Budget: 1 hour)

**GOAL:** Paper mode uses real option chain prices, not random simulation.

**DELIVERABLES:**

A) Audit fno/paper_engine.py
   - Currently uses random theta decay + noise (per ground truth)
   - Replace with: fetch real option chain prices via Dhan
   - Use real prices for entry, MTM, exit P&L

B) Behavior change:
   - On paper entry: use mid-price from current Dhan chain
   - On paper monitoring: refresh prices every 15 min from Dhan
   - On paper exit: use mid-price at exit time

C) Cache layer:
   - Paper mode shares same option_chain_cache as live
   - 5-min TTL is fine for paper monitoring

D) Validation:
   - Place 1 paper trade with new logic
   - Verify entry price matches mid of bid/ask from chain
   - Verify monitor updates use fresh prices
   - Verify exit P&L matches real chain delta

**ACCEPTANCE CRITERIA:**
- [ ] paper_engine.py uses real Dhan prices throughout
- [ ] No more random theta simulation
- [ ] 1 test paper trade validated end-to-end
- [ ] All 148+ tests pass

**STOP. Report. Wait for approval.**

---

### PHASE 6: 30-TRADE VALIDATION GATE (Budget: tracked over 30 trading days)

**GOAL:** Run 30 paper trades with all fixes applied. Track honestly.

THIS PHASE TAKES 30+ TRADING DAYS. Phases 1-5 ship the code.
Phase 6 is the validation gate that determines live deployment readiness.

**DELIVERABLES:**

A) `scripts/fno_paper_validation_tracker.py`
   - Runs daily, reads fno_strategies for current paper run
   - Tracks since "validation_start_date" (set today)
   - Output: `vishal-docs/FNO_VALIDATION_PROGRESS.md` (updated daily)

   Metrics tracked:
   - Trades placed
   - Trades closed
   - Win rate (closed only)
   - Profit factor
   - Avg P&L per trade
   - Max single-day drawdown
   - Max single-trade loss vs theoretical max loss
   - Adjustments triggered
   - Trades requiring force exit

B) Live deployment gate:
   ```
   IF trades >= 30
      AND win_rate >= 60%
      AND profit_factor >= 1.4
      AND no_trade_exceeded_max_loss
      AND adjustment_logic_fired_correctly_in_tested_cases:
       THEN approve live deployment with 1 lot, ₹50K margin
   ELSE:
       extend paper period or document failure
   ```

C) Add to cron (already runs F&O paper at 9:20 AM):
   No changes needed — existing cron continues

D) Add validation tracker to cron:
   ```
   30 10 * * 1-5 cd /home/ec2-user/dev-sandbox && \
       .venv/bin/python scripts/fno_paper_validation_tracker.py \
       >> logs/fno_validation.log 2>&1
   ```

**ACCEPTANCE CRITERIA:**
- [ ] Tracker script created and tested
- [ ] Cron entry added
- [ ] First report generated for current state
- [ ] Validation gate criteria documented

**STOP. Final report. F&O is now in PAPER VALIDATION mode for 30 trades.**

═══════════════════════════════════════════════════════════════════════
## PART 4: WHAT YOU MUST NOT DO
═══════════════════════════════════════════════════════════════════════

- ❌ Do not modify any swing/* file
- ❌ Do not modify any intraday/v3/* file (V3 build is in another session)
- ❌ Do not enable live F&O trading (cron stays disabled for vishal-live)
- ❌ Do not skip Phase 1 — bug must be diagnosed before fix
- ❌ Do not "tweak" P&L formula until you understand the bug
- ❌ Do not add new strategy types beyond the 5 in Phase 3 rules
- ❌ Do not retry failed tools more than 2 times
- ❌ Do not delete the LLM strategy engine — disable via config flag

═══════════════════════════════════════════════════════════════════════
## PART 5: REPORTING PROTOCOL
═══════════════════════════════════════════════════════════════════════

After each phase:

```
F&O PHASE X COMPLETE

Files created: [list]
Files modified: [list]
Tests added: [count]
Tests passing: [count]/[total]
Acceptance criteria: [N/N]
Time elapsed: [minutes]

[Phase 1 specific:]
Bug location: [file:line]
Root cause: [mechanism]
Severity: [CRITICAL / HIGH / MEDIUM]

[Phase 2 specific:]
Total trades affected: [N]
Cumulative P&L before fix: ₹[X]
Cumulative P&L after fix: ₹[Y]
Discrepancy: ₹[Z]
Trades with > 5% discrepancy: [N]

Awaiting approval for Phase X+1.
```

═══════════════════════════════════════════════════════════════════════
## PART 6: CONFIRMATION REQUIRED
═══════════════════════════════════════════════════════════════════════

Before writing code, reply with:

1. "I have read all 6 parts and understand the constraints."
2. "I will not modify swing/ or intraday/v3/ files."
3. "I will not enable live F&O trading in this prompt."
4. "I will follow phase gates strictly."
5. "I will diagnose the P&L bug fully before applying any fix."

Then state: "Beginning Phase 1: P&L Bug Investigation."

═══════════════════════════════════════════════════════════════════════
END OF F&O PROMPT
═══════════════════════════════════════════════════════════════════════
