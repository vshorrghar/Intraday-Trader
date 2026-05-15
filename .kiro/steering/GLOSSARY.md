# GLOSSARY — Technical Terms Used In This Project

Quick reference for trading and technical jargon. Cross-referenced from BUSINESS_DOC.md and TECHNICAL_DOC.md.

---

## TRADING TERMS

### VIX (India VIX)
**What**: Volatility index measuring expected 30-day NIFTY 50 volatility, calculated by NSE.
**Range**: Typically 10-30. Higher = more uncertainty.
**Why we use**: Above 25 means extreme fear/uncertainty. We skip trading when VIX > 25.
**Our gates**: VIX > 25 = SKIP entire session. VIX > 22 = REDUCE to 1 trade max. VIX <= 22 = normal.

### R:R (Risk-to-Reward Ratio)
**What**: Reward divided by risk in a trade.
**Formula (LONG)**: (target - entry) / (entry - stop_loss)
**Formula (SHORT)**: (entry - target) / (stop_loss - entry)
**Example**: Buy at 100, stop at 98 (risk 2), target at 106 (reward 6) = R:R 3.0
**Our minimum**: 2.0 (we reject any trade where reward isn't at least 2x risk)
**Why important**: At R:R 2.0, we can win only 33% of trades and still break even.

### LTP (Last Traded Price)
**What**: Most recent price at which a stock traded.
**Why we use**: Reference point for current market price. Updated every few seconds.

### LIMIT Order
**What**: Order to buy/sell at a specific price OR BETTER.
**Behavior**: BUY at Rs.100 limit means "buy at Rs.100 or lower, never higher".
**Risk**: May not fill if price moves away.

### MARKET Order
**What**: Order to buy/sell at the current market price, immediately.
**Behavior**: Always fills (if liquidity exists), but at whatever price the market gives.
**Risk**: Slippage on fast-moving stocks.

### Stop Loss (SL)
**What**: A protective sell order placed below entry (for long trades).
**Trigger**: When price drops to SL level, automatic sell to limit loss.
**Our rule**: Every trade has SL placed simultaneously with entry. No exceptions.

### Trailing Stop Loss
**What**: SL that moves up as price rises, locking in profits.
**Our rule**: Activates after 0.5% profit. SL moves up to entry price (breakeven).

### Force Exit
**What**: Manually closing all positions before market close.
**Our time**: 15:15 IST (15 min before market close).
**Why**: No overnight risk on intraday positions.

### Force Exit Time
**What**: 3:15 PM IST. We close all intraday positions automatically by then.

### MIS (Margin Intraday Square-off)
**What**: Order type for same-day delivery. Position auto-closes at end of day.
**Use**: Our intraday strategy only.

### CNC (Cash and Carry)
**What**: Order type for delivery (you actually own the shares).
**Use**: Swing and positional strategies.

### NRML (Normal)
**What**: Order type for futures/options that you can carry overnight.
**Use**: F&O module.

### Tick Size
**What**: Smallest price increment. NSE = Rs.0.05.
**Our handling**: All order prices rounded to nearest Rs.0.05.

### NSE Nifty 500
**What**: Index of top 500 NSE-listed stocks by market cap.
**Our universe**: We only trade stocks in this list (not penny stocks, not micro-caps).

### Sector
**What**: Industry classification (e.g., NIFTY IT, NIFTY BANK, NIFTY METAL).
**Our usage**: Pick stocks in top 5 performing sectors. Avoid worst sectors for longs.

### Breakout
**What**: Stock breaking above resistance (recent highs).
**Setup type**: Used in intraday and swing.

### Reversal
**What**: Stock reversing direction at key support/resistance.
**Setup type**: Higher confidence required.

### Pullback
**What**: Brief retracement before continuing trend.
**Setup type**: "Buy the dip" in uptrending stocks.

### Day High
**What**: Highest price stock traded today.
**Our usage**: We prefer stocks near day high (showing strength).

### 52-Week High
**What**: Highest price in past 12 months.
**Our usage**: Swing module looks for breakouts above 52-week high.

---

## OPTIONS / F&O TERMS

### IV (Implied Volatility)
**What**: Market's expectation of future volatility, derived from option prices.
**Range**: Higher IV = more expensive options.

### IV Percentile (IVP)
**What**: Where current IV ranks vs past year (0-100).
**Why we use**: IVP > 70 = sell premium. IVP < 30 = buy premium.

### Iron Condor
**What**: Sell OTM call AND put, buy further OTM call AND put for protection.
**When**: Sideways market, high IV (above 70 percentile).
**Profit**: From time decay and IV decrease.

### Short Straddle
**What**: Sell ATM call AND put simultaneously.
**Profit if**: Stock stays near strike at expiry.
**Risk**: Unlimited if stock moves big.

### Bull Put Spread
**What**: Sell higher strike put, buy lower strike put.
**View**: Bullish or neutral.

### Bear Call Spread
**What**: Sell lower strike call, buy higher strike call.
**View**: Bearish or neutral.

### Strike Price
**What**: Price at which option can be exercised.
**Example**: NIFTY 23000 CE = call option at strike 23000.

### CE (Call European)
**What**: Call option (right to buy at strike).

### PE (Put European)
**What**: Put option (right to sell at strike).

### ATM (At The Money)
**What**: Strike price at or near current market price.
**Example**: NIFTY at 23080, ATM strike = 23100 (nearest strike to spot).

### OTM (Out of The Money)
**What**: Strike below current price for puts, above for calls.

### ITM (In The Money)
**What**: Strike below current price for calls, above for puts.

### DTE (Days To Expiry)
**What**: Days until the option expires.
**Our rule**: Avoid options with < 2 DTE (theta accelerates).

### OI (Open Interest)
**What**: Total outstanding open contracts.
**Why important**: Higher OI = more liquidity, easier exits.

### OI Velocity
**What**: Rate of change of OI.
**Why we use**: Rapid OI buildup signals direction conviction.

### GEX (Gamma Exposure)
**What**: Total gamma exposure of dealers, indicates support/resistance levels.

### VRP (Variance Risk Premium)
**What**: Difference between implied and realized volatility.
**Use**: Positive VRP = options overpriced, sell them.

### Confluence Score
**What**: Combined signal score from multiple indicators (IV, OI, GEX, VRP).
**Our gates**:
- > 75 = naked selling allowed (high conviction)
- > 60 = directional buy allowed
- > 20 = hedged strategy allowed (Iron Condor, etc.)

### Theta
**What**: Daily time decay of option value.
**Effect**: Sellers profit from theta. Buyers lose to it.

### Vega
**What**: Option's sensitivity to IV changes.

### Delta
**What**: Option's sensitivity to underlying price (0.5 = ATM call).

### Expiry Day
**What**: The day options/futures contract expires.
**Our rule**: Only IRON_CONDOR, SHORT_STRADDLE, or DIRECTIONAL strategies allowed on expiry.

---

## TECHNICAL / INFRASTRUCTURE TERMS

### Bedrock
**What**: AWS service for accessing AI models (Claude, etc.).
**We use**: Claude Sonnet 4.5 via Bedrock for stock ranking.

### Claude Sonnet 4.5
**What**: AI model from Anthropic. Released 2025.
**Our use**: Final ranking of pre-filtered candidates with rationale.

### TOTP (Time-Based One-Time Password)
**What**: 6-digit code generated by authenticator app, changes every 30 seconds.
**Our use**: Required for Dhan broker login.
**Critical**: EC2 clock must be within 30 seconds of real time.

### chrony
**What**: Linux service for keeping system clock synchronized via NTP.
**Why critical**: TOTP depends on time accuracy.

### EC2 (Elastic Compute Cloud)
**What**: AWS virtual server.
**Our setup**: 2 instances of t3.medium in Mumbai region.

### S3 (Simple Storage Service)
**What**: AWS object storage.
**Our use**: Hosting dashboard files, syncing neha-live DB between EC2s.

### CloudFront
**What**: AWS content delivery network.
**Our use**: Caching dashboard for fast access via HTTPS.

### IAM (Identity and Access Management)
**What**: AWS access control.
**Our profile**: vishal-admin (used for all project operations).

### IST (Indian Standard Time)
**What**: UTC+5:30. Market hours: 9:15 AM - 3:30 PM IST.

### UTC (Coordinated Universal Time)
**What**: Reference time. EC2 cron schedules in UTC, market in IST.
**Conversion**: 9:30 AM IST = 4:00 UTC.

### SSM (Systems Manager Session Manager)
**What**: AWS service for browser-based shell access to EC2.
**Our use**: SSH-free access to both EC2 instances.

### SQLite
**What**: File-based database (no server needed).
**Our use**: Trade records, audit log, daily summaries (one DB per profile).

### YAML
**What**: Configuration file format (human-readable).
**Our use**: Profile configs (capital limits, thresholds).

### Cron
**What**: Linux scheduler for recurring tasks.
**Our schedules**: Continuous scanning every 15 min, EOD reports, DB syncs.

### Dhan API
**What**: REST API for placing orders on NSE through Dhan broker.
**Endpoint**: api.dhan.co/v2

### NSE API
**What**: Public APIs from National Stock Exchange.
**Our use**: Live quotes, index data, top gainers/losers.

### Scanner
**What**: Code that scores all stocks and returns top candidates.
**Output**: 30 candidates (15 long, 15 short).

### Selector
**What**: Code that filters scanner output, calls LLM, validates AI picks.
**Output**: Final 1-5 trades per scan cycle.

### Executor
**What**: Code that places actual orders with broker.
**Output**: Confirmed trade IDs and DB records.

### Monitor
**What**: Code that tracks open positions every 5 minutes.
**Decisions**: Trail SL, partial book, force exit.

### Pre-filter
**What**: Mathematical rules that cut 30 candidates to 20.
**Not LLM**: Pure Python.

### Audit Log
**What**: Record of every system event (order placed, SL adjusted, etc.).
**Purpose**: Forensic analysis if something goes wrong.

### Rule 20.7
**What**: Project rule that AI must remind user to git pull on NEW EC2 after every push from OLD EC2.
**Why**: Prevents stale code on NEW EC2.

---

## DATA / METRICS TERMS

### Win Rate
**What**: Percentage of trades that closed profitable.
**Our target**: >55% sustained.
**Example**: 6 winners out of 10 trades = 60% win rate.

### Drawdown
**What**: Peak-to-trough decline in capital.
**Example**: Capital was Rs.15,000, dropped to Rs.13,500 = 10% drawdown.
**Our limit**: Daily loss limit Rs.900 = 6% drawdown cap.

### Slippage
**What**: Difference between expected fill price and actual fill price.
**Example**: Wanted Rs.100, filled at Rs.100.30 = 0.3% slippage.

### Charges
**What**: All costs of trading: brokerage, STT, exchange fees, GST, stamp duty.
**Our typical**: Rs.40 per round trip.

### Round Trip
**What**: One complete trade (BUY + SELL or SELL + BUY).

### Net P&L
**What**: Profit/loss after all charges deducted.
**Always use**: Net P&L for performance evaluation, never gross.

### Capital Deployed
**What**: Total money in active positions.
**Our limit**: Per-profile daily_capital_limit.

### Per-Trade Max
**What**: Maximum capital in any single position.
**Our limit**: Rs.4,000-4,500 per live trade.

---

## DAILY OPERATIONS TERMS

### Pre-Market
**What**: 9:00-9:15 AM IST. We don't trade here.

### Opening Auction
**What**: 9:00-9:15 AM IST. Price discovery.

### Continuous Trading
**What**: 9:15 AM - 3:30 PM IST. Normal trading.

### Closing Auction
**What**: 3:30-3:40 PM IST. We don't participate.

### EOD (End of Day)
**What**: After 3:30 PM IST.

### Top Performers Capture
**What**: Daily cron at 3:35 PM IST that captures top 20 NSE movers and compares to our picks.
**Purpose**: Track scanner accuracy.

### War Room
**What**: Dashboard tab showing scanner accuracy and missed opportunities.

### EOD Summary
**What**: Comprehensive end-of-day report.
**Command**: bash scripts/eod_summary.sh

### Live Status
**What**: Mid-day snapshot of all profiles.
**Command**: bash scripts/live_status.sh

---

## CODE / DEVELOPMENT TERMS

### Heredoc
**What**: Bash syntax for embedding multi-line strings.
**Our use**: Editing Python files via SSH (no nano/vim).

### Git Flow
**What**: Our rule: only EC2 commits + pushes. Mac is read-only.
**Why**: Mac is corporate machine, AWS IT monitors git pushes.

### Profile YAML
**What**: Configuration file per trading account.
**Location**: config/profiles/.yaml
**Note**: Gitignored. Manually synced between EC2s.

### Steering Docs
**What**: Authoritative project documentation.
**Files**: RULES.md, STATE.md, HISTORY.md, STRATEGY.md, LEARNING.md, BUSINESS_DOC.md, TECHNICAL_DOC.md, GLOSSARY.md
**Location**: .kiro/steering/

### Bug 5
**What**: Daily trade limit not enforced during continuous scanning.
**Fix**: 2026-05-15. Risk_Manager._restore_daily_state now counts OPEN positions.

### Bug 6
**What**: neha-live data only on NEW EC2, invisible from OLD EC2.
**Fix**: 2026-05-15. NEW EC2 syncs DB to S3, OLD EC2 auto-pulls.
