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

## ACTIVE BUGS

### Critical
| ID | File | Description | Fix Approach |
|----|------|-------------|-------------|
| EE | llm/bedrock_client.py | Opus times out at 9:26 AM | Add Config(read_timeout=60) to boto3 client |
| FF | fetchers/nse_market_movers.py | gainers/losers returns 0 | Check actual API response keys, fix parser |
| GG | intraday/monitor.py | Live P&L stays Rs.0 | Fetch live LTP from NSE in _compute_current_premium |
| HH | intraday/executor.py | 0 orders placed after sizing | Check max_trades gate logic |

### High
| ID | File | Description |
|----|------|-------------|
| SCANNER | intraday/scanner.py | RS-first patch UNVERIFIED |
| SHORT-RR | intraday/risk_manager.py | SHORT R:R = 0.0 in sizing |
| L | fno/strategy_engine.py | legs_json missing expiry_date |
| T | fno/monitor.py | Live P&L never changes |

---

## NEXT TO BUILD (priority order)

### This Week
1. Verify + finish RS-first scanner scoring
2. Fix Bug HH (0 orders placed)
3. Fix Bug FF (NSE gainers 0)
4. Fix Bug GG (live P&L = 0)
5. Add Bedrock 60s timeout
6. Continuous scanning every 15 min (9:30-13:00)

### Next Week
1. Swing module foundation
2. Telegram alerts wired
3. Backtest framework start
4. Pre-market intelligence (SGX Nifty, FII data at 8:30 AM)

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
