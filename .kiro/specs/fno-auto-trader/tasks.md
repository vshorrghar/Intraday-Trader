# Implementation Plan: F&O Auto-Trader

## Overview

Build the `fno/` Python package that extends Wealth Builder Pro with automated Nifty, BankNifty, and FinNifty index options and futures trading. The implementation follows a priority order: package structure + models + config first, dashboard integration with demo data early (so the user can see something today), then core engines (Greeks, symbols, quant), strategy + execution + monitoring, risk + reporting, and finally entry point wiring.

## Tasks

- [x] 1. Create fno/ package structure, models, and config
  - [x] 1.1 Create `fno/__init__.py` and `fno/models.py` with all dataclasses
    - Create `fno/__init__.py` with package docstring
    - Implement `StrategyLeg`, `FnOPositionState` (Enum), `MarketRegime` (Enum), `FnOStrategySetup`, `OptionStrike`, `OptionChainSnapshot`, `QuantSignals`, `Greeks` dataclasses in `fno/models.py` exactly as specified in the design
    - Include all computed properties (`quantity`, `is_sell` on `StrategyLeg`)
    - _Requirements: 4.8, 6.5, 9.1, 9.2_

  - [x] 1.2 Create `fno/config.py` with FnO_Config dataclass and validation
    - Implement `FnO_Config` dataclass with all 22 config keys and documented defaults
    - Implement `load_fno_config(yaml_dict)` that loads from the `fno:` section of config.yaml
    - Handle missing `fno` section (use all defaults + log warning)
    - Handle invalid values (reject, use default, log error) for each key: negative `daily_loss_limit`, zero `max_positions`, `min_confidence_score` > 10, `mode` not in ["paper", "live"], `max_lots_per_trade` < 1, etc.
    - Validate that the selected broker's config section exists and has required API keys
    - Exit with clear error if broker config section is missing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [ ]* 1.3 Write property test for config defaults and validation
    - **Property 1: Config defaults and invalid value rejection**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.8, 1.9, 1.10**

  - [x] 1.4 Add `fno:` section to `config/config.yaml` with all default values
    - Add the complete `fno:` config block as specified in the design's Config Schema Addition
    - _Requirements: 1.1_

- [x] 2. Database schema extension for F&O
  - [x] 2.1 Extend `database/db_manager.py` with 5 new F&O tables
    - Add `fno_trades` table with all columns (id, trade_date, timestamp, index_name, tradingsymbol, option_type, strike_price, expiry_date, action, order_type, quantity, lots, price, trigger_price, broker_order_id, broker_name, status, entry_price, exit_price, pnl, mode, strategy_id FK)
    - Add `fno_strategies` table with all columns (id, trade_date, timestamp, strategy_type, index_name, legs_json, net_premium, max_profit, max_loss, net_delta, net_gamma, net_theta, net_vega, status, entry_time, exit_time, realized_pnl, mode, confidence_score, confluence_score, rationale)
    - Add `fno_daily_summary` table (id, trade_date, total_strategies, winning_strategies, losing_strategies, total_pnl, total_realized_loss, max_drawdown, broker_name, mode, paper_capital_remaining)
    - Add `fno_iv_history` table (id, date, index_name, atm_iv, spot_close)
    - Add `fno_spot_history` table (id, date, index_name, close_price, log_return)
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 16.8, 16.9_

  - [x] 2.2 Add F&O query methods to `database/db_manager.py`
    - Implement `insert_fno_trade(**kwargs)`, `update_fno_trade(trade_id, **kwargs)`
    - Implement `insert_fno_strategy(**kwargs)`, `update_fno_strategy(strategy_id, **kwargs)`
    - Implement `get_fno_trades_for_date(date)`, `get_fno_strategies_for_date(date)`
    - Implement `get_fno_daily_summary(date)`, `upsert_fno_daily_summary(date, **kwargs)`
    - Implement `get_fno_cumulative_pnl(start_date, end_date)`, `get_fno_daily_realized_loss(date)`
    - Implement `get_paper_trading_history(weeks)` — returns paper trading summary for the last N weeks
    - Implement `insert_fno_iv_history(date, index, atm_iv, spot_close)`, `get_fno_iv_history(index, days)`
    - Implement `insert_fno_spot_history(date, index, close, log_return)`, `get_fno_spot_history(index, days)`
    - _Requirements: 9.4, 9.5, 9.6, 16.8, 16.9_

- [x] 3. Dashboard integration with demo data
  - [x] 3.1 Create `fno/dashboard.py` — F&O Dashboard JSON writer
    - Implement `write_fno_dashboard_json(strategies, config, db, mode, broker, session_active)` following the pattern in `intraday/dashboard.py`
    - Write to `dashboard/api/fno_latest.json` with the exact JSON structure from the design: updated_at, mode, broker, session_active, paper_capital_remaining, today (strategies array with strategy_type/index/legs_summary/entry_premium/current_premium/unrealized_pnl/status/confluence_score/net_greeks, total_pnl, realized_loss, daily_loss_cap, loss_cap_pct, net_greeks), history (daily_pnl, cumulative_pnl, win_rate, total_days, strategy_breakdown)
    - Generate demo data on first run (2-3 sample strategies with realistic premiums) so the dashboard shows something immediately
    - _Requirements: 11.5, 11.8_

  - [x] 3.2 Add "F&O Live" tab to `dashboard/index.html`
    - Add a third tab button "🎯 F&O Live" alongside existing "Portfolio" and "⚡ Intraday Live" tabs
    - Create `tab-fno` container with: summary card (mode, today P&L, active strategies, paper capital remaining, net Greeks), daily loss tracker progress bar (green→yellow→red), strategies table (strategy_type, index, legs_summary, entry_premium, current_premium, unrealized_pnl, status, confluence_score, net_greeks), cumulative P&L chart, daily P&L chart, strategy breakdown chart
    - Implement `loadFnoData()` function that fetches `api/fno_latest.json` and populates all elements
    - Add auto-refresh every 60 seconds during market hours (9:15 AM – 3:30 PM IST)
    - Ensure F&O data is read independently from equity intraday data
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [ ]* 3.3 Write unit tests for dashboard JSON structure
    - Verify JSON output matches the exact structure the frontend expects
    - Test with empty strategies, single strategy, multiple strategies
    - _Requirements: 11.5_

- [x] 4. Checkpoint — Verify package structure, config, DB, and dashboard
  - Ensure all tests pass, ask the user if questions arise.
  - User should be able to open `dashboard/index.html` and see the F&O Live tab with demo data.

- [x] 5. Greeks calculator and symbol builder
  - [x] 5.1 Implement `fno/greeks.py` — FnO_Greeks_Calculator
    - Implement `compute_greeks(spot, strike, tte, iv, option_type, r)` using Black-Scholes for European-style index options
    - Implement `compute_option_price(spot, strike, tte, iv, option_type, r)` — Black-Scholes pricing
    - Implement `implied_volatility(market_price, spot, strike, tte, option_type, r)` — Newton-Raphson root finding with max 100 iterations
    - Implement `strategy_greeks(legs, spot)` — net Greeks for multi-leg strategy (sum of leg Greeks × direction × quantity)
    - Handle edge cases: zero TTE (return intrinsic value), deep ITM (delta → ±1), deep OTM (delta → 0)
    - Use `RISK_FREE_RATE = 0.07` (India 10Y govt bond yield)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.2 Write property test for Black-Scholes Greeks round-trip
    - **Property 6: Black-Scholes Greeks round-trip**
    - **Validates: Requirements 3.1, 3.2, 3.4, 3.5**

  - [ ]* 5.3 Write property test for net strategy Greeks additivity
    - **Property 7: Net strategy Greeks are additive**
    - **Validates: Requirements 3.3**

  - [x] 5.4 Implement `fno/symbols.py` — Symbol_Builder
    - Implement `build_dhan(index, expiry, strike, option_type)` — e.g., `NIFTY25JUL24500CE`
    - Implement `build_zerodha(index, expiry, strike, option_type)` — e.g., `NIFTY2572524500CE`
    - Implement `build_futures_dhan(index, expiry)` and `build_futures_zerodha(index, expiry)`
    - Implement `parse_symbol(symbol, broker)` — parse back to {index, expiry, strike, option_type}
    - Include `MONTH_CODES_ZERODHA` and `MONTH_NAMES_DHAN` mappings
    - Validate inputs: raise `ValueError` for invalid index, negative/zero strike, invalid option_type
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ]* 5.5 Write property test for symbol construction round-trip
    - **Property 13: Symbol construction round-trip**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

  - [ ]* 5.6 Write property test for invalid symbol input rejection
    - **Property 14: Invalid symbol inputs rejected**
    - **Validates: Requirements 13.5**

- [x] 6. Option chain fetcher and quant engine
  - [x] 6.1 Implement `fno/option_chain.py` — Option_Chain_Fetcher
    - Implement `fetch_option_chain(index, broker)` that retrieves complete option chain for current and next weekly expiry
    - Identify ATM strike (closest to spot, lower on tie)
    - Compute bid-ask spread for each contract
    - Compute PCR (total Put OI / total Call OI)
    - Compute Max Pain (strike minimizing total pain function)
    - Identify highest OI strikes for Calls and Puts separately
    - Maintain a rolling buffer of last 6 snapshots (~30 min) for OI velocity computation
    - Implement retry logic: retry once after 30s on failure, abort session if retry fails
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11_

  - [ ]* 6.2 Write property tests for option chain computations
    - **Property 2: ATM strike identification** — Validates: Requirements 2.3
    - **Property 3: PCR computation** — Validates: Requirements 2.9, 4.5
    - **Property 4: Max Pain computation** — Validates: Requirements 2.10, 4.6
    - **Property 5: Option chain snapshot buffer** — Validates: Requirements 2.8

  - [x] 6.3 Implement `fno/quant_engine.py` — Quant_Edge_Engine
    - Implement `compute_all_signals(chain, greeks_calc)` — orchestrator for all 6 signals
    - Implement `compute_iv_percentile(index, current_atm_iv)` — IVP from last 252 days of IV history, bootstrap from 30 days on first run
    - Implement `compute_oi_velocity(snapshots)` — OI change between latest and ~30min-ago snapshot, flag >500K changes
    - Implement `compute_iv_skew(chain, greeks_calc)` — 25-delta Put IV minus 25-delta Call IV, compare to 5-day average
    - Implement `compute_gex(chain, greeks_calc)` — GEX at each strike, gravity center, regime (PINNED/TRENDING)
    - Implement `compute_vrp(index, atm_iv)` — VRP = ATM IV - RV_20d, signal mapping
    - Implement `compute_confluence_score(...)` — weighted composite (0-100) with sub-score breakdown and strategy-type-specific thresholds
    - Implement `get_adaptive_weights(strategy_type)` — adjust weights after 20+ days based on historical win rates
    - Handle insufficient history gracefully: use neutral defaults, reduce sub-score contribution, log warning
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12_

  - [ ]* 6.4 Write property tests for quant engine signals
    - **Property 25: IV Percentile computation** — Validates: Requirements 16.1
    - **Property 26: OI Change Velocity** — Validates: Requirements 16.2
    - **Property 27: VRP computation** — Validates: Requirements 16.5
    - **Property 28: Confluence score bounds and thresholds** — Validates: Requirements 16.6, 16.12
    - **Property 30: Adaptive strategy weighting** — Validates: Requirements 16.11

- [x] 7. Checkpoint — Verify Greeks, symbols, option chain, and quant engine
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Strategy engine
  - [x] 8.1 Implement `fno/strategy_engine.py` — FnO_Strategy_Engine
    - Implement `MarketRegimeClassifier` — classify into SIDEWAYS, TRENDING_UP, TRENDING_DOWN, HIGH_VOLATILITY based on VIX, 3-day price action, and OI data
    - Implement the 7-strategy playbook with entry conditions, strike selection (OI-based support/resistance), and exit rules
    - Implement LLM integration: construct system prompt + user prompt with all quant data, call AWS Bedrock Claude Sonnet, parse JSON response
    - Implement strategy validation: (a) type in playbook, (b) valid strikes in chain, (c) confidence >= min, (d) expiry >= min_days_to_expiry, (e) max_loss <= per_trade_max_capital, (f) confluence meets threshold
    - Implement time-of-day rules: no SHORT_STRADDLE/SHORT_STRANGLE after 14:00, no DIRECTIONAL buys after 13:00
    - Implement expiry-day rules: only SHORT_STRADDLE, IRON_CONDOR, DIRECTIONAL allowed
    - Reject naked selling when paper history < 2 weeks
    - Compute max loss for each strategy (iron condor: max(W_c, W_p) × lots - premium; spreads: (W - P) × lots)
    - Abort on empty/invalid LLM response
    - Log regime, PCR, max pain, OI levels, full LLM prompt/response to audit trail
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14_

  - [ ]* 8.2 Write property tests for strategy engine
    - **Property 8: Market regime classification** — Validates: Requirements 4.3
    - **Property 9: Strategy validation** — Validates: Requirements 4.7, 4.9
    - **Property 10: Time-of-day rules** — Validates: Requirements 4.10
    - **Property 11: Expiry-day strategy filtering** — Validates: Requirements 4.11
    - **Property 29: Max loss computation for defined-risk strategies** — Validates: Requirements 4.9

- [x] 9. Broker abstraction extension
  - [x] 9.1 Extend `intraday/broker_base.py` with F&O abstract methods
    - Add `place_fno_order(tradingsymbol, exchange, transaction_type, order_type, product_type, quantity, price, trigger_price)` abstract method
    - Add `get_fno_positions()` abstract method returning normalized F&O positions
    - Add `get_fno_margins()` abstract method returning available_margin, used_margin, span_margin, exposure_margin
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 9.2 Implement F&O methods in `intraday/dhan_broker.py`
    - Implement `place_fno_order()` using Dhan API with `exchangeSegment="NSE_FNO"` and Dhan-format symbols
    - Implement `get_fno_positions()` with Dhan API, normalize to common interface
    - Implement `get_fno_margins()` with Dhan API
    - _Requirements: 12.4, 12.6, 12.7_

  - [x] 9.3 Implement F&O methods in `intraday/zerodha_broker.py`
    - Implement `place_fno_order()` using Kite Connect SDK with `exchange="NFO"` and Zerodha-format symbols
    - Implement `get_fno_positions()` with Kite API, normalize to common interface
    - Implement `get_fno_margins()` with Kite API
    - _Requirements: 12.5, 12.6, 12.7_

- [x] 10. Order executor and paper engine
  - [x] 10.1 Implement `fno/executor.py` — FnO_Order_Executor
    - Implement `execute_strategy(strategy, broker, config, db)` — place all legs of a multi-leg strategy
    - Place SELL legs first, then BUY legs (premium collection ordering)
    - Construct correct trading symbol per broker using Symbol_Builder
    - Wait `entry_delay_minutes` after 9:15 AM before first order
    - Implement rollback: if any leg fails, cancel all previously placed legs
    - Store broker_order_id for every placed order in DB
    - Log prominent warning banner at startup in live mode
    - Log all actions to audit trail with FNO_ prefixed event types
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 15.1_

  - [ ]* 10.2 Write property test for multi-leg execution ordering
    - **Property 12: Multi-leg execution ordering**
    - **Validates: Requirements 5.2**

  - [x] 10.3 Implement `fno/paper_engine.py` — Paper_Trade_Engine
    - Maintain virtual capital balance starting at `paper_capital`
    - Simulate order fills at last traded price from option chain
    - Deduct estimated SPAN + exposure margin on position open, release on close
    - Track simulated P&L per strategy
    - Enforce all same risk rules as live trading
    - Store all paper trades with `mode = "PAPER"` in DB
    - Generate same dashboard data as live, labeled as paper
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 11. Position monitor
  - [x] 11.1 Implement `fno/monitor.py` — FnO_Position_Monitor
    - Fetch positions every `monitor_interval_seconds` via BrokerClient or paper engine
    - Compute real-time Greeks for all open positions, aggregate net delta/gamma/theta/vega
    - Implement position state machine: PENDING → OPEN → PARTIAL_BOOKED → CLOSED / STOPPED_OUT / FORCE_EXITED / EXPIRED
    - Implement premium-based stop loss: trigger when combined premium moves against by `trailing_sl_trigger_pct` of collected premium
    - Implement partial profit booking: close when profit reaches `partial_book_pct` of max_profit
    - Implement force exit at `force_exit_time` IST with market orders
    - Implement expiry-day OTM close: close OTM positions within 1 day of expiry
    - Log delta/vega exposure warnings when thresholds exceeded
    - Update trade status in DB after each state transition
    - Log Greeks snapshots to audit trail on every position update
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 15.3_

  - [ ]* 11.2 Write property tests for position monitor
    - **Property 15: Position state machine transitions** — Validates: Requirements 6.5
    - **Property 16: Premium-based stop loss trigger** — Validates: Requirements 6.6
    - **Property 17: Partial profit booking** — Validates: Requirements 6.7
    - **Property 18: Greeks exposure warnings** — Validates: Requirements 6.3, 6.4

- [x] 12. Checkpoint — Verify strategy engine, executor, paper engine, and monitor
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Risk manager and reporter
  - [x] 13.1 Implement `fno/risk_manager.py` — FnO_Risk_Manager
    - Compute estimated SPAN + exposure margin for each strategy (broker API or local approximation)
    - Reject trade if margin exceeds available margin (real or paper)
    - Enforce `max_positions` limit
    - Enforce `max_lots_per_trade` per leg
    - Track cumulative realized losses, refuse new orders at `daily_loss_limit`
    - Log warning at 80% of loss cap (including unrealized losses)
    - On loss cap breach: cancel all pending, close all open positions
    - Implement VIX-based session control: skip if VIX > 1.5× threshold, halve max_positions if VIX > threshold
    - Reject naked selling without sufficient margin for 2-sigma move
    - Persist daily loss tracking state in DB for restart resilience
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [ ]* 13.2 Write property tests for risk manager
    - **Property 19: Margin enforcement** — Validates: Requirements 7.1, 7.2, 8.3
    - **Property 20: Position and lot limits** — Validates: Requirements 7.3, 7.4
    - **Property 21: Daily loss cap enforcement** — Validates: Requirements 7.5, 7.6
    - **Property 22: VIX-based session control** — Validates: Requirements 7.8

  - [x] 13.3 Implement `fno/reporter.py` — FnO_Reporter
    - Generate EOD JSON report at `output/reports/fno_YYYY-MM-DD.json` with all strategies, legs, P&L, win/loss counts, win rate
    - Compute strategy-level performance metrics grouped by strategy type: win rate, avg profit, avg loss, profit factor
    - Compute cumulative P&L as running total across all F&O trading days
    - Compute maximum peak-to-trough drawdown
    - Compute expectancy: `avg_profit × win_rate - |avg_loss| × (1 - win_rate)`
    - Track theta decay P&L separately for premium-selling strategies
    - Overwrite report file if it already exists for the date
    - Upsert `fno_daily_summary` row in DB
    - Update `dashboard/api/fno_latest.json` via `fno/dashboard.py`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [ ]* 13.4 Write property tests for reporter metrics
    - **Property 23: Performance metrics computation** — Validates: Requirements 10.2, 10.3, 10.5
    - **Property 24: Maximum drawdown** — Validates: Requirements 10.4

- [x] 14. Entry point and orchestration
  - [x] 14.1 Create `run_fno.py` — CLI entry point
    - Accept CLI arguments: `--live`, `--skip-scan`, `--force`
    - Verify trading hours (8:30 AM – 3:30 PM IST weekday) unless `--force`
    - Execute pipeline in order: load config → broker auth (if live) → fetch option chains → compute Greeks → compute quant signals → LLM strategy selection → risk validation → order execution → position monitoring loop → force exit at deadline → EOD report → dashboard update
    - Verify paper trading history before allowing `--live` mode
    - Abort gracefully on critical phase failure, generate partial report if strategies were placed
    - Log every phase start/completion with timestamps to console and audit log
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 15.1, 15.2, 15.3, 15.4_

  - [x] 14.2 Wire paper mode transition check
    - In `fno/config.py`, implement `verify_paper_history(db, weeks)` that checks DB for `paper_trading_weeks` of profitable paper history before allowing live mode
    - _Requirements: 1.7, 8.8_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Verify end-to-end: `python run_fno.py --force` runs in paper mode, places demo strategies, writes dashboard JSON, and the F&O Live tab shows data.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 30 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Priority ordering ensures the user sees dummy trades on the dashboard as early as possible (after task 4)
- All code is Python, matching the design document's language
