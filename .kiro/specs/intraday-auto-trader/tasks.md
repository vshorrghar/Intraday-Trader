# Implementation Plan: Intraday Auto-Trader

## Overview

Incremental implementation of the intraday auto-trading module for Wealth Builder Pro. The plan builds from foundational data models and configuration through broker abstraction, scanning/selection pipeline, execution/monitoring, risk management, reporting, and dashboard integration. Each task references specific requirements and design sections. All code is Python, using the existing project structure.

> **Future Enhancement:** ETF analysis support is out of scope for this plan but noted for a follow-up iteration.

## Tasks

- [x] 1. Create package structure, data models, and configuration
  - [x] 1.1 Create `intraday/` package with `__init__.py` and `models.py`
    - Create `intraday/__init__.py` with package docstring
    - Create `intraday/models.py` with dataclasses: `TradeSetup` (stock_name, nse_symbol, tradingsymbol, entry_price, target_price, stop_loss_price, confidence_score, rationale, strategy_type, quantity, risk_reward_ratio), `PositionState` enum (PENDING, OPEN, PARTIAL_BOOKED, CLOSED, STOPPED_OUT, FORCE_EXITED), and `IntraConfig` dataclass with all 14 config keys and their defaults as specified in the design
    - _Requirements: 1.1, 4.2_

  - [x] 1.2 Extend `config/config_loader.py` to load `IntraConfig`
    - Add `IntraConfig` loading from the `intraday` section of config.yaml
    - Implement default value fallback when the `intraday` section is missing (log warning)
    - Implement validation for each config key's valid range (e.g., daily_loss_cap > 0, 1 <= min_confidence_score <= 10, max_trades_per_day > 0); reject invalid values with logged error and use defaults
    - Validate that the selected broker's config section (dhan or zerodha) exists and has required keys; exit with error if missing
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ]* 1.3 Write property tests for config loading (Properties 1 & 2)
    - **Property 1: Config defaults and invalid value rejection** — For any subset of omitted keys and any out-of-range values, IntraConfig uses defaults for omitted/invalid keys and retains valid provided values
    - **Validates: Requirements 1.1, 1.7, 1.8**
    - **Property 2: Unsupported broker rejection** — For any broker string not in {"dhan", "zerodha"}, the broker factory raises ValueError
    - **Validates: Requirements 1.6**
    - Create `tests/test_intraday_properties.py` with these two property tests using `hypothesis`

  - [ ]* 1.4 Write unit tests for config loading edge cases
    - Test: missing intraday section uses all defaults
    - Test: missing broker config section exits with error
    - Test: complete valid config loads correctly
    - Test: invalid values (negative daily_loss_cap, confidence_score=15) fall back to defaults
    - Create `tests/test_intraday_config.py`
    - _Requirements: 1.1, 1.6, 1.7, 1.8, 1.9_

- [x] 2. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement broker abstraction layer
  - [x] 3.1 Create `intraday/broker_base.py` with `BrokerClient` ABC
    - Define abstract methods: `authenticate() -> bool`, `place_order(symbol, exchange, transaction_type, order_type, product_type, quantity, price, trigger_price) -> dict`, `modify_order(order_id, quantity, price, trigger_price, order_type) -> dict`, `cancel_order(order_id) -> dict`, `get_positions() -> list[dict]`, `get_margins() -> dict`
    - Add a `broker_factory(broker_name: str, config: dict) -> BrokerClient` function that returns DhanBrokerClient or ZerodhaBrokerClient, or raises ValueError for unsupported brokers
    - _Requirements: 8.1, 8.8, 1.4, 1.5, 1.6_

  - [x] 3.2 Create `intraday/dhan_broker.py` with `DhanBrokerClient`
    - Implement `place_order()` via POST to `https://api.dhan.co/v2/orders` with `productType="INTRADAY"`, `exchangeSegment="NSE_EQ"`, and `access-token` header
    - Implement `get_positions()` via GET `/v2/positions`, normalizing Dhan fields (tradingSymbol, netQty, buyAvg, sellAvg, realizedProfit, unrealizedProfit) to common dict format
    - Implement `get_margins()` via GET `/v2/fundlimit`, normalizing to `{"available_cash": float, "used_margin": float}`
    - Implement `modify_order()` and `cancel_order()` via Dhan API endpoints
    - Normalize all responses to include `broker_order_id` as a string
    - _Requirements: 8.2, 8.4, 8.6, 8.9_

  - [x] 3.3 Create `intraday/zerodha_broker.py` with `ZerodhaBrokerClient`
    - Implement `place_order()` via `kite.place_order(variety="regular", exchange="NSE", product="MIS", ...)`
    - Implement `get_positions()` via `kite.positions()["net"]`, normalizing to common dict format
    - Implement `get_margins()` via `kite.margins()`, normalizing to `{"available_cash": float, "used_margin": float}`
    - Implement `modify_order()` and `cancel_order()` via kiteconnect SDK
    - Normalize all responses to include `broker_order_id` as a string
    - _Requirements: 8.3, 8.5, 8.7, 8.9_

  - [ ]* 3.4 Write property test for broker order ID normalization (Property 10)
    - **Property 10: Broker order ID normalization** — For any valid order response from either broker, the normalized output contains a non-empty `broker_order_id` string
    - **Validates: Requirements 8.9**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 3.5 Write unit tests for broker abstraction
    - Test DhanBrokerClient with mocked HTTP responses (place_order, get_positions, get_margins)
    - Test ZerodhaBrokerClient with mocked kiteconnect SDK calls
    - Test broker_factory returns correct type or raises ValueError
    - Create `tests/test_intraday_broker.py`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_

- [x] 4. Implement OAuth authentication server
  - [x] 4.1 Create `intraday/auth_server.py` with Flask OAuth callback server
    - Implement Flask app on `http://127.0.0.1:5000/callback`
    - Implement Dhan 3-step OAuth: generate-consent → open browser → consume-consent to get access_token
    - Implement Zerodha Kite Connect flow: open login URL → receive request_token on callback → generate_session()
    - Persist token to `config/.broker_session.json` with `{"broker": str, "date": str, "access_token": str}`
    - On startup, check for existing same-day session file and reuse token (skip login)
    - Handle expired/invalid tokens: delete session file and trigger fresh login
    - Skip auth entirely in dry-run mode
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 4.2 Write unit tests for auth server
    - Test session file reuse for same-day token
    - Test expired token triggers re-auth
    - Test dry-run mode skips auth entirely
    - Create `tests/test_intraday_auth.py`
    - _Requirements: 7.4, 7.5, 7.6, 7.7_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement pre-market scanning and rule-based pre-filtering
  - [x] 6.1 Create `intraday/scanner.py` with `Pre_Market_Scanner`
    - Fetch NSE pre-open data, previous-day top gainers/losers, and sector indices using existing `fetchers/nse_market_movers.py` functions (`fetch_top_gainers`, `fetch_top_losers`, `fetch_most_active`, `fetch_sector_indices`)
    - Compute gap-up/gap-down percentages: `(pre_open_price - prev_close) / prev_close * 100`
    - Rank sectors by change percentage (descending) for momentum identification
    - Identify volume spikes by comparing pre-open volume to average where available
    - Implement retry logic: on fetch failure, retry once after 30 seconds; abort session if retry also fails
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 6.2 Create `intraday/selector.py` with rule-based pre-filter
    - Filter out stocks priced below `price_range_min` or above `price_range_max`
    - Filter out stocks with zero or missing volume
    - Flag stocks with `abs(gap_pct) > 3.0` as high-volatility candidates
    - Check sector alignment: verify stock belongs to a sector with positive momentum for long trades
    - Cap output at maximum 20 pre-filtered candidates
    - Log warning when fewer than 3 candidates pass the pre-filter
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 6.3 Write property tests for scanner and pre-filter (Properties 3, 4, 5)
    - **Property 3: Gap percentage calculation** — For any stock with positive pre_open_price and prev_close, gap_pct equals `(pre_open - prev_close) / prev_close * 100` with correct sign
    - **Validates: Requirements 2.2**
    - **Property 4: Sector momentum ranking** — For any list of SectorIndex with distinct change_pct, output is sorted descending by change_pct with same elements
    - **Validates: Requirements 2.3**
    - **Property 5: Pre-filter invariants** — For any stock list and valid price range config: all output stocks have price in range, volume > 0, high-volatility flagging is correct, and output has at most 20 stocks
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 6.4 Write unit tests for scanner and pre-filter
    - Test scanner with mocked NSE responses
    - Test scanner retry on failure and abort on double failure
    - Test pre-filter with 0 candidates, 1 candidate, 21+ candidates (cap at 20)
    - Create `tests/test_intraday_scanner.py` and `tests/test_intraday_selector.py`
    - _Requirements: 2.1, 2.5, 3.1, 3.2, 3.5, 3.6_

- [x] 7. Implement LLM trade selection
  - [x] 7.1 Add LLM trade selection to `intraday/selector.py`
    - Build system prompt with momentum analysis framework, risk rules (SL within 2%, R:R >= 2:1), price range, budget, and ORB strategy guidance as specified in the design
    - Build user prompt with date, VIX value, sector performance table, pre-filtered candidates table, gainers/losers summary
    - Send prompts to `BedrockClient.invoke()` and parse JSON response
    - Validate each pick: required fields present, confidence_score >= min_confidence_score, target > entry, SL < entry, R:R >= 2:1
    - Discard invalid picks, keep valid ones; abort session if zero valid picks remain
    - Handle empty/invalid JSON from LLM: log error and abort trading session
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 7.2 Write property test for trade setup validation (Property 6)
    - **Property 6: Trade setup validation** — For any dict representing an LLM pick, validation accepts iff all required fields present with correct types, confidence >= threshold, target > entry, SL < entry, and R:R >= 2.0
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 7.3 Write unit tests for LLM trade selection
    - Test with valid LLM response containing mixed-quality picks
    - Test with empty LLM response (abort)
    - Test with malformed JSON (abort)
    - Add to `tests/test_intraday_selector.py`
    - _Requirements: 4.2, 4.3, 4.6_

- [x] 8. Implement risk manager with position sizing and VIX checks
  - [x] 8.1 Create `intraday/risk_manager.py` with `Risk_Manager`
    - Calculate position size: `qty = per_trade_max_loss / (entry_price - stop_loss_price)`, rounded to whole shares
    - Allocate larger sizes to higher confidence scores proportionally
    - Verify total capital across all trades does not exceed available margin from `BrokerClient.get_margins()`; reduce sizes if needed
    - Implement VIX check: fetch India VIX from sector indices data; if VIX > 1.5x threshold → skip session; if VIX > threshold → halve max_trades_per_day
    - Implement daily loss cap tracking: track cumulative realized losses in SQLite; refuse new orders when cap reached; warn at 80% of cap including unrealized losses
    - Implement loss cap breach response: cancel all pending orders and close all open positions immediately
    - Persist daily loss tracking in SQLite for restart resilience
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 8.2 Write property tests for risk manager (Properties 7, 8, 9, 13)
    - **Property 7: Position sizing correctness** — For any valid TradeSetup, quantity is a positive integer, `qty * (entry - SL) <= per_trade_max_loss`, and higher confidence gets >= quantity
    - **Validates: Requirements 5.1, 5.3, 5.5**
    - **Property 8: Margin constraint** — For any list of sized trades and available_margin > 0, sum of `qty * entry_price` <= available_margin
    - **Validates: Requirements 5.2, 5.4**
    - **Property 9: VIX risk decisions** — For any vix_value, threshold, and max_trades: VIX > 1.5x → skip; threshold < VIX <= 1.5x → halve trades; VIX <= threshold → normal
    - **Validates: Requirements 6.1, 6.2**
    - **Property 13: Daily loss cap enforcement** — For any list of P&L values and cap > 0, cumulative loss computed correctly, cap breach flag correct, warning at 80%
    - **Validates: Requirements 11.1, 11.2, 11.4**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 8.3 Write unit tests for risk manager
    - Test position sizing with various entry/SL/confidence combinations
    - Test margin constraint reduces sizes when insufficient
    - Test VIX thresholds (normal, reduced, skip)
    - Test loss cap at exactly 100%, at 80% warning, restart with persisted loss
    - Create `tests/test_intraday_risk.py`
    - _Requirements: 5.1, 5.2, 6.1, 6.2, 11.1, 11.2, 11.4, 11.5_

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement database schema extension
  - [x] 10.1 Extend `database/db_manager.py` with intraday tables and query methods
    - Add `intraday_trades` table with all columns: id, trade_date, timestamp, symbol, tradingsymbol, action, order_type, product_type, quantity, price, trigger_price, broker_order_id, broker_name, status, entry_price, exit_price, target_price, stop_loss_price, confidence_score, strategy_type, rationale, pnl, mode
    - Add `intraday_daily_summary` table with columns: id, trade_date, total_trades, winning_trades, losing_trades, total_pnl, total_realized_loss, max_drawdown, broker_name, mode
    - Add `intraday_audit_log` table with columns: id, timestamp, event_type, details_json, trade_id (nullable FK)
    - Implement insert/update methods for trades (on place, modify, close)
    - Implement query methods: `get_trades_for_date(date)`, `get_daily_summary(date)`, `get_cumulative_pnl(start_date, end_date)`, `get_daily_realized_loss(date)`
    - All timestamps in IST
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 10.2 Write unit tests for database schema and queries
    - Test table creation, insert, update, and query methods
    - Test get_daily_realized_loss returns correct cumulative loss
    - Test IST timestamp formatting
    - Add to `tests/test_intraday_db.py`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 11. Implement order executor
  - [x] 11.1 Create `intraday/executor.py` with `Order_Executor`
    - Use the active BrokerClient instance for all order operations (place_order, modify_order, cancel_order)
    - Place LIMIT buy orders at entry price from Trade_Selector
    - Place corresponding stop-loss sell order immediately after buy confirmation
    - Wait for `entry_delay_minutes` after 9:15 AM IST before placing first order
    - In dry-run mode (no `--live` flag): log all order details to database and console without calling broker API; simulate fills at entry price and track simulated P&L
    - On order failure: log error with broker API response, skip that trade, continue with remaining
    - Store `broker_order_id` for every placed order in the database
    - Interact exclusively with BrokerClient ABC, never broker-specific implementations
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 8.8_

  - [ ]* 11.2 Write unit tests for order executor
    - Test dry-run mode logs orders without calling broker
    - Test live order placement with mocked BrokerClient
    - Test order failure handling (skip and continue)
    - Test entry delay timing logic
    - Create `tests/test_intraday_executor.py`
    - _Requirements: 9.1, 9.2, 9.4, 9.5, 9.7_

- [x] 12. Implement position monitor with state machine
  - [x] 12.1 Create `intraday/monitor.py` with `Position_Monitor`
    - Fetch positions from `BrokerClient.get_positions()` every `monitor_interval_seconds`
    - Implement state machine: PENDING → OPEN (filled), OPEN → CLOSED (target hit), OPEN → STOPPED_OUT (SL triggered), OPEN → PARTIAL_BOOKED (partial profit), OPEN → FORCE_EXITED (3:15 PM), PARTIAL_BOOKED → CLOSED/STOPPED_OUT/FORCE_EXITED
    - Target hit: place market sell to close position, log profit
    - Stop loss: verify SL order triggered, log loss
    - Trailing stop loss: when position gains > `trailing_sl_trigger_pct` from entry, move SL to `entry + 0.5 * (current - entry)`
    - Partial profit booking: when price reaches 50% of (target - entry) above entry, sell `partial_book_pct`% of position, move SL to breakeven for remainder
    - Force exit at `force_exit_time`: close all open positions with market sell regardless of P&L
    - On fetch failure: log error, retry after 30 seconds, continue monitoring
    - Update trade status in database after each state transition
    - Interact exclusively with BrokerClient ABC
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 8.8_

  - [ ]* 12.2 Write property tests for monitor calculations (Properties 11, 12)
    - **Property 11: Trailing stop loss calculation** — For any open position where gain > trigger_pct, new SL = entry + 0.5 * (current - entry), and new SL >= entry
    - **Validates: Requirements 10.4**
    - **Property 12: Partial profit booking** — For any position at 50%+ of target distance, partial_sell_qty = floor(qty * partial_book_pct / 100), remainder SL = entry (breakeven)
    - **Validates: Requirements 10.5**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 12.3 Write unit tests for position monitor
    - Test state transitions: PENDING→OPEN, OPEN→CLOSED, OPEN→STOPPED_OUT, OPEN→FORCE_EXITED, OPEN→PARTIAL_BOOKED
    - Test trailing SL adjustment
    - Test partial profit booking
    - Test force exit at deadline
    - Test fetch failure retry
    - Create `tests/test_intraday_monitor.py`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 13. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement reporting and performance analytics
  - [x] 14.1 Create `intraday/reporter.py` with `Performance_Tracker`
    - Generate EOD JSON report at `output/reports/intraday_YYYY-MM-DD.json` with: trade date, mode, broker name, all trades with entry/exit/P&L, total P&L, win/loss counts, win rate, avg profit/loss per winner/loser, expectancy, max intraday drawdown
    - Include cumulative statistics: running total P&L, overall win rate, max drawdown across all days
    - Calculate strategy-level performance grouped by `strategy_type`
    - Calculate profit factor: gross profits / gross losses
    - Track cumulative P&L as running total across all trading days
    - Compute maximum peak-to-trough drawdown across cumulative P&L series
    - Overwrite report file if it already exists for the date
    - Insert/update `intraday_daily_summary` row in database
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 14.1, 14.2, 14.3, 14.4_

  - [ ]* 14.2 Write property tests for performance metrics (Properties 14, 15)
    - **Property 14: Performance metrics calculation** — For any non-empty trade list: win_rate, avg_profit, avg_loss, expectancy, and profit_factor are computed correctly per formulas in design
    - **Validates: Requirements 13.2, 14.1**
    - **Property 15: Maximum drawdown algorithm** — For any daily P&L sequence, max_drawdown equals largest peak-to-trough decline in cumulative series; monotonically increasing series → drawdown = 0
    - **Validates: Requirements 14.4**
    - Add to `tests/test_intraday_properties.py`

  - [ ]* 14.3 Write unit tests for reporter
    - Test EOD report JSON structure and content
    - Test cumulative statistics across multiple days
    - Test strategy-level grouping
    - Test file overwrite behavior
    - Create `tests/test_intraday_reporter.py`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 14.1, 14.2_

- [x] 15. Implement dashboard integration
  - [x] 15.1 Create `intraday/dashboard.py` — Dashboard JSON API writer
    - Write `dashboard/api/intraday_latest.json` with structure: updated_at, mode, broker, session_active, today (trades, total_pnl, realized_loss, daily_loss_cap, loss_cap_pct), history (daily_pnl array, cumulative_pnl, win_rate, total_days)
    - Update JSON file after each monitoring cycle and at EOD
    - _Requirements: 15.5_

  - [x] 15.2 Add "Intraday Live" tab to `dashboard/index.html`
    - Add tab navigation for "Intraday Live" alongside existing tabs
    - Display trades table: symbol, entry price, current price, target, stop loss, quantity, unrealized P&L, status (color-coded)
    - Display daily loss tracker as progress bar (green → yellow at 50% → red at 80%) showing realized loss vs daily_loss_cap
    - Display historical charts using Chart.js: cumulative P&L line chart, daily P&L bar chart, win rate trend
    - Read data from `dashboard/api/intraday_latest.json`
    - Auto-refresh every 60 seconds during market hours (9:15 AM – 3:30 PM IST)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

  - [ ]* 15.3 Write unit tests for dashboard JSON generation
    - Test JSON file structure matches expected schema
    - Test correct P&L calculations in dashboard data
    - Add to `tests/test_intraday_dashboard.py`
    - _Requirements: 15.5_

- [x] 16. Implement audit trail and logging
  - [x] 16.1 Add audit logging throughout all modules
    - Log every action to `intraday_audit_log` table: scan results, pre-filter decisions, LLM prompts/responses, order placements, modifications, position updates, SL adjustments, exit decisions
    - Use Python logging with INFO for normal operations, ERROR for failures, all timestamps in IST
    - Store full LLM prompt and response in database for post-analysis
    - Log prominent warning banner at startup in live mode indicating real money is at risk
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [x] 17. Implement entry point script and wire everything together
  - [x] 17.1 Create `run_intraday.py` entry point script
    - Accept CLI arguments: `--live` (enable live trading, default dry-run), `--skip-scan` (use cached data), `--force` (ignore time-of-day checks)
    - Without `--force`: verify current time is 8:30 AM – 3:30 PM IST on a weekday; exit with message if outside hours
    - Execute phases in order: load config → broker auth (if live) → pre-market scan → rule-based pre-filter → LLM trade selection → position sizing → VIX check → order execution → position monitoring loop → force exit at deadline → EOD report → dashboard update
    - Log every phase start/completion with timestamps to console and database
    - On critical phase failure (config, auth, scan after retry, LLM): abort gracefully, log reason, generate partial report if any trades placed
    - Wire all modules together: Scanner → Selector → Risk_Manager → Executor → Monitor → Reporter → Dashboard
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [ ]* 17.2 Write integration tests for the full pipeline
    - Test end-to-end flow with all broker/NSE/LLM calls mocked
    - Test dry-run mode completes full pipeline without broker calls
    - Test abort on LLM failure generates partial report
    - Test time-of-day check enforcement
    - Create `tests/test_intraday_integration.py`
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

- [x] 18. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after major milestones
- Property tests (15 total) validate universal correctness properties from the design document
- Unit tests validate specific scenarios, edge cases, and integration points
- All broker interactions go through the BrokerClient ABC — no module touches broker-specific code directly
- ETF analysis support is a future enhancement, not included in this plan
