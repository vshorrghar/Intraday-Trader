# LEARNING.md — Business Journal

**Purpose**: What happened. What we learned. Money made/lost. Decisions taken.
**Update rule**: Append after every trading day. Never delete old entries.
**This is business language — no code details. Code details go in STRATEGY.md.**

---

## WEEK 1 (May 12-16, 2026)

### May 14 — Full Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | VEDL LONG | TBD |
| neha-live | SAIL LONG | -Rs.63 approx |
| neha-live | BHARTIARTL | Rs.0 (never placed — Bug HH) |

Cumulative all real money: approximately -Rs.165

#### What The Market Did Today
- NLCINDIA ran +17% — we missed it
- GODREJIND ran +13% — we missed it
- CIPLA ran +6.5% — we missed it
- We bought VEDL which moved +2.7% and went nowhere
- Metal sector led all day (NIFTY METAL +1.79%)
- VIX stayed elevated 18.7-19.0 — system correctly cautious

#### What We Learned
1. Our scanner is a volume picker not a momentum picker
   VEDL trades 38M shares/day — always wins on volume score
   CIPLA trades 4.7M — loses on volume even though move was 3x better
   Fix: RS-first scoring — change_from_open is the key signal

2. Bedrock Opus is slow at market open
   9:26 AM = 25 min hang = missed best entry window
   10:57 AM = 4 min 18 sec = acceptable
   Market open is when everyone hits Bedrock simultaneously
   Fix needed: 60 second timeout

3. Live P&L is completely blind
   SAIL was losing Rs.63 but monitor showed Rs.0 all day
   Trailing stop loss never activates because it needs P&L
   Only safety was the Dhan SL order placed at entry
   This is the most dangerous open bug

4. Two EC2s working correctly
   neha-live on NEW EC2 placed real trade successfully
   Dhan IP whitelist confirmed — separate IP required per account

#### Decisions Made Today
- Keep Opus 4.7 (quality model) but add timeout
- Rewrite scanner scoring from volume-first to RS-first
- Build continuous 15-min scanning (catch intraday breakouts)
- Build onboarding website for new users (Kiro prompt ready)
- Created STRATEGY.md and LEARNING.md for institutional memory

#### What We Are Competing Against
- Millions of Indian retail traders checking charts every minute
- Our edge: scan 500 stocks simultaneously, zero emotion, perfect rule execution
- Our weakness today: scanning wrong stocks (volume bias)
- After RS-first fix: our edge becomes real

---

### May 13

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | HINDZINC LONG | -Rs.28.30 |
| vishal paper | multiple | +Rs.57.69 |
| neha paper | multiple | -Rs.401.53 |

#### What We Learned
- Charges matter more than we thought
  Paper showed +Rs.261 gross but +Rs.57.69 after charges
  neha paper showed -Rs.81 gross but -Rs.401.53 after charges
  Always look at net P&L not gross
- Dashboard was hiding charges (Bug A+D) — fixed today
- NSE tick size (Rs.0.05) caused Dhan order rejections (Bug H) — fixed today

---

### May 12 — First Real Money Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | ONGC LONG | -Rs.53.80 |
| vishal-live | WIPRO SHORT | -Rs.20.00 |

#### What We Learned
- System placed real orders — architecture works
- Lost money on first two trades — expected in learning phase
- Short direction needs more validation (WIPRO SHORT unclear)

---

## PATTERN LIBRARY (grows over time)

### Patterns That Work (building evidence)
- Metal sector leadership + HINDALCO/VEDL continuation = follow sector leader
- Pharma gap up + continuing from open = usually holds through session
- VIX spike day = skip or 1 trade max with tight SL

### Patterns That Fail
- High volume PSU stocks (VEDL/ONGC/SAIL) = slow movers, poor R:R
- Entering stocks already up 10%+ at 11 AM = chasing, always loses
- Trading when VIX > 20 = wide stops, bad fills, choppy exits

### Market Timing Observations
- 9:15-9:30 AM: Most volatile, best moves START here
- 9:30-10:30 AM: Best entry window — momentum confirmed
- 10:30-12:00 PM: Mid-session, some continuation plays
- After 12:00 PM: Late entries risky, most moves 70% done
- 2:30-3:15 PM: End of day volatility, system avoids (force exit 3:15)

### VIX Observations (NSE India)
- VIX < 14: Easy market, trend days, system should be aggressive
- VIX 14-18: Normal, current thresholds appropriate
- VIX 18-20: Elevated, reduce to 1 trade, wider SL — current state
- VIX > 20: Skip day or 1 micro trade only
- VIX > 25: Full skip, capital protection mode

---

## DECISIONS LOG (append only)

### 2026-05-14: RS-first scoring rewrite
Old system: volume dominated — wrong stocks picked
New system: change_from_open is primary signal
Expected result: CIPLA/HINDALCO type stocks score higher than VEDL
Status: Patch in progress

### 2026-05-14: Multi-EC2 architecture confirmed
Each live user needs dedicated EC2
Cost: Rs.1,500/month per user
Non-negotiable: Dhan IP whitelist rule

### 2026-05-14: Upgraded to Claude Opus 4.7
Better analysis quality than Sonnet 4.5
Trade-off: Slower, more expensive
Problem found: Times out at market open
Mitigation needed: 60s boto3 timeout

### 2026-05-13: Dashboard charges visibility fixed
Was hiding gross/net difference
Now shows: gross P&L, charges, net P&L separately
Lesson: Always verify what dashboard actually shows

### 2026-05-12: First real money trade
Decision: Start with Rs.10,000, max Rs.600 loss/day
Rationale: Prove system works before scaling
Current status: Small losses, fixing underlying issues

---

## MONTHLY TARGETS

### May 2026
Target: Fix core bugs, establish baseline
- Fix scanner (RS-first) ← in progress
- Fix live P&L visibility (Bug GG)
- Fix 0 orders bug (Bug HH)
- 20+ paper trades per profile
- Establish win rate baseline
Success metric: Win rate > 50% on paper by end of month

### June 2026
Target: Prove the system
- RS-first scoring proven (2 weeks data)
- Continuous 15-min scanning live
- Telegram alerts working
- Win rate > 55% on paper
Capital: Consider Rs.25K if May shows > 55% win rate

### July-August 2026
Target: Scale carefully
- 50 profitable real trades milestone
- Scale to Rs.50K after milestone
- Swing module live on paper
Success metric: 3 months data, consistent positive months

---

## NORTH STAR

Goal: Rs.20,000-30,000 per day combined
Reality: Needs Rs.15-30L deployed + 12-18 months validation
Today: Rs.20,000 deployed (Rs.10K each vishal + neha live)
Path: Fix picks quality -> prove win rate -> scale capital -> reach goal

Today we lost Rs.165 real money.
But we identified WHY the scanner picks wrong stocks.
And we know exactly how to fix it.
That knowledge is worth more than Rs.165.
