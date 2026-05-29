# V3 Cross-Session Audit — 2026-05-28

**Purpose:** Damage assessment after another session modified V3 files mid-build.
**Audited by:** Kiro (V3 build session)
**Date:** 2026-05-28

---

## 1. intraday/v3/regime.py

- **Modification timestamp:** May 28 11:26 (MODIFIED by another session)
- **Relaxation marker present:** YES — "2026-05-28 — Universal Relaxation Pass"
- **File was COMPLETELY REWRITTEN** — different structure from Phase 3 version

| Parameter | Phase 3 (my version) | Current (relaxed) | Change |
|-----------|---------------------|-------------------|--------|
| TRENDING_UP threshold | +0.4% | +0.25% | Loosened |
| TRENDING_DOWN threshold | -0.4% | -0.25% | Loosened |
| RANGING threshold | 0.3% | 0.4% | Widened |
| VOLATILE VIX threshold | 22 | 25 | Raised significantly |
| VOLATILE range_pct | 1.2% | NOT PRESENT | Removed |
| breadth_pct input | Used in classification | NOT PRESENT | Removed |
| nifty_30min_range_pct input | Used in classification | NOT PRESENT | Removed |
| detect_regime() function | Present (with daily lock + file caching) | REMOVED | Breaking change |
| classify_regime() signature | (nifty_change, range, breadth, vix) | (nifty_change, vix) ONLY | Breaking change |
| Return type | dict with regime, reasoning, inputs | IntraRegime enum | Breaking change |
| Daily lock mechanism | File-based (logs/regime_YYYY-MM-DD.json) | NOT PRESENT | Removed |

**Status: INCONSISTENT — Breaking changes to API contract**

**Impact:**
- `detect_regime()` function REMOVED — my tests import it → ImportError
- `classify_regime()` signature changed (2 params instead of 4) → all callers break
- Return type changed from dict to Enum → orchestrator would need different handling
- Daily lock mechanism removed → regime can flip mid-day (violates V3 spec)
- Breadth calculation removed → less accurate regime detection

---

## 2. intraday/v3/strategies/vwap_mean_reversion.py

- **Modification timestamp:** May 28 09:10 (same as my Phase 5 deploy — NOT modified)
- **Relaxation marker present:** NO
- **All values match Phase 5:**

| Parameter | Expected | Current | Match |
|-----------|----------|---------|-------|
| MIN_BELOW_VWAP_PCT | 1.5 | 1.5 | ✓ |
| MAX_BELOW_VWAP_PCT | 3.0 | 3.0 | ✓ |
| STOP_LOSS_PCT | 1.0 | 1.0 | ✓ |
| TARGET_ABOVE_VWAP_PCT | 0.5 | 0.5 | ✓ |
| MIN_RR | 1.5 | 1.5 | ✓ |
| TIME_STOP_CANDLES | 6 | 6 | ✓ |
| Regime gate | regime != "RANGING" | regime != "RANGING" | ✓ |

**Status: CONSISTENT — No changes**

---

## 3. backtest/rule_engine.py

- **Modification timestamp:** May 25 15:06 (BEFORE my session — NOT modified)
- **Relaxation marker present:** NO

| Parameter | Expected | Current | Match |
|-----------|----------|---------|-------|
| V6 gap threshold | 1.5% | 1.5% | ✓ |
| min_rel_volume | 1.5 | 1.5 | ✓ |
| ORB time window end | hour >= 11 | hour >= 11 | ✓ |
| V4 FLAT behavior | return [] | return [] | ✓ |
| OR width max | 3.0% | 3.0% | ✓ |
| OR width min | 0.3% | 0.3% | ✓ |

**Status: CONSISTENT — No changes**

---

## 4. intraday/v3/strategies/orb_v6.py

- **Modification timestamp:** May 27 20:49 (my Phase 4 deploy — NOT modified)
- **Relaxation marker present:** NO
- **Status: CONSISTENT**

---

## 5. intraday/v3/strategies/orb_v4.py

- **Modification timestamp:** May 27 20:49 (my Phase 4 deploy — NOT modified)
- **Relaxation marker present:** NO
- **Status: CONSISTENT**

---

## 6. tests/v3/test_regime.py

- **Run result: ERROR — cannot import `detect_regime` (function removed from regime.py)**
- **Root cause:** Another session rewrote regime.py, removed `detect_regime()` function and changed `classify_regime()` signature
- **Tests affected:** ALL 9 regime tests fail to even collect

---

## 7. tests/v3/test_vwap_mr.py

- **Run result: 3/3 PASSED**
- **Status: CONSISTENT**

---

## 8. tests/v3/ overall

- **Excluding test_regime.py:** 46 passed
- **Including test_regime.py:** 1 collection error (ImportError)
- **Before relaxation (Phase 6 baseline):** 55/55 passed
- **Now:** 46 passed + 1 error (9 tests broken)

---

## 9. orchestrator.py

- **Does NOT exist yet** (Phase 7 not completed)
- **No hardcoded thresholds to conflict**
- **Impact:** Orchestrator will need to call the NEW regime.py API (IntraRegime enum, 2-param classify_regime) instead of the old 4-param detect_regime()

---

## Test Results Summary

| Metric | Before (Phase 6) | Now |
|--------|-------------------|-----|
| V3 tests passing | 55/55 | 46/46 (9 broken by import error) |
| Broken tests | 0 | 9 (all in test_regime.py) |
| Root cause | — | regime.py API contract changed |

---

## Recommendation

### Option A: KEEP relaxed regime.py, update tests (RECOMMENDED)
- The relaxation intent is correct (widen RANGING band, reduce VOLATILE false positives)
- BUT: restore `detect_regime()` with daily lock (critical for V3 spec — regime must not flip mid-day)
- AND: restore breadth_pct input (more accurate than VIX+change alone)
- Update test_regime.py to match new thresholds
- Time cost: ~30 minutes

### Option B: ROLL BACK regime.py to Phase 3 version
- Restores all 9 tests immediately
- But loses the relaxation benefit (wider RANGING band)
- Time cost: ~5 minutes (SCP my original file back)

### Option C: MERGE — take relaxed thresholds but restore full API
- Keep: TRENDING_UP=0.25, TRENDING_DOWN=-0.25, RANGING=0.4, VOLATILE_VIX=25
- Restore: detect_regime() with daily lock, breadth_pct input, dict return type
- Restore: nifty_30min_range_pct for VOLATILE detection
- Update tests to use new thresholds
- Time cost: ~45 minutes
- **This is the cleanest path forward**

### My judgment:
- **Go with Option C (MERGE)**
- The relaxed thresholds are directionally correct for more trade flow
- But removing breadth and daily lock was wrong — those are safety features
- The orchestrator (Phase 7) needs detect_regime() with daily lock

---

## Files Modified by Other Session

| File | Modified | Breaking | Action Needed |
|------|----------|----------|---------------|
| intraday/v3/regime.py | YES (rewritten) | YES | Merge: keep thresholds, restore API |
| intraday/v3/strategies/vwap_mean_reversion.py | NO | NO | None |
| backtest/rule_engine.py | NO | NO | None |
| intraday/v3/strategies/orb_v6.py | NO | NO | None |
| intraday/v3/strategies/orb_v4.py | NO | NO | None |
| intraday/v3/orchestrator.py | Does not exist | N/A | Build in Phase 7 |
