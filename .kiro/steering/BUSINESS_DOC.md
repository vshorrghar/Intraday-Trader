# Intraday Trader — Business Overview

## Executive Summary

An AI-augmented automated trading system for Indian stock market (NSE) that combines algorithmic decision-making with large language model intelligence. The system identifies and executes short-term trades during market hours with minimal human intervention, while maintaining strict risk controls.

**Status**: Live trading since May 12, 2026. Currently in capital validation phase (Phase 1 of 5).

**Real money deployed**: Rs.25,000 across two trading accounts.

**Goal**: Rs.20,000-30,000 daily profit at full deployment (requires Rs.15-30 lakh capital, 12-18 months validation).

---

## Problem Statement

Indian retail equity traders face three structural challenges:

1. **Information overload**: 500+ liquid stocks to monitor across 30+ sectors. Impossible to track manually.

2. **Emotional decisions**: Fear of missing out and panic selling cause 70% of retail trades to lose money (per SEBI 2023 study).

3. **Time constraints**: Most retail traders have full-time jobs and cannot actively monitor markets between 9:15 AM and 3:30 PM IST.

This system addresses all three:
- Scans 500+ stocks every 15 minutes during market hours
- Follows mathematical rules with zero emotion
- Operates fully automated, 24/7 cloud-hosted

---

## Market Context

**NSE India** is the world's largest derivatives exchange by volume. Daily turnover: Rs.80,000+ crores cash market, Rs.2.5 lakh crores derivatives.

**Retail participation** has grown 5x since 2020. 11+ crore demat accounts as of 2026.

**The opportunity**: Most retail traders use either pure technical analysis (charts) or pure fundamentals (P/E ratios). Few combine real-time multi-factor scoring with AI-assisted decision-making at scale.

---

## How It Works (Plain English)

Every 15 minutes during market hours (9:30 AM to 1:00 PM IST), the system runs this loop:

### Step 1: Market Scan
Pulls live data on 500+ NSE-listed stocks via Dhan broker API and NSE public APIs. Captures price, volume, sector performance, India VIX (volatility index).

### Step 2: Multi-Factor Scoring
Each stock scored on six independent signals:
- Intraday momentum (price moving in clear direction)
- Sector strength (is the sector leading the market today?)
- Volume confirmation (real conviction or thin liquidity?)
- Distance from day high (catching strength, avoiding fades)
- Relative strength (outperforming sector peers?)
- Time-of-day weighting (early entries get bonus, late entries discounted)

### Step 3: Top 30 Filter
30 highest-scored stocks selected (15 long candidates, 15 short candidates).

### Step 4: Pre-Filter
Mathematical rules cut 30 to 20 candidates:
- Price range Rs.50-5000 (avoid penny stocks and ultra-high price stocks)
- Volume floor: 500K shares OR 4%+ momentum with 100K minimum
- Volatility checks
- Sector alignment

### Step 5: AI Ranking
20 candidates sent to Claude Sonnet 4.5 (via AWS Bedrock). AI returns top 5 picks with:
- Specific entry price, target price, stop-loss price
- Confidence score 1-10
- Strategy type (momentum, gap, breakout, mean reversion)
- Detailed rationale
- Skip recommendation if no good setups exist

### Step 6: Validation
Python rejects AI picks that fail any of:
- Confidence below 7 (live profiles) or 8 (highest-conviction profiles)
- Risk:Reward ratio below 2.0
- Direction logic errors (long must have target above entry)

### Step 7: Position Sizing
For each valid pick, system calculates:
- Maximum capital allowed (Rs.4,000-4,500 per trade)
- Adjusted for VIX (reduce in high volatility)
- Daily capital limit check
- Daily loss limit check

### Step 8: Order Execution
- Places limit BUY order at entry price (with 0.3% buffer for fast movers)
- Waits 10 seconds for fill
- If unfilled, falls back to MARKET order on high-confidence picks
- Once filled, immediately places STOP-LOSS order
- All prices aligned to NSE Rs.0.05 tick size

### Step 9: Position Monitoring
Every 5 minutes:
- Check current price vs target/stop
- Move stop-loss higher if 0.5%+ profit (trailing)
- Book 50% of position if target hit
- Force-exit at 3:15 PM IST regardless

### Step 10: End-of-Day
- All positions closed
- P&L calculated with charges
- Database updated
- Dashboard refreshed
- Top 20 movers captured for accuracy tracking

---

## Trading Strategies

### Live: Intraday Momentum

**Time horizon**: Hours (entry 9:30 AM, exit by 3:15 PM)
**Holding period**: Same day, no overnight risk
**Stop loss**: 1.8-2% below entry
**Target**: 3.6-4% above entry
**Risk:Reward minimum**: 2:1

**Setup criteria**:
- Stock up 2-7% from open (momentum confirmed, not yet exhausted)
- Volume showing genuine interest (>500K shares or 4%+ move with 100K)
- Sector showing leadership (top 5 of 30 sectors)
- Price near day high (strength continuing)

**Example trade (real, May 15 2026)**:
- Stock: SAREGAMA
- Entry: Rs.399.35 at 10:00 AM
- Target: Rs.428.40
- Stop loss: Rs.391.50
- Outcome: Closed at Rs.421.50 = +Rs.105 profit on Rs.3,200 capital (3.3% gain)

### Active (Paper): F&O Options

**Time horizon**: Days to weeks
**Strategies**: Iron Condors, Bull Spreads, Bear Spreads
**Trigger**: Volatility regime detection (high IV percentile = sell premium)
**Currently paper-traded** for 2 weeks of validation before any real money deployment

### Planned: Swing Trading
2-10 day holds, delivery (CNC) orders, target 5-10% gains, stop loss 3-5%

### Planned: Positional
1-6 month holds with fundamental analysis, target 20-50% gains

---

## Risk Management

Every trade has automatic protections at multiple levels:

### Pre-trade
- **R:R minimum 2:1** — Reject trades where reward is less than 2x risk
- **Confidence floor** — Only trade AI picks with confidence 7+ (or 8+ for higher-bar profiles)
- **Capital cap per trade** — Maximum Rs.4,000-4,500 in any single position
- **Daily capital limit** — Maximum Rs.10,000-15,000 deployed in one day
- **VIX gate** — Skip trading if VIX > 25 (extreme fear/uncertainty)

### Mid-trade
- **Stop loss order** — Placed simultaneously with entry, broker enforces
- **Trailing stop** — Stop loss moves up after 0.5% profit
- **Partial booking** — Half position closed at target, rest trails
- **Force exit** — All positions closed at 3:15 PM IST

### Daily
- **Daily loss limit** — Rs.900 (live profiles) or Rs.9,000 (paper). Trading stops if breached.
- **Max trades per day** — 3 (live) or 6 (paper). Prevents overtrading.
- **Late-session gates** — After 11 AM, additional checks for revenue trading prevention

### Systemic
- **Multi-day capital scaling halt** — Cannot increase capital without 50 profitable trades milestone
- **All operations logged** — Full audit trail of every decision
- **Manual override capability** — Human can pause system at any time

---

## Capital Scaling Plan

The system scales capital only after proving consistency. Five phases:

| Phase | Trigger | Capital Per Profile | Total Capital |
|-------|---------|---------------------|---------------|
| 1 (current) | Live deployment | Rs.10,000-15,000 | Rs.25,000 |
| 2 | 50 profitable trades | Rs.50,000 | Rs.1,00,000 |
| 3 | 3 months consistent | Rs.2,00,000 | Rs.4,00,000 |
| 4 | 6 months consistent | Rs.5,00,000 | Rs.10,00,000 |
| 5 | 12+ months proven | Rs.10-25 lakh | Rs.20-50 lakh |

**Why slow scaling**: Premature capital scaling is the #1 reason algo traders lose money. A 60% win rate is not enough to scale aggressively because:
- Variance dominates short-term results
- Regime changes (bull/bear/sideways markets) require strategy adjustment
- System bugs only surface under real-money pressure

This system follows the proven principle: validate first, scale slowly, never risk what you cannot afford to lose entirely.

---

## Current Performance

### Live Trading Period: May 12 to May 15, 2026

**Total real money trades**: 18
**Profitable trades**: 6 (33%)
**Cumulative P&L**: -Rs.205 (across both profiles)

### Per-Profile Snapshot (May 15, 2026)

**Profile A (Trader 1, Rs.15K capital)**:
- 7 trades placed
- 0 winners, 7 losers
- Net P&L: -Rs.270
- Issue identified: trade limit not enforced (Bug 5), system overtraded
- Bug fixed for next session

**Profile B (Trader 2, Rs.10K capital)**:
- 5 trades placed
- 4 winners, 1 loser
- Net P&L: +Rs.94 (best day)
- Caught SAREGAMA winner (+Rs.105 single trade)

### Paper Trading (Rs.3,00,000 each)

**Paper Profile A**: 6 trades, 3W/3L, -Rs.1,732 (overtrading effect)
**Paper Profile B**: 6 trades, 1W/5L, -Rs.1,743 (large position size effect)

These losses on paper are expected during validation. Bug 5 fix prevents recurrence.

### Bugs Discovered and Fixed (Week 1)

The system found 6 bugs in production this week:

1. **Scanner saw only 169 of 500 stocks** at market open (volume filter timing) - FIXED
2. **NSE losers API endpoint returned errors** silently - FIXED  
3. **Limit orders failed on fast-moving stocks** in 10 seconds - FIXED
4. **Top performers cron not yet executed** (false alarm) - resolved
5. **Trade limit bypass via continuous scanning** - FIXED  
6. **Multi-EC2 visibility gap** for Profile B trades - FIXED

Each bug found and fixed validates the importance of careful monitoring during early phases.

---

## Operating Costs

### Cloud Infrastructure (Monthly)
- AWS EC2 t3.medium (2 instances): Rs.3,000
- AWS Bedrock API calls (Claude Sonnet 4.5): Rs.2,000-4,000
- S3 + CloudFront (dashboard hosting): Rs.200
- Data transfer: Rs.300

**Total infrastructure**: Rs.5,500-7,500/month

### Trading Costs (Per Trade)
- Brokerage (Dhan): Rs.20 flat
- STT, exchange fees, GST: ~Rs.15
- Stamp duty: ~Rs.5
- **Total per round-trip trade**: Rs.40

At 3 trades/day across 2 profiles: 6 round-trips/day × 21 trading days = 126 trades/month = Rs.5,040 in trading costs.

**Total monthly cost**: ~Rs.10,500-12,500

### Break-Even Analysis
At Rs.25,000 capital with Rs.12,000 monthly costs:
- Need to generate Rs.12,000 profit/month just to break even
- That's 48% monthly return on capital
- **System is unprofitable at current capital level due to fixed costs**

This is expected during Phase 1. Costs are largely fixed (Bedrock, EC2). At Phase 3 (Rs.4,00,000 capital), break-even drops to 3% monthly. At Phase 5 (Rs.20-50 lakh), trading profits dwarf operational costs.

---

## ROI Projections

### Conservative Scenario
**Assumption**: 55% win rate, average winner +3%, average loser -1.8%
**Expected daily edge**: 0.5% on deployed capital
**Trading days per year**: 250

| Phase | Capital | Daily P&L (avg) | Annual P&L | Annual ROI |
|-------|---------|-----------------|------------|------------|
| 1 | Rs.25,000 | Rs.125 | Rs.31,000 | 124% |
| 3 | Rs.4,00,000 | Rs.2,000 | Rs.5,00,000 | 125% |
| 5 | Rs.30,00,000 | Rs.15,000 | Rs.37,00,000 | 123% |

### Realistic Scenario  
**Assumption**: 50% win rate, average winner +2.5%, average loser -1.5%
**Expected daily edge**: 0.25% on deployed capital

| Phase | Capital | Annual ROI |
|-------|---------|------------|
| 1 | Rs.25,000 | 60% |
| 3 | Rs.4,00,000 | 60% |
| 5 | Rs.30,00,000 | 60% |

### Pessimistic Scenario
**Assumption**: Costs eat returns, win rate ~50% but slippage hurts
- **Phase 1 result**: Possible loss of Rs.10,000-30,000 per year (cost dominant)
- **Phase 3+**: Returns flat or slight positive

### Important Caveats
- **Past performance does not guarantee future returns**
- **Algo trading carries inherent market risk**
- **Regime changes can invalidate strategy**
- **Win rates change over time**

---

## Competitive Advantages

1. **Multi-factor scoring** beats single-indicator strategies (most retail uses MACD or RSI alone)

2. **AI ranking layer** captures patterns that pure rules miss while staying within mathematical guardrails

3. **Continuous scanning** every 15 minutes catches setups that fixed-time strategies miss

4. **Zero emotion** — system executes equally on Day 1 and Day 100, win or lose

5. **Full audit trail** — every decision logged with rationale, enables retrospective analysis

6. **Capital discipline** — scaling tied to proven results, not greed

7. **Multi-strategy roadmap** — intraday + F&O + swing + positional reduces single-strategy risk

---

## Risks and Mitigations

### Risk: AI provider outage (Bedrock down)
**Mitigation**: System has 60-second timeout, falls through gracefully. Could add fallback model.

### Risk: Broker API failure
**Mitigation**: Dhan API has 99.9% uptime SLA. Trades still protected by stop-loss orders placed simultaneously.

### Risk: Regime change (bull market becomes bear)
**Mitigation**: VIX-based gating reduces exposure in volatility. Long/short capability via SHORT signals (when SHORT operations enabled).

### Risk: Internet connectivity
**Mitigation**: AWS EC2 in Mumbai region with redundant network. Time-sync via chrony for TOTP authentication.

### Risk: Strategy degradation over time
**Mitigation**: Top movers comparison tracks scanner accuracy daily. Weekly review identifies if strategy needs adjustment.

### Risk: Single point of failure (one EC2 down)
**Mitigation**: Two-EC2 architecture with separate broker accounts. One EC2 failure does not stop other profile.

---

## Roadmap

### Near-term (next 30 days)
- Backtest framework (replay historical days through current logic)
- Telegram alerts for trade events  
- Dashboard "About" page for stakeholder visibility
- F&O strategy validation (move from paper to small live)

### Medium-term (60-90 days)
- News sentiment integration per stock
- Pre-market intelligence (SGX Nifty, FII flows)
- Onboarding website for new users to deploy own profiles
- Capital scaling to Phase 2 (Rs.50,000 each profile)

### Long-term (6-12 months)
- Swing trading module (2-10 day holds, delivery orders)
- Positional module (1-6 month holds with fundamentals)
- Mobile app for monitoring
- Multi-broker support (Zerodha, Angel One alongside Dhan)

---

## Investment Thesis

This is a research project with practical application. The core hypothesis: **systematic, multi-factor, AI-augmented stock selection can outperform random or single-indicator approaches over long timeframes.**

The hypothesis is being tested with real money in graduated phases. Capital deployed is constrained by what is acceptable to lose entirely if the hypothesis fails.

**Current state**: Validating system mechanics. Proving infrastructure works. Building data for backtesting.

**Next milestone**: 50 profitable trades to unlock Phase 2 capital scaling. Estimated 60-90 days at current pace.

**Investment if joining now**: This is bootstrapped personally. Not seeking external capital at Phase 1. Future phases may consider managed account model where additional capital is deployed under same system with profit-sharing.

---

## Conclusion

Intraday Trader is a working algorithmic trading system that has placed real money trades, identified and fixed real bugs, and built infrastructure for sustained operation. It is not a toy project, not a backtest, not vaporware. Real money has won and lost. Real lessons have been learned.

The path forward is methodical scaling tied to proven results. The infrastructure is built. The strategy is validated mechanically. Now we collect data and let edge prove itself.

The system is not magic. It is rules + data + AI + discipline. Properly executed, this combination can produce returns that beat passive index investing while requiring zero daily attention from the operator.
