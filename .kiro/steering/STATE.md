# STATE.md — Current Project State

**Last Updated**: 2026-05-13, late night
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-13) — END OF DAY

### Real Money P&L
- vishal-live: HINDZINC LONG -INR 28.30 net (gross -INR 24.75, charges INR 3.55)
- Cumulative real money: -INR 21.15 (across 2 trading days)

### Paper P&L (charges-adjusted)
- vishal: +INR 57.69 (was showing +INR 261, charges hidden)
- neha: -INR 401.53 (was showing -INR 81, charges hidden)
- neha-live: TOTP failed, no trades

### F&O Status
- All 3 paper profiles ran F&O
- Zero strategies selected — confluence score = 36 (need 50+ hedged, 75+ naked)
- Root cause: no IV/spot history → quant defaults to neutral
- LLM correctly rejected with garbage inputs

### Bugs Fixed Today (6 total)
1. Bug H — NSE tick size rounding (commit 8bbfd4d)
2. Rule 11 added — heredoc-only edits (d5b6cce)
3. Bug J — force exit logs P&L before fill (c98e2ec)
4. Bug J/K extended — SL hit + target hit same pattern (1cdc6d7)
5. Naked SL position — SL hit didn't place broker order (1cdc6d7)
6. Bug A + D — dashboard shows real exit_price + charges/gross/net (6af9619)

### New Issues Found
- F&O cold-start problem: no historical IV/spot → confluence locked low
- neha-live TOTP failure (config issue, not clock)
- AWS keys exposed in chat (Bug I, low urgency rotation)

### Commits Pushed Today
6af9619 Fix Bug A+D: dashboard real exit_price + charges 1cdc6d7 Fix Bug J+K everywhere + naked SL fix c98e2ec Fix Bug J+K: force exit waits for fill 3441976 Add RULES.md + STATE.md + HISTORY.md system d5b6cce Add Rule 11: Heredoc-only edits 8bbfd4d Fix Bug H: NSE tick size rounding

### Tomorrow's Plan (May 14)
1. Lower F&O confluence thresholds for paper (hedged 50->30, naked 75->50)
2. Build IV history persistence in F&O quant_engine
3. Backfill spot history from NSE bhavcopy
4. Investigate neha-live TOTP secret
5. Verify Bug H fix on first real cron at 9:26 AM IST

---

## ACTIVE BUGS

### Critical (real money)
1. neha-live TOTP failure — needs secret verification
2. F&O cold-start (no IV/spot history) — paper not trading

### High
3. Bug E — Wire Telegram alerts (alerts/telegram.py exists, not called)
4. Build swing module
5. Build positional module
6. Build backtest framework

### Medium
7. Bug G — Rotate Dhan credentials (exposed May 6)
8. Bug I — Rotate AWS keys (exposed May 13)
9. F&O monitor.py — same Bug J/K pattern needs fixing (paper-only)
10. Optimized F&O prompt (regime-aware)

### Low
11. Clean up Wealth Builder Pro leftover files
12. Risk manager R:R logging cosmetic fix

---

## REAL TRADES TO DATE (vishal-live)

### May 12 — First Real Trade Day
- ONGC LONG: -INR 53.80 net
- WIPRO SHORT: -INR 20 (verification needed for direction)
- Total: -INR 73.80

### May 13
- HINDZINC LONG: -INR 28.30 net (real, charges-adjusted)
- Total cumulative: -INR 102.10 (with May 12 net of -INR 73.80)

NOTE: Dashboard cumulative shows -INR 21.15 because May 12 was logged as INR 7.15 gross (Bug A active that day, never backfilled).

---

## EXECUTION PLAN — REVISED PRIORITIES

### Tomorrow (May 14) — Pre-Market
- 9:26 AM cron will fire vishal-live with all 6 fixes active
- This is the first clean test
- Watch for: SL placement success (Bug H fixed), exit fill capture (Bug J fixed)

### This Week
- Fix F&O cold-start (lower thresholds + build IV history)
- Investigate neha-live TOTP

### Next 4 Weeks (unchanged)
Week 1: Bug fixes + Swing foundation
Week 2: Positional module
Week 3: Stabilization + Telegram
Week 4: Backtest framework

End of STATE.md
