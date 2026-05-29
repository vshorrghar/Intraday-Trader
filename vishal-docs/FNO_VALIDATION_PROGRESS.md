# F&O Validation Progress
**Last Updated:** 2026-05-29 11:29 IST
**Validation Started:** 2026-05-29
**Days Elapsed:** 0

---

## Combined Metrics (All Profiles)

| Metric | Value |
|--------|-------|
| Trades placed | 0 |
| Trades closed | 0 |
| Total P&L | ₹0.00 |

### Profile: neha

| Metric | Value |
|--------|-------|
| Trades placed | 0 |
| Trades closed | 0 |
| Win rate | N/A |
| Profit factor | N/A |
| Avg P&L/trade | N/A |
| Total P&L | ₹0.00 |
| Max daily drawdown | ₹0.00 |
| Adjustments triggered | 0 |
| Force exits | 0 |
| Exceeded max_loss | ✅ No |

---

## Decision Gate

**Status:** ⏳ INSUFFICIENT_DATA
**Action:** Continue accumulating trades
**Reason:** Only 0 trades closed (need 30 minimum)

### Gate Criteria

| Criterion | Required | Current | Status |
|-----------|----------|---------|--------|
| Trades closed | ≥ 30 | 0 | ⏳ |
| Win rate | ≥ 60.0% | None% | ⏳ |
| Profit factor | ≥ 1.4 | None | ⏳ |
| No 2× max_loss breach | True | ✅ | ✅ |

---

## Notes

- All Phase 1-5 fixes deployed
- P&L bug fixed (lot-multiplication + MTM bounds)
- Real Dhan chain pricing active (no simulation)
- 50% profit targets active (IC), 70% (spreads)
- Adjustment engine active (0.5σ trigger)
- Rules-based strategy selection (no LLM)
- Regime allowlist: SIDEWAYS + HIGH_VOLATILITY
