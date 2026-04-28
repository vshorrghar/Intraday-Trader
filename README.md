# 💼 Wealth Builder Pro

A personal portfolio intelligence platform for Indian retail investors. Parses Groww broker XLSX exports, fetches live market data from Indian financial sources (NSE, AMFI, Screener.in), runs AI-driven analysis via AWS Bedrock Claude, and delivers insights through a web dashboard and scheduled email reports.

## What It Does

- Analyzes **269 stock holdings** and **61 mutual fund schemes** from Groww exports
- Generates AI verdicts: **BUY** 🟢 / **HOLD** 🟡 / **SELL** 🔴 / **EXIT** 🟣 for every stock
- MF recommendations: **CONTINUE SIP** / **STOP SIP** / **SWITCH** with alternative scheme suggestions
- Identifies **10 long-term stock picks** and **5 intraday trading setups** daily
- Tracks FII/DII flows, sector rotation signals, promoter activity, bulk deals
- Goal tracker: scenarios to reach ₹10 Crore with SIP acceleration analysis
- Tax loss harvesting identification based on holding period and unrealised P&L
- Three daily email reports (morning brief, midday snapshot, EOD report) via AWS SES
- Static web dashboard served via Nginx on EC2

## Quick Start (One Command)

```bash
cd ~/kiro/websites/w-builder
./go.sh
```

Paste AWS credentials from Isengard (all 3 export lines), press Enter on empty line. The script:
1. Finds latest Groww XLSX files in `~/Downloads`
2. Syncs code + files to EC2 Mumbai
3. Runs full AI analysis on EC2 (uses IAM role for Bedrock)
4. Pulls results back to Mac
5. Opens dashboard in Chrome

## View Dashboard

```bash
cd ~/kiro/websites/w-builder/output/reports
python3 -m http.server 8877 &
```
Open: **http://localhost:8877/dashboard.html**

## Architecture

```
Your Mac (Denmark)                         EC2 Server (Mumbai, India)
┌──────────────────────┐                  ┌─────────────────────────────────┐
│ Groww XLSX files      │                  │                                 │
│ from ~/Downloads      │── go.sh ───────→│ Parsers: Read XLSX files        │
│                       │   (SSH/SCP)      │ Fetchers: NSE, AMFI, Screener  │
│                       │                  │ LLM: Bedrock Claude analysis    │
│ Dashboard in Chrome   │←── go.sh ───────│ Reports: HTML + JSON output     │
│ localhost:8877        │   (SCP pull)     │ DB: SQLite persistence          │
└──────────────────────┘                  └─────────────────────────────────┘
```

EC2 in Mumbai is required because Indian stock websites (NSE, AMFI, Screener.in) block non-Indian IPs.

## Data Flow

```
XLSX Files → Parsers → Fetchers (live data) → LLM Analysis → Reports → Dashboard/Email
                                                                 ↓
                                                          SQLite DB + S3
```

### Daily Schedule (Weekdays, IST)

| Time | Report | What Runs |
|------|--------|-----------|
| 8:45 AM | Morning Brief | Parse XLSX → Bhavcopy + FII/DII + news + indices → AI portfolio analysis → email + dashboard |
| 12:30 PM | Midday Snapshot | Bhavcopy + bulk deals + Screener fundamentals → AI market scan + intraday setups → email + dashboard |
| 4:15 PM | EOD Report | Full parse + fetch cycle → AI portfolio + MF + market analysis → email + dashboard |

## Dashboard Tabs

| Tab | Content |
|-----|---------|
| 📊 Stocks | All holdings with AI verdict, target price, stop loss, tax harvest flag |
| 🏦 MFs & SIPs | All mutual funds with SIP advice, alternative scheme suggestions |
| 📈 Long-Term Picks | 10 new stocks AI recommends for 1-3 year horizon |
| ⚡ Intraday | 5 trading setups with entry, target, stop loss, rationale |
| 🌐 Market Intel | FII/DII flows, hot sectors, promoter signals, bulk deals |
| 🎯 Goal Tracker | ₹10 Crore scenarios with SIP acceleration analysis |


## Project Structure

```
├── go.sh                        # Main orchestrator: creds → EC2 sync → analysis → pull → open dashboard
├── run_analysis.py              # Full portfolio analysis pipeline (runs on EC2)
├── run_market_scan.py           # Market scan for new picks + intraday setups (runs on EC2)
├── build_dashboard.py           # Merges AI analysis + portfolio into dashboard data.json
├── pick_latest_files.py         # Auto-finds latest Groww XLSX in ~/Downloads
├── analyze_orders.py            # Detects active SIPs and recent buy grades from order history
│
├── parsers/                     # Groww XLSX file readers
│   ├── groww_stocks_parser.py   #   Stocks Holdings (header row 11, data row 12+, cols B-I)
│   ├── groww_mf_parser.py       #   Mutual Funds (header row 23, data row 24+, cols B-L)
│   ├── groww_pnl_parser.py      #   P&L Report (trade-level + scrip-level sheets)
│   └── models.py                #   Dataclasses: StockHolding, MFHolding, TradeRecord, ScripSummary
│
├── fetchers/                    # Live market data fetchers
│   ├── nse_bhavcopy.py          #   NSE end-of-day prices (keyed by ISIN, cached daily)
│   ├── nse_fii_dii.py           #   FII/DII flows (buy/sell/net values, cached daily)
│   ├── nse_bulk_deals.py        #   Bulk and block deals from NSE
│   ├── market_indices.py        #   Nifty 50, Sensex, Nifty Bank, Nifty Midcap 100
│   ├── amfi_nav_fetcher.py      #   Mutual fund NAV data from AMFI (keyed by scheme code)
│   ├── screener_fetcher.py      #   Stock fundamentals from Screener.in (1 req/sec rate limit)
│   ├── ipo_fetcher.py           #   IPO GMP data from Chittorgarh
│   ├── news_fetcher.py          #   Market news from ET RSS + BSE announcements (24hr filter)
│   ├── groww_api.py             #   Groww broker API client (for auto-trader)
│   └── models.py                #   Dataclasses for all fetcher outputs
│
├── llm/                         # AI analysis via AWS Bedrock Claude
│   ├── bedrock_client.py        #   Bedrock client (retries, exponential backoff, JSON parsing)
│   ├── portfolio_analyzer.py    #   Stock verdicts: BUY/HOLD/SELL/EXIT + targets + tax harvest
│   ├── mf_analyzer.py           #   MF recommendations: CONTINUE/STOP/SWITCH + alternatives
│   ├── market_scanner.py        #   Opportunities: promoter buying, multibaggers, FII accumulation
│   ├── intraday_engine.py       #   5 intraday setups with entry/target/stop loss
│   ├── auto_trader.py           #   Dry-run auto-trader (9:15 AM pick, 3:45 PM check)
│   ├── check_trade.py           #   Trade result validation and scorecard
│   └── models.py                #   Dataclasses: StockVerdict, MFRecommendation, etc.
│
├── reports/                     # Report generation and delivery
│   ├── html_builder.py          #   Renders Jinja2 templates for all 3 reports
│   ├── ses_sender.py            #   AWS SES email sender (3 retries, exponential backoff)
│   ├── s3_uploader.py           #   S3 report archival with date-stamped keys
│   └── dashboard_builder.py     #   Static HTML dashboard generator for Nginx
│
├── templates/                   # Jinja2 HTML email templates
│   ├── morning_brief.html       #   Portfolio summary, overnight changes, FII/DII, news
│   ├── midday_snapshot.html     #   Intraday setups, live performance, deal alerts
│   └── eod_report.html          #   Full verdicts, P&L, MF analysis, tax harvest, IPO GMP
│
├── database/                    # Persistence layer
│   └── db_manager.py            #   SQLite: holdings, verdicts, recommendations, cache tables
│
├── config/                      # Configuration
│   ├── config.yaml              #   App settings (AWS, portfolio paths, schedule, alerts)
│   ├── config.example.yaml      #   Template config with placeholder values
│   ├── config_loader.py         #   YAML loader with validation
│   └── logging_config.py        #   IST-aware logging with daily rotation
│
├── scripts/                     # Deployment and scheduling
│   ├── run_morning_brief.py     #   8:45 AM IST pipeline
│   ├── run_midday_snapshot.py   #   12:30 PM IST pipeline
│   ├── run_eod_report.py        #   4:15 PM IST pipeline
│   ├── deploy.sh                #   EC2 setup: apt, venv, Nginx, cron, directories
│   ├── setup_cron.sh            #   Auto-trader cron (9:15 AM pick, 3:45 PM check)
│   └── nginx.conf               #   Nginx server block for dashboard
│
├── tests/                       # Test suite
│   ├── conftest.py              #   Pytest fixtures + Hypothesis strategies
│   ├── unit/                    #   17 unit test files covering all modules
│   └── property/                #   Property-based tests (correctness properties)
│
├── input/                       # Groww XLSX exports (not in git)
├── output/reports/              # Dashboard + analysis results (not in git)
│   ├── dashboard.html           #   The dashboard UI
│   └── data.json                #   Dashboard data (AI verdicts, portfolio)
├── cache/                       # Cached market data (date-stamped)
│
├── run_local.sh                 # Local Mac runner (morning/midday/eod/test modes)
├── upload_portfolio.sh          # Find latest Groww files → copy to input/ → upload to EC2
├── sync_code.sh                 # Sync code to EC2 (excludes venv, cache, output, db)
├── sync_to_ec2.sh               # Sync code preserving EC2 config files
├── pull_report.sh               # Pull reports from EC2 to Mac
│
├── USER_GUIDE.md                # Simple user guide
├── AUTO_TRADER_GUIDE.md         # Auto-trader documentation
├── RECOVERY_PROMPT.md           # Paste into Kiro if it restarts
└── requirements.txt             # Python dependencies
```

## Modules Detail

### Parsers

| Module | Input | Output | Notes |
|--------|-------|--------|-------|
| `groww_stocks_parser` | Stocks Holdings XLSX | `list[StockHolding]` | Header row 11, classifies as stock/etf/invit by ISIN prefix |
| `groww_mf_parser` | Mutual Funds XLSX | `list[MFHolding]` | Header row 23, extracts XIRR, category, sub-category |
| `groww_pnl_parser` | P&L Report XLSX | `(list[TradeRecord], list[ScripSummary])` | Computes holding periods, tax classification (12mo stocks, 36mo debt MF) |

### Fetchers

| Module | Source | Data | Caching |
|--------|--------|------|---------|
| `nse_bhavcopy` | NSE | EOD prices by ISIN | Date-stamped files |
| `nse_fii_dii` | NSE API | FII/DII buy/sell/net | Daily cache |
| `nse_bulk_deals` | NSE | Bulk + block deals | No cache |
| `market_indices` | NSE | Nifty 50, Sensex, Bank Nifty, Midcap 100 | Daily cache |
| `amfi_nav_fetcher` | AMFI | MF NAV by scheme code | Daily cache |
| `screener_fetcher` | Screener.in | PE, market cap, ROCE, promoter holding | Rate limited (1/sec) |
| `ipo_fetcher` | Chittorgarh | IPO GMP, subscription status | No cache |
| `news_fetcher` | ET RSS + BSE | Market news (24hr filter) | No cache |

All fetchers fall back to cached data on network failure.

### LLM Analysis

| Module | Input | Output |
|--------|-------|--------|
| `portfolio_analyzer` | Holdings + bhavcopy + fundamentals + P&L | Stock verdicts with target/stop loss/tax harvest flag |
| `mf_analyzer` | MF holdings + NAV data | SIP recommendations with alternative schemes |
| `market_scanner` | Deals + FII/DII + fundamentals | Promoter buying, multibagger candidates, FII accumulation |
| `intraday_engine` | Market data | Exactly 5 setups with entry/target/stop loss/rationale |
| `auto_trader` | Market data | Dry-run: picks 1 stock at 9:15 AM, checks at 3:45 PM |

Bedrock client: Claude Sonnet via `us.anthropic.claude-sonnet-4-20250514-v1:0`, 3 retries with exponential backoff.

## AWS Infrastructure

| Service | Purpose | Region |
|---------|---------|--------|
| EC2 | t3.medium, runs analysis + serves dashboard via Nginx | ap-south-1 (Mumbai) |
| Bedrock | Claude Sonnet for AI analysis | us-east-1 |
| SES | Email report delivery | ap-south-1 |
| S3 | Report archival with date-stamped keys | ap-south-1 |
| IAM Role | EC2 instance role for Bedrock access (no creds on EC2) | — |

### EC2 Details

| Setting | Value |
|---------|-------|
| Region | ap-south-1 (Mumbai) |
| Instance | i-0a31ad57170cbfd0c |
| Key | `~/Downloads/wealth-builder-pro.pem` |
| SSH | `ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101` |
| App path | `~/wealth-builder-pro/` |

## Configuration

Copy `config/config.example.yaml` to `config/config.yaml` and fill in your values:

```yaml
aws:
  region: ap-south-1
  s3_bucket: wealth-builder-pro-reports
  ses_sender: "[email]"
  ses_recipient: "[email]"
  bedrock_model_id: "anthropic.claude-3-sonnet-20240229-v1:0"

portfolio:
  stocks_xlsx: /opt/wealth-builder-pro/data/stocks.xlsx
  mf_xlsx: /opt/wealth-builder-pro/data/mf.xlsx
  pnl_xlsx: /opt/wealth-builder-pro/data/pnl.xlsx

schedule:
  morning_brief: "03:15"     # UTC → 8:45 AM IST
  midday_snapshot: "07:00"   # UTC → 12:30 PM IST
  eod_report: "10:45"        # UTC → 4:15 PM IST

database:
  path: /opt/wealth-builder-pro/data/portfolio.db

cache:
  dir: /opt/wealth-builder-pro/cache

dashboard:
  output_dir: /var/www/wealth-builder-pro
```

## Database Schema (SQLite)

| Table | Purpose |
|-------|---------|
| `stock_holdings` | Timestamped stock holdings with live prices |
| `mf_holdings` | Timestamped MF holdings with current NAV |
| `stock_verdicts` | AI verdicts with target/stop loss/tax harvest flag |
| `mf_recommendations` | SIP recommendations with alternative schemes |
| `trade_records` | Trade-level P&L data |
| `bhavcopy_cache` | Cached NSE prices by date |
| `fii_dii_cache` | Cached FII/DII flows by date |

All timestamps stored in IST.

## Update Portfolio

1. Download from Groww app (files go to `~/Downloads/`):
   - Stocks Holdings Statement
   - Mutual Funds
   - Stocks P&L Report (optional)
2. Run `./go.sh` — auto-finds latest files by date

Or manually:
```bash
./upload_portfolio.sh    # finds latest Groww files, copies to input/, uploads to EC2
```

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -q

# Run unit tests only
python3 -m pytest tests/unit/ -q

# Run property tests only
python3 -m pytest tests/property/ -q

# Test parsers locally (no AWS needed)
./run_local.sh test
```

Test infrastructure uses:
- `pytest` for unit tests
- `hypothesis` for property-based testing
- Mocked boto3 for AWS services
- In-memory SQLite for database tests
- Mocked HTTP responses for fetcher tests

## Dependencies

```
openpyxl        # XLSX parsing
boto3           # AWS SDK (Bedrock, SES, S3)
jinja2          # HTML template rendering
pyyaml          # Config file parsing
requests        # HTTP client for fetchers
feedparser      # RSS feed parsing (news)
beautifulsoup4  # HTML scraping (Screener, IPO)
lxml            # XML/HTML parser
pytest          # Test framework
hypothesis      # Property-based testing
```

## Costs

| Resource | Cost |
|----------|------|
| EC2 (Mumbai, t3.medium, 24/7) | ~$30/month |
| EC2 (stopped when not using) | ~$3/month |
| Claude AI per analysis run | ~₹5-10 |
| Running once daily | ~$35/month total |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Dashboard blank / "refused" | Start server: `cd output/reports && python3 -m http.server 8877 &` |
| File listing instead of dashboard | Navigate to `http://localhost:8877/dashboard.html` |
| "security token invalid" | AWS creds expired — get fresh from Isengard, run `./go.sh` |
| "Connection timed out" | EC2 stopped — start from AWS Console → EC2 |
| "Could not parse credentials" | Paste ALL 3 export lines from Isengard, Enter on empty line |
| Laptop restarted | Data persists — just restart dashboard server |
| Kiro restarted | Paste recovery prompt from `RECOVERY_PROMPT.md` |

## Shell Scripts Reference

| Script | Purpose |
|--------|---------|
| `go.sh` | Main workflow: creds → EC2 sync → analysis → pull results → open dashboard |
| `run_local.sh` | Local Mac runner for morning/midday/eod/test modes |
| `upload_portfolio.sh` | Find latest Groww files → copy to input/ → upload to EC2 |
| `sync_code.sh` | Sync code to EC2 (excludes venv, cache, output, db) |
| `sync_to_ec2.sh` | Sync code preserving EC2 config files |
| `pull_report.sh` | Pull reports from EC2 to Mac |
| `scripts/deploy.sh` | EC2 setup: apt, venv, Nginx, cron, directories |
| `scripts/setup_cron.sh` | Auto-trader cron setup on EC2 |
