# Implementation Plan: Wealth Builder Pro

## Overview

Implement a Python-based personal wealth intelligence platform for Indian retail investors. The system parses Groww broker XLSX exports, fetches live market data from Indian financial sources, performs AI-driven portfolio analysis via AWS Bedrock Claude, delivers three daily HTML email reports via AWS SES, and serves a static web dashboard via Nginx. Implementation proceeds layer by layer: config → data models → parsers → fetchers → LLM → reports → database → pipelines → dashboard → deployment.

## Tasks

- [x] 1. Set up project structure, configuration, and data models
  - [x] 1.1 Create project directory structure and install dependencies
    - Create directories: `config/`, `parsers/`, `fetchers/`, `llm/`, `reports/`, `database/`, `scripts/`, `templates/`, `tests/unit/`, `tests/property/`
    - Create `requirements.txt` with: openpyxl, boto3, jinja2, pyyaml, requests, feedparser, beautifulsoup4, lxml, pytest, hypothesis
    - Create `__init__.py` files for each package
    - _Requirements: 24.1_

  - [x] 1.2 Implement configuration loader (`config/config_loader.py`)
    - Define `AppConfig` dataclass with all required fields (aws_region, s3_bucket, ses_sender, ses_recipient, bedrock_model_id, stocks_xlsx, mf_xlsx, pnl_xlsx, invit_isins, db_path, cache_dir, dashboard_output_dir)
    - Implement `load_config(config_path: str) -> AppConfig` that reads YAML and validates all required keys
    - Raise `ValueError` with missing key name if any required key is absent
    - Create sample `config/config.yaml` with placeholder values
    - _Requirements: 24.1, 24.2, 24.3, 24.4_

  - [x]* 1.3 Write property tests for configuration loading
    - **Property 29: Configuration loading completeness**
    - **Property 30: Configuration missing key error**
    - **Validates: Requirements 24.1, 24.2, 24.3, 24.4**

  - [x]* 1.4 Write unit tests for configuration loader
    - Test loading valid config, missing keys, invalid types
    - _Requirements: 24.1, 24.4_

  - [x] 1.5 Define all data model dataclasses
    - Create `parsers/models.py` with `StockHolding`, `MFHolding`, `TradeRecord`, `ScripSummary` dataclasses
    - Create `fetchers/models.py` with `BhavcopyRecord`, `FIIDIIFlow`, `DealRecord`, `StockFundamentals`, `NAVRecord`, `IPORecord`, `NewsItem`, `IndexData` dataclasses
    - Create `llm/models.py` with `StockVerdict`, `MFRecommendation`, `MarketOpportunity`, `IntradaySetup` dataclasses
    - Add JSON serialization/deserialization methods (`to_dict` / `from_dict`) to all parser dataclasses
    - _Requirements: 1.2, 1.7, 2.2, 2.5, 3.1, 3.2_

  - [x]* 1.6 Write property tests for data model round-trips
    - **Property 1: StockHolding JSON round-trip**
    - **Property 2: MFHolding JSON round-trip**
    - **Property 3: P&L data JSON round-trip**
    - **Validates: Requirements 1.8, 2.6, 3.6**


- [x] 2. Implement parsers layer
  - [x] 2.1 Implement Stocks Parser (`parsers/groww_stocks_parser.py`)
    - Implement `parse_stocks_xlsx(file_path: str) -> list[StockHolding]` reading header at row 11, data from row 12, columns B-I
    - Implement `classify_holding(isin: str, name: str, invit_isins: set[str]) -> str` returning exactly one of "stock", "etf", "invit"
    - Raise `ValueError` if header structure at row 11 doesn't match expected columns
    - Log and skip rows with missing/malformed values
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 22.1, 22.2, 22.3, 22.4, 22.5_

  - [x]* 2.2 Write property tests for Stocks Parser
    - **Property 4: Holding classification correctness and exclusivity**
    - **Property 5: Stock column extraction completeness**
    - **Validates: Requirements 1.2, 1.3, 1.4, 22.1, 22.2, 22.3, 22.4, 22.5**

  - [x]* 2.3 Write unit tests for Stocks Parser
    - Test valid XLSX parsing, wrong header structure error, malformed row skipping, ETF/InvIT classification
    - _Requirements: 1.1, 1.2, 1.5, 1.6_

  - [x] 2.4 Implement Mutual Funds Parser (`parsers/groww_mf_parser.py`)
    - Implement `parse_mf_xlsx(file_path: str) -> list[MFHolding]` reading header at row 23, data from row 24, columns B-L
    - Raise `ValueError` if header structure at row 23 doesn't match expected columns
    - Log and skip rows with missing/malformed values
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x]* 2.5 Write property test for MF Parser
    - **Property 6: MF column extraction completeness**
    - **Validates: Requirements 2.2**

  - [x]* 2.6 Write unit tests for MF Parser
    - Test valid XLSX parsing, wrong header structure error, malformed row skipping
    - _Requirements: 2.1, 2.3, 2.4_

  - [x] 2.7 Implement P&L Parser (`parsers/groww_pnl_parser.py`)
    - Implement `parse_pnl_xlsx(file_path: str) -> tuple[list[TradeRecord], list[ScripSummary]]` reading both trade-level and scrip-level sheets
    - Implement `compute_holding_period(buy_date, current_date) -> int` returning days between dates
    - Implement `classify_tax_term(holding_period_days, security_type) -> str` with 12-month threshold for stocks/equity MF and 36-month threshold for debt MF
    - Raise `ValueError` if expected sheets are missing
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 2.8 Write property tests for P&L Parser
    - **Property 7: Trade record extraction**
    - **Property 8: Holding period computation**
    - **Property 9: Tax term classification**
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [ ]* 2.9 Write unit tests for P&L Parser
    - Test trade-level and scrip-level extraction, missing sheet error, holding period edge cases, tax classification thresholds
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Checkpoint - Parsers complete
  - Ensure all tests pass, ask the user if questions arise.


- [x] 4. Implement fetchers layer
  - [x] 4.1 Implement NSE Bhavcopy Fetcher (`fetchers/nse_bhavcopy.py`)
    - Implement `fetch_bhavcopy() -> dict[str, BhavcopyRecord]` downloading and parsing NSE Bhavcopy CSV, keyed by ISIN
    - Implement `get_cached_bhavcopy(cache_dir: str) -> dict[str, BhavcopyRecord] | None` for fallback
    - Store downloaded Bhavcopy with date-stamped filename in cache directory
    - On network failure, log and fall back to cached data
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 4.2 Write property test for Bhavcopy parsing
    - **Property 10: Bhavcopy CSV parsing**
    - **Validates: Requirements 4.2**

  - [x] 4.3 Implement FII/DII Flow Fetcher (`fetchers/nse_fii_dii.py`)
    - Implement `fetch_fii_dii() -> FIIDIIFlow` calling NSE FII/DII API
    - Parse response into structured `FIIDIIFlow` object with computed net values
    - On failure, log and use cached data
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 4.4 Write property test for FII/DII parsing
    - **Property 11: FII/DII response parsing**
    - **Validates: Requirements 5.2**

  - [x] 4.5 Implement Bulk/Block Deals Fetcher (`fetchers/nse_bulk_deals.py`)
    - Implement `fetch_bulk_deals() -> list[DealRecord]` fetching and parsing bulk and block deals from NSE
    - On failure, log and return empty list
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 4.6 Write property test for Deal record parsing
    - **Property 12: Deal record parsing**
    - **Validates: Requirements 6.2**

  - [x] 4.7 Implement Screener Fetcher (`fetchers/screener_fetcher.py`)
    - Implement `fetch_fundamentals(symbol: str) -> StockFundamentals` scraping Screener.in public page
    - Implement rate limiting (1 request per second) via `time.sleep()`
    - On failure, log and mark fundamentals as unavailable
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 4.8 Write property test for Screener fundamentals
    - **Property 13: Screener fundamentals extraction**
    - **Validates: Requirements 7.2**

  - [x] 4.9 Implement AMFI NAV Fetcher (`fetchers/amfi_nav_fetcher.py`)
    - Implement `fetch_amfi_nav() -> dict[str, NAVRecord]` downloading and parsing AMFI NAV text data, keyed by scheme code
    - On failure, log and use cached NAV data
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 4.10 Write property test for AMFI NAV lookup
    - **Property 14: AMFI NAV lookup**
    - **Validates: Requirements 8.2**

  - [x] 4.11 Implement IPO Fetcher (`fetchers/ipo_fetcher.py`)
    - Implement `fetch_ipo_gmp() -> list[IPORecord]` scraping Chittorgarh for IPO GMP data
    - On failure, log and return empty list
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 4.12 Write property test for IPO record extraction
    - **Property 15: IPO record extraction**
    - **Validates: Requirements 9.2**

  - [x] 4.13 Implement News Fetcher (`fetchers/news_fetcher.py`)
    - Implement `fetch_news() -> list[NewsItem]` fetching from ET RSS and BSE announcements RSS
    - Filter to retain only items published within last 24 hours
    - On feed failure, log and continue with available feeds
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 4.14 Write property test for News item extraction
    - **Property 16: News item extraction and filtering**
    - **Validates: Requirements 10.2, 10.3**

  - [x] 4.15 Implement Market Indices Fetcher (`fetchers/market_indices.py`)
    - Implement `fetch_indices() -> list[IndexData]` fetching Nifty 50, Sensex, Nifty Bank, Nifty Midcap 100 from NSE
    - On failure, log and use cached index data
    - _Requirements: 23.1, 23.2, 23.3_

  - [ ]* 4.16 Write property test for Market index parsing
    - **Property 31: Market index data parsing**
    - **Validates: Requirements 23.2**

  - [ ]* 4.17 Write unit tests for all fetchers
    - Test each fetcher with mocked HTTP responses (success, failure, malformed)
    - Test cache fallback behavior for Bhavcopy, FII/DII, AMFI, and indices
    - Test Screener rate limiting
    - _Requirements: 4.3, 5.3, 6.3, 7.3, 7.4, 8.3, 9.3, 10.4, 23.3_

- [x] 5. Checkpoint - Fetchers complete
  - Ensure all tests pass, ask the user if questions arise.


- [x] 6. Implement LLM layer
  - [x] 6.1 Implement Bedrock Client (`llm/bedrock_client.py`)
    - Implement `BedrockClient.__init__(region, model_id)` initializing boto3 Bedrock runtime client
    - Implement `BedrockClient.invoke(system_prompt, user_prompt) -> dict` sending prompt to Claude Sonnet and parsing JSON response
    - Handle Bedrock API timeout, throttling (retry with exponential backoff, max 3 retries), and invalid JSON responses
    - _Requirements: 11.1, 11.6_

  - [x] 6.2 Implement Portfolio Analyzer (`llm/portfolio_analyzer.py`)
    - Implement `analyze_portfolio(holdings, bhavcopy, fundamentals, pnl_data, client) -> list[StockVerdict]`
    - Build system prompt instructing Claude to generate buy/hold/sell/exit verdicts with target and stop loss prices
    - Include tax loss harvesting identification based on negative unrealised P&L and short-term holding period
    - Ensure only real data from parsers/fetchers is passed to the LLM prompt
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 6.3 Write property tests for Portfolio Analyzer output
    - **Property 17: Stock verdict output structure**
    - **Property 18: Tax loss harvesting flag**
    - **Validates: Requirements 11.2, 11.3, 11.4**

  - [x] 6.4 Implement Market Scanner (`llm/market_scanner.py`)
    - Implement `scan_opportunities(deals, fii_dii, fundamentals, client) -> list[MarketOpportunity]`
    - Identify promoter buying, multibagger candidates, and FII accumulation signals
    - Use only real data from fetchers
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 6.5 Implement Intraday Engine (`llm/intraday_engine.py`)
    - Implement `generate_intraday_setups(market_data, client) -> list[IntradaySetup]`
    - Generate exactly 5 setups with entry, target, stop loss, and rationale
    - Use only real data
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 6.6 Write property test for Intraday setup output
    - **Property 19: Intraday setup output structure**
    - **Validates: Requirements 13.1, 13.2, 13.3**


  - [x] 6.7 Implement MF Analyzer (`llm/mf_analyzer.py`)
    - Implement `analyze_mutual_funds(holdings, nav_data, client) -> list[MFRecommendation]`
    - Generate continue/stop/switch recommendations; include alternative scheme for switch recommendations
    - Use only real data from MF_Parser and AMFI_Fetcher
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 6.8 Write property test for MF recommendation output
    - **Property 20: MF recommendation output structure**
    - **Validates: Requirements 14.2, 14.3**

  - [ ]* 6.9 Write unit tests for LLM layer
    - Test BedrockClient with mocked boto3 (success, timeout, throttling, invalid JSON)
    - Test each analyzer with mocked BedrockClient responses
    - _Requirements: 11.2, 11.6, 13.1, 14.2_

- [x] 7. Checkpoint - LLM layer complete
  - Ensure all tests pass, ask the user if questions arise.


- [x] 8. Implement database layer
  - [x] 8.1 Implement DB Manager (`database/db_manager.py`)
    - Implement `DBManager.__init__(db_path)` creating SQLite connection and all tables (stock_holdings, mf_holdings, stock_verdicts, mf_recommendations, trade_records, bhavcopy_cache, fii_dii_cache) per the design schema
    - Implement `store_holdings`, `store_mf_holdings`, `store_verdicts`, `store_mf_recommendations` with IST timestamps
    - Implement `get_holdings_at(date)` and `get_latest_verdicts()` for historical queries
    - Handle write failures by logging and continuing without halting
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

  - [ ]* 8.2 Write property tests for database operations
    - **Property 26: Database holdings round-trip**
    - **Property 27: Database historical query**
    - **Validates: Requirements 19.1, 19.2, 19.3**

  - [ ]* 8.3 Write unit tests for DB Manager
    - Test table creation, store and retrieve operations, write failure handling using in-memory SQLite
    - _Requirements: 19.1, 19.2, 19.3, 19.4_


- [x] 9. Implement reports layer
  - [x] 9.1 Create HTML email templates (`templates/`)
    - Create `morning_brief.html` Jinja2 template with portfolio summary, overnight changes, FII/DII flows, and news sections; mobile-responsive with color-coded verdicts
    - Create `midday_snapshot.html` Jinja2 template with intraday setup cards, live portfolio performance, and deal alerts; mobile-responsive with color-coded cards
    - Create `eod_report.html` Jinja2 template with full verdicts, day P&L, MF analysis, tax harvesting, IPO GMP, and FII/DII bar charts; mobile-responsive
    - _Requirements: 15.2, 15.3, 16.2, 16.3, 17.2, 17.3_

  - [x] 9.2 Implement HTML Builder (`reports/html_builder.py`)
    - Implement `build_morning_brief(context) -> str` rendering morning brief template
    - Implement `build_midday_snapshot(context) -> str` rendering midday template
    - Implement `build_eod_report(context) -> str` rendering EOD template
    - _Requirements: 15.2, 16.2, 17.2_

  - [ ]* 9.3 Write property tests for report content
    - **Property 21: Morning brief report content**
    - **Property 22: Midday report content**
    - **Property 23: EOD report content**
    - **Validates: Requirements 15.2, 16.2, 17.2**

  - [x] 9.4 Implement SES Sender (`reports/ses_sender.py`)
    - Implement `send_email(html_body, subject, sender, recipient, region) -> bool` using boto3 SES
    - Implement retry logic: up to 3 retries with exponential backoff (1s, 2s, 4s)
    - Log each attempt and final failure
    - _Requirements: 15.4, 15.5, 16.4, 16.5, 17.4, 17.5_

  - [ ]* 9.5 Write property test for SES retry behavior
    - **Property 24: SES retry behavior**
    - **Validates: Requirements 15.5, 16.5, 17.5**

  - [ ]* 9.6 Write unit tests for SES Sender
    - Test successful send, retry on failure, max retry exhaustion using mocked boto3
    - _Requirements: 15.4, 15.5_


  - [x] 9.7 Implement S3 report archival (`reports/s3_uploader.py`)
    - Implement `upload_report(html_body, report_type, s3_bucket, region) -> bool` uploading HTML to S3 with date-stamped key
    - Implement `upload_xlsx(file_path, s3_bucket, region) -> bool` for portfolio file archival
    - On failure, log and return False without blocking
    - _Requirements: 20.1, 20.2, 20.3_

  - [ ]* 9.8 Write unit tests for S3 uploader
    - Test successful upload, failure handling using mocked boto3
    - _Requirements: 20.1, 20.3_

- [x] 10. Checkpoint - Reports and database complete
  - Ensure all tests pass, ask the user if questions arise.


- [x] 11. Implement dashboard and pipeline orchestration
  - [x] 11.1 Implement Dashboard Builder (`reports/dashboard_builder.py`)
    - Implement `build_dashboard(context, output_dir)` generating static HTML/CSS/JS files for Nginx
    - Include portfolio summary (invested value, current value, P&L), stock verdicts with color-coded indicators, MF recommendations, and FII/DII flow visualization
    - Ensure responsive design for desktop and mobile
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

  - [ ]* 11.2 Write property test for Dashboard content
    - **Property 25: Dashboard content completeness**
    - **Validates: Requirements 18.1, 18.2, 18.3, 18.4**

  - [x] 11.3 Implement pipeline scripts (`scripts/`)
    - Create `scripts/run_morning_brief.py` orchestrating: parse XLSX → fetch Bhavcopy, FII/DII, news, indices → AI portfolio analysis → build morning brief HTML → send email via SES → archive to S3 → update dashboard → store to DB
    - Create `scripts/run_midday_snapshot.py` orchestrating: fetch Bhavcopy, bulk/block deals, Screener fundamentals → AI market scan, intraday setups → build midday HTML → send email → archive → update dashboard → store to DB
    - Create `scripts/run_eod_report.py` orchestrating: full parse + fetch cycle → AI portfolio, MF, market analysis → build EOD HTML → send email → archive → update dashboard → store to DB
    - Each script loads config, initializes components, handles top-level errors with logging
    - _Requirements: 15.1, 16.1, 17.1, 21.1, 21.2, 21.3_

  - [x] 11.4 Implement logging configuration
    - Set up Python `logging` with INFO/WARNING/ERROR levels
    - Log format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
    - File output with daily rotation at `/opt/wealth-builder-pro/logs/app.log`
    - Timestamps in IST
    - _Requirements: 21.5_


- [x] 12. Implement scheduling and deployment
  - [x] 12.1 Create cron configuration and deploy script (`scripts/deploy.sh`)
    - Create crontab entries for 3:15 UTC (8:45 AM IST), 7:00 UTC (12:30 PM IST), 10:45 UTC (4:15 PM IST) on weekdays (Mon-Fri)
    - Create `deploy.sh` handling: apt dependencies, Python venv setup, Nginx config for dashboard static files, cron installation, directory creation for logs/cache/data
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 18.5_

  - [ ]* 12.2 Write property test for IST/UTC cron conversion
    - **Property 28: IST to UTC cron conversion**
    - **Validates: Requirements 21.4**

  - [x] 12.3 Create Nginx configuration for dashboard
    - Create Nginx server block config serving static files from dashboard output directory
    - _Requirements: 18.5_

- [x] 13. Implement test infrastructure and shared fixtures
  - [x] 13.1 Create test conftest and Hypothesis strategies (`tests/conftest.py`)
    - Define Hypothesis custom strategies for generating valid `StockHolding`, `MFHolding`, `TradeRecord`, `ScripSummary` instances
    - Define strategies for valid ISIN strings (12-char alphanumeric, INE/INF prefixes)
    - Define strategies for valid CSV/JSON/XML response bodies for fetcher tests
    - Define strategies for valid YAML config dictionaries
    - Define strategies for valid HTML template context dictionaries
    - Set up shared pytest fixtures for mocked boto3 clients, tmp_path XLSX files, and in-memory SQLite
    - _Requirements: 1.8, 2.6, 3.6_

- [x] 14. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major layer
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All AWS services (Bedrock, SES, S3) are mocked in tests using `unittest.mock`
- Database tests use in-memory SQLite (`:memory:`)
- Fetcher tests use mocked HTTP responses
