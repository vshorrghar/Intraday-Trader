# Requirements Document

## Introduction

Wealth Builder Pro is a personal wealth intelligence platform for Indian retail investors. The system ingests portfolio data from Groww broker XLSX exports (stocks, mutual funds, P&L reports), fetches live market data from Indian financial sources (NSE, AMFI, Screener.in, etc.), performs AI-driven portfolio analysis via AWS Bedrock Claude, and delivers three daily HTML email reports via AWS SES. A web dashboard served via Nginx provides on-demand access to portfolio insights. The platform runs on an AWS EC2 instance in ap-south-1 and uses SQLite for persistence and S3 for storage.

## Glossary

- **Portfolio_Parser**: The subsystem responsible for reading and parsing Groww broker XLSX export files into structured data objects
- **Stocks_Parser**: The component that parses Groww Stocks Holdings XLSX files with header at row 11 and data from row 12 onward
- **MF_Parser**: The component that parses Groww Mutual Funds XLSX files with header at row 23 and data from row 24 onward
- **PnL_Parser**: The component that parses Groww P&L Report XLSX files containing trade-level and scrip-level sheets
- **Data_Fetcher**: The subsystem responsible for retrieving live market data from external Indian financial sources
- **NSE_Fetcher**: The component that fetches data from National Stock Exchange sources including Bhavcopy, FII/DII flows, and bulk/block deals
- **AMFI_Fetcher**: The component that fetches mutual fund NAV data from the AMFI website
- **Screener_Fetcher**: The component that fetches stock fundamental data from Screener.in public pages
- **IPO_Fetcher**: The component that fetches IPO GMP data from Chittorgarh
- **News_Fetcher**: The component that fetches market news from Economic Times and BSE announcements RSS feeds
- **AI_Analyzer**: The subsystem that uses AWS Bedrock Claude Sonnet to perform portfolio analysis and generate investment insights
- **Report_Builder**: The subsystem that generates HTML email reports and dashboard content
- **Email_Sender**: The component that delivers HTML email reports via AWS SES using boto3
- **Dashboard**: The web UI served via Nginx that displays portfolio insights and reports
- **ISIN**: International Securities Identification Number, a 12-character alphanumeric code uniquely identifying a security
- **IST**: Indian Standard Time (UTC+05:30), the timezone used for all scheduling and display
- **NAV**: Net Asset Value, the per-unit price of a mutual fund scheme
- **Bhavcopy**: The official end-of-day price file published by NSE
- **FII_DII_Flow**: Foreign Institutional Investor and Domestic Institutional Investor buy/sell activity data
- **XIRR**: Extended Internal Rate of Return, used to measure mutual fund returns
- **SES**: Amazon Simple Email Service
- **InvIT**: Infrastructure Investment Trust, identified by specific ISINs
- **ETF**: Exchange Traded Fund, identified by ISINs starting with INF or names containing ETF/BEES/NASDAQ/MAFANG/MAHKTECH/SILVER

## Requirements

### Requirement 1: Parse Groww Stocks Holdings XLSX

**User Story:** As an investor, I want to import my Groww stocks holdings export, so that the system can analyze my equity portfolio.

#### Acceptance Criteria

1. WHEN a Groww Stocks Holdings XLSX file is provided, THE Stocks_Parser SHALL read the header row at row 11 and extract data rows starting from row 12
2. WHEN a Groww Stocks Holdings XLSX file is provided, THE Stocks_Parser SHALL extract the following columns for each holding: Stock Name, ISIN, Quantity, Avg buy price, Buy value, Closing price, Closing value, Unrealised P&L
3. WHEN an ISIN starts with the prefix "INE", THE Stocks_Parser SHALL classify the holding as a stock
4. WHEN an ISIN starts with the prefix "INF" or the Stock Name contains any of "ETF", "BEES", "NASDAQ", "MAFANG", "MAHKTECH", or "SILVER", THE Stocks_Parser SHALL classify the holding as an ETF
5. IF the XLSX file does not contain the expected header structure at row 11, THEN THE Stocks_Parser SHALL raise a descriptive error indicating the format mismatch
6. IF a data row contains missing or malformed values for required columns, THEN THE Stocks_Parser SHALL log the row number and skip the row without halting the parse
7. THE Stocks_Parser SHALL produce a structured list of holding objects from the parsed data
8. FOR ALL valid Stocks Holdings XLSX files, parsing then serializing to JSON then parsing the JSON SHALL produce an equivalent list of holding objects (round-trip property)

### Requirement 2: Parse Groww Mutual Funds XLSX

**User Story:** As an investor, I want to import my Groww mutual funds export, so that the system can analyze my MF portfolio.

#### Acceptance Criteria

1. WHEN a Groww Mutual Funds XLSX file is provided, THE MF_Parser SHALL read the header row at row 23 and extract data rows starting from row 24
2. WHEN a Groww Mutual Funds XLSX file is provided, THE MF_Parser SHALL extract the following columns for each scheme: Scheme Name, AMC, Category, Sub-category, Folio No, Source, Units, Invested Value, Current Value, Returns, XIRR
3. IF the XLSX file does not contain the expected header structure at row 23, THEN THE MF_Parser SHALL raise a descriptive error indicating the format mismatch
4. IF a data row contains missing or malformed values for required columns, THEN THE MF_Parser SHALL log the row number and skip the row without halting the parse
5. THE MF_Parser SHALL produce a structured list of mutual fund scheme objects from the parsed data
6. FOR ALL valid Mutual Funds XLSX files, parsing then serializing to JSON then parsing the JSON SHALL produce an equivalent list of scheme objects (round-trip property)

### Requirement 3: Parse Groww P&L Report XLSX

**User Story:** As an investor, I want to import my Groww P&L report, so that the system can determine buy dates, holding periods, and tax implications.

#### Acceptance Criteria

1. WHEN a Groww P&L Report XLSX file is provided, THE PnL_Parser SHALL extract data from both the trade-level and scrip-level sheets
2. WHEN trade-level data is parsed, THE PnL_Parser SHALL extract buy dates and ISIN mappings for each trade
3. THE PnL_Parser SHALL compute the holding period for each position by calculating the difference between the buy date and the current date in IST
4. THE PnL_Parser SHALL classify each position as short-term or long-term based on the holding period (stocks: 12 months threshold, mutual funds: 36 months threshold for debt, 12 months for equity)
5. IF the XLSX file does not contain the expected trade-level or scrip-level sheets, THEN THE PnL_Parser SHALL raise a descriptive error identifying the missing sheet
6. FOR ALL valid P&L Report XLSX files, parsing then serializing to JSON then parsing the JSON SHALL produce an equivalent set of trade and scrip objects (round-trip property)

### Requirement 4: Fetch NSE Bhavcopy Data

**User Story:** As an investor, I want the system to fetch official end-of-day prices from NSE, so that my portfolio valuations are accurate.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for Bhavcopy retrieval, THE NSE_Fetcher SHALL download the latest NSE Bhavcopy CSV file
2. WHEN the Bhavcopy CSV is downloaded, THE NSE_Fetcher SHALL parse the CSV and extract closing prices indexed by ISIN
3. IF the NSE Bhavcopy endpoint is unreachable or returns an error, THEN THE NSE_Fetcher SHALL log the failure and use the most recent cached Bhavcopy data
4. THE NSE_Fetcher SHALL store each downloaded Bhavcopy in the local cache with a date-stamped filename

### Requirement 5: Fetch FII/DII Flow Data

**User Story:** As an investor, I want to see daily FII and DII activity, so that I can understand institutional money flows.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for FII/DII retrieval, THE NSE_Fetcher SHALL call the NSE FII/DII API and retrieve the latest buy and sell values for both FII and DII categories
2. THE NSE_Fetcher SHALL parse the API response into structured FII_DII_Flow objects containing date, FII buy value, FII sell value, FII net value, DII buy value, DII sell value, and DII net value
3. IF the NSE FII/DII API is unreachable or returns an error, THEN THE NSE_Fetcher SHALL log the failure and use the most recent cached FII/DII data

### Requirement 6: Fetch NSE Bulk and Block Deals

**User Story:** As an investor, I want to see bulk and block deal activity, so that I can identify promoter and institutional signals.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for bulk/block deal retrieval, THE NSE_Fetcher SHALL fetch the latest bulk deals and block deals data from NSE
2. THE NSE_Fetcher SHALL parse each deal record and extract the deal type, security name, ISIN, client name, quantity, and price
3. IF the NSE bulk/block deals endpoint is unreachable or returns an error, THEN THE NSE_Fetcher SHALL log the failure and return an empty deal list

### Requirement 7: Fetch Stock Fundamentals from Screener.in

**User Story:** As an investor, I want fundamental data for my stock holdings, so that the AI can make informed analysis.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for a specific stock, THE Screener_Fetcher SHALL fetch the public page for that stock from Screener.in without requiring login credentials
2. THE Screener_Fetcher SHALL extract key fundamental metrics including PE ratio, market cap, book value, dividend yield, ROCE, and promoter holding percentage
3. IF the Screener.in page for a stock is unreachable or the stock is not found, THEN THE Screener_Fetcher SHALL log the failure and mark the stock fundamentals as unavailable
4. THE Screener_Fetcher SHALL implement rate limiting to avoid exceeding 1 request per second to Screener.in

### Requirement 8: Fetch Mutual Fund NAV from AMFI

**User Story:** As an investor, I want current NAV data for my mutual fund schemes, so that my MF valuations are up to date.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for NAV retrieval, THE AMFI_Fetcher SHALL download the latest NAV data from the AMFI website
2. THE AMFI_Fetcher SHALL parse the NAV data and provide lookup by scheme code or scheme name
3. IF the AMFI website is unreachable or returns an error, THEN THE AMFI_Fetcher SHALL log the failure and use the most recent cached NAV data

### Requirement 9: Fetch IPO GMP Data

**User Story:** As an investor, I want to see current IPO grey market premiums, so that I can evaluate upcoming IPO opportunities.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for IPO data retrieval, THE IPO_Fetcher SHALL fetch the latest IPO GMP data from Chittorgarh
2. THE IPO_Fetcher SHALL extract IPO name, price band, GMP value, estimated listing price, and subscription status for each active IPO
3. IF the Chittorgarh website is unreachable or returns an error, THEN THE IPO_Fetcher SHALL log the failure and return an empty IPO list

### Requirement 10: Fetch Market News

**User Story:** As an investor, I want relevant market news, so that the AI analysis includes current market context.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for news retrieval, THE News_Fetcher SHALL fetch the latest articles from Economic Times RSS feed and BSE announcements RSS feed
2. THE News_Fetcher SHALL extract the headline, publication date, source, and summary for each news item
3. THE News_Fetcher SHALL filter news items to retain only those published within the last 24 hours
4. IF an RSS feed is unreachable or returns an error, THEN THE News_Fetcher SHALL log the failure and continue with available feeds

### Requirement 11: AI Portfolio Analysis

**User Story:** As an investor, I want AI-driven analysis of my stock holdings, so that I receive actionable buy/hold/sell/exit verdicts with targets and stop losses.

#### Acceptance Criteria

1. WHEN parsed stock holdings and live market data are available, THE AI_Analyzer SHALL send the portfolio data to AWS Bedrock Claude Sonnet via boto3 for analysis
2. THE AI_Analyzer SHALL generate a verdict of buy, hold, sell, or exit for each stock holding
3. THE AI_Analyzer SHALL generate a stop loss price and a target price for each stock holding
4. THE AI_Analyzer SHALL identify tax loss harvesting opportunities based on buy dates from the PnL_Parser and current unrealised P&L
5. THE AI_Analyzer SHALL use only real data from parsers and fetchers and SHALL NOT generate fabricated prices, volumes, or metrics
6. IF the AWS Bedrock API call fails, THEN THE AI_Analyzer SHALL log the error and mark the analysis as unavailable for the current cycle

### Requirement 12: AI Market Opportunity Scanning

**User Story:** As an investor, I want the AI to identify market opportunities, so that I can discover promoter signals, multibagger candidates, and FII-driven plays.

#### Acceptance Criteria

1. WHEN bulk/block deal data and FII/DII flow data are available, THE AI_Analyzer SHALL identify stocks with significant promoter buying activity
2. THE AI_Analyzer SHALL identify potential multibagger candidates based on fundamental data from the Screener_Fetcher and institutional activity patterns
3. THE AI_Analyzer SHALL identify stocks with significant FII accumulation based on FII/DII flow data and bulk deal data
4. THE AI_Analyzer SHALL use only real data from fetchers and SHALL NOT generate fabricated signals or opportunities

### Requirement 13: AI Intraday Setup Generation

**User Story:** As an investor, I want 5 daily intraday trading setups, so that I can evaluate short-term trading opportunities.

#### Acceptance Criteria

1. WHEN live market data and technical indicators are available, THE AI_Analyzer SHALL generate exactly 5 intraday trading setups per analysis cycle
2. THE AI_Analyzer SHALL provide an entry price, exit target price, and stop loss price for each intraday setup
3. THE AI_Analyzer SHALL provide a rationale for each setup based on available market data
4. THE AI_Analyzer SHALL use only real data and SHALL NOT fabricate price levels or technical patterns

### Requirement 14: AI Mutual Fund Analysis

**User Story:** As an investor, I want AI analysis of my mutual fund schemes, so that I receive SIP continue, stop, or switch recommendations.

#### Acceptance Criteria

1. WHEN parsed mutual fund holdings and current NAV data are available, THE AI_Analyzer SHALL analyze each mutual fund scheme against its category benchmark
2. THE AI_Analyzer SHALL generate a recommendation of continue, stop, or switch for each SIP
3. WHEN a switch recommendation is generated, THE AI_Analyzer SHALL suggest an alternative scheme within the same category
4. THE AI_Analyzer SHALL use only real data from the MF_Parser and AMFI_Fetcher and SHALL NOT generate fabricated NAV values or returns

### Requirement 15: Morning Brief Email Report

**User Story:** As an investor, I want a morning brief email at 8:45 AM IST, so that I start my trading day with portfolio insights and market context.

#### Acceptance Criteria

1. WHEN the system clock reaches 8:45 AM IST on a weekday, THE Report_Builder SHALL generate the morning brief HTML email report
2. THE Report_Builder SHALL include portfolio summary, overnight market changes, FII/DII flows, and key news in the morning brief
3. THE Report_Builder SHALL render the morning brief using an HTML template with color-coded verdicts and mobile-responsive design
4. WHEN the morning brief HTML is generated, THE Email_Sender SHALL deliver the email via AWS SES using boto3 without SMTP credentials
5. IF the SES API call fails, THEN THE Email_Sender SHALL log the error and retry delivery up to 3 times with exponential backoff

### Requirement 16: Midday Analysis Email Report

**User Story:** As an investor, I want a midday analysis email at 12:30 PM IST, so that I receive intraday setups and live market updates during trading hours.

#### Acceptance Criteria

1. WHEN the system clock reaches 12:30 PM IST on a weekday, THE Report_Builder SHALL generate the midday analysis HTML email report
2. THE Report_Builder SHALL include intraday setups with entry/exit/stop loss cards, live portfolio performance, and bulk/block deal alerts in the midday report
3. THE Report_Builder SHALL render the midday report using an HTML template with color-coded setup cards and mobile-responsive design
4. WHEN the midday report HTML is generated, THE Email_Sender SHALL deliver the email via AWS SES using boto3 without SMTP credentials
5. IF the SES API call fails, THEN THE Email_Sender SHALL log the error and retry delivery up to 3 times with exponential backoff

### Requirement 17: End-of-Day Summary Email Report

**User Story:** As an investor, I want an end-of-day summary email at 4:15 PM IST, so that I review the full day's performance and AI verdicts after market close.

#### Acceptance Criteria

1. WHEN the system clock reaches 4:15 PM IST on a weekday, THE Report_Builder SHALL generate the end-of-day summary HTML email report
2. THE Report_Builder SHALL include full portfolio verdicts (buy/hold/sell/exit), day P&L, MF analysis, tax harvesting opportunities, and IPO GMP data in the EOD report
3. THE Report_Builder SHALL render the EOD report using an HTML template with color-coded verdicts, FII/DII bar charts, and mobile-responsive design
4. WHEN the EOD report HTML is generated, THE Email_Sender SHALL deliver the email via AWS SES using boto3 without SMTP credentials
5. IF the SES API call fails, THEN THE Email_Sender SHALL log the error and retry delivery up to 3 times with exponential backoff

### Requirement 18: Web Dashboard

**User Story:** As an investor, I want a web dashboard, so that I can view my portfolio insights and reports on demand.

#### Acceptance Criteria

1. THE Dashboard SHALL display the latest portfolio summary including total invested value, current value, and overall P&L
2. THE Dashboard SHALL display the most recent AI verdicts for each stock holding with color-coded buy/hold/sell/exit indicators
3. THE Dashboard SHALL display the most recent mutual fund analysis with SIP recommendations
4. THE Dashboard SHALL display the latest FII/DII flow data with visual bar representation
5. THE Dashboard SHALL be served via Nginx on the EC2 instance
6. THE Dashboard SHALL render correctly on both desktop and mobile screen sizes

### Requirement 19: Data Persistence

**User Story:** As an investor, I want my portfolio history tracked over time, so that I can observe trends and changes in my holdings.

#### Acceptance Criteria

1. WHEN a portfolio parse is completed, THE Database SHALL store the parsed holdings data in SQLite with a timestamp in IST
2. WHEN an AI analysis cycle is completed, THE Database SHALL store the generated verdicts and recommendations in SQLite with a timestamp in IST
3. THE Database SHALL retain historical records to allow querying portfolio state for any past date
4. IF a database write operation fails, THEN THE Database SHALL log the error and continue operation without halting the application

### Requirement 20: Report Storage on S3

**User Story:** As an investor, I want generated reports stored in S3, so that I have a durable archive of all reports.

#### Acceptance Criteria

1. WHEN an HTML email report is generated, THE Report_Builder SHALL upload the report HTML to an S3 bucket in ap-south-1 with a date-stamped key
2. WHEN a portfolio XLSX file is uploaded, THE System SHALL store the file in S3 with a date-stamped key
3. IF an S3 upload fails, THEN THE Report_Builder SHALL log the error and continue with email delivery without blocking the report cycle

### Requirement 21: Scheduling and Cron Configuration

**User Story:** As an investor, I want the system to run automatically on schedule, so that I receive reports without manual intervention.

#### Acceptance Criteria

1. THE System SHALL configure cron jobs on the EC2 instance to trigger the morning brief pipeline at 8:45 AM IST on weekdays
2. THE System SHALL configure cron jobs on the EC2 instance to trigger the midday analysis pipeline at 12:30 PM IST on weekdays
3. THE System SHALL configure cron jobs on the EC2 instance to trigger the end-of-day summary pipeline at 4:15 PM IST on weekdays
4. THE System SHALL use IST (UTC+05:30) for all cron schedule calculations
5. IF a scheduled pipeline run fails, THEN THE System SHALL log the failure with the pipeline name, timestamp, and error details

### Requirement 22: Security Classification of Holdings

**User Story:** As an investor, I want my holdings correctly classified as stocks, ETFs, or InvITs, so that analysis and tax treatment are accurate.

#### Acceptance Criteria

1. WHEN an ISIN starts with the prefix "INE", THE Portfolio_Parser SHALL classify the holding as a stock
2. WHEN an ISIN starts with the prefix "INF", THE Portfolio_Parser SHALL classify the holding as an ETF
3. WHEN a holding name contains any of "ETF", "BEES", "NASDAQ", "MAFANG", "MAHKTECH", or "SILVER", THE Portfolio_Parser SHALL classify the holding as an ETF regardless of ISIN prefix
4. WHEN an ISIN matches a known InvIT ISIN list, THE Portfolio_Parser SHALL classify the holding as an InvIT
5. THE Portfolio_Parser SHALL assign exactly one classification (stock, ETF, or InvIT) to each holding

### Requirement 23: Fetch Market Indices Data

**User Story:** As an investor, I want current market index levels, so that reports include benchmark context like Nifty 50 and Sensex.

#### Acceptance Criteria

1. WHEN the Data_Fetcher is triggered for index data retrieval, THE NSE_Fetcher SHALL fetch the latest values for Nifty 50, Sensex, Nifty Bank, and Nifty Midcap 100
2. THE NSE_Fetcher SHALL extract the index name, last traded price, change value, and change percentage for each index
3. IF the index data endpoint is unreachable or returns an error, THEN THE NSE_Fetcher SHALL log the failure and use the most recent cached index data

### Requirement 24: Configuration Management

**User Story:** As a developer, I want all configurable values externalized, so that I can change settings without modifying code.

#### Acceptance Criteria

1. THE System SHALL read AWS region, S3 bucket name, SES sender email, SES recipient email, and Bedrock model ID from a configuration file or environment variables
2. THE System SHALL read portfolio XLSX file paths from the configuration
3. THE System SHALL read cron schedule times from the configuration
4. IF a required configuration value is missing, THEN THE System SHALL raise a descriptive error at startup identifying the missing configuration key
