# Requirements Document

## Introduction

The Intraday Auto-Trader is a production-grade automated intraday trading module for the Wealth Builder Pro Python application. It targets the Indian stock market (NSE equity cash segment) and aims to generate a minimum of ₹5,000 INR daily profit through AI-driven stock selection, automated order execution via a broker-agnostic abstraction layer (supporting both Dhan and Zerodha Kite Connect), real-time position monitoring, and disciplined risk management. The module operates within a daily capital limit of ₹5,000 (the total capital the tool is allowed to deploy per day across all trades), a per-trade capital limit of ₹2,500, and a separate daily loss safety net of ₹2,500. It supports both dry-run and live execution modes. It leverages Claude Sonnet 4.5 on AWS Bedrock as an intelligent trade selector layered on top of rule-based pre-filters, and integrates with the existing dashboard for live monitoring.

## Glossary

- **Trader**: The main intraday auto-trading orchestrator module (`run_intraday.py`) that coordinates scanning, selection, execution, monitoring, and reporting
- **Pre_Market_Scanner**: The component that fetches and analyzes NSE pre-open data, previous-day movers, gap analysis, and sector momentum before market open
- **Trade_Selector**: The component combining rule-based pre-filters with Claude Sonnet 4.5 LLM analysis to select high-confidence intraday trade candidates
- **BrokerClient**: An abstract base class (`intraday/broker_base.py`) defining the broker-agnostic interface with methods: `authenticate()`, `place_order()`, `modify_order()`, `cancel_order()`, `get_positions()`, `get_margins()`
- **DhanBrokerClient**: A concrete implementation of BrokerClient (`intraday/dhan_broker.py`) that communicates with the Dhan REST API v2 using a 3-step OAuth flow (generate-consent → browser login → consume-consent)
- **ZerodhaBrokerClient**: A concrete implementation of BrokerClient (`intraday/zerodha_broker.py`) that communicates with the Zerodha Kite Connect API using the `kiteconnect` Python SDK
- **Order_Executor**: The component that places, modifies, and cancels INTRADAY orders via the active BrokerClient — fully broker-agnostic
- **Position_Monitor**: The component that tracks open positions at regular intervals, manages trailing stop losses, partial profit booking, and force-exits — fully broker-agnostic
- **Risk_Manager**: The component that enforces daily loss caps, per-trade loss limits, position sizing rules, and market volatility checks
- **Performance_Tracker**: The component that records trade outcomes, calculates P&L, win rates, expectancy, drawdown, and generates end-of-day reports
- **Dashboard_View**: The "Intraday Live" tab added to the existing HTML dashboard showing real-time trades, P&L, and historical performance
- **Auth_Server**: A local Flask HTTP server at `http://127.0.0.1:5000/callback` that captures OAuth login redirects for both Dhan and Zerodha and exchanges tokens for access credentials
- **BedrockClient**: The existing AWS Bedrock client in `llm/bedrock_client.py` that invokes Claude Sonnet 4.5
- **DBManager**: The existing SQLite database manager in `database/db_manager.py`
- **Intraday_Config**: The `intraday` section of `config/config.yaml` containing all tunable trading parameters including `broker` key to select active broker
- **Dhan_Config**: The `dhan` section of `config/config.yaml` containing `client_id`, `api_key`, and `api_secret` for Dhan OAuth authentication
- **Zerodha_Config**: The `zerodha` section of `config/config.yaml` containing `api_key`, `api_secret`, and `user_id` for Kite Connect authentication
- **Broker_Session**: A persisted JSON file at `config/.broker_session.json` storing the active broker's access token with date for same-day reuse
- **MIS_Order**: A Market Intraday Squared-off order — product type `"MIS"` on Zerodha Kite Connect and `"INTRADAY"` on Dhan, auto-squared by broker at end of day
- **Confidence_Score**: An integer from 1 to 10 assigned by the LLM to each trade candidate indicating conviction level
- **Trailing_Stop_Loss**: A dynamic stop loss that moves upward as the stock price increases, locking in profits
- **ORB**: Opening Range Breakout — a strategy that trades breakouts of the high/low range formed in the first 15-30 minutes of trading
- **VWAP**: Volume Weighted Average Price — a benchmark used to assess whether a stock is trading above or below fair intraday value
- **VIX**: India VIX volatility index — used to gauge overall market fear/greed and determine trade eligibility
- **Force_Exit_Time**: 3:15 PM IST — the hard deadline by which all open intraday positions are closed
- **Entry_Delay**: A configurable wait period (default 10 minutes) after market open at 9:15 AM before executing trades, to avoid opening volatility
- **Daily_Capital_Limit**: The maximum total capital the tool is allowed to deploy across all trades in a single trading day (₹5,000). Tracked as the sum of (quantity × entry_price) for all trades placed today. The user plans to increase this over time as trust in the system grows.
- **Per_Trade_Max_Capital**: The maximum capital allowed to be deployed on any single trade (₹2,500). Position sizing: quantity = min(per_trade_max_capital / entry_price, available_margin / entry_price), rounded to whole shares.
- **Daily_Loss_Limit**: A separate safety net — the maximum cumulative realized loss allowed per trading day (₹2,500, half of daily capital). If breached, all positions are closed immediately.

## Requirements

### Requirement 1: Configuration Management

**User Story:** As a trader, I want all intraday trading parameters centralized in config.yaml with support for multiple brokers, so that I can tune the system and switch brokers without modifying code.

#### Acceptance Criteria

1. THE Intraday_Config SHALL contain the following keys with default values: `broker` ("dhan"), `daily_capital_limit` (5000), `per_trade_max_capital` (2500), `max_trades_per_day` (5), `price_range_min` (50), `price_range_max` (1000), `monitor_interval_seconds` (300), `force_exit_time` ("15:15"), `entry_delay_minutes` (10), `min_confidence_score` (7), `vix_threshold` (20), `target_profit_per_day` (5000), `trailing_sl_trigger_pct` (0.5), `partial_book_pct` (50), `daily_loss_limit` (2500)
2. THE Dhan_Config SHALL contain the following keys: `client_id`, `api_key`, and `api_secret`
3. THE Zerodha_Config SHALL contain the following keys: `api_key`, `api_secret`, and `user_id`
4. WHEN the `intraday.broker` key is set to `"dhan"`, THE Trader SHALL instantiate a DhanBrokerClient for all broker operations
5. WHEN the `intraday.broker` key is set to `"zerodha"`, THE Trader SHALL instantiate a ZerodhaBrokerClient for all broker operations
6. WHEN the `intraday.broker` key is set to an unsupported value, THE Trader SHALL exit with an error message listing supported brokers
7. WHEN the Intraday_Config section is missing from config.yaml, THE Trader SHALL use the default values defined in the code and log a warning
8. WHEN any Intraday_Config value is outside its valid range (e.g., negative `daily_capital_limit`, zero `max_trades_per_day`, `min_confidence_score` > 10), THE Trader SHALL reject the value, use the default, and log an error with the invalid key and value
9. WHEN the selected broker's config section is missing or incomplete, THE Trader SHALL exit with an error message indicating the required credentials for that broker

### Requirement 2: Pre-Market Scanning

**User Story:** As a trader, I want the system to scan the market before open, so that it identifies the strongest intraday candidates using data-driven analysis.

#### Acceptance Criteria

1. WHEN the Trader is started, THE Pre_Market_Scanner SHALL fetch NSE pre-open market data, previous trading day top gainers and losers, and sector index performance using the existing `nse_market_movers` fetcher
2. THE Pre_Market_Scanner SHALL compute gap-up and gap-down percentages for each stock by comparing pre-open price to previous close
3. THE Pre_Market_Scanner SHALL identify sector momentum by ranking sectors from the `fetch_sector_indices()` data by change percentage
4. THE Pre_Market_Scanner SHALL identify volume spikes by comparing current pre-open volume to the stock average volume where available
5. IF the Pre_Market_Scanner fails to fetch data from NSE, THEN THE Trader SHALL log the error, retry once after 30 seconds, and abort the trading session if the retry also fails

### Requirement 3: Rule-Based Pre-Filtering

**User Story:** As a trader, I want a rule-based filter before the LLM, so that only technically viable candidates reach the expensive AI analysis step.

#### Acceptance Criteria

1. THE Trade_Selector SHALL filter out stocks priced below `price_range_min` or above `price_range_max` from the Intraday_Config
2. THE Trade_Selector SHALL filter out stocks with zero or missing volume data
3. THE Trade_Selector SHALL flag stocks showing gap-up or gap-down greater than 3% as high-volatility candidates
4. THE Trade_Selector SHALL check sector alignment by verifying the stock belongs to a sector with positive momentum for long trades
5. THE Trade_Selector SHALL pass a maximum of 20 pre-filtered candidates to the LLM for analysis
6. WHEN fewer than 3 candidates pass the pre-filter, THE Trade_Selector SHALL log a warning and proceed with available candidates

### Requirement 4: LLM Trade Selection

**User Story:** As a trader, I want Claude Sonnet 4.5 to analyze pre-filtered candidates and select 3-5 high-confidence trades with precise entry, target, and stop loss levels.

#### Acceptance Criteria

1. THE Trade_Selector SHALL send pre-filtered candidate data to the BedrockClient with a system prompt specifying: momentum analysis, volume confirmation, sector strength, support/resistance levels, gap analysis, and VWAP consideration
2. THE Trade_Selector SHALL require the LLM to return a JSON response containing for each pick: `stock_name`, `nse_symbol`, `tradingsymbol`, `entry_price`, `target_price`, `stop_loss_price`, `confidence_score` (1-10), `rationale`, and `strategy_type`
3. THE Trade_Selector SHALL discard picks with a `confidence_score` below the `min_confidence_score` from Intraday_Config
4. THE Trade_Selector SHALL validate that each pick has `target_price` above `entry_price` and `stop_loss_price` below `entry_price` for long trades
5. THE Trade_Selector SHALL validate that the risk-reward ratio (target minus entry divided by entry minus stop loss) is at least 2:1 for each pick
6. IF the BedrockClient returns an empty response or invalid JSON, THEN THE Trade_Selector SHALL log the error and abort the trading session without placing orders
7. THE Trade_Selector SHALL include ORB strategy candidates by requesting the LLM to identify stocks likely to break their opening range within the first 30 minutes

### Requirement 5: Position Sizing

**User Story:** As a trader, I want smart position sizing that maximizes profit potential while respecting capital limits, so that the system deploys capital efficiently within the daily capital limit.

#### Acceptance Criteria

1. THE Risk_Manager SHALL calculate position size for each trade as: `quantity = floor(per_trade_max_capital / entry_price)`, ensuring no single trade deploys more than `per_trade_max_capital` from Intraday_Config
2. THE Risk_Manager SHALL verify that the total capital deployed across all trades today (sum of `quantity * entry_price` for all trades placed today) does not exceed `daily_capital_limit` from Intraday_Config
3. THE Risk_Manager SHALL allocate larger position sizes to trades with higher confidence scores, proportional to the score, within the per-trade capital limit
4. WHEN the calculated position size results in a total deployed capital exceeding `daily_capital_limit` or available margin, THE Risk_Manager SHALL reduce the position size to fit within the remaining capital budget
5. THE Risk_Manager SHALL round position sizes to whole share quantities
6. THE Risk_Manager SHALL require a mandatory stop loss on every trade for safety, even though position sizing is capital-based rather than loss-based

### Requirement 6: Market Volatility Check

**User Story:** As a trader, I want the system to skip or reduce trading when the market is excessively volatile, so that it avoids high-risk conditions.

#### Acceptance Criteria

1. WHEN the India VIX value exceeds the `vix_threshold` from Intraday_Config, THE Risk_Manager SHALL reduce the maximum number of trades to half of `max_trades_per_day` (rounded down) and log the reason
2. WHEN the India VIX value exceeds 1.5 times the `vix_threshold`, THE Risk_Manager SHALL skip the entire trading session and log the reason
3. THE Risk_Manager SHALL fetch the India VIX value from the sector indices data returned by `fetch_sector_indices()`

### Requirement 7: Broker Authentication

**User Story:** As a trader, I want the system to handle daily broker login automatically for both Dhan and Zerodha, so that I only need to log in once each morning via the browser.

#### Acceptance Criteria

1. WHEN the Trader starts a live trading session, THE Auth_Server SHALL start a local Flask HTTP server on `http://127.0.0.1:5000/callback` to receive the broker's OAuth login redirect
2. WHEN the selected broker is Dhan, THE Auth_Server SHALL perform a 3-step OAuth flow: (a) POST to `https://auth.dhan.co/app/generate-consent?client_id={clientId}` with `app_id` and `app_secret` headers to obtain a `consentAppId`, (b) open `https://auth.dhan.co/login/consentApp-login?consentAppId={consentAppId}` in the default browser for user login, (c) POST to `https://auth.dhan.co/app/consumeApp-consent?tokenId={tokenId}` with `app_id` and `app_secret` headers to obtain the `access_token`
3. WHEN the selected broker is Zerodha, THE Auth_Server SHALL generate and open the Kite Connect login URL (`https://kite.zerodha.com/connect/login?v=3&api_key=<api_key>`) in the default browser, and upon redirect with a `request_token`, exchange it for an `access_token` using `kiteconnect.KiteConnect.generate_session(request_token, api_secret)`
4. THE Auth_Server SHALL persist the `access_token` to `config/.broker_session.json` with the current date and broker name, so that repeated runs on the same trading day reuse the token without re-login
5. WHEN a persisted `access_token` exists for the current date and the active broker, THE BrokerClient SHALL reuse the token and skip the login flow
6. IF the `access_token` is expired or invalid (broker API returns an authentication error), THEN THE BrokerClient SHALL delete the persisted session file and trigger a fresh login flow
7. WHEN operating in dry-run mode, THE Trader SHALL skip the broker login flow entirely

### Requirement 8: Broker Abstraction Layer

**User Story:** As a trader, I want a broker-agnostic interface so that the trading engine works identically regardless of whether I use Dhan or Zerodha.

#### Acceptance Criteria

1. THE BrokerClient abstract base class SHALL define the following abstract methods: `authenticate() -> bool`, `place_order(symbol, exchange, transaction_type, order_type, product_type, quantity, price, trigger_price) -> dict`, `modify_order(order_id, quantity, price, trigger_price, order_type) -> dict`, `cancel_order(order_id) -> dict`, `get_positions() -> list[dict]`, `get_margins() -> dict`
2. THE DhanBrokerClient SHALL implement `place_order()` by POSTing to `https://api.dhan.co/v2/orders` with `access-token` header, using `productType="INTRADAY"` and `exchangeSegment="NSE_EQ"` for intraday NSE equity trades
3. THE ZerodhaBrokerClient SHALL implement `place_order()` by calling `kite.place_order(variety="regular", exchange="NSE", product="MIS", ...)` using the `kiteconnect` SDK
4. THE DhanBrokerClient SHALL implement `get_positions()` by calling `GET https://api.dhan.co/v2/positions` and normalizing the response to the common position dict format
5. THE ZerodhaBrokerClient SHALL implement `get_positions()` by calling `kite.positions()` and extracting the `net` key, normalizing to the common position dict format
6. THE DhanBrokerClient SHALL implement `get_margins()` by calling `GET https://api.dhan.co/v2/fundlimit` and normalizing the response to the common margins dict format
7. THE ZerodhaBrokerClient SHALL implement `get_margins()` by calling `kite.margins()` and normalizing the response to the common margins dict format
8. THE Order_Executor, Position_Monitor, and Risk_Manager SHALL interact exclusively with the BrokerClient abstract interface, never with broker-specific implementations directly
9. WHEN `place_order()` returns a response, THE BrokerClient implementation SHALL normalize the broker-specific order ID to a generic `broker_order_id` field in the returned dict

### Requirement 9: Order Execution via Broker Abstraction

**User Story:** As a trader, I want the system to automatically place intraday orders through the active broker at market open, so that I do not need to manually enter trades.

#### Acceptance Criteria

1. THE Order_Executor SHALL use the active BrokerClient instance with `place_order()`, `modify_order()`, and `cancel_order()` methods
2. THE Order_Executor SHALL place LIMIT buy orders at the entry price specified by the Trade_Selector
3. THE Order_Executor SHALL place a corresponding stop-loss sell order for every buy order immediately after the buy order is confirmed
4. WHEN the `--live` flag is not provided, THE Trader SHALL operate in dry-run mode, logging all order details to the database and console without calling the broker API
5. WHEN the Trader operates in dry-run mode, THE Trader SHALL simulate order fills at the entry price and track simulated P&L
6. THE Order_Executor SHALL wait for `entry_delay_minutes` after 9:15 AM IST before placing the first order
7. IF an order placement fails, THEN THE Order_Executor SHALL log the error with the broker API response, skip that trade, and continue with remaining trades
8. THE Order_Executor SHALL store the `broker_order_id` for every placed order in the database for audit and reconciliation

### Requirement 10: Position Monitoring

**User Story:** As a trader, I want the system to monitor open positions every 5 minutes and automatically exit at target or stop loss, so that profits are captured and losses are limited.

#### Acceptance Criteria

1. WHILE positions are open, THE Position_Monitor SHALL fetch current positions from `BrokerClient.get_positions()` every `monitor_interval_seconds` from Intraday_Config
2. WHEN a position reaches the target price, THE Position_Monitor SHALL place a market sell order to close the position and log the profit
3. WHEN a position hits the stop loss price, THE Position_Monitor SHALL verify the stop-loss order has been triggered and log the loss
4. THE Position_Monitor SHALL implement trailing stop loss: WHEN a position gains more than `trailing_sl_trigger_pct` from entry, THE Position_Monitor SHALL move the stop loss upward to lock in at least 50% of the unrealized gain
5. THE Position_Monitor SHALL implement partial profit booking: WHEN a position reaches 50% of the distance between entry and target, THE Position_Monitor SHALL sell `partial_book_pct` percent of the position and move the stop loss to breakeven for the remainder
6. WHEN the current time reaches `force_exit_time` from Intraday_Config, THE Position_Monitor SHALL close all open positions with market sell orders regardless of profit or loss
7. IF a position monitoring cycle fails to fetch data from the broker, THEN THE Position_Monitor SHALL log the error, retry after 30 seconds, and continue monitoring

### Requirement 11: Daily Loss Cap Enforcement

**User Story:** As a trader, I want a hard daily loss cap of ₹5,000 that cannot be overridden, so that I never lose more than I can afford in a single day.

#### Acceptance Criteria

1. THE Risk_Manager SHALL track cumulative realized losses for the current trading day in the SQLite database
2. WHEN the cumulative realized loss for the day reaches or exceeds `daily_loss_cap` from Intraday_Config, THE Risk_Manager SHALL immediately cancel all pending orders and close all open positions
3. WHEN the daily loss cap is reached, THE Risk_Manager SHALL refuse to place any new orders for the remainder of the trading day and log the cap breach
4. THE Risk_Manager SHALL include unrealized losses from open positions when evaluating proximity to the daily loss cap, triggering a warning at 80% of the cap
5. THE Risk_Manager SHALL persist the daily loss tracking data in SQLite so that a system restart within the same trading day resumes with the correct cumulative loss

### Requirement 12: Database Schema Extension

**User Story:** As a trader, I want all intraday trades logged in the database with broker-agnostic field names, so that I have a complete audit trail and can analyze historical performance regardless of which broker was used.

#### Acceptance Criteria

1. THE DBManager SHALL create an `intraday_trades` table with columns: `id`, `trade_date`, `timestamp`, `symbol`, `tradingsymbol`, `action` (BUY/SELL), `order_type`, `product_type`, `quantity`, `price`, `trigger_price`, `broker_order_id`, `broker_name`, `status` (PENDING/OPEN/PARTIAL_BOOKED/CLOSED/STOPPED_OUT/FORCE_EXITED), `entry_price`, `exit_price`, `target_price`, `stop_loss_price`, `confidence_score`, `strategy_type`, `rationale`, `pnl`, `mode` (DRY_RUN/LIVE)
2. THE DBManager SHALL create an `intraday_daily_summary` table with columns: `id`, `trade_date`, `total_trades`, `winning_trades`, `losing_trades`, `total_pnl`, `total_realized_loss`, `max_drawdown`, `broker_name`, `mode`
3. THE DBManager SHALL create an `intraday_audit_log` table with columns: `id`, `timestamp`, `event_type`, `details_json`, `trade_id` (nullable FK to intraday_trades)
4. WHEN a trade is placed, modified, or closed, THE DBManager SHALL insert or update the corresponding row in `intraday_trades` with the current timestamp in IST
5. THE DBManager SHALL provide query methods: `get_trades_for_date(date)`, `get_daily_summary(date)`, `get_cumulative_pnl(start_date, end_date)`, `get_daily_realized_loss(date)`

### Requirement 13: End-of-Day Reporting

**User Story:** As a trader, I want a detailed end-of-day report saved as JSON, so that I can review each day's performance and refine the strategy.

#### Acceptance Criteria

1. WHEN all positions are closed for the day (either by target, stop loss, or force exit), THE Performance_Tracker SHALL generate a JSON report at `output/reports/intraday_YYYY-MM-DD.json`
2. THE Performance_Tracker SHALL include in the report: trade date, mode (DRY_RUN/LIVE), broker name, list of all trades with entry/exit prices and P&L, total P&L, win count, loss count, win rate percentage, average profit per winner, average loss per loser, expectancy per trade, and maximum intraday drawdown
3. THE Performance_Tracker SHALL include cumulative statistics: running total P&L across all trading days, overall win rate, and maximum drawdown
4. IF the report file already exists for the date, THEN THE Performance_Tracker SHALL overwrite the file with the latest data

### Requirement 14: Performance Analytics

**User Story:** As a trader, I want detailed performance analytics tracked over time, so that I can evaluate whether the system has a genuine edge.

#### Acceptance Criteria

1. THE Performance_Tracker SHALL calculate and store the following metrics per trading day: win rate, average profit per winning trade, average loss per losing trade, expectancy (average win times win rate minus average loss times loss rate), profit factor (gross profits divided by gross losses), and maximum drawdown
2. THE Performance_Tracker SHALL calculate strategy-level performance by grouping trades by `strategy_type` and computing win rate and average P&L per strategy
3. THE Performance_Tracker SHALL track cumulative P&L as a running total across all trading days
4. THE Performance_Tracker SHALL identify the maximum peak-to-trough drawdown across the cumulative P&L series

### Requirement 15: Dashboard Integration

**User Story:** As a trader, I want a live "Intraday Live" tab on the existing dashboard, so that I can monitor today's trades and historical performance in real time.

#### Acceptance Criteria

1. THE Dashboard_View SHALL add an "Intraday Live" tab to the existing `dashboard/index.html` file
2. THE Dashboard_View SHALL display a table of today's trades showing: symbol, entry price, current price, target, stop loss, quantity, unrealized P&L, and status (PENDING/OPEN/PARTIAL_BOOKED/CLOSED/STOPPED_OUT/FORCE_EXITED)
3. THE Dashboard_View SHALL display a daily loss tracker showing current realized loss against the `daily_loss_cap` as a progress bar
4. THE Dashboard_View SHALL display historical performance charts: cumulative P&L over time, daily P&L bar chart, and win rate trend
5. THE Dashboard_View SHALL read trade data from a JSON API file at `dashboard/api/intraday_latest.json` generated by the Performance_Tracker
6. THE Dashboard_View SHALL auto-refresh every 60 seconds when the trading session is active (between 9:15 AM and 3:30 PM IST)

### Requirement 16: Entry Point Script

**User Story:** As a trader, I want a single entry point script `run_intraday.py` that orchestrates the entire intraday trading workflow from scan to report.

#### Acceptance Criteria

1. THE Trader SHALL accept command-line arguments: `--live` (enable live trading, default is dry-run), `--skip-scan` (skip pre-market scan and use cached data), and `--force` (ignore time-of-day checks for testing)
2. WHEN started without `--force`, THE Trader SHALL verify the current time is between 8:30 AM and 3:30 PM IST on a weekday, and exit with an informative message if outside trading hours
3. THE Trader SHALL execute the following phases in order: load configuration, broker authentication (if live mode), pre-market scan, rule-based pre-filter, LLM trade selection, position sizing, volatility check, order execution, position monitoring loop, force exit at deadline, end-of-day report generation, and dashboard data update
4. THE Trader SHALL log every phase start and completion with timestamps to both console and the database
5. IF any critical phase fails (configuration load, broker authentication, pre-market scan after retry, LLM selection), THEN THE Trader SHALL abort gracefully, log the failure reason, and generate a partial report if any trades were placed

### Requirement 17: Audit Trail and Logging

**User Story:** As a trader, I want every action logged to the database and console, so that I can audit and debug the system behavior.

#### Acceptance Criteria

1. THE Trader SHALL log every action to the `intraday_audit_log` SQLite table including: scan results, pre-filter decisions, LLM prompts and responses, order placements, order modifications, position updates, stop loss adjustments, and exit decisions
2. THE Trader SHALL use Python logging with level INFO for normal operations and level ERROR for failures, with timestamps in IST
3. THE Trader SHALL store the full LLM prompt and response for each trading session in the database for post-analysis
4. WHEN operating in live mode, THE Trader SHALL log a prominent warning banner at startup indicating real money is at risk
