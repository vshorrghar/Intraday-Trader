# F&O P&L Revalidation Report
**Generated:** 2026-05-29 14:43

---

## Database: `database/portfolio.db`

### Summary
- Total strategies audited: **30**
- Corrupted (lot-mult bug): **5** (IDs: [34, 35, 39, 40, 41])
- Suspicious (bounds violation): **0** (IDs: [])
- NULL P&L (no exit recorded): **9**
- Clean: **16**

### Cumulative P&L
- **BEFORE correction:** ₹85,917.06
- **AFTER correction:** ₹36,283.46
- **Discrepancy (inflated profit):** ₹49,633.60

### Fix Applied
- Rows corrected: 5
- Column `corrected_pnl` populated
- Original `realized_pnl` preserved (audit trail)

### Corrupted Strategies (lot-multiplication bug)

| ID | Date | Type | Index | net_premium | Stored P&L | Corrected P&L | num_lots |
|---|---|---|---|---|---|---|---|
| 34 | 2026-04-28 | IRON_CONDOR | NIFTY | ₹259.50 | ₹778.50 | ₹259.50 | 3 |
| 35 | 2026-04-28 | IRON_CONDOR | FINNIFTY | ₹23,226.00 | ₹69,678.00 | ₹23,226.00 | 3 |
| 39 | 2026-05-01 | IRON_CONDOR | NIFTY | ₹521.25 | ₹1,563.75 | ₹521.25 | 3 |
| 40 | 2026-05-01 | BULL_PUT_SPREAD | NIFTY | ₹167.50 | ₹335.00 | ₹167.50 | 2 |
| 41 | 2026-05-01 | IRON_CONDOR | BANKNIFTY | ₹726.30 | ₹2,178.90 | ₹726.30 | 3 |

---
