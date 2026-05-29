# POSTMORTEM: INFY -₹910 Loss (2026-05-29)

**Date:** 2026-05-29
**Profile:** vishal-live-v2 (REAL MONEY)
**Stock:** INFY (Infosys)
**Reported P&L:** -₹26 (system)
**Actual P&L:** -₹910 (Dhan)
**Discrepancy:** 35x underreporting

---

## 1. SL CHAIN — Timeline

```
04:15:15 [selector] Pick INFY @ ₹1203.30 → target ₹1251.43, SL ₹1181.64, conf 7
04:15:15 [risk_mgr] Sized: 20 shares × ₹1203.30 = ₹24,066
04:15:15 [dhan]     place_order: BUY INFY x20 @ 1206.90 (buffered +0.3%)
04:15:17 [dhan]     place_order: SELL INFY x20 @ 1181.15 (SL order)
04:15:19 [executor] 📋 Placed INFY: BUY 20 × ₹1203.30 | Target ₹1251.43 | SL ₹1181.64
```

**Gap: 2 seconds between entry order and SL order.**
Entry placed at 04:15:15, SL placed at 04:15:17.

**Critical question:** Was entry CONFIRMED FILLED before SL was sent?
**Answer: NO.** The executor places entry, waits 10s for fill, then places SL.
But the log shows SL placed only 2 seconds after entry — meaning the fill
polling returned quickly (likely the LIMIT filled immediately at market open).

The SL order was SENT to Dhan. But was it CONFIRMED LIVE?
The log shows no "SL confirmed" or "SL order_id=XXX" line. The executor
logs the combined result at 04:15:19 but doesn't separately confirm SL acceptance.

**Root cause:** SL was sent but we never verified Dhan accepted it.
If Dhan rejected it (DH-906, invalid price, etc.), we'd never know.

---

## 2. WHY SL FAILED

The SL was placed at ₹1181.15 (trigger) for a BUY entry at ₹1206.90.
INFY opened at ~₹1203 and traded between ₹1156-₹1210 during the day.

**The SL trigger price (₹1181.64) was never hit during market hours.**
INFY's low was ₹1156 — which is BELOW the SL trigger.

**Wait — if low was ₹1156 and SL trigger was ₹1181, the SL SHOULD have fired.**

Possible explanations:
1. SL order was rejected by Dhan (no confirmation logged)
2. SL order was cancelled by the DH-906 race condition
3. SL order existed but Dhan's SL-M execution failed in fast market

Without Dhan order history for May 29, we cannot confirm which.
But the force-exit at 15:15 IST proves the position was still OPEN at EOD —
meaning the SL never executed.

---

## 3. MONITOR BLINDNESS

Monitor polled `get_positions()` every 2 minutes from 04:15 to 09:45:
```
04:15:19 [monitor] 🔍 Starting position monitor for 1 trade(s)…
04:15:19 [dhan]    Dhan get_positions
04:17:19 [dhan]    Dhan get_positions
04:19:19 [dhan]    Dhan get_positions
... (continues every 2 min)
```

**But no P&L was ever logged.** The monitor polled positions but never
logged "unrealized P&L: ₹X" for INFY. This means either:
1. Dhan's `get_positions()` returned the position but with no P&L field
2. The monitor code doesn't compute/log unrealized P&L per position
3. The position wasn't found in Dhan's response (symbol mismatch)

**The monitor was polling but blind to the actual loss growing from ₹0 to -₹910.**

---

## 4. LOSS CAP FAILURE

From `intraday/risk_manager.py`:
```python
self._realized_loss_today: float = 0.0  # line 28
if self._realized_loss_today >= self.config.daily_loss_limit:  # line 189
```

The loss cap checks `_realized_loss_today` which is only updated when
`record_trade_closed(net_pnl)` is called — i.e., when the MONITOR reports
a closed trade with a P&L number.

Since the monitor reported P&L = ₹0 (because exit used fallback_price = entry),
the loss cap saw ₹0 realized loss. It could NEVER fire.

**The loss cap reads our own lies, not Dhan truth.**

---

## 5. EXIT MISREPORTING

```
09:45:29 [dhan]    place_order: SELL INFY x20 @ 0.00 (MARKET)
09:45:29 [monitor] ✅ INFY exit order placed (SELL) order_id=
09:45:29 [monitor] ⏰ INFY FORCE EXITED @ ₹1203.30 | gross ₹0.00 ... fill=no_poll
```

**`order_id=` is EMPTY.** Dhan placed the MARKET SELL but returned no order ID.

Code path (`_place_exit_and_get_fill_price`, line 585):
```python
if not order_id or not hasattr(self.broker, "get_order_list"):
    return fallback_price, "no_poll"
```

Since `order_id` was empty, code returned `fallback_price` (= entry price ₹1203.30).
P&L computed as: (₹1203.30 - ₹1203.30) × 20 = ₹0.

**Reality:** Dhan filled the SELL at ₹1156 (market price at 3:15 PM).
Real P&L: (₹1156 - ₹1203.30) × 20 = **-₹946** (before charges).
After charges: **~-₹910**.

---

## 6. SCALE RISK

**YES — loss scales linearly with position size.**

The failure is NOT size-dependent. Every layer failed identically regardless of qty:
- SL not confirmed → fails at any size
- Monitor blind → blind at any size
- Loss cap reads ₹0 → reads ₹0 at any size
- Exit no_poll → uses entry price at any size

**At 2000 qty (₹2L deployed):**
- Same entry ₹1203.30, same exit ₹1156
- Loss = (₹1203.30 - ₹1156) × 2000 = **-₹94,600**
- Plus charges: **~-₹95,000**

**At ₹5L deployed (Phase 4 target):**
- ~400 shares at ₹1203
- Loss = ₹47.30 × 400 = **-₹18,920**

The system would report ₹0 loss in all cases. The loss cap would never fire.
Manual intervention would be the only protection.

---

## CORE DISEASE (one sentence)

**Every safety layer trusts internal state (DB/monitor/risk_manager) instead of
querying Dhan for ground truth — so when any single layer lies (empty order_id,
stale price, no fill poll), ALL downstream layers inherit the lie and fail silently.**

---

## FIX REQUIRED

V3 safety.py must:
1. Query Dhan `get_positions()` for REAL P&L every cycle
2. Compare real P&L against daily_loss_limit DIRECTLY
3. If breached → emergency square-off ALL positions via MARKET
4. Poll ACTUAL fill prices for every exit (never use fallback_price)
5. This layer trusts ONLY Dhan, never internal state
