# F&O P&L Revalidation Report
**Generated:** 2026-05-28
**Scope:** All databases (local + EC2 production)

---

## Executive Summary

| Database | Strategies | Corrupted | Before | After | Discrepancy |
|----------|-----------|-----------|--------|-------|-------------|
| portfolio.db (local) | 30 | 5 | ₹85,917 | ₹36,283 | ₹49,634 |
| vishal.db (EC2) | 35 | 1 | ₹96,925 | ₹5,115 | ₹91,810 |
| neha.db (EC2) | 15 | 1 | -₹117,526 | ₹486 | -₹118,013 |
| vishal-live.db (EC2) | 3 | 0 | ₹2,600 | ₹2,600 | ₹0 |

**Total strategies corrected: 7** (5 local + 1 vishal + 1 neha)

---

## TRUE F&O Performance (EC2 Production — Corrected)

| Metric | Value |
|--------|-------|
| **Total strategies with P&L** | 53 |
| **Winners** | 46 |
| **Losers** | 7 |
| **Win rate** | **86.8%** |
| **Cumulative P&L** | **₹8,201.50** |
| **Avg P&L per trade** | **₹154.75** |

### Per-Profile Breakdown
| Profile | Strategies | Win Rate | P&L |
|---------|-----------|----------|-----|
| vishal (paper) | 35 | 85.7% | ₹5,115 |
| neha (paper) | 15 | 86.7% | ₹486 |
| vishal-live (paper F&O) | 3 | 100% | ₹2,600 |

---

## Bugs Found and Corrected

### Bug 1: Lot-Multiplication Double-Count (f77de67)
**Affected:** portfolio.db strategies 34, 35, 39, 40, 41
**Mechanism:** `_execute_exit()` multiplied `realized_pnl` by `num_lots`, but `net_premium` already included total quantity.
**Fix:** Divided stored P&L by num_lots.
**Status:** Code fixed in c36773a (May 3). Data corrected today.

### Bug 2: MTM Unbounded P&L Write (_check_exit_triggers)
**Affected:** vishal.db strategy 16, neha.db strategy 11
**Mechanism:** `_check_exit_triggers()` wrote `compute_strategy_pnl()` output directly to DB without bounds checking. When option chain returned wrong prices (stale data, wrong expiry match), P&L was wildly wrong.
- vishal.db ID=16: ₹92,026 profit on ₹216 premium Iron Condor (426× max theoretical)
- neha.db ID=11: -₹120,949 loss on ₹63 premium Iron Condor (41× max theoretical loss)

**Fix:** Capped corrected_pnl at max_profit (for profits) and -max_loss (for losses).
**Status:** Data corrected today. Code fix needed in `_check_exit_triggers` to add bounds check (Phase 5 scope).

---

## Corrupted Strategies Detail

### portfolio.db (local) — 5 corrupted (lot-mult bug)

| ID | Date | Type | Index | Premium | Stored P&L | Corrected | Reason |
|---|---|---|---|---|---|---|---|
| 34 | 2026-04-28 | IRON_CONDOR | NIFTY | ₹260 | ₹779 | ₹260 | ÷3 lots |
| 35 | 2026-04-28 | IRON_CONDOR | FINNIFTY | ₹23,226 | ₹69,678 | ₹23,226 | ÷3 lots |
| 39 | 2026-05-01 | IRON_CONDOR | NIFTY | ₹521 | ₹1,564 | ₹521 | ÷3 lots |
| 40 | 2026-05-01 | BULL_PUT_SPREAD | NIFTY | ₹168 | ₹335 | ₹168 | ÷2 lots |
| 41 | 2026-05-01 | IRON_CONDOR | BANKNIFTY | ₹726 | ₹2,179 | ₹726 | ÷3 lots |

### vishal.db (EC2) — 1 corrupted (MTM bounds bug)

| ID | Date | Type | Index | Premium | Stored P&L | Corrected | Reason |
|---|---|---|---|---|---|---|---|
| 16 | 2026-05-19 | IRON_CONDOR | BANKNIFTY | ₹216 | ₹92,026 | ₹216 | Capped at max_profit |

### neha.db (EC2) — 1 corrupted (MTM bounds bug)

| ID | Date | Type | Index | Premium | Stored P&L | Corrected | Reason |
|---|---|---|---|---|---|---|---|
| 11 | 2026-05-19 | IRON_CONDOR | BANKNIFTY | ₹63 | -₹120,949 | -₹2,937 | Capped at -max_loss |

---

## Viability Assessment

### The Good
- **86.8% win rate** across 53 paper trades is strong
- Most trades are small but positive (avg ₹155/trade)
- Iron Condor strategy dominates (correct for premium selling)
- System correctly identifies sideways markets

### The Concerning
- **₹8,201 total P&L on 53 trades** = very small edge per trade
- Many "winners" are just ₹12-22 (force-exited with minimal theta decay)
- The 2 MTM bugs (₹92K profit, ₹121K loss) show option chain data is unreliable
- Without the bugs, the system barely breaks even
- Average winner: ~₹155. Average loser: unknown but likely larger per-trade

### The Honest Truth
- Win rate is high but profit per trade is tiny
- The system force-exits most trades before meaningful theta decay
- Real edge (if any) is masked by data quality issues
- Need 30+ trades with VERIFIED real-time pricing before any live decision

---

## Next Steps
1. ✅ Data corrected across all DBs
2. Fix `_check_exit_triggers` to add bounds check (prevent future MTM bugs)
3. Phase 3: Replace LLM with rules engine for deterministic strategy selection
4. Phase 5: Fix paper mode to use real Dhan prices (not simulation)
5. Phase 6: 30-trade validation with accurate pricing
