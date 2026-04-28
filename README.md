# Dev Sandbox

Personal portfolio intelligence + AI-powered auto-trading platform for Indian markets (NSE).

## What It Does

### Portfolio Analysis (Wealth Builder)
- Parses Groww broker XLSX exports (269 stocks, 61 MF schemes)
- AI verdicts: BUY / HOLD / SELL / EXIT for every stock
- MF recommendations: CONTINUE SIP / STOP SIP / SWITCH
- 10 long-term picks + 5 intraday setups daily
- FII/DII flows, sector rotation, promoter activity tracking
- Three daily email reports via AWS SES
- Goal tracker: ₹10 Crore scenarios with SIP acceleration

### Intraday Auto-Trader
- AI-powered equity cash segment trading (NSE)
- Claude Sonnet selects trades from live NSE market data
- Pre-market scan → LLM selection → Position sizing → Order execution → Monitoring
- Trailing stop-losses, partial profit booking, force-exit at 15:15 IST
- Fetches live NSE quotes every 2 min for persistent monitoring
- Dry-run and live modes via Dhan broker

### F&O Auto-Trader
- AI-powered Nifty/BankNifty/FinNifty options trading
- Quant Edge Engine: IV percentile, VRP, GEX regime, confluence scoring
- Strategies: Iron Condor, Straddle, Strangle, Bull/Bear Spreads, Naked CE/PE
- Black-Scholes Greeks computation (Delta, Gamma, Theta, Vega)
- Paper mode with theta decay simulation
- Monitors every 30s until force-exit at 15:15 IST

## Architecture

```
MacBook (Denmark)                    EC2 (Mumbai, ap-south-1)
┌─────────────────────┐             ┌──────────────────────────────┐
│ Kiro IDE            │             │ Cron (Mon-Fri):              │
│ Code development    │── sync ───→ │   09:20 IST: FnO trader     │
│                     │             │   09:25 IST: Intraday trader │
│ Dashboard (CF URL)  │←── S3 ─────│   15:20 IST: Sync dashboard  │
└─────────────────────┘             │                              │
                                    │ Bedrock Claude (us-east-1)   │
                                    │ NSE live data                │
                                    │ Dhan broker API              │
                                    └──────────────────────────────┘
```

## Quick Start

### Run Locally (Mac)
```bash
# Intraday (dry-run)
python run_intraday.py --force

# F&O (paper mode)
python run_fno.py --force

# Demo mode (simulates with cached data)
python run_intraday.py --demo
```

### EC2 (Automated via Cron)
Scripts fire automatically Mon-Fri. Check results:
```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@13.206.144.6 "tail -50 ~/dev-sandbox/logs/fno_$(date +%Y-%m-%d).log"
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@13.206.144.6 "tail -50 ~/dev-sandbox/logs/intraday_$(date +%Y-%m-%d).log"
```

### Dashboard
CloudFront URL (private S3 + OAC): `https://d2q1cy3ph7jbd0.cloudfront.net`

## Project Structure

```
├── run_intraday.py          # Intraday auto-trader entry point
├── run_fno.py               # F&O auto-trader entry point
├── run_daily.sh             # Cron: intraday daily runner
├── run_fno_daily.sh         # Cron: FnO daily runner
├── run_analysis.py          # Portfolio analysis pipeline
├── build_dashboard.py       # Dashboard data builder
│
├── intraday/                # Intraday trading modules
│   ├── scanner.py           #   NSE pre-market scan + live quote enrichment
│   ├── selector.py          #   LLM trade selection + validation
│   ├── executor.py          #   Order execution (Dhan/Zerodha)
│   ├── monitor.py           #   Position monitor with live NSE prices
│   ├── risk_manager.py      #   Position sizing + VIX checks + loss caps
│   ├── reporter.py          #   EOD performance report
│   ├── auth_server.py       #   Broker TOTP authentication
│   └── models.py            #   TradeSetup, IntraConfig dataclasses
│
├── fno/                     # F&O trading modules
│   ├── option_chain.py      #   Option chain fetcher + snapshot buffer
│   ├── greeks.py            #   Black-Scholes Greeks calculator
│   ├── quant_engine.py      #   IV percentile, VRP, GEX, confluence
│   ├── strategy_engine.py   #   LLM strategy selection
│   ├── executor.py          #   Multi-leg order execution
│   ├── monitor.py           #   Position monitor with premium simulation
│   ├── paper_engine.py      #   Paper trading engine
│   ├── risk_manager.py      #   Greeks exposure + loss caps
│   ├── reporter.py          #   F&O EOD report + dashboard JSON
│   └── config.py            #   FnO configuration loader
│
├── fetchers/                # Market data fetchers
│   ├── nse_market_movers.py #   Gainers, losers, most active, sectors
│   ├── nse_fii_dii.py       #   FII/DII flows
│   ├── nse_bhavcopy.py      #   EOD prices
│   ├── screener_fetcher.py  #   Stock fundamentals
│   └── ...
│
├── llm/                     # AI analysis
│   └── bedrock_client.py    #   AWS Bedrock Claude client
│
├── config/                  # Configuration
│   ├── config.yaml          #   All settings (broker, trading, AWS)
│   └── config_loader.py     #   YAML loader + validation
│
├── database/                # SQLite persistence
│   └── db_manager.py
│
├── dashboard/               # Web dashboard
│   ├── index.html           #   Dashboard UI
│   └── api/                 #   JSON data files
│
└── scripts/                 # Deployment helpers
```

## Configuration

All in `config/config.yaml`:
- AWS: Bedrock model, region, SES
- Broker: Dhan (client_id, api_key, api_secret, totp_secret, pin)
- Intraday: capital limits, max trades, confidence threshold, VIX threshold
- FnO: paper/live mode, allowed indices, strategies, Greeks limits

## EC2 Details

| Setting | Value |
|---------|-------|
| Instance | i-0256713c061011a5f (t3.medium) |
| Region | ap-south-1 (Mumbai) |
| IP | 13.206.144.6 |
| Key | ~/Downloads/wealth-builder-pro.pem |
| SSH | Only from whitelisted IPs |
| Cron | FnO 09:20 IST, Intraday 09:25 IST, Dashboard sync 15:20 IST |

## Dependencies

```
boto3, requests, pyyaml, openpyxl, scipy, numpy
jinja2, beautifulsoup4, flask, hypothesis, pytest
```
