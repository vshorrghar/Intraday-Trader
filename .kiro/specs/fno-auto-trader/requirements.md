# Requirements Document: F&O Auto-Trader

## Introduction

The F&O Auto-Trader is an automatic Futures & Options trading module for the Wealth Builder Pro application. It extends the existing intraday equity auto-trader to support Nifty, BankNifty, and FinNifty index options and futures trading. The module reuses the existing broker abstraction layer (Dhan/Zerodha), OAuth authentication infrastructure, config system, and database layer. It starts in a mandatory dry-run/paper trading mode using simulated capital before transitioning to live trading. All F&O trading activity is visible on the existing dashboard as a new "F&O Live" tab alongside the current "Intraday Live" tab.

Key differences from the existing equity intraday module: F&O instruments have strike prices, expiry dates, option types (CE/PE), Greeks (delta, gamma, theta, vega), weekly expiry dynamics, SPAN + exposure margin requirements, and multi-leg strategy support (straddles, strangles, spreads, iron condors). The risk profile is fundamentally different — naked option selling can result in losses exceeding deployed capital.

## Glossary

- **FnO_Config**: The configuration dataclass for the F&O auto-trader, loaded from the `fno` section of `config/config.yaml`
- **FnO_Strategy_Engine**: The module that selects and constructs F&O trading strategies based on market conditions and LLM analysis
- **FnO_Order_Executor**: The module that places, modifies, and cancels F&O orders through the BrokerClient ABC
- **FnO_Position_Monitor**: The module that tracks open F&O positions, manages Greeks exposure, and enforces exit rules
- **FnO_Risk_Manager**: The module that enforces margin requirements, position limits, Greeks thresholds, and daily loss caps for F&O trading
- **FnO_Reporter**: The module that generates end-of-day performance reports and writes dashboard JSON for F&O trades
- **FnO_Greeks_Calculator**: The module that computes option Greeks (delta, gamma, theta, vega) using the Black-Scholes model
- **Option_Chain_Fetcher**: The module that retrieves live option chain data (strikes, premiums, OI, volume) from NSE/broker APIs
- **BrokerClient**: The existing abstract base class in `intraday/broker_base.py` that provides a broker-agnostic interface for order placement, position fetching, and margin queries
- **Strategy_Leg**: A single leg of a multi-leg F&O strategy, containing instrument details, transaction type, quantity, and price
- **Paper_Trade_Engine**: The simulation engine that executes trades using virtual capital without placing real broker orders
- **SPAN_Margin**: Standard Portfolio Analysis of Risk margin — the initial margin required by the exchange for F&O positions
- **Exposure_Margin**: Additional margin over SPAN required by the exchange as a safety buffer
- **Greeks**: Option sensitivity measures — delta (price sensitivity), gamma (delta sensitivity), theta (time decay), vega (volatility sensitivity)
- **IV**: Implied Volatility — the market's expectation of future price movement, derived from option premiums
- **OI**: Open Interest — the total number of outstanding derivative contracts that have not been settled
- **ATM**: At-The-Money — an option whose strike price is closest to the current underlying price
- **OTM**: Out-of-The-Money — a call option with strike above spot, or a put option with strike below spot
- **ITM**: In-The-Money — a call option with strike below spot, or a put option with strike above spot
- **Lot_Size**: The fixed number of units per contract for an index derivative (e.g., Nifty lot size is 25)
- **Expiry**: The date on which a derivative contract expires and must be settled
- **Quant_Edge_Engine**: The quantitative analysis module that computes institutional-grade signals — IV Percentile, OI Change Velocity, IV Skew, Gamma Exposure (GEX), Volatility Risk Premium (VRP), and Confluence Score — to provide measurable statistical edge for every trade
- **IV Percentile (IVP)**: The percentage of trading days in the last year where IV was lower than today's IV. IVP > 70 means options are expensive (sell), IVP < 30 means options are cheap (buy)
- **OI Change Velocity**: The rate of Open Interest change at each strike over a rolling 30-minute window, used to detect real-time institutional positioning
- **IV Skew**: The difference in Implied Volatility between OTM Puts and OTM Calls, indicating the market's directional fear/greed bias
- **GEX (Gamma Exposure)**: The aggregate gamma exposure of market makers across all strikes, determining whether the market will mean-revert (positive GEX) or trend (negative GEX)
- **VRP (Volatility Risk Premium)**: The gap between Implied Volatility and Realized Volatility — the core edge in option selling, positive ~85% of the time
- **Confluence Score**: A weighted composite score (0-100) combining all quantitative signals, requiring minimum thresholds before any trade is executed
- **RV (Realized Volatility)**: The actual historical volatility of the underlying, computed as the annualized standard deviation of daily log returns
- **Max Pain**: The strike price where the maximum number of option contracts expire worthless, acting as a gravitational pull for the index near expiry
- **PCR (Put-Call Ratio)**: Total Put OI divided by total Call OI — PCR > 1.2 is bullish (strong put writing = support), PCR < 0.8 is bearish

## Requirements

### Requirement 1: F&O Configuration

**User Story:** As a trader, I want to configure F&O trading parameters separately from equity intraday trading, so that I can control F&O-specific risk limits, strategy preferences, and capital allocation independently.

#### Acceptance Criteria

1. THE FnO_Config SHALL load configuration from the `fno` section of `config/config.yaml` with the following keys: `broker`, `mode` (paper/live), `paper_capital`, `daily_capital_limit`, `per_trade_max_capital`, `max_positions`, `allowed_indices`, `allowed_strategies`, `max_lots_per_trade`, `force_exit_time`, `entry_delay_minutes`, `monitor_interval_seconds`, `daily_loss_limit`, `max_delta_exposure`, `max_vega_exposure`, `min_days_to_expiry`, `target_profit_per_day`, `trailing_sl_trigger_pct`, `partial_book_pct`, `min_confidence_score`, `vix_threshold`, `paper_trading_weeks`
2. WHEN the `fno` section is missing from `config/config.yaml`, THE FnO_Config SHALL use documented default values for all keys and log a warning
3. WHEN a config key has a value outside its valid range, THE FnO_Config SHALL reject the invalid value, use the documented default, and log an error describing the invalid value and the default used
4. THE FnO_Config SHALL validate that the selected broker's config section (dhan or zerodha) exists and contains required API keys
5. IF the selected broker's config section is missing, THEN THE FnO_Config SHALL exit with a clear error message identifying the missing section
6. WHEN the `mode` key is set to `paper`, THE FnO_Config SHALL set `paper_capital` to the configured value (default ₹500,000) and disable all real broker order calls
7. WHEN the `mode` key is set to `live`, THE FnO_Config SHALL verify that `paper_trading_weeks` worth of paper trading history exists in the database before allowing live trading
8. THE FnO_Config SHALL default `allowed_indices` to `["NIFTY", "BANKNIFTY", "FINNIFTY"]`
9. THE FnO_Config SHALL default `allowed_strategies` to `["STRADDLE", "STRANGLE", "IRON_CONDOR", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "NAKED_CE", "NAKED_PE"]`
10. THE FnO_Config SHALL default `max_lots_per_trade` to 1, `max_positions` to 3, and `daily_loss_limit` to ₹5,000

### Requirement 2: Option Chain Data Fetching

**User Story:** As a trader, I want the system to fetch real-time option chain data for Nifty, BankNifty, and FinNifty, so that the strategy engine can analyze strikes, premiums, open interest, and volume to make informed trading decisions.

#### Acceptance Criteria

1. THE Option_Chain_Fetcher SHALL retrieve the complete option chain for each index in `allowed_indices`, including strike price, expiry date, option type (CE/PE), last traded price, bid price, ask price, open interest, change in OI from previous day, volume, and implied volatility
2. WHEN fetching option chain data, THE Option_Chain_Fetcher SHALL retrieve data for the current weekly expiry and the next weekly expiry
3. THE Option_Chain_Fetcher SHALL identify the ATM strike as the strike price closest to the current spot price of the underlying index
4. THE Option_Chain_Fetcher SHALL compute the bid-ask spread for each option contract as `ask_price - bid_price`
5. IF the option chain fetch fails, THEN THE Option_Chain_Fetcher SHALL retry once after 30 seconds and abort the trading session if the retry also fails
6. THE Option_Chain_Fetcher SHALL retrieve the current spot price of each underlying index alongside the option chain
7. THE Option_Chain_Fetcher SHALL retrieve lot size information for each index from the exchange data
8. THE Option_Chain_Fetcher SHALL store each option chain snapshot with a timestamp in memory (last 6 snapshots, ~30 minutes of data) to enable OI Change Velocity computation by the Quant_Edge_Engine
9. THE Option_Chain_Fetcher SHALL compute and include the **Put-Call Ratio (PCR)** with each snapshot: PCR = total Put OI / total Call OI across all strikes for the current expiry
10. THE Option_Chain_Fetcher SHALL compute and include the **Max Pain** strike with each snapshot: the strike price where the sum of (Call ITM value × Call OI + Put ITM value × Put OI) is minimized across all strikes
11. THE Option_Chain_Fetcher SHALL identify the **highest OI strikes** for both Calls and Puts separately, as these represent institutional resistance and support levels respectively

### Requirement 3: Greeks Calculation

**User Story:** As a trader, I want the system to calculate option Greeks for every position and candidate trade, so that I can understand the risk exposure from price movement, time decay, and volatility changes.

#### Acceptance Criteria

1. THE FnO_Greeks_Calculator SHALL compute delta, gamma, theta, and vega for any option given: spot price, strike price, time to expiry (in years), risk-free rate, and implied volatility
2. THE FnO_Greeks_Calculator SHALL use the Black-Scholes model for European-style index options
3. WHEN computing Greeks for a multi-leg strategy, THE FnO_Greeks_Calculator SHALL return the net Greeks as the sum of individual leg Greeks, accounting for buy/sell direction and quantity
4. THE FnO_Greeks_Calculator SHALL compute IV from the option's market price using numerical root-finding when IV is not provided by the exchange
5. FOR ALL valid option parameters, computing the option price from Greeks and then re-deriving Greeks from that price SHALL produce values within 0.01 of the original Greeks (round-trip property)
6. THE FnO_Greeks_Calculator SHALL handle edge cases: zero time to expiry (return intrinsic value), deep ITM options (delta approaching ±1), and deep OTM options (delta approaching 0)

### Requirement 4: F&O Strategy Playbook — The Money-Making Engine

**User Story:** As a trader, I want the system to use a battle-tested playbook of proven F&O strategies that professional Indian options traders use daily, so that the LLM selects the right strategy for the right market condition and generates consistent income.

---

#### STRATEGY PLAYBOOK — Plain English Explanation

**How F&O Works (for beginners):**
- In F&O, you don't buy/sell stocks directly. You trade *contracts* on indices like Nifty (top 50 companies) or BankNifty (top 12 banks).
- A **Call (CE)** = a bet that the index will go UP. A **Put (PE)** = a bet that the index will go DOWN.
- You can **BUY** options (pay premium, limited risk, unlimited reward) or **SELL** options (collect premium, limited reward, higher risk).
- **The secret**: Markets move sideways 60-70% of the time. Option SELLERS collect premium and win most days. Option BUYERS win big but less often.
- **Our edge**: The LLM reads VIX, OI data, PCR ratio, support/resistance, and market mood to pick the RIGHT strategy for TODAY's condition. No emotion, no greed, no fear.

**The 7 Core Strategies (ranked by safety):**

**Strategy 1: IRON CONDOR (Safest — "The Daily Bread")**
- *What it is*: You sell both a Call and a Put far from current price, and buy protection even further out. 4 legs total.
- *Example*: Nifty at 24,500. Sell 24,800 CE + Buy 24,900 CE + Sell 24,200 PE + Buy 24,100 PE. Collect ~₹80-120 premium.
- *When to use*: Sideways market, VIX between 12-18, no big events, 2+ days to expiry.
- *Max profit*: Premium collected (₹2,000-3,000 per lot). *Max loss*: Spread width minus premium (₹500-1,500 per lot).
- *Win rate*: 65-75% historically. This is the bread-and-butter strategy.

**Strategy 2: SHORT STRANGLE (High Income — "The Premium Collector")**
- *What it is*: Sell an OTM Call AND an OTM Put. No protection. Higher premium, higher risk.
- *Example*: Nifty at 24,500. Sell 24,800 CE + Sell 24,200 PE. Collect ~₹150-200 premium.
- *When to use*: High VIX (>16), market expected to stay in range, 3+ days to expiry.
- *Max profit*: Full premium (₹3,750-5,000 per lot). *Max loss*: Unlimited (but we use strict SL).
- *Win rate*: 70-80% with proper strike selection. MUST have SL at 1.5x premium collected.

**Strategy 3: BULL PUT SPREAD (Bullish — "The Support Catcher")**
- *What it is*: Sell a Put near support level, buy a cheaper Put below it for protection.
- *Example*: Nifty at 24,500, support at 24,300. Sell 24,300 PE + Buy 24,200 PE. Collect ~₹30-50 premium.
- *When to use*: Market bouncing off support, bullish trend, VIX moderate.
- *Max profit*: Premium collected. *Max loss*: Spread width minus premium.
- *Win rate*: 60-70%. Best when combined with OI analysis showing strong put writing at support.

**Strategy 4: BEAR CALL SPREAD (Bearish — "The Resistance Fader")**
- *What it is*: Sell a Call near resistance level, buy a cheaper Call above it for protection.
- *Example*: Nifty at 24,500, resistance at 24,700. Sell 24,700 CE + Buy 24,800 CE. Collect ~₹30-50 premium.
- *When to use*: Market hitting resistance, bearish trend, VIX moderate.
- *Max profit*: Premium collected. *Max loss*: Spread width minus premium.
- *Win rate*: 60-70%. Best when OI shows heavy call writing at resistance.

**Strategy 5: SHORT STRADDLE (Expiry Day Special — "The Theta Crusher")**
- *What it is*: Sell ATM Call AND ATM Put on expiry day. Maximum theta decay.
- *Example*: Nifty at 24,500 on Thursday expiry. Sell 24,500 CE + Sell 24,500 PE. Collect ~₹200-300 premium.
- *When to use*: ONLY on expiry day (Thursday for Nifty, Wednesday for BankNifty), VIX < 18, no major events.
- *Max profit*: Full premium (₹5,000-7,500 per lot). *Max loss*: Unlimited (strict SL mandatory).
- *Win rate*: 60-65%. High reward but needs tight management. Exit if index moves 100+ points from entry.

**Strategy 6: LONG STRADDLE (Event Play — "The Volatility Bomb")**
- *What it is*: BUY ATM Call AND ATM Put before a big event. Profit from big move in either direction.
- *Example*: Buy 24,500 CE + Buy 24,500 PE before RBI policy. Pay ~₹300 premium.
- *When to use*: Before RBI policy, budget, election results, major global events. VIX expected to spike.
- *Max profit*: Unlimited if big move happens. *Max loss*: Premium paid (₹7,500 per lot).
- *Win rate*: 40-50%. But winners are 3-5x the losers. Only use before confirmed high-impact events.

**Strategy 7: DIRECTIONAL OPTION BUY (Momentum — "The Trend Rider")**
- *What it is*: Buy a slightly OTM Call (bullish) or Put (bearish) when strong trend is confirmed.
- *Example*: Nifty breaking above 24,600 with volume. Buy 24,700 CE at ₹80, target ₹150, SL ₹40.
- *When to use*: Clear breakout/breakdown with volume, VIX rising, strong sector momentum.
- *Max profit*: 2-5x premium paid. *Max loss*: Premium paid.
- *Win rate*: 35-45%. But R:R is 2:1 to 5:1. Small bets, big wins.

---

#### Acceptance Criteria

1. THE FnO_Strategy_Engine SHALL implement the 7-strategy playbook above, each with specific entry conditions, strike selection rules, and exit rules as defined in this requirement
2. THE FnO_Strategy_Engine SHALL use AWS Bedrock Claude Sonnet to analyze market conditions and select the optimal strategy from the playbook, providing the LLM with: current spot prices, India VIX level, option chain data (ATM ± 10 strikes with OI, volume, IV), days to expiry, Put-Call Ratio (PCR), max pain level, recent price trend (5-day), support/resistance levels from OI data, and sector momentum from existing fetchers
3. THE FnO_Strategy_Engine SHALL implement a **Market Regime Classifier** that categorizes the current market into one of 4 regimes before strategy selection:
   - **SIDEWAYS** (VIX 10-15, range-bound last 3 days) → prefer IRON_CONDOR, SHORT_STRANGLE
   - **TRENDING_UP** (higher highs, higher lows, bullish OI) → prefer BULL_PUT_SPREAD, DIRECTIONAL_CE_BUY
   - **TRENDING_DOWN** (lower highs, lower lows, bearish OI) → prefer BEAR_CALL_SPREAD, DIRECTIONAL_PE_BUY
   - **HIGH_VOLATILITY** (VIX > 20, or event day) → prefer LONG_STRADDLE, IRON_CONDOR with wider wings
4. THE FnO_Strategy_Engine SHALL select strikes using **OI-based support/resistance**: the strike with highest Put OI is support, the strike with highest Call OI is resistance. Sell legs SHALL be placed at or beyond these OI walls.
5. THE FnO_Strategy_Engine SHALL compute the **Put-Call Ratio (PCR)** from the option chain: PCR = total Put OI / total Call OI. PCR > 1.2 = bullish (more puts written = market supported), PCR < 0.8 = bearish (more calls written = market capped).
6. THE FnO_Strategy_Engine SHALL compute **Max Pain** — the strike price where option buyers lose the most money — and use it as a magnet level for expiry-day strategies. Nifty tends to gravitate toward max pain on expiry.
7. WHEN the LLM recommends a strategy, THE FnO_Strategy_Engine SHALL validate: (a) strategy type is in the playbook, (b) all legs have valid strikes in the option chain, (c) confidence score >= `min_confidence_score`, (d) expiry >= `min_days_to_expiry` (except for expiry-day strategies), (e) risk-reward ratio meets minimum threshold for that strategy type
8. THE FnO_Strategy_Engine SHALL construct each strategy as a list of Strategy_Leg objects: index, strike price, expiry date, option type (CE/PE/FUT), transaction type (BUY/SELL), lot size, number of lots, and entry price
9. THE FnO_Strategy_Engine SHALL compute the maximum possible loss for each strategy before execution and reject strategies where max loss exceeds `per_trade_max_capital`
10. THE FnO_Strategy_Engine SHALL apply **time-of-day rules**: no new SHORT_STRADDLE or SHORT_STRANGLE entries after 2:00 PM IST (theta decay advantage diminishes), DIRECTIONAL buys only before 1:00 PM IST (need time for move to play out)
11. THE FnO_Strategy_Engine SHALL apply **expiry-day special rules**: on expiry day, ONLY allow SHORT_STRADDLE, IRON_CONDOR, and DIRECTIONAL strategies. No new SHORT_STRANGLE (gamma risk too high on expiry).
12. THE FnO_Strategy_Engine SHALL reject naked option selling (SHORT_STRANGLE, SHORT_STRADDLE) when paper trading history is less than 2 weeks
13. IF the LLM returns an empty response or invalid JSON, THEN THE FnO_Strategy_Engine SHALL abort the trading session without placing any orders
14. THE FnO_Strategy_Engine SHALL log the market regime classification, PCR, max pain, OI-based support/resistance, and the full LLM prompt/response to the audit trail for every strategy selection

### Requirement 5: F&O Order Execution

**User Story:** As a trader, I want the system to execute F&O orders through the existing broker abstraction layer, so that I can trade options and futures on both Dhan and Zerodha without broker-specific code in the F&O module.

#### Acceptance Criteria

1. THE FnO_Order_Executor SHALL place F&O orders exclusively through the BrokerClient ABC interface, using the `NFO` exchange segment instead of `NSE`
2. WHEN placing a multi-leg strategy, THE FnO_Order_Executor SHALL place all legs as individual orders in rapid sequence, starting with sell legs (to collect premium first) and then buy legs
3. THE FnO_Order_Executor SHALL construct the correct trading symbol for each leg in the broker-specific format (e.g., `NIFTY25JUL24500CE` for Dhan, `NIFTY2472524500CE` for Zerodha)
4. WHEN in paper trading mode, THE FnO_Order_Executor SHALL simulate order fills at the last traded price from the option chain, deduct simulated margin from paper capital, and track simulated P&L without calling any broker API
5. THE FnO_Order_Executor SHALL wait `entry_delay_minutes` after 9:15 AM IST before placing the first order
6. IF any leg of a multi-leg strategy fails to execute, THEN THE FnO_Order_Executor SHALL attempt to cancel all previously placed legs of that strategy and log the partial execution as an error
7. THE FnO_Order_Executor SHALL store the broker order ID for every placed order in the database
8. THE FnO_Order_Executor SHALL log a prominent warning banner at startup when in live mode indicating real money is at risk with F&O trading

### Requirement 6: F&O Position Monitoring

**User Story:** As a trader, I want the system to continuously monitor open F&O positions, track Greeks exposure, and enforce exit rules, so that positions are managed according to the configured risk parameters.

#### Acceptance Criteria

1. THE FnO_Position_Monitor SHALL fetch positions from BrokerClient.get_positions() every `monitor_interval_seconds` and match them against the database records
2. THE FnO_Position_Monitor SHALL compute real-time Greeks for all open positions using current market data and aggregate net delta, gamma, theta, and vega across all positions
3. WHEN the net delta exposure across all positions exceeds `max_delta_exposure`, THE FnO_Position_Monitor SHALL log a warning and flag the portfolio as delta-heavy
4. WHEN the net vega exposure across all positions exceeds `max_vega_exposure`, THE FnO_Position_Monitor SHALL log a warning and flag the portfolio as vega-heavy
5. THE FnO_Position_Monitor SHALL implement a state machine for each strategy: PENDING → OPEN → PARTIAL_BOOKED → CLOSED / STOPPED_OUT / FORCE_EXITED / EXPIRED
6. WHEN the combined premium of a sold strategy (straddle/strangle) moves against the position by more than the `trailing_sl_trigger_pct` of collected premium, THE FnO_Position_Monitor SHALL trigger a stop-loss exit for the entire strategy
7. WHEN a strategy reaches `partial_book_pct` of its maximum profit, THE FnO_Position_Monitor SHALL close the position to book partial profits
8. WHEN the current time reaches `force_exit_time` IST, THE FnO_Position_Monitor SHALL close all open positions with market orders regardless of P&L
9. WHEN an option contract is within 1 day of expiry and is OTM, THE FnO_Position_Monitor SHALL close the position to avoid expiry-day gamma risk
10. THE FnO_Position_Monitor SHALL update trade status in the database after each state transition

### Requirement 7: F&O Risk Management

**User Story:** As a trader, I want the system to enforce strict risk limits for F&O trading including margin requirements, position limits, and daily loss caps, so that catastrophic losses from leveraged derivatives are prevented.

#### Acceptance Criteria

1. THE FnO_Risk_Manager SHALL compute the estimated SPAN + exposure margin for each strategy before execution using the broker's margin calculator API or a local approximation
2. WHEN the estimated margin for a new strategy exceeds the available margin (real or paper), THE FnO_Risk_Manager SHALL reject the trade
3. THE FnO_Risk_Manager SHALL enforce that the total number of open strategy positions does not exceed `max_positions`
4. THE FnO_Risk_Manager SHALL enforce that no single strategy uses more than `max_lots_per_trade` lots per leg
5. THE FnO_Risk_Manager SHALL track cumulative realized losses for the day and refuse new orders when `daily_loss_limit` is reached
6. WHEN cumulative realized loss reaches 80% of `daily_loss_limit`, THE FnO_Risk_Manager SHALL log a warning including unrealized losses
7. IF the daily loss limit is breached, THEN THE FnO_Risk_Manager SHALL immediately cancel all pending orders and close all open positions
8. THE FnO_Risk_Manager SHALL implement VIX-based session control: if VIX exceeds 1.5 times `vix_threshold`, skip the trading session entirely; if VIX exceeds `vix_threshold`, reduce `max_positions` by half
9. THE FnO_Risk_Manager SHALL reject naked option selling strategies where the theoretical maximum loss is unlimited, unless the account has sufficient margin to cover a 2-standard-deviation move in the underlying
10. THE FnO_Risk_Manager SHALL persist daily loss tracking state in the database for restart resilience

### Requirement 8: Paper Trading Mode

**User Story:** As a trader, I want to run the F&O auto-trader in paper trading mode for the first few weeks using simulated capital, so that I can validate the strategy engine and risk management before risking real money.

#### Acceptance Criteria

1. WHEN mode is `paper`, THE Paper_Trade_Engine SHALL maintain a virtual capital balance starting at `paper_capital` (default ₹500,000)
2. THE Paper_Trade_Engine SHALL simulate order fills at the last traded price from the option chain at the time of order placement
3. THE Paper_Trade_Engine SHALL deduct estimated SPAN + exposure margin from virtual capital when a position is opened and release it when the position is closed
4. THE Paper_Trade_Engine SHALL track simulated P&L for each strategy based on the difference between entry premium and current premium
5. THE Paper_Trade_Engine SHALL enforce all the same risk rules as live trading: daily loss limit, position limits, margin checks, Greeks thresholds, and force exit timing
6. THE Paper_Trade_Engine SHALL store all paper trades in the database with `mode = "PAPER"` to distinguish them from live trades
7. THE Paper_Trade_Engine SHALL generate the same dashboard data and reports as live trading, clearly labeled as paper trading results
8. WHEN transitioning from paper to live mode, THE FnO_Config SHALL verify that at least `paper_trading_weeks` (default 3) weeks of paper trading data exists with a positive cumulative P&L

### Requirement 9: Database Schema for F&O

**User Story:** As a trader, I want all F&O trades, strategies, and daily summaries stored in the database, so that I can review historical performance and the system can restore state after restarts.

#### Acceptance Criteria

1. THE DBManager SHALL create an `fno_trades` table with columns: id, trade_date, timestamp, index_name, tradingsymbol, option_type (CE/PE/FUT), strike_price, expiry_date, action (BUY/SELL), order_type, quantity, lots, price, trigger_price, broker_order_id, broker_name, status, entry_price, exit_price, pnl, mode (PAPER/LIVE), strategy_id (FK to fno_strategies)
2. THE DBManager SHALL create an `fno_strategies` table with columns: id, trade_date, timestamp, strategy_type, index_name, legs_json (JSON array of leg details), net_premium, max_profit, max_loss, net_delta, net_gamma, net_theta, net_vega, status, entry_time, exit_time, realized_pnl, mode, confidence_score, rationale
3. THE DBManager SHALL create an `fno_daily_summary` table with columns: id, trade_date, total_strategies, winning_strategies, losing_strategies, total_pnl, total_realized_loss, max_drawdown, broker_name, mode, paper_capital_remaining
4. THE DBManager SHALL provide query methods: `get_fno_trades_for_date(date)`, `get_fno_strategies_for_date(date)`, `get_fno_daily_summary(date)`, `get_fno_cumulative_pnl(start_date, end_date)`, `get_fno_daily_realized_loss(date)`, `get_paper_trading_history(weeks)`
5. THE DBManager SHALL store all timestamps in IST format
6. THE DBManager SHALL extend the existing `intraday_audit_log` table to support F&O events by adding event types prefixed with `FNO_`

### Requirement 10: F&O Reporting and Performance Analytics

**User Story:** As a trader, I want end-of-day performance reports for F&O trading with strategy-level analytics, so that I can evaluate which strategies are profitable and track overall F&O performance.

#### Acceptance Criteria

1. THE FnO_Reporter SHALL generate an EOD JSON report at `output/reports/fno_YYYY-MM-DD.json` with: trade date, mode, broker name, all strategies with legs/entry/exit/P&L, total P&L, win/loss counts, win rate
2. THE FnO_Reporter SHALL compute strategy-level performance metrics grouped by strategy type: win rate, average profit, average loss, and profit factor for each strategy type
3. THE FnO_Reporter SHALL compute cumulative P&L as a running total across all F&O trading days
4. THE FnO_Reporter SHALL compute maximum peak-to-trough drawdown across the cumulative P&L series
5. THE FnO_Reporter SHALL compute expectancy: `avg_profit × win_rate - abs(avg_loss) × (1 - win_rate)`
6. THE FnO_Reporter SHALL track theta decay P&L separately — the portion of profit attributable to time decay in premium-selling strategies
7. THE FnO_Reporter SHALL overwrite the report file if it already exists for the date
8. THE FnO_Reporter SHALL insert or update the `fno_daily_summary` row in the database

### Requirement 11: Dashboard Integration

**User Story:** As a trader, I want to see all F&O trading activity on the existing dashboard as a new tab, so that I can monitor positions, Greeks, P&L, and strategy performance alongside my equity intraday trading.

#### Acceptance Criteria

1. THE Dashboard SHALL add a new "F&O Live" tab to `dashboard/index.html` alongside the existing "Portfolio" and "Intraday Live" tabs
2. THE Dashboard SHALL display a summary card showing: mode (Paper/Live), today's P&L, number of active strategies, paper capital remaining (in paper mode), and net portfolio Greeks (delta, gamma, theta, vega)
3. THE Dashboard SHALL display a strategies table showing: strategy type, index, legs summary, entry premium, current premium, unrealized P&L, status, and net Greeks per strategy
4. THE Dashboard SHALL display a daily loss tracker as a progress bar (green → yellow at 50% → red at 80%) showing realized loss versus `daily_loss_limit`
5. THE FnO_Reporter SHALL write dashboard data to `dashboard/api/fno_latest.json` with structure: updated_at, mode, broker, session_active, paper_capital_remaining, today (strategies, total_pnl, realized_loss, daily_loss_cap, loss_cap_pct, net_greeks), history (daily_pnl array, cumulative_pnl, win_rate, total_days)
6. THE Dashboard SHALL display historical charts using Chart.js: cumulative P&L line chart, daily P&L bar chart, and strategy-type performance breakdown
7. THE Dashboard SHALL auto-refresh every 60 seconds during market hours (9:15 AM – 3:30 PM IST)
8. THE Dashboard SHALL read F&O data from `dashboard/api/fno_latest.json` independently from the equity intraday data

### Requirement 12: Broker Abstraction Extension for F&O

**User Story:** As a developer, I want the existing BrokerClient ABC extended to support F&O-specific operations, so that the F&O module can place derivative orders through the same broker-agnostic interface.

#### Acceptance Criteria

1. THE BrokerClient ABC SHALL be extended with a `place_fno_order()` method accepting: tradingsymbol, exchange (`NFO`), transaction_type, order_type, product_type (`NRML` or `MIS`), quantity, price, trigger_price, and returning a dict with `broker_order_id` and `status`
2. THE BrokerClient ABC SHALL be extended with a `get_fno_positions()` method that returns F&O positions normalized to include: tradingsymbol, index_name, option_type, strike_price, expiry_date, quantity, buy_avg, sell_avg, pnl, product_type
3. THE BrokerClient ABC SHALL be extended with a `get_fno_margins()` method that returns F&O-specific margin information: available_margin, used_margin, span_margin, exposure_margin
4. THE DhanBrokerClient SHALL implement `place_fno_order()` using the Dhan API with `exchangeSegment="NSE_FNO"` and the Dhan-format trading symbol
5. THE ZerodhaBrokerClient SHALL implement `place_fno_order()` using the Kite Connect SDK with `exchange="NFO"` and the Zerodha-format trading symbol
6. THE DhanBrokerClient and ZerodhaBrokerClient SHALL each implement `get_fno_positions()` and `get_fno_margins()` with broker-specific API calls normalized to the common interface
7. FOR ALL valid F&O order responses from either broker, the normalized output SHALL contain a non-empty `broker_order_id` string

### Requirement 13: Trading Symbol Construction

**User Story:** As a developer, I want a utility that constructs the correct F&O trading symbol for each broker, so that orders are placed with the exact symbol format each broker expects.

#### Acceptance Criteria

1. THE Symbol_Builder SHALL construct Dhan-format F&O symbols: `{INDEX}{YY}{MMM}{STRIKE}{CE/PE}` (e.g., `NIFTY25JUL24500CE`)
2. THE Symbol_Builder SHALL construct Zerodha-format F&O symbols: `{INDEX}{YY}{M}{DD}{STRIKE}{CE/PE}` where M is a single-character month code (e.g., `NIFTY2572524500CE`)
3. THE Symbol_Builder SHALL construct futures symbols for both brokers: `{INDEX}{YY}{MMM}FUT` for Dhan, `{INDEX}{YY}{M}{DD}FUT` for Zerodha
4. FOR ALL valid combinations of index, expiry date, strike price, and option type, constructing a symbol and then parsing it back SHALL produce the original parameters (round-trip property)
5. IF an invalid index name, strike price, or option type is provided, THEN THE Symbol_Builder SHALL raise a ValueError with a descriptive message

### Requirement 14: Entry Point and Orchestration

**User Story:** As a trader, I want a single entry point script to run the F&O auto-trader, so that I can start the system with a simple command and have it execute the full trading pipeline.

#### Acceptance Criteria

1. THE `run_fno.py` script SHALL accept CLI arguments: `--live` (enable live trading, default paper mode), `--skip-scan` (use cached option chain data), `--force` (ignore time-of-day checks)
2. WHEN `--force` is not provided, THE `run_fno.py` script SHALL verify the current time is between 8:30 AM and 3:30 PM IST on a weekday and exit with a message if outside trading hours
3. THE `run_fno.py` script SHALL execute phases in order: load config → broker auth (if live) → fetch option chains → compute Greeks → LLM strategy selection → risk validation → order execution → position monitoring loop → force exit at deadline → EOD report → dashboard update
4. WHEN `--live` is provided but insufficient paper trading history exists, THE `run_fno.py` script SHALL exit with a message indicating the required paper trading period
5. IF a critical phase fails (config, auth, option chain fetch, LLM), THEN THE `run_fno.py` script SHALL abort gracefully, log the reason, and generate a partial report if any strategies were placed
6. THE `run_fno.py` script SHALL log every phase start and completion with timestamps to console and the audit log table

### Requirement 15: Audit Trail

**User Story:** As a trader, I want a complete audit trail of all F&O trading decisions and actions, so that I can review what the system did and debug any issues.

#### Acceptance Criteria

1. THE FnO_Order_Executor SHALL log every action to the `intraday_audit_log` table with `FNO_` prefixed event types: FNO_SCAN, FNO_STRATEGY_SELECTED, FNO_LLM_PROMPT, FNO_LLM_RESPONSE, FNO_ORDER_PLACED, FNO_ORDER_MODIFIED, FNO_ORDER_CANCELLED, FNO_POSITION_UPDATE, FNO_SL_ADJUST, FNO_EXIT, FNO_ERROR
2. THE audit log SHALL store the full LLM prompt and response for every strategy selection call
3. THE audit log SHALL store Greeks snapshots for every position update
4. THE audit log SHALL use IST timestamps for all entries

### Requirement 16: Quantitative Edge Engine — The Institutional Brain

**User Story:** As a trader, I want the system to use quantitative signals that institutional trading desks use — IV percentile mean reversion, OI change velocity, IV skew analysis, gamma exposure mapping, and multi-signal confluence scoring — so that every trade has a measurable statistical edge, not just a guess.

---

#### THE 6 QUANTITATIVE EDGES — Plain English Explanation

**Why this matters:**
A small-town trader selling strangles makes money 70% of the time but gets wiped out in the other 30% because they have no EDGE — they're just hoping the market stays flat. The big firms don't hope. They MEASURE. They only enter when 3-4 signals line up. That's what this engine does.

**Edge 1: IV Percentile Mean Reversion — "Sell When Expensive, Buy When Cheap"**
- *What it is*: Implied Volatility (IV) always comes back to its average. When IV is in the top 20% of its 1-year range (IV Percentile > 80), options are EXPENSIVE → sell them. When IV is in the bottom 20% (IV Percentile < 20), options are CHEAP → buy them.
- *How we use it*: Compute IV Percentile = (% of days in last 252 trading days where IV was lower than today). If IVP > 70 → sell premium (strangles, iron condors). If IVP < 30 → buy premium (straddles, directional). Between 30-70 → use spreads.
- *The edge*: When you sell options at IVP > 70, you're selling something overpriced. Even if the market moves against you, the IV crush (IV dropping back to normal) works in your favor. This is how Citadel's options desk prints money.

**Edge 2: OI Change Velocity — "Follow the Smart Money"**
- *What it is*: It's not just WHERE the Open Interest is, it's HOW FAST it's changing. A sudden spike of 10 lakh+ OI at a specific strike in the last 30 minutes means big institutional money is building a position there.
- *How we use it*: Track OI change between option chain snapshots (every 3-5 minutes). If Put OI at a strike increases by > 5 lakh in 30 min → institutions are WRITING puts there → that's a strong support floor. If Call OI spikes → that's a ceiling. The LLM uses this to place sell legs BEHIND these institutional walls.
- *The edge*: Retail traders look at static OI. We look at the VELOCITY of OI change. A strike that gained 15 lakh Put OI in the last hour is a much stronger support than one that's had 15 lakh for 3 days.

**Edge 3: IV Skew Analysis — "The Market's Hidden Fear Gauge"**
- *What it is*: In a normal market, OTM Puts have higher IV than OTM Calls (because people pay more for crash protection). When this skew STEEPENS (put IV rises much faster than call IV), the market is getting scared. When it FLATTENS, the market is complacent.
- *How we use it*: Compute Put-Call IV Skew = IV of 25-delta Put minus IV of 25-delta Call. If skew is widening → fear is rising → sell call spreads (bearish), avoid selling puts. If skew is narrowing → complacency → sell put spreads (bullish), or sell strangles.
- *The edge*: The skew tells you what the OPTIONS MARKET thinks, which is often smarter than the spot market. A steepening skew 2 days before a crash is the canary in the coal mine. We read it; retail traders don't.

**Edge 4: Gamma Exposure (GEX) Mapping — "Where the Market MUST Go"**
- *What it is*: Market makers who sell options must hedge by buying/selling the underlying. The total gamma exposure across all strikes creates "magnetic zones" where the market gets pulled toward or repelled from.
- *How we use it*: Compute net GEX at each strike = Σ(OI × gamma × contract_multiplier × spot_price / 100) for all calls and puts. Positive GEX zones = market gets pinned there (mean-reverting). Negative GEX zones = market accelerates through (trending). The highest positive GEX strike is the "gravity center" for the day.
- *The edge*: On days with high positive GEX, the market is PINNED — perfect for selling straddles/strangles. On days with negative GEX (usually after big moves), the market trends — perfect for directional plays. This is literally what Jane Street and Optiver use.

**Edge 5: Realized vs Implied Volatility Gap — "The Volatility Risk Premium"**
- *What it is*: Implied Volatility (what options are priced at) is almost ALWAYS higher than Realized Volatility (what actually happens). This gap is called the Volatility Risk Premium (VRP). When the gap is wide, option sellers have a huge edge.
- *How we use it*: Compute VRP = ATM IV - 20-day Realized Volatility. If VRP > 5 percentage points → options are very overpriced → aggressive premium selling. If VRP < 2 → options are fairly priced → use spreads instead of naked selling. If VRP < 0 (rare) → options are UNDERPRICED → buy premium.
- *The edge*: Studies show VRP is positive ~85% of the time in Nifty options. By measuring it precisely, we only sell when the edge is fattest. This is the single most profitable edge in all of options trading.

**Edge 6: Multi-Signal Confluence Score — "The Decision Matrix"**
- *What it is*: No single signal is reliable alone. The magic happens when 3-4 signals agree. We compute a Confluence Score (0-100) that weights all edges together.
- *How we use it*: Each edge contributes a sub-score:
  - IV Percentile signal: 0-20 points (strongest when IVP > 80 for selling, < 20 for buying)
  - OI Velocity signal: 0-20 points (strongest when clear institutional walls visible)
  - IV Skew signal: 0-15 points (strongest when skew confirms direction)
  - GEX signal: 0-15 points (strongest when GEX regime matches strategy type)
  - VRP signal: 0-15 points (strongest when VRP > 5 for selling strategies)
  - PCR + Max Pain alignment: 0-15 points (strongest when both confirm same direction)
- *Minimum to trade*: Confluence Score >= 60 for any strategy. >= 75 for naked selling. >= 50 for hedged strategies (iron condors, spreads).
- *The edge*: By requiring multiple independent signals to agree, we avoid the #1 killer of retail traders: taking trades based on a single indicator. When IV is high AND OI walls are strong AND GEX is positive AND VRP is wide — that's when we go in heavy.

---

#### Acceptance Criteria

1. THE Quant_Edge_Engine SHALL compute **IV Percentile** for each index: IVP = (number of trading days in last 252 where ATM IV was lower than today's ATM IV) / 252 × 100. IVP > 70 signals "sell premium", IVP < 30 signals "buy premium", 30-70 signals "use spreads".
2. THE Quant_Edge_Engine SHALL track **OI Change Velocity** by storing option chain snapshots every `monitor_interval_seconds` and computing the rate of OI change at each strike over the last 30 minutes. A Put OI increase > 500,000 at a single strike SHALL be flagged as "institutional support building". A Call OI increase > 500,000 SHALL be flagged as "institutional resistance building".
3. THE Quant_Edge_Engine SHALL compute **IV Skew** as the difference between the IV of the 25-delta Put and the IV of the 25-delta Call for each index. Skew widening (today's skew > 5-day average skew) SHALL signal bearish sentiment. Skew narrowing SHALL signal bullish sentiment.
4. THE Quant_Edge_Engine SHALL compute **Gamma Exposure (GEX)** at each strike: GEX_strike = Σ(OI × gamma × lot_size × spot / 100) across all options at that strike, with call gamma positive and put gamma negative. The strike with highest net positive GEX SHALL be identified as the "gravity center". Net negative total GEX across all strikes SHALL signal a trending day.
5. THE Quant_Edge_Engine SHALL compute **Volatility Risk Premium (VRP)**: VRP = ATM_IV - RV_20d, where RV_20d is the annualized standard deviation of the last 20 daily log returns of the underlying × √252. VRP > 5 SHALL signal "strong sell premium edge". VRP < 2 SHALL signal "weak edge, use spreads only". VRP < 0 SHALL signal "buy premium".
6. THE Quant_Edge_Engine SHALL compute a **Confluence Score** (0-100) for each candidate strategy by summing weighted sub-scores from all 6 edges: IV Percentile (0-20), OI Velocity (0-20), IV Skew (0-15), GEX (0-15), VRP (0-15), PCR+MaxPain (0-15). The minimum Confluence Score to execute any trade SHALL be 60. Naked selling strategies SHALL require >= 75. Hedged strategies (iron condors, spreads) SHALL require >= 50.
7. THE Quant_Edge_Engine SHALL provide all computed signals (IVP, OI velocity map, IV skew, GEX map, VRP, confluence score breakdown) to the LLM as structured data in the strategy selection prompt, so the LLM can incorporate quantitative evidence into its reasoning.
8. THE Quant_Edge_Engine SHALL store historical IV data (daily ATM IV for each index) in a new `fno_iv_history` database table to enable IV Percentile computation. On first run, it SHALL bootstrap from the last 30 days of available data and build up to 252 days over time.
9. THE Quant_Edge_Engine SHALL store historical spot price data (daily close for each index) in a new `fno_spot_history` database table to enable Realized Volatility computation.
10. THE Quant_Edge_Engine SHALL log all computed signals, sub-scores, and the final confluence score to the audit trail for every strategy evaluation, enabling post-trade analysis of which edges contributed to winning vs losing trades.
11. THE Quant_Edge_Engine SHALL implement an **Adaptive Strategy Weighting** system: after 20+ trading days of history, compute the win rate of each strategy type and increase the confluence score bonus for strategies with > 60% win rate, decrease it for strategies with < 40% win rate. This makes the system learn from its own performance.
12. THE Quant_Edge_Engine SHALL implement a **"No Edge, No Trade"** rule: if the maximum confluence score across all candidate strategies is below 50, the system SHALL skip the trading session entirely and log "No sufficient edge detected today". This prevents trading on marginal setups — the #1 cause of retail losses.
