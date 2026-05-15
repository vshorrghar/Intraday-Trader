# FNO_STRATEGY.md - F&O Strategy Reference

Comprehensive F&O strategy documentation. Cross-reference GLOSSARY.md for term definitions.

Status as of 2026-05-15: F&O paper code exists but does not track real prices or P&L. Bug T (live P&L never changes) is open. All paper trades currently have null P&L. Not production-ready.

This document defines what F&O should look like, what gaps exist, and the path to real money deployment.

---

## 1. WHY F&O IS THE PATH TO Rs.10K-20K DAILY

### Capital Math For Intraday-Only Path

To hit Rs.20K/day with intraday alone:
- Average daily edge: 1-2% on deployed capital
- Required capital: Rs.10-20 lakh
- Phase to reach: Phase 4-5 (12-18 months minimum)

### Capital Math For F&O Path

F&O leverage allows similar daily targets at Phase 2-3 capital:
- Iron Condor on NIFTY: deploy Rs.50,000 margin, capture Rs.500-1500 daily theta decay
- 2-3 Iron Condors active simultaneously
- Average Rs.1000-1500 per active condor per week

Realistic F&O target at Phase 2 (Rs.50K capital each profile):
- 2 active Iron Condors: ~Rs.300-500/day average
- 1 directional weekly: ~Rs.1000-2000/week
- Combined: Rs.10K-15K weekly

This is achievable. But only with proper paper validation first.

---

## 2. CURRENT STATE - HONEST ASSESSMENT

### What Works
- 7 strategy types defined in code
- Confluence score thresholds (20/60/75)
- Expiry day strategy filter
- LLM integration via Bedrock
- Database schema
- Cron scheduling per profile

### What Does Not Work
- No real option prices: trades use synthetic prices
- No P&L tracking: all 84 paper trades show null pnl, null exit_price
- No exit logic: strategies open and never close
- No mark-to-market: live position values not updated daily
- No validation data: cannot tell if strategies would have made money

### What This Means
F&O paper data from May 14-15 is unusable for performance evaluation. Before any conclusion about F&O viability, we need to fix paper mode to track real prices and compute real P&L.

---

## 3. STRATEGY PLAYBOOK

### 3.1 IRON_CONDOR

Setup: Sell OTM CE + Sell OTM PE + Buy further OTM CE + Buy further OTM PE
View: Sideways market, low conviction on direction
Profit when: Index stays between short strikes at expiry
Max profit: Net premium collected (typically Rs.500-1500 per lot)
Max loss: Strike width minus net premium

When to use:
- IV percentile > 70 (premium expensive, sell it)
- VIX 12-18 (sideways volatility regime)
- 3-7 DTE (theta decay accelerating)
- No major events in next 5 days

Example NIFTY Iron Condor (NIFTY at 23100):
- Sell 23400 CE at Rs.45
- Buy 23600 CE at Rs.20 (protection)
- Sell 22800 PE at Rs.40
- Buy 22600 PE at Rs.18 (protection)
- Net premium: Rs.47/lot = Rs.1175 (50 qty/lot)
- Max profit: Rs.1175 if NIFTY stays between 22800 and 23400
- Max loss: Rs.5825 if NIFTY moves beyond protection strikes

Exit rules:
- Profit target: 50% of max profit
- Stop loss: Loss equals 1.5x max profit
- Time exit: Close 1 day before expiry regardless

### 3.2 SHORT_STRADDLE

Setup: Sell ATM CE + Sell ATM PE simultaneously
View: Strong belief market won't move much
Max profit: Total premium collected
Max loss: UNLIMITED (theoretical)

When to use:
- IV percentile > 80 (extreme premium)
- Expiry day only (theta crushes)
- Confluence required >= 75

Risk: This is naked selling. One big move can wipe out account.

### 3.3 SHORT_STRANGLE

Setup: Sell OTM CE + Sell OTM PE (different strikes)
View: Range-bound market, less aggressive than straddle
Max loss: UNLIMITED (theoretical)

When to use:
- IV percentile > 70
- 3-5 DTE
- Confluence >= 75

Vs Straddle: Wider profit range, smaller premium. Lower probability of max loss.

### 3.4 BULL_PUT_SPREAD

Setup: Sell higher-strike PE + Buy lower-strike PE
View: Bullish or neutral
Max profit: Net premium collected
Max loss: Strike width minus net premium

When to use:
- Confluence >= 20
- IV percentile > 60
- Bullish technical setup

Exit rules:
- Profit target: 70% of max credit
- Stop loss: Loss equals max credit collected
- Time exit: 2 days before expiry

### 3.5 BEAR_CALL_SPREAD

Mirror of Bull Put Spread for downside views.
Setup: Sell lower-strike CE + Buy higher-strike CE
View: Bearish or neutral

### 3.6 DIRECTIONAL_CE_BUY

Setup: Buy ATM or slightly OTM call
View: Strong bullish conviction
Max profit: UNLIMITED (theoretical)
Max loss: Premium paid

When to use:
- Confluence >= 60
- IV percentile < 40
- Major bullish catalyst
- Not on expiry day

Risk: 80% of buyers lose. Use only on highest conviction setups.

### 3.7 DIRECTIONAL_PE_BUY

Mirror of CE_BUY for bearish conviction.

---

## 4. STRATEGY SELECTION LOGIC

### 4.1 Market Regime Classification

TRENDING_UP: NIFTY > 20-DMA, breadth > 65% green, VIX < 16
TRENDING_DOWN: NIFTY < 20-DMA, breadth < 35% green, VIX > 18
SIDEWAYS: NIFTY within 1% of 20-DMA, breadth 40-60% green
HIGH_VOLATILITY: VIX > 22 OR daily range > 2%
EXPIRY_DAY: Day before/of weekly expiry

### 4.2 Strategy Recommendations By Regime

TRENDING_UP: Prefer BULL_PUT_SPREAD, DIRECTIONAL_CE_BUY
TRENDING_DOWN: Prefer BEAR_CALL_SPREAD, DIRECTIONAL_PE_BUY
SIDEWAYS: Prefer IRON_CONDOR, SHORT_STRANGLE
HIGH_VOLATILITY: Prefer IRON_CONDOR (wider strikes)
EXPIRY_DAY: SHORT_STRADDLE (intraday only)

### 4.3 Confluence Score Components

- IV Percentile (IVP): 0-30 points
- OI Velocity: 0-20 points
- VRP: 0-20 points if positive
- GEX: 0-15 points
- IV Skew: 0-15 points

Total: 0-100 confluence score.

### 4.4 Strategy Gates

Hedged strategies (defined risk):
- Confluence >= 20

Directional buy:
- Confluence >= 60

Naked selling (unlimited risk):
- Confluence >= 75
- Time block: Not allowed after 14:00 IST

Directional buy time block:
- Not allowed after 13:00 IST

Expiry day allowed only:
- SHORT_STRADDLE, IRON_CONDOR, DIRECTIONAL_CE_BUY, DIRECTIONAL_PE_BUY

---

## 5. POSITION SIZING

### 5.1 Margin Requirements

Iron Condor (defined risk):
- NIFTY 1 lot: ~Rs.40000
- BANKNIFTY 1 lot: ~Rs.55000
- FINNIFTY 1 lot: ~Rs.30000

Short Straddle (undefined risk):
- NIFTY 1 lot: ~Rs.120000
- BANKNIFTY 1 lot: ~Rs.180000

Directional buy: just premium paid (Rs.5000-25000 per lot)

### 5.2 Per-Trade Limits (current paper config)

- per_trade_max_capital: Rs.25000
- max_lots_per_trade: 1
- daily_capital_limit: Rs.50000

### 5.3 Live Capital Plan

Phase F-1: Rs.50000 capital, 1 lot max, IRON_CONDOR only
Phase F-2: Rs.100000 capital, 2 lots max, add spreads
Phase F-3: Rs.200000 capital, add directional buys
Phase F-4: Rs.500000 capital, full strategy library

Each phase requires 2-4 weeks validation in previous phase.

---

## 6. EXIT MANAGEMENT

### 6.1 Daily Monitoring (Required, Currently Missing)

Monitor every hour:
- Current option prices
- Mark-to-market P&L
- Distance from breakeven points
- Time decay accumulation

### 6.2 Exit Triggers Per Strategy

Iron Condor / Strangles:
- Profit: Close at 50% of max profit
- Loss: Close at 2x credit received
- Time: Close 1 day before expiry
- Breach: Close immediately if either short strike breached

Bull/Bear Spreads:
- Profit: Close at 70% of credit
- Loss: Close at full credit
- Time: Close 2 days before expiry

Directional Buys:
- Profit: Trail stop at 50% gain
- Loss: Cut at 30% premium loss
- Time: Close before 2:00 PM if no movement

Short Straddle (expiry day only):
- Profit: 30% of credit
- Loss: 2x credit hard stop
- Time: 3:00 PM mandatory close

---

## 7. THE BUG T FIX PLAN

### 7.1 What Bug T Is

From STATE.md: F&O live P&L never changes

The fno/monitor.py code runs but:
1. Does not fetch current option chain from NSE
2. Does not compute mark-to-market
3. Does not update fno_trades.pnl field
4. Does not log unrealized P&L

Result: All paper trades show null P&L. Cannot validate strategy performance.

### 7.2 Fix Components

Component A: Option Chain Fetcher (already exists)
- File: fetchers/options_fetcher.py (built May 14)
- Status: Working but not used by monitor.py

Component B: Mark-to-Market Calculator (NEEDS BUILDING)
For each open position, fetch current premium for each leg, compute P&L.

Component C: Update Loop (NEEDS BUILDING)
Cron entry every 30 min during market.

Component D: Exit Trigger (NEEDS BUILDING)
After P&L update, check exit conditions per strategy.

### 7.3 Estimated Work

- Component B: 4-6 hours coding
- Component C: 1-2 hours
- Component D: 2-4 hours
- Testing: 4-6 hours
- Total: 1-2 working days

### 7.4 After Bug T Fix

We can finally answer:
- Does Iron Condor make money in current market?
- What is the win rate?
- Average profit per strategy?

---

## 8. ROAD TO REAL F&O MONEY

### Phase F-0: Fix Paper Mode (1-2 weeks)
- Build mark-to-market calculator
- Build update loop cron
- Build exit trigger logic
- Test on dummy positions
- Deploy to all 3 paper profiles
- Verify daily P&L flows

### Phase F-1: Paper Validation (2-3 weeks)
- 30+ Iron Condor paper trades minimum
- 5+ different VIX regimes
- Mix of expiry/non-expiry days

Go/No-Go criteria for live:
- Win rate > 60% on Iron Condors
- Average win > 2x average loss
- LLM strategy selection accuracy > 70%
- No catastrophic single losses

### Phase F-2: Live Pilot (4 weeks)
- Rs.50000 capital, vishal-live profile only
- 1 lot max, IRON_CONDOR only
- 1 active position at a time
- 4 weeks = ~10-15 trades minimum

### Phase F-3: Live Scaling (ongoing)
- Expand to Rs.100000 capital
- 2 simultaneous positions allowed
- Add BULL_PUT_SPREAD and BEAR_CALL_SPREAD

### Realistic Timeline

- Now: Bug T fix needed
- Week 1-2: Build paper tracking
- Week 3-5: Paper validation
- Week 6: Decision on live deployment
- Week 7-10: Live pilot
- Month 4+: Scaling

Earliest realistic Rs.10K-20K daily target with F&O: 4-6 months from today.

---

## 9. RISK MANAGEMENT

### 9.1 Position-Level Risk
- IRON_CONDOR: Max loss = strike width - credit
- SPREADS: Max loss = strike width - credit
- DIRECTIONAL: Max loss = premium paid
- STRADDLE/STRANGLE: UNLIMITED in theory

### 9.2 Daily Loss Cap
- Paper: Rs.5000 daily loss limit
- Live (when deployed): Rs.2000 starting cap

### 9.3 Black Swan Mitigation
- Max one Iron Condor per index simultaneously
- No naked selling without paper validation
- Hard stop loss on every position
- Force close before major events

---

## 10. METRICS TO TRACK (POST-FIX)

Strategy Performance:
- Win rate per strategy type
- Average profit per winning trade
- Average loss per losing trade
- Sharpe ratio per strategy
- Max consecutive losses

Operational:
- LLM strategy selection accuracy
- Time from entry to exit
- Premium decay capture rate
- Slippage on entries and exits

Business:
- Net P&L per day (after charges)
- Capital deployed vs available
- ROI per Rs.10000 deployed
- Comparison vs intraday returns

---

## 11. KNOWN LIMITATIONS

11.1 Strike Selection: May pick suboptimal strikes
11.2 Slippage: Real F&O has 5-15% slippage
11.3 Regulatory: SEBI may change F&O margin requirements
11.4 Tax: F&O profits taxed as business income
11.5 Psychological: Watching naked positions during volatility

---

## 12. REFERENCE READING

- "Options as a Strategic Investment" by Lawrence McMillan
- "Option Volatility and Pricing" by Sheldon Natenberg
- NSE F&O Bhavcopy archive (free, daily data)
- Sensibull strategy backtester (paid)

---

## 13. CONCLUSION

F&O is the fastest realistic path to Rs.10K-20K daily target. But:
- Current paper mode is broken (Bug T)
- Cannot validate without real prices
- Need 4-6 months of disciplined work before live deployment
- Risks are larger than intraday (especially naked selling)

Recommended next action: Fix Bug T (1-2 weeks). Without that fix, any F&O discussion is theoretical.

After fix: 4 weeks paper validation tells us if F&O strategies actually work. Then we decide.

This is the honest path. Anyone promising faster is selling something.
