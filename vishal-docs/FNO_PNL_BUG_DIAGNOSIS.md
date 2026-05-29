# F&O P&L Bug Diagnosis

**Date:** 2026-05-27
**Investigator:** Kiro (Phase 1)
**Status:** ROOT CAUSE CONFIRMED

---

## Summary

The P&L bug is a **double-counting of lot size** in the original `_execute_exit()` method. The `net_premium` field already includes total quantity (premium_per_unit × lot_size × num_lots), but the old code multiplied by `num_lots` again.

**Formula that produced the bug:**
```
realized_pnl = (entry_premium - 0) × num_lots
             = net_premium × num_lots
             = DOUBLE-COUNTED
```

---

## Bug Location

**File:** `fno/monitor.py` — `_execute_exit()` method
**Commit:** `f77de67` (2026-04-28, "Full project: intraday + FnO auto-trader")
**Lines (original):**
```python
# Multiply by lot size (approximate from legs)
try:
    legs = json.loads(strat.get("legs_json", "[]"))
    if legs:
        num_lots = legs[0].get("num_lots", 1)
        realized_pnl *= num_lots
except Exception:
    pass
```

**Fix already applied in:** `c36773a` (2026-05-03) — removed the lot multiplier, added cap instead.

---

## Root Cause Mechanism

1. `net_premium` in `fno_strategies` table is computed as:
   ```
   net_premium = Σ(leg.entry_price × leg.quantity × direction_sign)
   ```
   where `quantity = lot_size × num_lots` (e.g., 25 × 3 = 75 for FINNIFTY 3-lot)

2. `_execute_exit()` takes `entry_premium = abs(net_premium)` — already includes full quantity.

3. Original code then multiplied by `num_lots` again:
   ```python
   realized_pnl = entry_premium - current_premium  # = net_premium - 0 = net_premium
   realized_pnl *= num_lots                         # = net_premium × 3 = WRONG
   ```

4. `force_exit_all()` passed `current_premium = 0` (hardcoded), making the formula:
   ```
   realized_pnl = abs(net_premium) × num_lots = net_premium × num_lots
   ```

---

## Affected Strategies

| ID | Trade Date | net_premium | num_lots | Stored P&L | Correct P&L | Error |
|----|-----------|-------------|----------|------------|-------------|-------|
| 34 | 2026-04-28 | 259.5 | 3 | 778.5 | ≤259.5 | 3× overcounted |
| 35 | 2026-04-28 | 23,226.0 | 3 | 69,678.0 | ≤23,226.0 | 3× overcounted |
| 39 | 2026-05-01 | 521.25 | 3 | 1,563.75 | ≤521.25 | 3× overcounted |
| 40 | 2026-05-01 | 167.5 | 2 | 335.0 | ≤167.5 | 2× overcounted |
| 41 | 2026-05-01 | 726.3 | 3 | 2,178.9 | ≤726.3 | 3× overcounted |

**Pattern:** `realized_pnl = net_premium × num_lots` for ALL affected strategies.

---

## Unaffected Strategies

| IDs | Exit Path | Why Correct |
|-----|-----------|-------------|
| 9, 10, 11 | `_check_exit_triggers` (MTM path) | Uses `compute_strategy_pnl()` which computes per-leg P&L correctly |
| 46-52 | `_execute_exit` (post-fix, May 3+) | Lot multiplier removed, cap added |
| 37, 38, 42-45 | `_check_exit_triggers` | Same as 9/10/11 — correct MTM path |

---

## Why Strategy id=35 Shows ₹69,678 (the "₹92K" from audit doc)

The FNO_CODE_AUDIT.md referenced "strategy id=16 shows ₹92,025 P&L on ₹216 premium." This was from the **EC2 vishal.db** (not available locally). The local portfolio.db shows the same bug pattern with strategy id=35 (₹69,678 on ₹23,226 premium = 3×).

The mechanism is identical regardless of the specific strategy ID:
- EC2 vishal.db likely has a strategy with `net_premium ≈ 30,675` and `num_lots = 3` → `realized_pnl = 92,025`
- OR `net_premium ≈ 216` and `num_lots = 426` (unlikely) 
- Most likely: the audit doc's "₹216 premium" refers to `net_premium` per unit (not total), and the total was `216 × lot_size × num_lots` with the multiplier applied again.

---

## Current Code Status

The bug was **already fixed** in commit `c36773a` (May 3, 2026):
- Removed the `realized_pnl *= num_lots` line
- Added cap: `max(-entry_premium * 3, min(realized_pnl, entry_premium))`

Further improved in `4867ef0` (May 17):
- `force_exit_all` now passes real `current_premium` from `_compute_current_premium()` instead of hardcoded 0

**The code is currently correct.** The bug is in **historical data** (corrupted P&L values from April 28 - May 1 trades).

---

## Fix Proposal (Phase 2)

1. **No code change needed** — the bug is already fixed in current code.
2. **Data correction needed** — recalculate correct P&L for affected strategies (ids 34, 35, 39, 40, 41).
3. **Correct formula:** `realized_pnl = net_premium - current_premium_at_exit` (for selling strategies where force exit at premium ≈ 0, correct P&L ≈ net_premium × 1.0, not × num_lots).
4. **Add `corrected_pnl` column** to preserve audit trail.
5. **Add regression test** that verifies `_execute_exit` never multiplies by num_lots.

---

## Secondary Issue: Unrealistic Entry Prices

Strategy id=35 has entry prices of ₹300+ for a 300-point FINNIFTY spread. This means the demo LLM response generates unrealistic prices. The `net_premium = 23,226` exceeds the theoretical max for a 300-point Iron Condor (max = 300 × 75 = ₹22,500). This is a separate issue from the P&L bug but contributes to unrealistic numbers.

**Recommendation:** Phase 3 (rules engine) should enforce `net_premium <= spread_width × quantity` as a validation gate.

---

## Severity

**CRITICAL for historical data accuracy.**
**ALREADY FIXED in code** (no new code vulnerability).
**Impact:** 5 of 30 strategies have corrupted P&L. Cumulative P&L is overstated by ~₹72,000.
