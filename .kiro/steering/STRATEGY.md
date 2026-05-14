# STRATEGY.md — Technical Evolution Log

**Purpose**: How the system makes decisions. What changed. What is planned.
**Update rule**: Update CURRENT SYSTEM whenever code changes. Append EVOLUTION LOG.
**Read this before touching any trading code.**

---

## CURRENT SYSTEM (as of 2026-05-14)

### Scanner (intraday/scanner.py)
Source: NSE Nifty 500 API
Scoring: RS-FIRST model (replacing volume-first — patch status UNVERIFIED)
Output: Top 15 LONG + 15 SHORT = 30 candidates
Min score threshold: >= 3 (was > 0)

#### RS-First Scoring Model (NEW — being applied)
Signal 1: Intraday continuation change_from_open (0-5 pts) — MOST IMPORTANT
  > 4.0% = 5pts, > 2.0% = 4pts, > 1.0% = 3pts, > 0.5% = 2pts, > 0.0% = 1pt

Signal 2: Momentum strength change_pct (0-4 pts)
  > 5.0% = 4pts, > 3.0% = 3pts, > 2.0% = 2pts, > 1.0% = 1pt

Signal 3: Price at/near day high (0-2 pts)
  < 0.5% from high = 2pts, < 1.5% from high = 1pt

Signal 4: Volume confirmation (0-2 pts) — confirms only, does NOT lead
  > 5M = 2pts, > 2M = 1pt

Signal 5: FNO stock liquidity bonus (0-1 pt)

Penalties:
  change_from_open > 8% = -4 (chasing)
  change_from_open > 6% = -2 (likely chasing)
  gap up + now selling = -3 (gap fade)
  huge gap + no follow = -2 (gap exhaustion)

#### Old Scoring Model (REPLACED — do not restore)
Was: change_pct > 0 = +2, volume > 2M = +2, volume > 5M = +1
Problem: VEDL (38M volume, +2.66%) always beat CIPLA (+6.52%) and HINDALCO (+2.06%)
Proof: May 14 market — CIPLA +6.52%, GODREJIND +12.9% missed. VEDL picked.

#### Score Comparison (May 14 real data)
Symbol     NewScore  OldScore  change_from_open  change_pct
CIPLA         8        4         +3.82%           +6.52%
ADANIENT      9        5         +3.85%           +5.18%
HINDALCO      5        4         +1.04%           +2.06%
VEDL          4        7         +0.90%           +2.66%
NLCINDIA      3        2*        +9.84%           +17.36%
(* NLCINDIA gets chasing penalty -4 at 11AM, but at 9:30AM would score 9+)

### Selector (intraday/selector.py)
Pre-filter: 30 -> 20 candidates (price range, high_volatility flag)
LLM: Claude Opus 4.7 via AWS Bedrock us-east-1
Validation: R:R >= 2.0, confidence >= threshold, direction logic
Known issue: Opus slow at 9:26 AM market open (Bug EE — no timeout set)

### Risk Manager (intraday/risk_manager.py)
VIX gate: > threshold -> reduce max trades to 1
Daily loss cap: Rs.600 (vishal-live/neha-live)
Per trade max: Rs.4,000
Late session gates: after 11 AM IST
Known bug: SHORT R:R calculated as 0.0 (sizing wrong for shorts)

### Executor (intraday/executor.py)
Entry order -> wait for fill -> SL order
Tick-aligned prices (Rs.0.05 NSE tick) — Bug H fixed May 13
Direction-aware: LONG=BUY entry, SHORT=SELL entry
Bug HH: 0 orders placed at 12:03 PM neha-live — cause unknown

### Monitor (intraday/monitor.py)
5-min cycles via get_positions API
Trailing SL after 0.5% profit
50% partial book at target
Force exit 15:15 IST
Bug GG: Live P&L stays Rs.0 — _compute_current_premium not fetching live prices
Impact: Trailing SL never triggers on live trades

### Cron Schedule
9:26 AM: vishal-live (real money) — OLD EC2
9:28 AM: neha-live (real money) — NEW EC2
9:25/12:00/13:30: vishal paper — OLD EC2
9:27/12:02/13:32: neha paper — OLD EC2
F&O: 9:20-9:24 AM — OLD EC2

---

## EVOLUTION LOG (newest first)

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
