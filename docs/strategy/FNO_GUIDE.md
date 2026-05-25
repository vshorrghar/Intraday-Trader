# F&O Guide — Everything You Need to Know

## What is F&O?

F&O = **Futures & Options.** We only use **Options.**

Think of options like **insurance policies for stocks.** Just like you buy car insurance (pay premium, get protection), options work the same way — but for stock prices.

**We are the insurance company.** We SELL options (insurance) and collect premium. If nothing bad happens (stock stays in range), we keep the premium. That's our profit.

---

## The Basics — Call and Put

### Call Option (CE)
- Buyer pays premium for the RIGHT to buy at a fixed price
- **We SELL calls** = we bet the price WON'T go above a certain level
- Example: NIFTY is at 24,000. We sell 24,500 CE for ₹50
  - If NIFTY stays below 24,500 → we keep ₹50 ✅
  - If NIFTY goes above 24,500 → we lose money ❌

### Put Option (PE)
- Buyer pays premium for the RIGHT to sell at a fixed price
- **We SELL puts** = we bet the price WON'T go below a certain level
- Example: NIFTY is at 24,000. We sell 23,500 PE for ₹45
  - If NIFTY stays above 23,500 → we keep ₹45 ✅
  - If NIFTY goes below 23,500 → we lose money ❌

### Key Insight
> When you SELL an option, time is your friend. Every minute that passes, the option loses value (theta decay). You sold it for ₹50, and by end of day it's worth ₹10. You pocket ₹40.

---

## Our Strategies (What the App Does)

### 1. Iron Condor (Our Main Strategy) ⭐

**What:** Sell BOTH a call AND a put, with protection on each side.

**Real Example:**
```
NIFTY is at 24,000

We do 4 things simultaneously:
  SELL 24,500 CE @ ₹50    (bet: NIFTY won't go above 24,500)
  BUY  24,700 CE @ ₹30    (protection if we're wrong)
  SELL 23,500 PE @ ₹45    (bet: NIFTY won't go below 23,500)
  BUY  23,300 PE @ ₹25    (protection if we're wrong)

Premium collected: (₹50 - ₹30) + (₹45 - ₹25) = ₹40
Per lot (75 units): ₹40 × 75 = ₹3,000

Profit zone: NIFTY stays between 23,500 and 24,500
Max profit: ₹3,000 (if NIFTY stays in range)
Max loss: ₹12,000 (if NIFTY breaks out of range)
```

**Visual:**
```
        Max Loss          Profit Zone          Max Loss
    ←─────────────|═══════════════════|─────────────→
              23,500    24,000     24,500
                ↑                      ↑
           Put side                Call side
```

**Why it works:** NIFTY moves 500+ points in a day only ~10% of the time. 90% of days, we keep the premium.

---

### 2. Bull Put Spread

**What:** Sell a put + buy a cheaper put below it. Bet that market won't fall.

```
NIFTY at 24,000

  SELL 23,800 PE @ ₹80    (collect premium)
  BUY  23,600 PE @ ₹50    (protection)

Net premium: ₹30 × 75 = ₹2,250
Max loss: (23,800 - 23,600 - 30) × 75 = ₹12,750
Profit if: NIFTY stays above 23,800
```

**When we use it:** Market is bullish (going up). We bet it won't fall.

---

### 3. Bear Call Spread

**What:** Sell a call + buy a cheaper call above it. Bet that market won't rise.

```
NIFTY at 24,000

  SELL 24,200 CE @ ₹70    (collect premium)
  BUY  24,400 CE @ ₹40    (protection)

Net premium: ₹30 × 75 = ₹2,250
Max loss: (24,400 - 24,200 - 30) × 75 = ₹12,750
Profit if: NIFTY stays below 24,200
```

**When we use it:** Market is bearish (going down). We bet it won't rise.

---

### 4. Short Strangle

**What:** Sell a call AND a put without protection. Higher risk, higher reward.

```
NIFTY at 24,000

  SELL 24,500 CE @ ₹50
  SELL 23,500 PE @ ₹45

Premium: ₹95 × 75 = ₹7,125
Max loss: UNLIMITED (that's why it's risky)
Profit if: NIFTY stays between 23,405 and 24,595
```

**When we use it:** Very confident market will stay in range. VIX is high (premiums are fat).

---

## The Greeks — What They Mean

Greeks tell you HOW your position behaves. Think of them as dashboard gauges in a car.

### Delta (Δ) — Direction Gauge
```
Delta = How much your position moves when NIFTY moves ₹1

Our target: Delta near 0 (market-neutral)

Delta +10 = You make ₹10 when NIFTY goes up ₹1
Delta -10 = You make ₹10 when NIFTY goes DOWN ₹1
Delta 0   = You don't care which way NIFTY goes ← THIS IS US

Why near 0? Because we're selling BOTH calls and puts.
We don't bet on direction. We bet on RANGE.
```

### Theta (Θ) — Time Decay (OUR BEST FRIEND) 💰
```
Theta = How much money you make PER DAY just from time passing

Our dashboard shows: Theta +434
This means: We earn ₹434 EVERY DAY just by holding our positions

Why? Options lose value over time. We sold them expensive,
they become cheaper, we profit from the difference.

Think of it like: You sold ice cream for ₹100.
Every hour it melts a little. By evening it's worth ₹20.
You keep ₹80. That's theta.
```

### Gamma (Γ) — Acceleration
```
Gamma = How fast Delta changes when NIFTY moves

Our target: Gamma near 0

High gamma = Your position can suddenly become very directional
Low gamma = Your position stays stable

We want low gamma = boring = predictable = profitable
```

### Vega (ν) — Volatility Sensitivity
```
Vega = How much your position changes when VIX (fear index) moves 1%

Our dashboard shows: Vega -40,579
Negative vega = We PROFIT when volatility DROPS

Why negative? We SOLD options. When fear drops:
- Options become cheaper
- We sold them expensive, now they're cheap
- We pocket the difference

VIX drops from 18 to 17 → We make ~₹40,579 × 1% = ₹406
```

### Summary Table

| Greek | Our Value | What We Want | Why |
|-------|-----------|-------------|-----|
| Delta | ~0 | Near zero | We don't bet on direction |
| Theta | +434 | Positive (high) | We earn money from time decay |
| Gamma | ~0 | Near zero | Position stays stable |
| Vega | -40,579 | Negative | We profit when fear drops |

---

## Key Terms on the Dashboard

### PCR (Put-Call Ratio)
```
PCR = Total Puts traded / Total Calls traded

PCR > 1.0 = More puts being bought = Market is fearful = GOOD for us
             (fearful market = high premiums = more money to collect)

PCR < 0.5 = More calls being bought = Market is greedy = Be careful
PCR 0.5-1.0 = Normal range
```

### Max Pain
```
Max Pain = The price where maximum option buyers LOSE money

If Max Pain is 24,000 and NIFTY is at 24,000:
  → Market tends to stay near Max Pain on expiry day
  → Good for our Iron Condors (we want NIFTY to stay in range)
```

### IV Percentile (IVP)
```
IVP = How expensive are options RIGHT NOW compared to last year?

IVP 80% = Options are more expensive than 80% of the past year
         → GREAT time to SELL options (we get fat premiums)

IVP 20% = Options are cheap
         → Bad time to sell (thin premiums, not worth the risk)

Our app only trades when IVP is favorable.
```

### Confluence Score
```
Confluence = How many signals agree that this trade is good

Score 0-100:
  60+ = Strong setup, multiple signals agree → TRADE ✅
  40-60 = Mixed signals → Maybe trade
  <40 = Weak setup → SKIP ❌

Our app requires confluence > 50 for hedged strategies.
```

### VRP (Volatility Risk Premium)
```
VRP = Implied Volatility - Realized Volatility

VRP > 0 = Options are OVERPRICED compared to actual market movement
         → Perfect for selling! We collect more than we should.

VRP < 0 = Options are UNDERPRICED
         → Don't sell, not worth the risk.

Think of it like: Insurance company charges ₹10,000/year for car insurance.
Actual average claim is ₹6,000/year. VRP = ₹4,000 (their profit margin).
We want to be that insurance company.
```

---

## How Our App Makes Money — Step by Step

### Morning (9:20 AM IST)
1. Fetch option chains for NIFTY, BANKNIFTY, FINNIFTY
2. Calculate Greeks, IVP, VRP, PCR, Max Pain
3. Send all data to Claude AI
4. Claude picks 2-5 strategies (Iron Condors, Spreads)
5. App places orders (paper mode = fake money)

### During the Day (9:20 AM - 3:15 PM)
6. Monitor every 30 seconds
7. Theta decay eats away at option premiums → our profit grows
8. If market moves too much → stop loss triggers → exit
9. If premium drops to near zero → target hit → exit with full profit

### Evening (3:15 PM)
10. Force exit everything
11. Calculate P&L
12. Update dashboard

### Where the Money Comes From
```
We sold options for ₹3,000 in the morning.
By 3:15 PM, those options are worth ₹1,500 (theta ate them).
We "buy back" at ₹1,500.
Profit: ₹3,000 - ₹1,500 = ₹1,500

On a good day: ₹2,000-3,000
On a bad day: -₹5,000 to -₹10,000 (but stop loss limits this)
Average: ₹1,000-2,000/day
```

---

## Risk Management

### What Can Go Wrong?

1. **Market crashes 500+ points** → Our put side gets hit
   - Protection: We bought cheaper puts (Iron Condor has a floor)
   - Max loss is capped at ₹10,000-15,000 per strategy

2. **Market rockets 500+ points** → Our call side gets hit
   - Same protection on the upside

3. **VIX spikes (sudden fear)** → All options become expensive
   - Our sold options become more expensive to buy back = loss
   - But our bought options also become expensive = partial offset

### Safety Features in Our App
- **Daily loss cap: ₹25,000** — if hit, stops trading for the day
- **Max delta exposure: 200** — won't take too much directional risk
- **Max vega exposure: 2,000** — limits volatility risk
- **Force exit at 3:15 PM** — no overnight risk
- **Confidence filter** — only trades setups with score ≥ 4/10
- **VIX threshold: 35** — won't trade in extreme panic

---

## Real Results (Paper Money)

| Date | Strategies | P&L | Win Rate |
|------|-----------|-----|----------|
| Apr 23 | 8 | +₹4,726 | 100% |
| Apr 27 | 2 | ₹0 | — |
| Apr 28 | 2 | +₹1,249 | 100% |
| Apr 29 | 3 | +₹2,600 | 100% |
| Apr 30 | 2 | +₹1,953 | 100% |
| **Total** | | **+₹10,528** | **100%** |

---

## Glossary

| Term | Meaning |
|------|---------|
| CE | Call Option (bet price goes UP) |
| PE | Put Option (bet price goes DOWN) |
| ATM | At The Money (strike = current price) |
| OTM | Out of The Money (strike far from current price) |
| ITM | In The Money (strike past current price) |
| Premium | Price of the option (what we collect when selling) |
| Strike | The fixed price in the option contract |
| Expiry | When the option expires (weekly for index options) |
| Lot Size | Minimum quantity (NIFTY = 75, BANKNIFTY = 30) |
| Margin | Money broker blocks as guarantee |
| Spot | Current market price of the index |
| IV | Implied Volatility (how scared the market is) |
| VIX | India VIX (fear index, higher = more fear) |
