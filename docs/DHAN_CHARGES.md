# Dhan Brokerage Charges Reference

**Source:** https://dhan.co/pricing-and-charges/
**Last verified:** May 12, 2026
**Account type:** Retail Individual (HUF/Corporate/NRI rates differ)

---

## Equity Delivery (CNC)

| Charge | Rate |
|--------|------|
| Brokerage | ₹0 (FREE) |
| STT | 0.1% on BUY + SELL |
| Exchange (NSE) | 0.0030699% on turnover |
| Exchange (BSE) | 0.00375% on turnover |
| SEBI Turnover | 0.0001% of turnover |
| Stamp Duty | 0.015% on BUY turnover only |
| IPFT Contribution | 0.0000001% of turnover |
| GST | 18% on (brokerage + exchange + SEBI + IPFT) |

**Used by:** swing/, positional/ (when built)

---

## Equity Intraday (MIS)

| Charge | Rate |
|--------|------|
| Brokerage | ₹20 OR 0.03% per executed order, whichever LOWER |
| STT | 0.025% on SELL side only |
| Exchange (NSE) | 0.0030699% on turnover |
| Exchange (BSE) | 0.00375% on turnover |
| SEBI Turnover | 0.0001% of turnover |
| Stamp Duty | 0.003% on BUY turnover only |
| IPFT Contribution | 0.0000001% of turnover |
| GST | 18% on (brokerage + exchange + SEBI + IPFT) |

**Used by:** intraday/

---

## Equity MTF (Margin Trading Facility)

| Charge | Rate |
|--------|------|
| Brokerage | ₹20 OR 0.03% per executed order, whichever LOWER |
| STT | 0.1% on BUY + SELL |
| Exchange (NSE) | 0.0030699% on turnover |
| Exchange (BSE) | 0.00375% on turnover |
| SEBI Turnover | 0.0001% of turnover |
| Stamp Duty | 0.015% on BUY turnover only |
| IPFT Contribution | 0.0000001% of turnover |
| GST | 18% on (brokerage + exchange + SEBI + IPFT) |

**Used by:** Not currently used

---

## Equity Futures

| Charge | Rate |
|--------|------|
| Brokerage | ₹20 flat per executed order |
| STT | 0.05% on SELL side only |
| Exchange (NSE) | 0.0018299% on turnover |
| Exchange (BSE) | 0 |
| SEBI Turnover | 0.0001% of turnover |
| Stamp Duty | 0.002% on BUY turnover only |
| IPFT Contribution | 0.0000001% of turnover |
| GST | 18% on (brokerage + exchange + SEBI + IPFT) |

**Used by:** fno/ (futures legs)

---

## Equity Options

| Charge | Rate |
|--------|------|
| Brokerage | ₹20 flat per executed order |
| STT | 0.15% on SELL side (on PREMIUM) |
| STT (exercised) | 0.15% on intrinsic value |
| Exchange (NSE) | 0.0355299% on PREMIUM |
| Exchange (BSE Index) | 0.0325% on PREMIUM |
| Exchange (BSE Stock) | 0.005% on PREMIUM |
| SEBI Turnover | 0.0001% of turnover (premium-based) |
| Stamp Duty | 0.003% on BUY turnover only |
| IPFT Contribution | 0.0000001% of turnover |
| GST | 18% on (brokerage + exchange + SEBI + IPFT) |

**Used by:** fno/ (option legs)

---

## Important Notes

1. **Rounding:** Stamp Duty and STT rounded to nearest rupee. Other charges to 2 decimals.
2. **STT exemptions:** Does NOT apply to GOLD ETFs, LIQUID ETFs, Gilt ETFs, certain International ETFs.
3. **Physical delivery:** F&O resulting in physical delivery has 0.10% brokerage on contract value.
4. **Expired/exercised options:** ₹20 per contract still applies.
5. **Auto-square-off:** ₹20 + GST per order if Dhan auto-squares before market close.
6. **Call & Trade:** ₹50 + GST per order via trade desk.
7. **BSE special groups:** X, XT, Z = 0.10% transaction. P, ZP = 1%. IF, M, MS, MT, R, TS = 0.00275%.
8. **OFS:** ₹300 per crore.

---

## Disclaimers

- Rates can change with 15 days notice from Dhan.
- These rates are for retail individuals only.
- HUF, NRI, Corporate, Partnership, Trust accounts have different rates.
- Always cross-check with Dhan contract note for exact charges.

---

## Code References

When updating charges in code, modify these files:

| Segment | File | Function |
|---------|------|----------|
| Equity Intraday | `intraday/monitor.py` | `_calculate_dhan_charges()` |
| Equity Delivery | `swing/monitor.py` (TBD) | TBD |
| Equity Delivery | `positional/monitor.py` (TBD) | TBD |
| Equity Futures | `fno/monitor.py` | TBD |
| Equity Options | `fno/monitor.py` | TBD |

If Dhan rates change, update this file FIRST, then update the code.

---

## Update Log

| Date | Change | By |
|------|--------|-----|
| 2026-05-12 | Initial creation from Dhan website | Vishal |
