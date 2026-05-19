# STRATEGY.md — Technical Evolution Log

**Purpose**: How the system makes decisions. What changed. What is planned.
**Update rule**: Update CURRENT SYSTEM whenever code changes. Append EVOLUTION LOG.
**Read this before touching any trading code.**

---

## CURRENT SYSTEM (as of 2026-05-14, end of day)

### Scanner (intraday/scanner.py) — RS-First v3
Source: NSE Nifty 500 API (filter: price Rs.50-5000, volume > 500K)
Output: Top 15 LONG + 15 SHORT = 30 candidates
Min score threshold: >= 3 (was > 0)

#### Scoring Model — RS-First v3 (LIVE since 2026-05-14)

Signal 1: Intraday continuation change_from_open (0-5 pts) — MOST IMPORTANT
  > 4.0% = 5pts, > 2.0% = 4pts, > 1.0% = 3pts, > 0.5% = 2pts, > 0.0% = 1pt

Signal 2: Momentum strength change_pct (0-8 pts) — boosted from 0-4 to reward true gems
  > 15.0% = 8pts (rare massive winner)
  > 10.0% = 6pts (huge winner)
  > 7.0% = 5pts (strong winner)
  > 5.0% = 4pts
  > 3.0% = 3pts
  > 2.0% = 2pts
  > 1.0% = 1pt

Signal 3: Price near day high (0-2 pts)
  < 0.5% from high = 2pts, < 1.5% from high = 1pt

Signal 4: Volume confirmation (0-2 pts) — confirms only, does NOT lead
  > 5M = 2pts, > 2M = 1pt

Signal 5: FNO liquidity bonus (0-1 pt)

Signal 6: Sector rotation bonus (0-5 pts) — NEW v3
  Top 3 sector = +3pts, top 5 = +2pts, top 8 = +1pt
  Outperforming own sector by >2% = +2pts (relative strength)

#### Penalties (v3)

Fade detector (replaces old chasing penalty):
  Fell > 3% from day high = -3pts
  Fell > 1.5% from day high = -1pt
  Note: Stocks at/near day high get NO penalty regardless of total gain

Trap detector (NEW v3):
  Big gap (>5%) with no sector support (sector negative) = -5pts
  Buying climax: at 52w high + change > 8% = -2pts

#### Time-Aware Multiplier (NEW v3)

Applied to FINAL score before max(score, 0):
  First hour (9:30-10:30 IST): 1.5x — best entries
  Sweet spot (10:30-11:45 IST): 1.0x
  Caution (11:45-13:15 IST): 0.7x
  Late session (after 13:15): 0.4x

#### Why v3 Will Pick Real Gems (validation example)

Score comparison with May 14 real data + first hour 1.5x multiplier:

Symbol     v3 Score  v1 Score  Gain    From Open  Sector
SAREGAMA      31         5      +15.15%  +13.14%   Media
NLCINDIA      27         3      +14.61%   +7.27%   Power
CIPLA         25         8      +8.09%    +5.34%   Pharma
ADANIENT      24         9      +8.85%    +7.47%   Mining
VEDL          19        10      +4.99%    +3.19%   Metals
HINDALCO      11         5      +2.06%    +1.04%   Metals

v3 ranks SAREGAMA/NLCINDIA/CIPLA above VEDL.
v1 ranked VEDL #1 due to 38M raw volume.

### Selector (intraday/selector.py)
Pre-filter: 30 -> 20 candidates (price range, high_volatility flag)
LLM: Claude Opus 4.7 via AWS Bedrock us-east-1
Bedrock client: 60s read_timeout, 10s connect_timeout, 1 retry (FIXED Bug EE)
Validation: R:R >= 2.0, confidence >= threshold, direction logic
Trade history fed to LLM (last 30 days per symbol)

### Risk Manager (intraday/risk_manager.py)
VIX gates (NEW logic since May 14):
  > 25 -> SKIP entire session
  > 22 -> reduce to 1 trade max
  <= 22 -> normal trading per profile max

R:R calculation: direction-aware (FIXED SHORT-RR bug)
  LONG: rr = (target - entry) / (entry - sl)
  SHORT: rr = (entry - target) / (sl - entry)
  Reject if rr < 2.0

Daily loss caps:
  vishal-live: Rs.900 (was 600)
  neha-live: Rs.900 (was 600)
  vishal/neha paper: Rs.9,000

Per-trade max:
  vishal-live: Rs.4,500 (was 4,000)
  others: profile-specific

Late session gates (after 11 AM IST):
  Gate 1: Max trades placed -> SKIP
  Gate 2: Loss > 50% of daily limit -> SKIP
  Gate 3: REMOVED (was breadth gate)

### Executor (intraday/executor.py)
Entry order -> wait up to 10s for fill (poll 2s) -> SL order
Tick-aligned prices (Rs.0.05 NSE tick)
Direction-aware: LONG=BUY entry, SHORT=SELL entry
Security ID lookup: numeric ID resolved from config/nse_security_ids.json
Bug HH still OPEN: 0 orders placed at 12:03 PM neha-live May 14 — cause unknown

### Monitor (intraday/monitor.py)
5-min cycles via get_positions API
Live P&L: fetches from broker, falls back to NSE LTP if broker has no LTP (FIXED Bug GG)
Trailing SL after 0.5% profit
50% partial book at target
Force exit 15:15 IST
Calls broker SELL order on target/SL/force exit (not just DB updates)

### Cron Schedule (continuous since May 14)
Both EC2s: */15 4-7 * * 1-5 — every 15 min, 9:30 AM to 1:00 PM IST

OLD EC2:
  vishal-live (live), vishal (paper), neha (paper) — all */15
  F&O paper for 3 profiles at 9:20-9:24 AM
  Top performers capture at 3:35 PM IST
  Dashboard sync hourly 9 AM-5 PM IST

NEW EC2:
  neha-live (live) — */15 only

### Top Performers Capture (NEW since May 14)
Script: scripts/capture_top_performers.py
Runs: 3:35 PM IST (10:05 UTC) via cron
Captures: Top 20 NSE Nifty 500 gainers
Stores: daily_top_performers table in all 5 profile DBs
Diagnostics: Computes why_missed reason per stock for stocks we did NOT pick

Why-missed reasons computed:
  - "change_from_open X% > 8% (chasing penalty -4)" [v1 only — removed in v3]
  - "Scored lower than top 15 LONG candidates"
  - "Price > Rs.5000 (above range)" or "below range"
  - "Volume < 500K (too low)"
  - "PICKED" if we did pick it

### Dashboard War Room Tab (NEW since May 14)
URL: https://d2q1cy3ph7jbd0.cloudfront.net (click War Room tab)
Shows: Top 20 movers, scanner accuracy, why missed each one
Data source: dashboard/api/top_performers.json
Sync: scripts/sync_top_performers.py (runs after capture)

---

## EVOLUTION LOG (newest first)

### v3.5 — 2026-05-19 (THE INDENT BUG — ROOT CAUSE FOUND)
Commit: a2e5d66

The bug that wore seven faces. One indent fix in `intraday/executor.py` line 198
resolves all of these previously-thought-distinct issues:

- TATASTEEL 4x duplication (May 18)
- BANDHAN/MOTHERSON/CANBK 2x (May 18)
- ETERNAL phantom trade (May 18)
- INFY 3.5x today (May 19)
- Bug 5b counter false failures
- Same-symbol block bypass
- DB-vs-Dhan P&L 14x drift
- 5 of 7 INFY shares unprotected by SL today

**The bug**:
Line 198 had `return None` at 12-space indent.
This made it a sibling of `if filled_qty == 0:` instead of a child.
Function returned None unconditionally after MARKET retry block.

**The flow** (when LIMIT rejected → MARKET retry succeeds):
- Before fix: place LIMIT → reject → place MARKET → fill → return None.
  No SL. No DB write. No monitor handoff.
- After fix: place LIMIT → reject → place MARKET → fill → place SL → DB write → monitor.

**Why it hid for so long**:
- LIMIT first-try fills worked correctly (no MARKET retry needed)
- DryRun broker can't simulate real Dhan tick-size rejections
- MARKET retry only fires on confidence >= 8 setups
- Bug only visible by comparing Dhan API output vs our DB

**How we found it**:
1. Subscribed Dhan Data API Rs.499/mo (May 17)
2. Built scripts/sync_dhan_live.py (May 19 morning) — pulled real-time orders
3. Compared dhan_live.json vs intraday_trades — saw missing rows
4. Read executor.py with cat -A — spotted indent mismatch



### v3.4 — 2026-05-17 evening (DATA API LIVE + BACKTEST FOUNDATION)
Commit: 562030d

Tonight's session unlocked two major capabilities:

**1. Dhan Data API subscription active (Rs.499/month)**
For client_id 1110941563 (vishal, vishal-live profiles).
NOT covered: client_id 1111523334 (neha, neha-live).

Unlocks:
- Real option chain reads (option_chain endpoint, 470 strikes with Greeks/IV/OI)
- Historical OHLC API (/v2/charts/intraday) — minute candles for any equity
- Live Market Feed (WebSocket) — not yet wired
- Bulk market quotes — not yet wired

**2. Backtest engine v0.1**

intraday/dhan_broker.py: added get_historical_ohlc() method per Dhan v2 spec.
Verified: 750 5-min candles for TCS over 11 trading days, real OHLC data.

backtest/data_loader.py:
- load_nifty50_universe() — 50 hardcoded symbol→securityId mappings
- fetch_and_cache_historical() — 200ms rate-limited, JSON cache per symbol/range
- Cache: cache/historical/{symbol}_{interval}min_{from}_{to}.json

backtest/scanner_replay.py:
- replay_scanner_for_date() — uses first 3 candles (9:15-9:30 AM) as scan snapshot
- _score_stock_at_930() — replicates 7 of 9 scanner v3 signals
- compare_picks_to_actuals() — falls back to self-comparison if DB top performers empty
- run_backtest() — date range loop, JSON output

**HONEST LIMITATIONS of v0.1:**

Signals replicated (7):
- Intraday continuation
- Momentum strength (vs prev close)
- Price near day high
- Volume confirmation (extrapolated 3-candle to full day)
- FNO bonus (hardcoded Nifty 50 list)
- Time multiplier (fixed 1.5x for 9:30 AM)
- Fade detector

Signals OMITTED:
- Sector rotation bonus (needs sector index data, not in OHLC)
- 52-week high/low (needs daily candles, current data is intraday)

First test run: 5 stocks, 4 days. Reported 75% hit rate but **the comparison was self-referential** (fell back to ranking same 5 stocks by their own EOD performance). Real validation needs 50+ stock universe.

### Next Steps For Backtest v0.2
1. Run with full Nifty 50 universe (50 stocks)
2. Populate daily_top_performers table for past 30 days OR fetch from Dhan
3. Add sector data fetcher to enable Signal 6
4. Add daily OHLC fetcher to enable 52w signals
5. Validate scanner accuracy on real comparison set

### v3.3 — 2026-05-17 (BUG T SUB-BUGS)
Commits: 2584676 (May 16), 4867ef0 (May 17)

After May 15 Bug T fix shipped, Kiro found 3 sub-bugs that defeated the original fix:

T-1: MTM cron one-liner broken
- Inline shell -c with embedded Python failed under cron environment
- Replaced with scripts/fno_mtm_run.py (proper Python entry)
- Wrapper scripts/fno_mtm_update.sh handles env + logging
- Cron now points to wrapper script

T-2: Paper mode skipped Dhan auth
- run_fno.py paper mode never called auth -> option_chain_cache had no client
- All option chain fetches returned None silently
- Fix: paper mode now auths real Dhan broker (read-only API calls)
- Real money trades still gated by --live flag

T-3: force_exit_all passed current_premium=0
- Force exit at expiry day 3 PM logged P&L using zero premium
- Defeated entire Bug T fix on the most important exit path
- Fix: compute current_premium from option chain BEFORE recording exit P&L

Side fix (commit 2584676):
- neha-live didn't have dashboard login entry in passwords.json
- index.html mapping for neha-live was broken
- Now: neha and neha-live separate passwords, vishal/vishal-live shared

Validation expected Monday May 18:
- F&O strategies show real entry prices in DB
- MTM cron runs every 30 min and updates current_price column
- Force exits at expiry log real P&L not zero
- neha-live dashboard accessible at ?profile=neha-live

Risks:
- Paper mode now hitting Dhan API for option chain — uses 1 API call/30min/profile
- If Dhan rate-limits, fallback to NSE bhavcopy still not built
- T-3 fix only addresses force_exit_all; other exit paths may still pass 0

### v3.2 — 2026-05-15 (BUG 5 + BUG T + STREAM 3)
Commits: a9df59b, 68e910c, a0ec15e, 6b8de75

**Bug 5 (CRITICAL — discovered EOD)**: max_trades_per_day not enforced
- _restore_daily_state in risk_manager.py only counted CLOSED status trades
- Continuous scan every 15 min saw "0 trades placed today" — counter never incremented
- Real cost today: vishal-live placed 7 trades (limit 3). Lost ~Rs.223.
- Fix: Inverted logic — counts all BUY except REJECTED/CANCELLED/FAILED/ABANDONED/PENDING
- File: intraday/risk_manager.py
- Status: needs Monday validation

**Bug T (FIXED)**: F&O paper P&L now uses real Dhan option chain prices
- New: fno/option_chain_cache.py (5-min TTL, 2s rate limit, graceful failure)
- New: fno/pnl_calculator.py (pure logic, callable data source)
- Modified: fno/monitor.py (update_all_open_strategies + exit triggers)
- DB: added current_price column, marked 84 stale trades CLOSED
- Cron: */30 4-9 * * 1-5 mark-to-market every 30 min during market hours
- Validation blocked until Monday market open (Dhan API 9:15-3:30 IST only)

**Bug 6 (FIXED)**: neha-live data invisible from OLD EC2
- NEW EC2: scripts/sync_neha_live_db.sh -> s3://.../db-sync/neha-live.db
- NEW EC2: scripts/sync_neha_live_dashboard.sh -> s3://.../api/neha-live/
- OLD EC2 hourly sync excludes db-sync/* (preserves NEW EC2 data)
- Both crons */15 4-10 * * 1-5

Validation expected Monday May 18:
- Bug 5: trade counter should increment correctly across continuous scans
- Bug T: F&O strategies show real entry prices, MTM updates in fno_pnl_update.log
- Bug 6: neha-live data accessible from OLD EC2 dashboard reads

Risks:
- Bug 5 fix may falsely block legitimate trades (low risk — verified logic)
- Bug T relies on Dhan optionchain — fallback to NSE bhavcopy if API stays 401
- F&O exit triggers untested in production — may fire prematurely

### v3.1 — 2026-05-15 (POST-V3 BUGFIX)
Commits: a9df59b, 68e910c, a0ec15e

Bugs found from Day 1 of scanner v3 in production:

**Bug 1: Scanner only saw 169/500 stocks**
- 500K volume filter was too aggressive at 9:30 AM (volume hadn't built yet)
- Fix: momentum-aware filter. Pass if change_pct >= 4% AND volume >= 100K
- File: intraday/scanner.py
- Effect: TDPOWERSYS-type early breakouts now reach scanner

**Bug 2: NSE losers API endpoint dead**
- ?index=losers returned "Missing index or key." error
- Found losers in gainers response under SecLwr20 key
- Fix: fetch_top_losers() now calls gainers endpoint, extracts SecLwr20
- File: fetchers/nse_market_movers.py
- Effect: SHORT candidates restored (was 0 for unknown duration)

**Bug 3: Limit orders don't fill on fast movers**
- SAREGAMA +7% surge: limit at LTP didn't fill in 10s, cancelled
- Fix: +0.3% buffer on entry limit (LONG: 1.003x, SHORT: 0.997x)
- Tick aligned to NSE Rs.0.05 (round * 20 / 20)
- MARKET fallback after 10s timeout if confidence_score >= 8
- File: intraday/executor.py
- Effect: Fast movers fill or fall back to MARKET on conf>=8 picks

Validation expected Monday May 18:
- Scanner output: "Nifty500 scan: 250+ total" (was 169)
- Losers fetched: count > 0
- Fast mover fills: "buffered" or "MARKET retry" log lines

Risks:
- Buffer adds 0.3% slippage tax on all trades (~Rs.7K/year estimated)
- MARKET fallback could fill +1-2% above LTP, but bounded by SL
- Bug 1 may add low-quality momentum candidates

### v3 — 2026-05-14 (END OF DAY) — LIVE TOMORROW
Commits: 23a0261, 308e8b5, ddac03e, cf80098, 25361a5, 6ef8ab5, 8fe6d03

Scanner changes:
- Removed chasing penalty (penalized real winners like SAREGAMA +15%)
- Added fade detector (only penalize stocks falling from day high)
- Boosted momentum to 0-8 pts (was 0-4 pts) — rewards +10%/+15% movers
- Added sector rotation bonus (0-5 pts) — top 3 sector gets boost
- Added time-aware multiplier (1.5x first hour, 0.4x late session)
- Added trap detector (gap with no sector support, buying climax)

Other changes:
- Bedrock 60s read_timeout (was hanging 25 min at 9:26 AM peak)
- NSE gainers API fix (returns 20 now, was returning 0)
- Live P&L fetches NSE LTP fallback (was stuck at Rs.0)
- SHORT R:R now direction-aware (was always 0.0)
- VIX logic: >25 SKIP, >22 reduce to 1 (fixed levels, not profile-relative)
- Capital limits raised: vishal-live 10K->15K, max trades 2->3, loss 600->900
- Continuous scanning every 15 min (was 3 fixed times/day)
- Top 20 capture daily with why_missed diagnostics
- War Room dashboard tab live with scanner accuracy tracker
- Telegram module config-aware (needs token in config.yaml to activate)
- Options fetcher created (NSE option chain, ATM strike, IV percentile)
- daily_top_performers table on all 5 profile DBs

Validation expected tomorrow morning:
- SAREGAMA-type stocks should rank top of candidates (was being filtered out)
- VEDL-type slow stocks should rank lower (won't dominate every day)
- Bedrock should respond within 60s (no 25 min hang)
- Scanner accuracy on War Room should improve from 3/20 to 8+/20

Risk: Win rate may drop short term (50-55% vs 60% before).
Reward: Average winner becomes 4-6% (vs 1.5%).


### v1.3 — 2026-05-14 (IN PROGRESS)
Changes attempted:
- RS-first scanner scoring (patch status UNVERIFIED — check grep RS-FIRST scanner.py)
- STRATEGY.md + LEARNING.md created
- War Room tab added to dashboard
- Identified Bug HH, GG, FF, EE

Key insight: Scanner was volume-dominated — missed all real movers.
CIPLA +6.52%, GODREJIND +12.9%, NLCINDIA +17.36% all missed on May 14.
VEDL +2.66% picked because 38M raw volume.

### v1.2 — 2026-05-14 (overnight)
- Multi-EC2 architecture: neha-live moved to NEW EC2 (13.202.63.223)
- Reason: Dhan one-IP-per-account rule
- neha-live thresholds aligned with vishal-live (confidence 7, VIX 18)
- F&O fixes: legs_json expiry_date, hedged confluence 60->20
- First F&O paper trades placed (4 IRON_CONDORs synthetic)

### v1.1 — 2026-05-13
- Bug H fixed: NSE tick size rounding (Dhan error omsErrorCode 16283)
- Bug J fixed: Force exit waits for fill before logging P&L
- Bug K fixed: SL hit + target hit place broker orders
- Bug A+D fixed: Dashboard shows real exit_price + charges
- Rule 11 added: Heredoc-only edits for .py files

### v1.0 — 2026-05-12
- First real money trade: ONGC LONG vishal-live
- Basic volume-first scanner live
- Paper trading active vishal + neha
- F&O paper active (but P&L synthetic)

---

## ACTIVE BUGS (as of 2026-05-15)

### Critical (need Monday validation)
| ID | File | Status |
|----|------|--------|
| 5 | intraday/risk_manager.py | FIXED — counts all non-rejected/cancelled BUYs as trades. Validate Monday. |
| T | fno/monitor.py + pnl_calculator.py + run_fno.py + scripts/fno_mtm_run.py | FIXED in 6b8de75 + 4867ef0 (T-1/T-2/T-3 sub-bugs). Validate Monday market hours. |
| HH | intraday/executor.py | OPEN — 0 orders placed at 12:03 PM neha-live May 14, root cause unknown |

### High
| ID | File | Description |
|----|------|-------------|
| TELEGRAM-WIRE | alerts/telegram.py | Module ready, not called from monitor/executor |
| SL-TIMING | intraday/executor.py | SL placed before BUY confirmed fill |
| L | fno/strategy_engine.py | legs_json expiry_date partial fix |
| DASHBOARD-NEHA-LIVE | dashboard/index.html | neha-live tab missing in UI nav |

### Recently Fixed (2026-05-14 to 2026-05-15)
| ID | Commit | Description |
|----|--------|-------------|
| EE | 23a0261 | Bedrock 60s read_timeout |
| FF | 23a0261, 68e910c | NSE gainers + losers (SecLwr20) |
| GG | 23a0261 | Live P&L NSE LTP fallback |
| SHORT-RR | 23a0261 | Direction-aware R:R math |
| SCANNER | 6ef8ab5, 8fe6d03 | RS-First v3 scoring verified live |
| 1 | a9df59b | Momentum-aware volume filter |
| 2 | 68e910c | NSE losers SecLwr20 |
| 3 | a0ec15e | Buffered limit + MARKET fallback |
| 6 | abb236e, 7777382 | neha-live S3 sync |

---

## NEXT TO BUILD (priority order, as of 2026-05-15)

### Monday May 18 — Validation Day
1. Verify Bug 5 (max_trades_per_day) holds under continuous scan
2. Verify Bug T (F&O real prices) — option chain HTTP 200 during market hours
3. Verify Bug 6 (neha-live S3 sync) — data visible from OLD EC2 dashboard
4. Verify Bugs 1, 2, 3 (scanner v3.1) on live market data

### This Week
1. Fix Bug HH (0 orders placed) — root cause investigation
2. Wire Telegram alerts (TELEGRAM-WIRE) — phone notifications on real money
3. Fix dashboard neha-live tab (UI nav)
4. Fix SL-TIMING (wait for BUY fill before placing SL)

### Next Week
1. Swing module foundation
2. Backtest framework start
3. Pre-market intelligence (SGX Nifty, FII data at 8:30 AM)
4. Evaluate F&O strategies after 7 days clean MTM data

### This Month
1. Positional module
2. Onboarding website live (Kiro prompt ready)
3. Scale to Rs.50K after 50 profitable trades

---

## BEDROCK CLIENT FIX (exact code)

Current (broken — no timeout):
  self.client = boto3.client("bedrock-runtime", region_name=region)

Fix needed:
  from botocore.config import Config
  self.client = boto3.client(
      "bedrock-runtime",
      region_name=region,
      config=Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 1})
  )

---

## CONTINUOUS SCANNING PLAN

Current: 2 scans/day (9:26 AM, 12:01 PM)
Target: Every 15 min from 9:30 to 13:00

Cron change needed on OLD EC2:
Remove: 56 3 * * 1-5 and 31 6 * * 1-5
Add: */15 4-7 * * 1-5 (every 15 min 9:30-13:00 IST)

Guard already exists in risk_manager:
- Daily trade limit hit -> exit quietly
- Max positions open -> exit quietly
- Good setup found -> enter

Same change needed on NEW EC2 for neha-live.
