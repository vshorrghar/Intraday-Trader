# EDGE.md — Why This System Should Make Money

**Purpose:** Document the theoretical reasons each strategy SHOULD be profitable in Indian equity markets, given that millions of retail traders run similar logic and SEBI data shows ~90% lose money net of costs.

**Update rule:** Annually, or when win rate diverges materially from theoretical edge.

**Reading order in steering:** RULES.md → STATE.md → EDGE.md → STRATEGY.md → WIN_RATE_TRACKING.md

**Author:** Vishal (founder, principal trader)
**Last updated:** 2026-05-19

---

## DOCUMENT PURPOSE

Before any strategy in this system risks real capital, this document must state in clear English: WHY this strategy should make money, given competition from millions of other retail traders.

If a strategy cannot be defended in this document with a coherent edge statement backed by validated data, it should NOT be deployed with real capital.

---

## THE FUNDAMENTAL TRUTH

SEBI data 2022-2024: ~90% of individual intraday equity/F&O traders lose money net of costs. This is not curve-fit. This is actual client-level data.

Why do most lose? Three reasons:
1. **No edge** — they trade based on tips, news, gut feel
2. **No discipline** — emotional decisions during volatility
3. **No capital management** — overconfidence after wins, revenge trades after losses

Our system addresses #2 (discipline via rules) and #3 (capital management via risk_manager). This document addresses #1: do we have edge?

If we don't, no amount of code quality saves us.

---

## STRATEGY 1: INTRADAY (RS-First v3 + LLM)

### One-Sentence Thesis

We capture 1-2% intraday momentum continuation when stocks break key levels on volume with sector confirmation in the first 90 minutes of trading, before retail FOMO drives the move toward exhaustion.

### What Inefficiency Are We Exploiting?

Indian retail dominates intraday volume (60-70% per NSE data). Retail behavior is predictable:

- **9:15-9:30 AM:** Volatility from overnight order unwinding. Retail panicking on gaps.
- **9:30-10:30 AM:** Smart money positioning. Retail still digesting news.
- **10:30-11:30 AM:** FOMO buying as breakouts confirm.
- **11:30-2:30 PM:** Lunch lull. Retail attention drops.
- **2:30-3:15 PM:** Exit pressure builds. Stops cascade.

Our scanner enters during the SMART-MONEY window (9:30-10:30 AM, time multiplier 1.5x in scoring). We exit before the FOMO exhaustion via force exit at 15:15 IST.

This means we sell INTO retail FOMO buying. We don't need stocks to keep moving up — we just need them to move enough to capture our 4% target before retail late-comers exhaust the move.

### What's Our Specific Edge vs Other Retail?

**1. Speed advantage**
- Scanner processes Nifty 500 in <3 minutes
- Retail can manually monitor 10-20 stocks max
- We see opportunities 30-60 minutes before manual scans

**2. Discipline advantage**
- Hard SL at entry (no "let me wait, it'll come back")
- Force exit at 15:15 IST (no holding losers overnight in MIS)
- 1% capital risk per trade (no all-in revenge trades)
- LLM provides rationale, but PYTHON enforces R:R minimum

**3. Multi-signal ranking**
- 6 signals + 3 penalties (RS-First v3)
- Most retail uses 1-2 indicators (RSI, MACD)
- Confidence scoring prevents marginal entries

**4. Bedrock LLM ranking advantage**
- Evaluates 20 candidates simultaneously
- Cross-references sector, news, technicals in <5 seconds
- Most retail picks 1-2 stocks based on gut

### When Does This Edge WORK?

Trending markets (Nifty above 50-DMA, ADX > 20) — momentum continues
VIX 13-20 range (normal volatility, predictable retail patterns)
First 90 minutes of session (best risk/reward window per time multiplier)
Sector leaders in green sectors (rotation tailwind compounds entry)
High-conviction setups (confidence 8+, multi-signal alignment)
Regular trading days (no expiry, no major events)
Liquid Nifty 500 stocks (Rs.5+ Cr daily turnover for clean fills)

### When Does This Edge FAIL?

Range-bound choppy markets (whipsaw eats stops; retail correctly waits)
VIX above 22 (wider stops, slower fills, fear dominates)
Last 90 minutes (force exit fights against late-day moves)
F&O expiry days (Thursday volatility distorts equity moves)
Earnings windows (5 days before/after — IV makes options moves dominate)
Black swan events (war, election shocks — system has no edge in panic)
Range-bound sector days (rotation matters; breakouts fail without sector backing)
Low volatility days (VIX < 12, ranges too tight for 4% targets)

### What Could KILL This Edge in Future?

1. **More retail using algos:** Streak, AlgoTest, Tradetron adoption growing. Our speed advantage shrinks. **Mitigation:** Move to swing/positional (less crowded).

2. **SEBI rule changes:** SEBI tightening intraday rules. Margin requirements may increase. **Mitigation:** Diversify to CNC delivery strategies.

3. **Bedrock latency:** Already a problem at 9:26 AM market open (was 25-min hang). **Mitigation:** Multiple LLM providers, direct Anthropic API fallback.

4. **Brokerage cost increases:** Currently Rs.20 flat. If raised to Rs.50-100, edge halves. **Mitigation:** Larger trade sizes (capital scaling) reduces per-trade %.

5. **Sector rotation models becoming common:** RS-First scoring is institutionally well-known. Retail catching up. **Mitigation:** Add proprietary signals (news sentiment, options flow).

### Required Win Rate To Be Profitable (Math, Not Feelings)

Per current setup (vishal-live):
- Per trade max: Rs.4,500
- Charges round-trip: ~Rs.50 (1.1% of trade value)
- Average target: 4% gross = 2.9% net
- Average stop: -1.8% gross = -2.9% net
- R:R achieved: ~1:1 (after charges, both win and loss are similar magnitude)

Win rate breakeven calculation:
- R:R 2.0 with zero charges: 33% breakeven
- With actual charges (1.1% drag): 47% breakeven
- With slippage (0.3-0.5% extra): 50-55% breakeven
- **Realistic breakeven on real money: 55%**

Target win rate for profitability: **60%**
Target win rate for "money machine": **65%+**

**Honest assessment:** 60% achievable with discipline. 65% requires regime adaptation we don't yet have. Anyone claiming >70% intraday win rate on Indian equities is either lying, curve-fit, or using risk asymmetry to fake the number.

### Current Win Rate Status

[FILL_IN — extract from intraday_trades table for each profile]

- vishal-live (real money May 12-19): 5 trades, 0 wins / 5 losses = 0%
  *Statistically meaningless — sample too small*
- vishal paper (April-May): [FILL_IN] trades, [FILL_IN]% win rate
- neha paper (April-May): [FILL_IN] trades, [FILL_IN]% win rate

**Statistical significance threshold:** 50+ trades minimum for any meaningful read. Currently below threshold for real money.

### Validation Plan Before Scaling Capital

1. Reach 50+ real-money intraday trades (current: 5)
2. Verify 55%+ win rate over rolling 30-day window
3. Verify R:R achieved >= 1.5x (not just 2:1 target — actual)
4. Verify max drawdown < 15% from any peak
5. Verify Bug 1 fix holds for 30+ trading days (no new bugs of similar class)
6. Verify breakeven across at least 3 different VIX regimes

Only after all 6: scale Rs.15K → Rs.30K. Not before.

### Risks This Edge Could Be Wrong About

I am honest that this edge thesis could be incorrect:

1. **Retail FOMO timing may not match my model:**
   - Retail might buy EARLY (9:15-9:30) and sell late, not vice versa.
   - Our 9:30+ entries would then be buying FROM smart money TO dumb money.
   - This would reverse our intended edge.
   - **Validation needed:** Compare entry-time vs exit-time win rates.

2. **LLM advantage may be illusory:**
   - Bedrock has same data as everyone else.
   - LLM rationale may be sophisticated storytelling, not edge.
   - **Validation needed:** Compare scanner+rules vs scanner+rules+LLM win rates.

3. **Sector rotation might be lagging:**
   - By time scanner sees sector leadership, move is half done.
   - Real edge would require ANTICIPATING rotation, not following.
   - **Validation needed:** Backtest sector rotation entry timing.

4. **Charges may be higher than modeled:**
   - Slippage on Rs.4500 trades real-world likely 0.3-0.5% extra.
   - Adjusted breakeven: 55-60%, not 50%.
   - **Validation needed:** Audit actual fill prices vs intended.

These are honest possibilities. Win rate validation will reveal which is true.

---

## STRATEGY 2: F&O (Multi-Strategy Options)

### Status: BROKEN AS OF MAY 2026

### Edge Thesis (Theoretical)

We sell premium when IV is high (IVP > 70) and buy premium when IV is low. We use confluence scoring (IV percentile + OI velocity + GEX + VRP) to identify when option pricing is irrational.

### Honest Truth

This module has NEVER produced reliable P&L data due to Bug T (3 resurrections):
- May 15: First Bug T fix
- May 17: Sub-bugs T-1, T-2, T-3
- May 19: BANKNIFTY P&L showing Rs.92,025 (max possible was Rs.216)

**We literally don't know if we have edge here.** All paper P&L data is contaminated.

### What's Probably Wrong

When the same bug class returns 3 times, the architecture is wrong, not the code. Likely root causes:
- Caching layer issue (stale option chain prices)
- Symbol normalization issue (NIFTY vs NIFTY24MAYFUT vs etc.)
- Integer vs string ID confusion
- Greek calculation depending on stale spot price

### Decision Pending (See DECISIONS.md)

Three options:
A. Rewrite F&O from scratch with different architecture (3 weeks)
B. Continue debugging Bug T (4th attempt, low confidence)
C. Kill F&O module entirely, focus on equity strategies

### Edge Status: NOT VALIDATED

Currently this strategy DOES NOT MEET edge threshold to deploy capital. No real money will be deployed in F&O until decision made and statistical validation completed (minimum 30 days clean MTM data).

---

## STRATEGY 3: SWING (20-DMA Pullback Strategy)

### Status: TO BE BUILT (Prompt 2B in progress May 19 night)

### One-Sentence Thesis

We buy uptrending defensive sector stocks when they pullback to 20-DMA with RSI(2) oversold, capturing 5-10% bounces over 5-15 day windows before broader retail recognizes the setup.

### What Inefficiency Are We Exploiting?

Indian retail focuses on:
- Breakout trades (chasing strength) — crowded space
- Penny stock momentum — degenerate gambling
- F&O speculation — most lose money
- Intraday scalping — charges destroy

**Defensive sector pullbacks (pharma, FMCG, healthcare grinders) are BORING.** Most retail won't trade them. Reasons:
- Low volatility = low excitement
- Slow grinds = need patience (most retail don't have)
- Not popular on YouTube/Twitter
- Don't move 10% in a day

This creates persistent inefficiency. Smart institutional money buys these on pullbacks. Smart systematic retail (us) can ride alongside if patient enough.

### What's Our Specific Edge?

**1. Patience advantage**
- 5-15 day hold tolerance
- 99% of intraday traders won't compete here
- Daily monitoring (not 5-min) reduces emotional reactions

**2. Defensive sector expertise (built over time):**
- Pharma earnings cycles: predictable
- FMCG seasonality: festival quarters, monsoon impact
- Healthcare consolidation patterns

**3. Capital deployment efficiency:**
- CNC delivery (not MIS), no margin pressure
- Lower charges (0.4-0.6% round-trip vs 1.1% intraday)
- More room for thesis to play out

**4. Lower competition zone:**
- Quant funds dominate momentum
- Active funds dominate large-cap value
- Defensive sector pullbacks are under-allocated

### When This Edge WORKS

Markets above 200-DMA (long-term bull regime)
VIX 13-20 (normal, not panic)
Defensive sector outperformance vs Nifty (rotation tailwind)
Stock above 50-DMA AND 200-DMA (uptrend confirmed)
RSI(2) below 10 at 20-DMA (oversold + level confluence)
No earnings within 5 days (event risk avoided)
Bullish reversal candle pattern (entry confirmation)

### When This Edge FAILS

Bear markets (Nifty below 200-DMA — defensive falls less but still falls)
Pure trending markets (no pullbacks to 20-DMA, miss entries)
Sector-specific news shock (pharma price control, FMCG taxation)
Stock breaks 50-DMA (failed pullback, now downtrend)
Earnings surprise (8-15% gap can overwhelm position size)
Macro events (RBI policy, Budget) — defensive responds to liquidity changes

### Required Win Rate To Be Profitable

Per planned setup (vishal-live, paper for first 4 weeks):
- Per trade max: Rs.5,000 (1% of Rs.5L target)
- Charges round-trip CNC: ~Rs.30 (0.6%)
- Average target: 7% gross = 6.4% net
- Average stop: -5% gross = -5.6% net
- R:R: 1:1.4 (target 7% / stop 5% = 1.4)

Win rate breakeven:
- R:R 1.4 with zero charges: 42% breakeven
- With actual charges: 45% breakeven
- With slippage: 47% breakeven

Target win rate: **55-60%**
Investors Way framework claims 55-65% on similar setups historically.

### Risks This Edge Could Be Wrong About

1. **Defensive sectors crowded by mutual funds:**
   - SIPs heavily allocated to FMCG, Pharma
   - Smart money already priced in
   - Our 'edge' may just be chasing mutual fund flows
   - **Validation:** Compare returns vs Nifty Pharma index over hold period

2. **20-DMA pullback may be overused:**
   - Available in every charting platform
   - May have been arbitraged away
   - **Validation:** Backtest verify edge persists over 5-year window

3. **Capital efficiency may be poor:**
   - 5-15 day holds = 25 trades/year per Rs.50K capital
   - Even at 60% win rate: limited absolute returns
   - May not scale to Rs.50K/month income easily
   - **Validation:** Calculate annualized return at expected win rate

---

## STRATEGY 4: POSITIONAL (TO BE BUILT)

[Skip for now — building swing first. Will document edge before any positional development.]

---

## EDGE COMPARISON TABLE

| Strategy | Theoretical Edge | Validation Status | Real Money? | Win Rate |
|----------|------------------|-------------------|-------------|----------|
| Intraday | Medium (50-60%) | Unvalidated (5 trades) | YES Rs.15K | 0% (sample too small) |
| F&O | Unknown (broken) | NA | NO | NA |
| Swing | Medium-High (potential) | Not started | NO | NA |
| Positional | Unknown | Not built | NO | NA |

**Total real money exposure today: Rs.15K (intraday only).**
**Strategies with statistically validated edge: 0 of 4.**

This means today, all real money exposure is on UNVALIDATED edge. This is the highest priority risk to address.

---

## OVERARCHING META-EDGE

Beyond individual strategies, our system has these META-EDGES vs typical retail:

1. **Multi-strategy diversification** (when all built)
2. **Multi-account risk distribution** (vishal, neha, vishal-live, neha-live)
3. **Documentation discipline** (this document, RULES, STATE, etc.)
4. **AI-augmented decisions with rule guardrails** (LLM ranks, Python decides)
5. **Capital scaling discipline** (proof-gated, not emotion-driven)
6. **Bug-fix transparency** (HISTORY.md, BUGS_AND_FIXES.md)
7. **Real-time broker reconciliation** (Rs.499/mo Dhan Data API)
8. **Manual override mechanisms** (pause/resume per profile)

These META-EDGES compound over time. Even if individual strategies fail to validate, the institutional framework creates lasting value vs typical retail traders.

---

## ANNUAL REVIEW

This document must be re-read and updated annually, or when any of:
- Win rate diverges 10+ points from theoretical
- Major regime shift (rupee crisis, SEBI rule change)
- New module added to system
- Strategy capital deployment doubles or halves

Last review: 2026-05-19 (initial draft)
Next review due: 2027-05-19

---

## SIGNATURES

This document represents my honest assessment of WHY this trading system should make money. I commit to:
- Updating it when reality diverges from thesis
- Reading it before any major capital scaling decision
- Sharing with any future partner / IA / RA / fund manager evaluating strategies
- Killing any strategy whose edge thesis fails statistical validation

If a strategy in this system has been deployed for 50+ trades and the win rate is 10+ points below theoretical breakeven, that strategy WILL be paused for review per Rule 25 (Swing Pre-Live Gate) precedent.

Vishal | 2026-05-19 | Founder, Principal Trader
