# STATE.md — Current Project State

**Last Updated**: 2026-05-15, ~23:00 IST (end of triple-stream session)
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-15) — TRIPLE-STREAM SESSION

### Session Outcome
- Stream 1: Scanner v3 bugfixes (Bugs 1, 2, 3 from Day 1 production)
- Stream 2: F&O Bug T fix — real Dhan price paper trading
- Stream 3: Bug 6 fix — neha-live data visibility from OLD EC2 (DB + dashboard sync via S3)
- Stream 4: 4 new steering docs added
- Bug 5 discovered EOD: max_trades_per_day not enforced (real cost ~Rs.220 today)

### Commits Today (newest first)
- 6b8de75 — feat: Bug T fix — F&O real-price MTM + exit triggers + option chain cache
- 5d79c29 — docs: add FNO_STRATEGY.md
- 3f3fdbe — docs: add BUSINESS_DOC + TECHNICAL_DOC + GLOSSARY to steering/
- 7777382 — feat: live_status + eod_summary scripts + Bug 5 status fix + Bug 6 neha-live sync
- abb236e — fix: Bug 6 - sync neha-live.db OLD<->NEW via S3
- a0ec15e — fix: buffered limit (+0.3% tick-aligned) + MARKET fallback for conf>=8 (Bug 3)
- 68e910c — fix: NSE losers endpoint dead — use SecLwr20 from gainers (Bug 2)
- a9df59b — fix: momentum-aware volume filter (Bug 1)

### Real Money Trades This Week
| Date | Profile | Stock | Direction | Net P&L |
|------|---------|-------|-----------|---------|
| May 12 | vishal-live | ONGC LONG | -Rs.53.80 |
| May 12 | vishal-live | WIPRO SHORT | -Rs.20.00 |
| May 13 | vishal-live | HINDZINC LONG | -Rs.28.30 |
| May 14 | vishal-live | VEDL x10 @ 334.30 | TBD |
| May 14 | neha-live | SAIL x19 @ 206.42 | -Rs.63 |
| May 15 | vishal-live | INFY x4 @ 1124.10 | TBD (open EOD) |
| May 15 | vishal-live | HDFCBANK x5 @ 779.90 | TBD (open EOD) |
| May 15 | vishal-live | SAREGAMA x10 @ 411.90 | NEVER FILLED — Bug 3 |

Cumulative: ~-Rs.165 closed + Bug 5 cost ~Rs.220 today

---

## STREAM 1: SCANNER/EXECUTOR BUGS — FIXED

### Bug 1 (CRITICAL): Scanner saw only 169/500 stocks — a9df59b
- Root: 500K volume filter rejected stocks at 9:30 AM
- Fix: Pass if change_pct >= 4% AND volume >= 100K
- File: intraday/scanner.py

### Bug 2 (HIGH): NSE losers API dead — 68e910c
- Root: ?index=losers returns "Missing index or key."
- Fix: Use SecLwr20 from gainers response
- File: fetchers/nse_market_movers.py
- Verified: 20 losers (NOIDATOLL 16.55% sample)

### Bug 3 (HIGH): Limit orders fail on fast movers — a0ec15e
- Root: SAREGAMA limit at LTP did not fill in 10s
- Fix: +0.3% buffer (1.003x LONG, 0.997x SHORT) + tick-align + MARKET fallback if conf>=8
- File: intraday/executor.py

### Bug 4: NOT A BUG (cron just hadnt fired)

### Bug 5 (CRITICAL — DISCOVERED EOD): max_trades_per_day bypassed
- Root: _restore_daily_state only counted CLOSED trades. OPEN didnt count.
- Effect: Continuous scan saw "0 trades placed" -> bypassed daily limit
- Real cost: vishal-live placed 7 trades (limit 3). Lost ~Rs.223.
- Fix: Counts all BUY except REJECTED/CANCELLED/FAILED/ABANDONED/PENDING
- File: intraday/risk_manager.py
- Status: Fixed in code, needs Monday validation

---

## STREAM 2: F&O BUG T FIX — REAL DHAN PRICES

### Built (commit 6b8de75)

**fno/option_chain_cache.py** (NEW)
- 5-min TTL cache shared across profiles
- Cache: cache/option_chain__.json
- 2-sec rate limiting
- Graceful failure

**fno/pnl_calculator.py** (NEW)
- Pure logic, accepts get_chain_func callable (data-source agnostic)
- compute_leg_pnl(), compute_strategy_pnl(), update_strategy_pnl_in_db()
- SELL: (entry - current) * qty | BUY: (current - entry) * qty

**fno/monitor.py** (MODIFIED)
- Added update_all_open_strategies(profile)
- Exit triggers per strategy:
  - IRON_CONDOR: 50% max profit OR 1.5x max loss OR <=1 day expiry
  - SHORT_STRADDLE/STRANGLE: 30% credit OR 2x credit loss OR expiry day 3 PM
  - BULL_PUT/BEAR_CALL_SPREAD: 70% credit OR full loss OR <=2 days expiry
  - DIRECTIONAL_*: 50% gain trail OR 30% loss OR before 2 PM if no movement

**DB changes (all 4 DBs)**
- Added current_price column to fno_trades
- Marked 84 stale open trades CLOSED (synthetic):
  - vishal: 48 | neha: 24 | vishal-live: 12 | neha-live: 0

**Cron added (OLD EC2 only)**
*/30 4-9 * * 1-5 update_all_open_strategies for vishal-live, vishal, neha

### Validation BLOCKED until Monday
- Dhan optionchain returned HTTP 401 + 404 fallback (after-hours)
- Dhan auth itself works (positions API returned 4 items)
- Likely: optionchain only available 9:15 AM - 3:30 PM IST
- First real test: Monday May 18 morning

---

## STREAM 3: BUG 6 FIX — NEHA-LIVE VISIBILITY

### Built on NEW EC2

**scripts/sync_neha_live_db.sh**
- Pushes database/neha-live.db -> s3://.../db-sync/neha-live.db
- Cron: */15 4-10 * * 1-5

**scripts/sync_neha_live_dashboard.sh**
- Syncs dashboard/api/neha-live/ -> s3://.../api/neha-live/
- Cron: */15 4-10 * * 1-5

### S3 Architecture
- OLD EC2 sync: aws s3 sync dashboard/ ... --exclude "db-sync/*" (preserves NEW EC2 DB)
- NEW EC2: pushes neha-live DB + dashboard JSON every 15 min
- Verified: /api/neha-live/intraday_latest.json returns 200 OK

### Pending: Dashboard neha-live tab missing in UI nav (HTML update)

---

## STREAM 4: STEERING DOCS EXPANSION

| File | Status |
|------|--------|
| BUSINESS_DOC.md | NEW |
| TECHNICAL_DOC.md | NEW |
| GLOSSARY.md | NEW |
| FNO_STRATEGY.md | NEW |
| STRATEGY.md | UPDATED |
| LEARNING.md | UPDATED |
| STATE.md | UPDATED (this file) |
| HISTORY.md | UNCHANGED |
| RULES.md | UNCHANGED |

Reading order: RULES -> STATE -> STRATEGY -> LEARNING -> GLOSSARY -> BUSINESS_DOC -> TECHNICAL_DOC -> FNO_STRATEGY

---

## LIVE STATUS (2026-05-15, 23:00 IST)

### Both EC2s Running
| EC2 | IP | Profiles |
|-----|----|----------|
| OLD | 13.206.144.6 | vishal-live, vishal, neha paper, F&O (3), F&O MTM cron |
| NEW | 13.202.63.223 | neha-live ONLY + DB sync to S3 + dashboard sync |

### Git Sync Status
- OLD EC2: 6b8de75
- NEW EC2: a0ec15e
- ACTION Monday: ssh ec2-user@13.202.63.223 "cd ~/dev-sandbox && git pull"

### Active Crons OLD EC2
- */15 4-7 * * 1-5 — intraday vishal-live, vishal, neha
- 50/52/54 3 * * 1-5 — F&O daily for vishal/neha/vishal-live
- */30 4-9 * * 1-5 — F&O MTM update (NEW today)
- 5 10 * * 1-5 — Top performers capture
- 0 3-10 * * 1-5 — Dashboard S3 sync + CloudFront invalidation

### Active Crons NEW EC2
- */15 4-7 * * 1-5 — intraday neha-live
- */15 4-10 * * 1-5 — sync neha-live DB to S3
- */15 4-10 * * 1-5 — sync neha-live dashboard JSON to S3

### Capital Limits
| Profile | Capital | Max Trades | Loss Limit | VIX |
|---------|---------|------------|------------|-----|
| vishal-live | Rs.15,000 | 3 | Rs.900 | 20 |
| neha-live | Rs.10,000 | 3 | Rs.900 | 20 |
| vishal paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |
| neha paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |

---

## ACTIVE BUGS / OPEN WORK

### Critical
| ID | Description | Status |
|----|-------------|--------|
| Bug 5 | max_trades_per_day not enforced | FIXED, needs Monday validation |
| Bug T | F&O P&L synthetic | FIXED, needs Monday market-hours validation |
| Bug HH | 0 orders placed at 12:03 PM neha-live (May 14) | OPEN |
| TELEGRAM-WIRE | Module ready, not called from monitor/executor | OPEN |

### High
- Dashboard neha-live tab missing (UI update)
- SL-TIMING: SL placed before BUY confirmed fill
- Dhan optionchain validation blocked until Monday

### Medium / Low / Future
- F&O legs_json expiry_date partial fix
- Dhan + AWS credentials rotation
- Backtest engine
- News + fundamentals fetchers
- Swing live deployment
- Positional module
- Onboarding website

---

## MONDAY MORNING CHECKLIST (2026-05-18)

### Pre-Market
1. timedatectl on both EC2s
2. NEW EC2: cd ~/dev-sandbox && git pull
3. git log --oneline -3 on both

### Market Open 9:30 AM IST
1. tail -f logs/intraday_vishal-live_2026-05-18.log
2. Bug 1: "Nifty500 scan: 250+ total" (was 169)
3. Bug 2: Losers count > 0
4. Bug 3: "buffered" or "MARKET retry" on fast movers
5. Bug 5: trade counter increments correctly across continuous scans

### F&O Open 9:24 AM IST
1. Strategies have real Dhan strike prices in entry_price
2. ls cache/option_chain_*.json

### Mid-Session every 30 min
1. cat logs/fno_pnl_update.log
2. fno_trades.current_price populated
3. fno_strategies P&L updating
4. Exit triggers fire when conditions met

### EOD 3:35 PM IST
1. cat logs/top_performers.log
2. War Room scanner accuracy
3. EOD summary shows real F&O P&L

### Watch For
- Bug 5 trade counter (most important — real money)
- Bug T option chain HTTP status (401 = Dhan API issue)
- Buffer 0.3% slippage acceptable
- F&O exit triggers not firing prematurely

---

## INFRASTRUCTURE

| Item | Value |
|------|-------|
| OLD EC2 | 13.206.144.6 (i-0256713c061011a5f) |
| NEW EC2 | 13.202.63.223 (i-0233c705c9104383e) |
| Dashboard | https://d2q1cy3ph7jbd0.cloudfront.net |
| GitHub | https://github.com/vshorrghar/Intraday-Trader.git |
| Bedrock | Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5) us-east-1 |
| AWS Profile | vishal-admin |
| Latest commit OLD | 6b8de75 |
| Latest commit NEW | a0ec15e (needs pull) |
| S3 db-sync prefix | s3://dev-sandbox-dashboard-176767908884/db-sync/ |
| S3 per-profile prefix | s3://dev-sandbox-dashboard-176767908884/api// |

---

## CAPITAL SCALING REMINDER

Phase 1: Rs.10K-15K live (current).
Phase 2 unlocks at: 50 profitable trades on real money.
Current: ~5 closed real money trades (Bug 5 inflated count today, dont count those).
Wait for 20+ validated trades on RS-First v3 + Bug 5 fix before evaluating.

---

## HOW TO RESUME ANY CHAT

Paste RULES.md + STATE.md + your question. Any AI that lectures without reading both is wasting your time.

End of STATE.md
