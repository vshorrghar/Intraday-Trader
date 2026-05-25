# Recovery Prompt

Paste this into a new Kiro chat session if Kiro restarts, crashes, or you start a new conversation.
This tells Kiro everything about your app so it can help you immediately.

---

```
I have a working app called Wealth Builder Pro at ~/kiro/websites/w-builder/

It's a personal portfolio intelligence app for Indian stock market. Here's what it does:
- Parses Groww broker XLSX exports (stocks, mutual funds, P&L reports)
- Fetches live Indian market data from NSE, AMFI, Screener.in on EC2 Mumbai
- Sends everything to AWS Bedrock Claude for AI analysis (BUY/HOLD/SELL/EXIT verdicts)
- Generates a dashboard at http://localhost:8877/dashboard.html

Folder: ~/kiro/websites/w-builder/

Key files:
- go.sh — ONE command that does everything (paste AWS creds → syncs to EC2 → runs analysis → pulls results → opens dashboard)
- run_analysis.py — portfolio analysis pipeline (parse XLSX → send to Claude → get verdicts for all 269 stocks + 61 MF schemes)
- run_market_scan.py — market scan (fetch FII/DII, bulk deals, news → Claude → long-term picks + intraday setups)
- build_dashboard.py — merges Claude analysis + parsed portfolio into dashboard data.json
- pick_latest_files.py — finds latest Groww XLSX files in ~/Downloads and copies to input/
- output/reports/dashboard.html — the dashboard UI (static HTML with tabs: Stocks, MF, Long-Term, Intraday, Market, Goal Tracker)
- output/reports/data.json — dashboard reads this JSON
- parsers/groww_stocks_parser.py — parses Groww Stocks Holdings XLSX (header row 11, data row 12+)
- parsers/groww_mf_parser.py — parses Groww Mutual Funds XLSX (header row 23, data row 24+)
- parsers/groww_pnl_parser.py — parses Groww P&L Report XLSX
- parsers/models.py — dataclasses: StockHolding, MFHolding, PnLTrade
- fetchers/ — NSE bhavcopy, FII/DII, bulk deals, AMFI NAV, market indices, news, IPO GMP, Screener.in
- llm/bedrock_client.py — AWS Bedrock Claude client
- llm/portfolio_analyzer.py, market_scanner.py, mf_analyzer.py — AI analysis modules
- config/config.yaml — settings (AWS region, S3 bucket, SES emails, Bedrock model)
- tests/ — full unit test suite (pytest + hypothesis)
- requirements.txt — openpyxl, boto3, jinja2, pyyaml, requests, feedparser, beautifulsoup4, lxml, pytest, hypothesis

EC2 details:
- Instance: i-0a31ad57170cbfd0c in ap-south-1 (Mumbai)
- Key: ~/Downloads/wealth-builder-pro.pem
- User: ec2-user
- Path on EC2: ~/wealth-builder-pro/
- EC2 has IAM role for Bedrock — no AWS creds needed on EC2
- Mac needs Isengard creds ONLY for SSH/SCP to EC2
- Bedrock model: us.anthropic.claude-sonnet-4-20250514-v1:0

To see dashboard right now:
  cd ~/kiro/websites/w-builder/output/reports && python3 -m http.server 8877 &
  Open http://localhost:8877/dashboard.html

To run fresh analysis:
  cd ~/kiro/websites/w-builder && ./go.sh

Don't rewrite or modify any existing code unless I ask. Just help me use and enhance it.
```
