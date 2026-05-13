# STATE.md — Current Project State

**Last Updated**: 2026-05-14, ~05:30 IST (overnight session)
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-14) — OVERNIGHT SESSION SUMMARY

### Major architectural change: neha-live moved to second EC2

**Reason**: Dhan enforces IP whitelist per account. `13.206.144.6` is whitelisted on vishal's Dhan. Dhan refused to whitelist same IP on neha's account ("IP in use" error). Two accounts cannot share one IP for order placement.

**Solution**: Cloned EC2 via AMI → launched second instance for neha-live only.

| | OLD EC2 | NEW EC2 |
|---|---|---|
| IP | 13.206.144.6 | **13.202.63.223** |
| Instance ID | i-0256713c061011a5f | **i-0233c705c9104383e** |
| AMI used | source | ami-0bcad2c34474f8080 |
| EIP allocation | (existing) | eipalloc-0209566bfde3a903b |
| Profiles fired by cron | vishal, neha (paper), vishal-live, paper FnO for all | **ONLY neha-live intraday** |
| Dashboard S3 sync | ✓ (continues here) | ✗ (disabled to avoid race) |
| Time sync | ✓ chrony active | ✓ chrony active (cloned) |
| Code | latest commit a8ef5b5 | latest (cloned at AMI time) |

### Verification done tonight (NEW EC2)
- ✅ TOTP auth: succeeded for neha (NEHA SAXENA, ID 1111523334)
- ✅ Dhan funds API: HTTP 200, available_balance ₹10,000, IP whitelist proven working
- ✅ Cron stripped to ONLY neha-live entries (9:28 AM + 12:03 PM IST)
- ✅ Stale session file deleted
- ✅ Imports clean

### neha-live profile thresholds aligned with vishal-live
| Field | Before | After |
|---|---|---|
| intraday min_confidence_score | 8 | **7** |
| intraday vix_threshold | 16 | **18** |
| intraday price_range_min | (missing) | 100 |
| intraday price_range_max | (missing) | 2000 |
| fno daily_loss_limit | 3000 | 5000 |
| fno vix_threshold | 16 | 18 |

Capital limits unchanged: ₹10K daily, ₹4K/trade, ₹600 daily loss, max 2 trades/day.

Profile yamls are gitignored (contain TOTP/PIN). Patch applied manually on BOTH EC2s.

### F&O fixes pushed earlier this session (commits)
- `5be64f5` — F&O hedged confluence 60→45 (since updated to 20 in subsequent commit)
- `94ba876` — F&O paper observation phase: confluence 20, confidence 7→6 (vishal/neha), IV+spot persistence wired
- `a8ef5b5` — Fix Bug L: legs_json includes expiry_date + lot_size

### F&O breakthroughs + new bugs
- 🎯 First F&O paper trades EVER placed: 4 IRON_CONDORs in vishal smoke test (synthetic data)
- 🐛 Bug L fixed: legs_json now includes expiry_date + lot_size
- 🐛 Bug O surfaced: Vega exposure -18654 on iron condor (hedged should be near-zero) — alert spams every 30s
- 🐛 Bug Q: duplicate `return` statement at fno/monitor.py:79-80
- 🐛 Bug R: duplicate docstring at fno/monitor.py:184-185
- 🐛 Bug S: paper P&L is fully simulated (random walk + theta math), no relation to real market
- 🐛 Bug T: live mode `_compute_current_premium` returns entry_premium (no P&L change ever)
- 🐛 Bug X: `_compute_strategy_greeks` returns stored values, never refreshes (root of Bug O)
- 🐛 Bug Y: paper P&L confirmed 100% synthetic
- 🐛 Bug Z: P&L cap uses entry_premium not max_profit (wrong for sold strategies)
- 🐛 Bug AA: paper exits don't release used_margin
- 🐛 Bug BB: hardcoded lot_size=50 fallback (NIFTY=75, BANKNIFTY=15, FINNIFTY=40)
- 🐛 Bug CC: Greeks summed including just-closed strategies
- 🐛 Bug DD: F&O paper mode uses fake option chain (`demo=True` default in run_fno.py:205) — strategy validation invalid

### Dhan API findings (verified tonight)
- Auth (TOTP login) works without IP whitelist
- Order placement REQUIRES IP whitelist (DH-905 'Invalid IP' otherwise)
- Token rate limit: once per 2 minutes per account
- Production code caches token in `config/.broker_session_.json` (no re-auth per cron)
- ₹499/month Data API subscription: NOT needed for intraday (uses NSE free); NOT verified for option chain (test was inconclusive due to rate limit)

### Tomorrow at 9:28 AM IST — neha demo expectation
- NEW EC2 cron fires `run_intraday.py --profile neha-live --live`
- Auth succeeds (verified tonight)
- Scanner pulls Nifty 500 from NSE
- LLM picks (confidence ≥7), R:R ≥2 validation
- If selected → REAL BUY order in neha's Dhan account
- Neha sees order in her Dhan app (THAT is the demo)
- Monitor 5-min cycles, exit on target/SL/force-exit at 15:15 IST
- Max possible loss: ₹600 (hard cap)

### Tomorrow morning checklist
1. SSH NEW EC2 `13.202.63.223`, verify hostname + time sync
2. 9:28 AM IST: `tail -f logs/intraday_neha-live_$(date +%Y-%m-%d).log`
3. Have neha's Dhan app open alongside

---

## YESTERDAY (2026-05-13) — END OF DAY

### Real Money P&L
- vishal-live: HINDZINC LONG -INR 28.30 net (gross -INR 24.75, charges INR 3.55)
- Cumulative real money: -INR 21.15 (across 2 trading days)

### Paper P&L (charges-adjusted)
- vishal: +INR 57.69 (was showing +INR 261, charges hidden)
- neha: -INR 401.53 (was showing -INR 81, charges hidden)
- neha-live: TOTP failed, no trades

### F&O Status (updated late night May 13)
- BREAKTHROUGH: First F&O paper trades ever placed — 4 IRON_CONDORs in smoke test
- Three structural fixes landed (commit pending push):
  1. Hedged confluence 60→20 (paper observation phase, will auto-tighten)
  2. IV+spot persistence wired into run_fno.py Phase 8 (1 row/day, was missing)
  3. F&O paper confidence 7→6 for vishal+neha only (vishal-live/neha-live stay at 8)
- Cold-start clock starts now: by ~early June (day 21) IVP/VRP become real
- vishal.db now has 4 rows in fno_strategies + 3 rows in fno_iv_history

### NEW BUGS FOUND tonight (visible only because trades flowed):
- Bug L: fno_strategies.legs_json does NOT include expiry_date field
  - Monitor.py tries datetime.strptime('','%Y-%m-%d') and fails on all 12 legs
  - Result: tradingsymbol build fails, P&L falls back to fake near-zero values
  - Fix scope: insert path serialization (ensure leg.expiry_date in JSON)
- Bug M: Force exit doesn't place broker exit orders when symbol build fails
  - Status flips to FORCE_EXITED in DB but no actual exit order attempted
  - Linked to Bug L — fix L first
- Bug N: Vega exposure alert -22219 vs limit 2000 — misfires from bad leg reads
  - Linked to Bug L

### Watch May 14 9:20 AM cron
- vishal F&O paper will likely place strategies again (gates loose)
- Same Bugs L/M/N will repeat — that's expected, fix planned for May 14

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
