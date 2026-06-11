---
inclusion: auto
---

# CHARTER.md — TRADER-FIRST CHARTER (READ FIRST, EVERY SESSION)

**Authority:** This is RULE 0. Overrides all other rules. Read before writing a single line of code. Author: Vishal (owner).

**Why:** A real-money stop-loss failure (₹910, 2026-05-29 INFY) proved that in a trading system, EXECUTION AND RISK MANAGEMENT ARE THE PRODUCT, not the features. A trader can forgive a missing feature. A trader cannot forgive a risk-management failure.

## PRIORITY ORDER (NEVER INVERT)
1. Execution reliability
2. Risk management protection
3. Order validation & safety checks
4. Failure recovery mechanisms
5. Monitoring & alerts
6. New feature development  ← ALWAYS LAST

## THE 7 QUESTIONS — ASK BEFORE EVERY IMPLEMENTATION
1. If I were trading my own capital, would I trust this feature?
2. What happens if the market moves violently?
3. What happens if an order is rejected?
4. What happens if a stop-loss modification fails?
5. What happens if network latency occurs?
6. What happens if broker APIs behave unexpectedly?
7. Can this failure create financial loss for a trader?

## THE STANDARD
- Challenge every feature with real-world edge cases and violent market
  scenarios — NOT just "does the code work under normal conditions."
- Think like a trader protecting capital, not a developer shipping code.
- A trader cares whether capital was protected, not whether code ran.

## THE GATE — "HAVE WE EARNED THE CONFIDENCE TO GO LIVE?"
Never "Can we launch?" Always "Have we EARNED confidence?"
ALL 10 green before ANY module goes live with real capital:
[ ] 1. Numbers are REAL (no fake/demo/placeholder trades in P&L)
[ ] 2. Tested in ALL regimes (up/down/sideways/volatile/crash)
[ ] 3. Order rejection handled (survives a rejected order)
[ ] 4. Stop-loss failure handled (defined behavior when SL doesn't fire)
[ ] 5. Partial-fill protected (F&O all-legs-or-none; no naked legs)
[ ] 6. Reconciliation clean (DB matches broker truth)
[ ] 7. Monitor shows TRUTH (reads broker, not internal state — no ₹0 lies)
[ ] 8. Sample size sufficient (enough REAL trades to trust the edge)
[ ] 9. Survives worst historical week (the crash test)
[ ] 10. Gut check: "I would trade MY OWN money on this exact behavior"

## ON FAILURES FOUND IN PAPER
Every paper-mode issue is a GIFT — caught free, not with capital.
Surface loudly. Never hide, hand-wave, or rationalize a failure.

## ON NUMBERS
Never trust an optimistic number. Verify against broker truth or clean data.
A contaminated/unverified number is WORSE than no number — it deploys capital on a lie.
(Refs: ₹910 monitor lie; 48%-vs-61% backtest; fake ₹1000 F&O demo trades.)

## ON BALANCE (paper vs safety)
STRICT on safety (orders, stops, caps, naked-leg protection) — never relax.
LOOSE on filters IN PAPER (let strategies fire to collect data) — a silent strategy teaches nothing.
Tighten later from what we SEE, not fear.
