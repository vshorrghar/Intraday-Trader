# F&O Relaxation Pre-Check
**Generated:** 2026-05-28 (READ-ONLY analysis, no code modified)

---

## 1. CURRENT STATE OF RULES ENGINE

Values currently in `fno/rules_strategy_engine.py`:

### IRON_CONDOR rule:
| Filter | Current Value | Notes |
|--------|--------------|-------|
| confluence_score min | **8** | (was 12 in prompt, already relaxed in code) |
| IVP min | **40** | (was 50 in prompt, already relaxed in code) |
| VRP min | **0.5** | (was 1.0 in prompt, already relaxed in code) |
| DTE range | **3-12** | (was 4-10 in prompt, already relaxed in code) |
| Regime allowlist | `SIDEWAYS` only | Single regime |
| Strike sigma width | **0.5σ** | (was 0.7σ in prompt, already relaxed in code) |

### BULL_PUT_SPREAD:
| Filter | Current Value |
|--------|--------------|
| IVP min | **45** |
| DTE range | **4-15** | (was 5-14 in prompt, already relaxed) |
| Strike delta (short) | 0.30 |
| Strike delta (long) | 0.15 |

### BEAR_CALL_SPREAD:
| Filter | Current Value |
|--------|--------------|
| IVP min | **45** |
| DTE range | **4-15** |

### LONG_STRADDLE:
| Filter | Current Value |
|--------|--------------|
| IVP max (cheap vol) | **30** |
| VRP max | Not explicitly checked (only IVP + event_day) |

### Hard Skips:
| Filter | Current Value |
|--------|--------------|
| VIX max | **25** |
| Confluence floor | **8** |

### Summary
The code was ALREADY written with relaxed values (the "2026-05-28: relaxed" comments in the code indicate these were applied during Phase 3 creation). The prompt said "relaxed for paper flow" and the implementation took that literally.

---

## 2. PHASE 3 BACKTEST RESULTS

From `vishal-docs/FNO_RULES_VS_LLM_COMPARISON.md`:

| Metric | Value |
|--------|-------|
| Projected trades per month | **15-18** (moderate estimate) |
| Projected avg P&L per trade | **₹141** |
| Days rules fire ZERO when LLM placed | ~2/12 (VIX/IVP gates) |
| Days rules say NO_TRADE but LLM placed | ~2/12 |

Note: This was a PROJECTION based on probability modeling, not a replay of historical data (we don't have stored IVP/VRP per historical day to replay exactly).

---

## 3. TIGHTNESS DIAGNOSIS

Ranked by impact on trade frequency (most restrictive first):

### 1st: Regime = SIDEWAYS only (for Iron Condor)
**Impact: HIGH.** Indian market is sideways ~60% of days. The other 40% (trending) can only trigger spreads. Since 97% of historical trades were Iron Condors, this single filter blocks ~40% of potential trading days for the primary strategy.

**Relaxation option:** Add `MarketRegime.HIGH_VOLATILITY` to IC allowlist (with tighter strikes). Or allow IC when regime is ambiguous/borderline.

### 2nd: IVP ≥ 40 (for Iron Condor)
**Impact: MEDIUM.** By definition, IVP < 40 occurs 40% of the time. Combined with regime filter, this blocks another ~16% of remaining days.

**Relaxation option:** Drop to IVP ≥ 30 (only skip when IV is genuinely cheap).

### 3rd: VRP ≥ 0.5 (for Iron Condor)
**Impact: MEDIUM-LOW.** VRP is usually positive in Indian markets (options overpriced). VRP < 0.5 occurs maybe 20-30% of days. But when VRP is low, selling premium has less edge.

**Relaxation option:** Drop to VRP ≥ 0 (only skip when realized vol exceeds implied — rare).

### Honorable mention: DTE 3-12
Already quite wide. Weekly expiry cycle means most days have DTE 1-7. The 3-12 range covers most scenarios. Not a major limiter.

---

## 4. PHASE 4 (ADJUSTMENT LOGIC) DEPENDENCIES

### Does Phase 4 depend on specific Phase 3 filter values?
**NO.** Adjustment logic triggers on POSITION STATE (underlying near short strike), not on entry filters. Entry filters determine IF a trade is placed; adjustment logic determines what happens AFTER it's placed.

### Will relaxing entry filters affect adjustment trigger logic?
**INDIRECTLY.** Looser entry filters → more trades → more positions to monitor → more adjustment triggers. But the adjustment LOGIC itself (0.5σ proximity trigger, max 2 adjustments) is independent of entry thresholds.

### Constants shared between rules_strategy_engine.py and adjustment_engine.py?
**ONE:** The `sigma_multiplier` (0.5σ) used for strike selection is related to the adjustment trigger (0.5σ proximity). If we widen entry strikes to 0.5σ, the adjustment trigger at 0.5σ means it fires when underlying reaches the short strike — which is correct behavior. No conflict.

---

## 5. TEST IMPACT

### Tests that hardcode specific thresholds:

| Test | Hardcoded Values | Would Break If... |
|------|-----------------|-------------------|
| `test_no_trade_when_confluence_low` | confluence=7 | confluence_min drops below 7 |
| `test_iron_condor_when_sideways_moderate_ivp` | ivp=45, vrp=0.8 | IVP min drops below 45 OR VRP min drops below 0.8 |
| `test_iron_condor_rejected_low_ivp` | ivp=35 | IVP min drops to 35 or below |
| `test_iron_condor_dte_boundary_low` | dte=3 | DTE min drops below 3 |
| `test_iron_condor_dte_too_high` | dte=13 | DTE max rises above 13 |

### Tests that would fail if confluence_min drops from 8 to lower:
- `test_no_trade_when_confluence_low` uses confluence=7. If min drops to 6, this test would PASS when it should FAIL. **1 test needs update.**

### Tests that test exact strike selection:
- `test_strike_selection_iron_condor` — tests structure (PE_buy < PE_sell < spot < CE_sell < CE_buy) and wing width ≥ 100pts. Does NOT test exact sigma value. **0 tests would break from sigma change.**

---

## 6. WORK COST ESTIMATE

| Dimension | Assessment |
|-----------|-----------|
| Time to apply relaxation | **~15 minutes** (change 5-6 constants + update 1-2 test assertions) |
| Tests requiring updates | **1-3** (depending on how far you relax) |
| Risk to Phase 3 deliverables | **LOW** — structure unchanged, only threshold values shift |
| Recommend timing | **Apply NOW** — before Phase 4 |

### Reasoning for "Apply NOW":
1. Phase 4 (adjustment logic) is independent of entry thresholds
2. Relaxation is a config-level change, not architectural
3. Getting more trades flowing ASAP means more data for Phase 6 validation
4. No point building adjustment logic for trades that never fire

### What "even looser" could look like:

| Filter | Current | Possible Relaxation | Risk |
|--------|---------|--------------------|----|
| Confluence min | 8 | 5 | LOW (paper mode) |
| IVP min (IC) | 40 | 30 | MEDIUM (less edge when IV cheap) |
| VRP min (IC) | 0.5 | 0.0 | MEDIUM (no edge guarantee) |
| DTE range (IC) | 3-12 | 2-14 | LOW (wider window) |
| Regime (IC) | SIDEWAYS only | SIDEWAYS + HIGH_VOL | MEDIUM (wider strikes needed) |
| Sigma (strikes) | 0.5σ | 0.4σ | LOW (closer strikes = more premium but more risk) |
| IVP min (spreads) | 45 | 35 | LOW (spreads are hedged) |

**Projected impact of full relaxation:**
- Current: 15-18 trades/month
- After full relaxation: 20-30 trades/month
- Reaches 30-trade validation gate in ~5-6 weeks instead of ~7-8 weeks

---

## CONCLUSION

The rules engine was ALREADY written with relaxed values (the Phase 3 prompt said "relaxed for paper flow" and the code implemented that). The current thresholds are:
- Confluence ≥ 8 (not 12)
- IVP ≥ 40 (not 50)
- VRP ≥ 0.5 (not 1.0)
- DTE 3-12 (not 4-10)
- Sigma 0.5 (not 0.7)
- **Regime: SIDEWAYS + HIGH_VOLATILITY** (expanded Phase 3.1, was SIDEWAYS only)

### Updated Trade Projection (Post Phase 3.1 Regime Expansion)

**Before expansion (SIDEWAYS only):**
- IC eligible days: ~60% (sideways market probability)
- Projected: 15-18 trades/month

**After expansion (SIDEWAYS + HIGH_VOLATILITY):**
- IC eligible days: ~60% (sideways) + ~25% (HIGH_VOL with VIX 20-25) = ~85%
- But HIGH_VOL days still gated by IVP≥40 + VRP≥0.5
- Net increase: ~30-40% more eligible days
- **New projection: 20-25 trades/month**

This hits the target range of 15-25 trades/month requested by user.

**Awaiting user decision on whether further relaxation is needed.**
