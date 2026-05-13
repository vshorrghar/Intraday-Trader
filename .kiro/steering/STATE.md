# STATE.md — Current Project State

**Last Updated**: 2026-05-13, evening
**Update Protocol**: Replace TODAY section with new block at end of each session. Move yesterday's TODAY into RECENT BUG FIXES. Archive entries older than 7 days into HISTORY.md.

---

## TODAY (2026-05-13)

### Live Positions (vishal-live)
- HINDZINC LONG @ INR 671.75, qty 5
  - Manual SL set at INR 657 (system SL was rejected by Dhan — Bug H discovered)
  - Target: INR 698.62
  - Status at 11:48 AM check: -INR 2.50 (basically flat)
  - Force exit: 15:15 IST

### Trades Today
- vishal-live: HINDZINC LONG (open at last check)
- vishal paper: 1 trade open (recovering, was -INR 252, now -INR 22)
- neha paper: GROWW stopped out -INR 29, HINDZINC still open (-INR 14)
- neha-live: TOTP FAILED 3 times — no trade executed

### Bugs Fixed Today
- Bug H FIXED: SL prices not aligned to NSE tick 0.05 -> Dhan rejected with omsErrorCode 16283
  - File: intraday/executor.py
  - Fix: Round both sl_limit_price and sl_trigger_price to nearest 0.05
  - Commit: 8bbfd4d
- Rule 11 added: Heredoc-only edits, no nano/vim
  - Commit: d5b6cce
- Project directory structure added to steering file (commit pending push)
- Rule 8 corrected: Use vishal-admin profile, not IMDSv2 tokens (in this RULES.md regen)
- Rule 19 added: EC2 clock sync / TOTP failure diagnostics (in this RULES.md regen)

### New Issues Found Today
- neha-live TOTP FAILS: 3 attempts, all "Invalid TOTP" — config issue, not clock
  - Clock confirmed synchronized via timedatectl
  - Need to verify totp_secret in config/profiles/neha-live.yaml
  - Status: PENDING

### Commits Pushed Today
d5b6cce Add Rule 11: Heredoc-only edits, no interactive editors 8bbfd4d Fix Bug H: Round SL prices to NSE tick 0.05 (omsErrorCode 16283)
Plus pending: directory structure addition + RULES.md regeneration

### Tomorrow's Plan (May 14)
1. Watch first cron with tick-size fix live (9:26 AM IST)
2. Investigate neha-live TOTP failure — check totp_secret value
3. Fix Bug A (P&L field names — snake_case from Dhan)
4. Wire Telegram alerts (Bug E)
5. Start swing module skeleton (Week 1 plan)

---

## ACTIVE BUGS (PRIORITY ORDER)

### Critical (real money affected)
1. Bug A — Dashboard P&L vs Dhan App mismatch
   - File: intraday/monitor.py commit 5d26767
   - Code expects camelCase (realizedProfit), Dhan returns snake_case (pnl)
   - Status: Identified, fix not applied

2. Bug C — WIPRO short verification needed
   - DB action says "BUY" for WIPRO but it was SHORT_MOMENTUM (May 12 trade)
   - File: intraday/executor.py
   - Status: Likely fixed by May 12 direction-aware fix (commit 265cc48), needs verification on next SHORT trade

3. Bug D — P&L doesn't include charges in display
   - Dashboard shows INR 7.15 gross, real is -INR 53 (after ~INR 60 charges)
   - charges.py module exists, monitor.py needs to use it for display
   - Status: charges.py created May 12, integration into dashboard pending

4. neha-live TOTP failure (NEW — May 13)
   - 3 invalid TOTP errors from Dhan
   - Clock OK, need to verify secret in yaml
   - Status: PENDING

### High
5. Bug E — Wire Telegram alerts
   - Module: alerts/telegram.py exists, NOT called from main flow
   - Need: hook into monitor.py (trade events) and executor.py (order events)
6. Build swing/ module (paper)
7. Build positional/ module (paper)
8. Build backtest framework

### Medium
9. Bug F — SL placement (FIXED May 12, commit 3754e75) — verification pending on real SHORT trade
10. Bug G — Rotate Dhan credentials (security, exposed in chat May 6)
11. Bug I — Rotate AWS access keys (NEW, low urgency, exposed in chat May 13)
12. Optimized F&O prompt (regime-aware)
13. News fetcher for swing/positional context
14. Fundamentals fetcher for positional

### Low
15. Clean up Wealth Builder Pro leftover files
16. Permanent IMDSv2 disable in ~/.bashrc (we use vishal-admin profile, IMDSv2 unused)
17. Risk manager R:R logging (cosmetic, shows 0.0)
18. F&O monitor.py needs same direction-aware fixes (paper-only, can wait)

---

## RECENT BUG FIXES (LAST 7 DAYS)

### May 13
- Bug H: NSE tick size rounding for SL orders (commit 8bbfd4d)
- Rule 11: Heredoc-only edits convention (commit d5b6cce)

### May 12 (5 critical fixes)
- Critical Fix #1: Time sync — removed duplicate chrony server entry, restarted chronyd
- Critical Fix #2: get_order_list() method added to DhanBrokerClient
- Critical Fix #3: SL placement bug — wait_for_fill before SL (commit 3754e75)
- Critical Fix #4: charges.py module created — accurate intraday/delivery/futures/options charges
- Critical Fix #5: SHORT trades direction fix — was executing as LONG (commit 265cc48)
  - LONG: BUY entry -> SELL SL
  - SHORT: SELL entry -> BUY SL
  - Verified with mock tests for all 4 quadrants

### May 11
- vishal-live confidence 8 -> 7
- vishal-live VIX 16 -> 18
- Stock universe: 20 -> Nifty 500 with scoring
- SHORT setups added
- Trade history fed to LLM

### May 10 (Pre-Live Audit — 7 critical fixes)
- Exit not calling broker (intraday) -> Fixed
- Exit not calling broker (F&O) -> Fixed
- Profiles sharing one session file -> Per-profile files
- TOTP silent hang -> 3 retries, no browser fallback
- Daily state not restored -> Now restored from DB
- Afternoon session disabled for live
- Late session gates added

### May 9
- BEARISH never skip (paper)
- intraday/monitor.py: target hit places SELL MARKET at broker
- intraday/monitor.py: force exit places SELL MARKET at broker
- fno/monitor.py: _execute_exit places reverse leg orders at broker
- Commit: 5f9e6c2

### May 8
- Complete dashboard UI rewrite (872 lines)
- passwords.json with SHA-256
- EC2 IAM role: AmazonS3FullAccess + CloudFrontFullAccess
- IMDSv2 token workaround (later replaced by vishal-admin profile approach)

### May 7
- Dhan IP whitelist -> 13.206.144.6 added
- SSH restored -> security group updated
- Margins API fallback
- Session token expiry -> 6h check, re-auth
- Hourly S3 sync added
- R:R minimum 1.5 -> 2.0
- High volatility rejection added

---

## RECENT COMMITS (LAST 10)

d5b6cce Add Rule 11: Heredoc-only edits, no interactive editors 8bbfd4d Fix Bug H: Round SL prices to NSE tick 0.05 (omsErrorCode 16283) 265cc48 Fix CRITICAL bug: SHORT trades were executed as LONGs 3754e75 Fix SL placement + accurate charges calculation ce8e008 Fix FnO: fetch real VIX from NSE instead of hardcoded 15.0 3b58370 Sync dashboard to S3 immediately after every session bd0db24 Add sync_dashboard.sh + hourly S3 sync ccbbf9c gitignore: dashboard runtime files 9918a64 Add trade history to LLM context, telegram config 5d26767 Fix P&L: use Dhan realizedProfit (HAS BUG — field names wrong)
---

## REAL TRADES TO DATE (vishal-live only)

### May 12 — First Real Trade Day
- ONGC LONG: Buy INR 297.35, Sell INR 296.05, qty 13, Net -INR 53.80 (Dhan app, after charges)
- WIPRO SHORT: -INR 20 (verification needed for direction)
- Total: -INR 73.80 net real money loss

### May 13 — Today
- HINDZINC LONG: Open at time of last check, ~flat (-INR 2.50)

---

## EXECUTION PLAN — NEXT 4 WEEKS

### Week 1 (May 13-17) — Bug Fixes + Swing Foundation
- May 13: Bug H fix (DONE), Rule 11 (DONE), Rule 8/19 (DONE), neha-live TOTP fix (PENDING)
- May 14: Bug A fix (P&L field names), wire Telegram, start swing skeleton
- May 15: Build swing/scanner.py, swing/selector.py
- May 16: Build swing/executor.py, swing/monitor.py
- May 17: Cron + dashboard for swing, paper run validation

### Week 2 (May 18-24) — Positional Module
- Build positional/ skeleton, scanner, fundamentals fetcher
- positional/selector.py with fundamentals context
- positional/executor.py + monitor.py
- Cron + dashboard

### Week 3 (May 25-31) — Stabilization + Telegram
- Fix bugs from swing/positional paper runs
- Bug F verification on real SHORT trades
- Rotate Dhan credentials (Bug G)
- Rotate AWS keys (Bug I)
- Optimized F&O prompt
- News fetcher

### Week 4 (Jun 1-7) — Backtest Framework
- backtest/ module
- Download NSE bhavcopy 5 years
- Backtest all 4 strategies
- Identify which has actual edge
- Decide what scales to live capital

---

## MARKET REGIME CONTEXT (May 13 2026)

- VIX: 19.12 (slightly elevated, above vishal-live threshold of 18 — VIX gate triggered today)
- Iran-USA war tensions ongoing
- Today's market: 20/27 sectors green, NIFTY METAL leading +1.16%
- Bias: Bullish today (LLM picked all LONGs)
- May 12 was bearish — LLM picked one LONG + one SHORT correctly

End of STATE.md
