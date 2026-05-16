# Intraday Trader — Technical Documentation

Comprehensive technical reference. Cross-reference GLOSSARY.md for term definitions.

**Last Updated**: 2026-05-15

## 1. SYSTEM OVERVIEW

Architecture: Rules narrow 500+ stocks to top 20, then AI ranks final 5.

Modules:
- Intraday: LIVE since May 12, 2026 (Rs.10K-15K real money)
- F&O: Paper since May 14, 2026 (Rs.50K paper)
- Swing: Paper since May 15, 2026 (Rs.25K paper)
- Positional: Planned

Profiles:
- vishal-live: Real Rs.15,000, OLD EC2
- neha-live: Real Rs.10,000, NEW EC2
- vishal: Paper Rs.3L, OLD EC2
- neha: Paper Rs.3L, OLD EC2

## 2. INFRASTRUCTURE

- OLD EC2: i-0256713c061011a5f, 13.206.144.6, t3.medium, ap-south-1
- NEW EC2: i-0233c705c9104383e, 13.202.63.223, t3.medium, ap-south-1
- AWS Profile: vishal-admin
- Bedrock: us-east-1, Claude Sonnet 4.5
- S3: dev-sandbox-dashboard-176767908884
- CloudFront: E3NXP6TCRJKVX1
- Dashboard: https://d2q1cy3ph7jbd0.cloudfront.net
- Broker: Dhan REST API v2

## 3. INTRADAY MODULE

### Scanner (intraday/scanner.py)

Volume Filter (Bug 1 fix):
- Pass if volume >= 500K
- OR pass if abs(change_pct) >= 4% AND volume >= 100K

Scoring (RS-First v3):
- Signal 1: change_from_open (0-5 pts)
- Signal 2: momentum/change_pct (0-8 pts) - rewards big winners
- Signal 3: near day high (0-2 pts)
- Signal 4: volume confirmation (0-2 pts)
- Signal 5: FNO liquidity bonus (0-1 pt)
- Signal 6: sector rotation (0-5 pts)

Penalties:
- Fade detector: -3 if fell >3% from day high, -1 if >1.5%
- Trap detector: -5 gap with no sector support, -2 buying climax

Time Multiplier (final score):
- 9:30-10:30 IST: x 1.5
- 10:30-11:45 IST: x 1.0
- 11:45-13:15 IST: x 0.7
- After 13:15 IST: x 0.4

Min score: 3

### Selector (intraday/selector.py)

Pre-filter: 30 to 20 candidates
LLM: Claude Sonnet 4.5 via AWS Bedrock
Bedrock client: 60s read_timeout, 10s connect_timeout, 1 retry
Validation: confidence >= 7 (or 8), R:R >= 2.0, direction logic

### Executor (intraday/executor.py)

1. Place LIMIT BUY at entry_price * 1.003 (Bug 3 buffer)
2. Tick-align to Rs.0.05: round(price * 20) / 20
3. Wait 10s for fill, poll every 2s
4. If unfilled and confidence >= 8: cancel + MARKET fallback (Bug 3)
5. Once filled: place STOP-LOSS immediately
6. Direction-aware: LONG=BUY+SELL_SL, SHORT=SELL+BUY_SL

### Monitor (intraday/monitor.py)

Cycle: 5 min
Trailing SL: After 0.5% profit, SL moves to entry
Partial booking: 50% closed at target
Force exit: 15:15 IST

### Risk Manager (intraday/risk_manager.py)

VIX Gates:
- VIX > 25: SKIP entire session
- VIX > 22: REDUCE to 1 trade max
- VIX <= 22: Normal trading

Trade Counting (Bug 5 fix):
EXCLUDED_STATUSES = {REJECTED, CANCELLED, FAILED, ABANDONED, PENDING}
Counts: OPEN, FORCE_EXITED, STOPPED_OUT, TARGET_HIT, CLOSED, PARTIAL_BOOKED

Late Session Gates (after 11 AM IST):
- Max trades placed: SKIP
- Loss > 50% of daily limit: SKIP

### Configuration

vishal-live: capital Rs.15K, max trades 3, loss limit Rs.900, conf 7, vix 20
neha-live: capital Rs.10K, max trades 3, loss limit Rs.900, conf 8, vix 20
vishal/neha paper: capital Rs.3L, max trades 6, loss limit Rs.9K, conf 7, vix 18

## 4. F&O MODULE

Strategy types: IRON_CONDOR, SHORT_STRADDLE, SHORT_STRANGLE, BULL_PUT_SPREAD, BEAR_CALL_SPREAD, DIRECTIONAL_CE_BUY, DIRECTIONAL_PE_BUY

Confluence gates:
- Hedged strategies: confluence >= 20
- Directional buy: confluence >= 60
- Naked selling: confluence >= 75

Expiry day allowed: SHORT_STRADDLE, IRON_CONDOR, DIRECTIONAL only

Quant signals: IV percentile, OI velocity, IV skew, GEX, VRP

Config (paper):
- capital Rs.50K, daily limit Rs.50K, per-trade Rs.25K
- daily loss Rs.5K, max lots 1, conf 8, vix 22
- Naked selling blocked after 14:00 IST
- Directional buy blocked after 13:00 IST

## 5. SWING MODULE

Setup types: BREAKOUT, PULLBACK, REVERSAL, MOMENTUM

Scanner (swing/scanner.py) fetches:
- Sector indices (sector strength)
- Delivery leaders (institutional interest)
- 52-week breakouts
- Live quotes for enrichment

Config (SwingConfig):
- daily_capital_limit: Rs.1,00,000
- per_trade_max_capital: Rs.30,000
- max_open_positions: 5
- min_confidence_score: 6
- max_hold_days: 15
- target_pct: 8.0
- stop_loss_pct: 4.0 (R:R 2:1)
- trailing_sl_trigger_pct: 5.0
- price_range: Rs.50-5000
- scan_time: 15:30 IST
- monitor_time: 09:30 IST

Cron:
- 5 10 * * 1-5 (3:35 PM IST scan)
- 5 4 * * 1-5 (9:35 AM IST monitor)

May 15 picks: NLCINDIA, VEDL, HDFCBANK, NAZARA, SAREGAMA, TMPV, HFCL

## 6. DATABASE SCHEMA

### intraday_trades
Columns: id, trade_date, timestamp, symbol, tradingsymbol, action, order_type, product_type, quantity, price, trigger_price, broker_order_id, broker_name, status, entry_price, exit_price, target_price, stop_loss_price, confidence_score, strategy_type, rationale, pnl, mode

Status values: PENDING, OPEN, PARTIAL_BOOKED, CLOSED, STOPPED_OUT, FORCE_EXITED, REJECTED, CANCELLED

### intraday_audit_log
Columns: id, timestamp, event_type, details_json, trade_id

### intraday_daily_summary
Columns: id, trade_date, total_trades, winning_trades, losing_trades, total_pnl, total_realized_loss, max_drawdown, broker_name, mode

### fno_trades, fno_strategies
Strategy-level + per-leg trades

### swing_trades, positional_trades
Same as intraday + hold_days, exit_date

### daily_top_performers
Tracks scanner accuracy. Columns include picked_by_us, why_missed.

## 7. CRON SCHEDULE (UTC)

Continuous intraday (9:30 AM-1:00 PM IST):
*/15 4-7 * * 1-5  run_daily.sh --profile 

F&O (single run):
50 3 * * 1-5  vishal (9:20 IST)
52 3 * * 1-5  neha (9:22 IST)
54 3 * * 1-5  vishal-live (9:24 IST)

Swing:
5 10 * * 1-5  scan (3:35 PM IST)
5 4 * * 1-5   monitor (9:35 AM IST)

Top performers:
5 10 * * 1-5  capture_top_performers.py

Dashboard sync:
0 3-10 * * 1-5  S3 sync + CloudFront invalidation

NEW EC2 only (Bug 6):
*/15 4-10 * * 1-5  sync_neha_live_db.sh

## 8. AWS BEDROCK INTEGRATION

Client config (Bug EE fix):
- read_timeout=60
- connect_timeout=10
- max_attempts=1

Model: Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5)
Region: us-east-1

Cost per scan:
- Input: ~Rs.40
- Output: ~Rs.10
- Total: Rs.50/scan

Daily cost (3 profiles, ~14 scans): Rs.2,100
Monthly cost: ~Rs.42,000

This is high for current Phase 1 capital but sustainable from Phase 3+.

## 9. BUG HISTORY (May 12-15, 2026)

Bug 1 (FIXED): Scanner saw only 169/500 stocks. 500K volume filter rejected stocks at 9:30 AM. Fix: momentum bypass.

Bug 2 (FIXED): NSE losers API endpoint dead. Fix: Use SecLwr20 from gainers response.

Bug 3 (FIXED): Limit orders failed on fast movers in 10s. Fix: 0.3% buffer + MARKET fallback for conf >= 8.

Bug 4: NOT a bug. Top performers cron just hadn't run yet.
Bug 5 (FIXED): max_trades_per_day not enforced during continuous scanning. _restore_daily_state only counted CLOSED trades. Real cost ~Rs.223 today. Fix: counts all non-rejected/cancelled BUYs. File: intraday/risk_manager.py. Needs Monday validation.
Bug T (FIXED): F&O paper P&L was synthetic theta-decay. Now uses real Dhan option chain via fno/option_chain_cache.py + fno/pnl_calculator.py. Cron */30 4-9 * * 1-5 mark-to-market every 30 min. 84 stale trades cleaned up. Validation Monday May 18.
Bug 6 (FIXED): neha-live data only on NEW EC2. Solution: NEW EC2 syncs DB + dashboard JSON to S3 every 15 min. OLD EC2 dashboard reads from S3.

Bug 5 (FIXED): max_trades_per_day not enforced. _restore_daily_state only counted CLOSED trades. Fix: count any non-rejected/cancelled BUY.

Bug 6 (FIXED): neha-live data only on NEW EC2. Fix: NEW EC2 syncs DB to S3, OLD EC2 auto-pulls.

## 10. OPERATIONS

### Common Commands

Mid-day status:
bash scripts/live_status.sh

EOD summary:
bash scripts/eod_summary.sh

Specific date:
bash scripts/eod_summary.sh 2026-05-15

Manual scan:
cd ~/dev-sandbox && export AWS_PROFILE=vishal-admin && .venv/bin/python run_intraday.py --force --profile vishal-live --live

Time sync:
timedatectl

AWS check:
aws sts get-caller-identity --profile vishal-admin

### SSM Access

aws ssm start-session --target i-0256713c061011a5f --profile vishal-admin --region ap-south-1
aws ssm start-session --target i-0233c705c9104383e --profile vishal-admin --region ap-south-1

### Log Locations

~/dev-sandbox/logs/intraday__.log
~/dev-sandbox/logs/cron_.log
~/dev-sandbox/logs/fno__.log
~/dev-sandbox/logs/swing_cron.log
~/dev-sandbox/logs/top_performers.log
~/dev-sandbox/logs/db_sync.log (NEW EC2)

## 11. ENGINEERING ROADMAP

Near-term (30 days):
- Backtest framework
- Telegram alerts
- News fetcher per stock
- Bedrock cost optimization

Medium-term (60-90 days):
- Pre-market intelligence (SGX Nifty, FII flows)
- Onboarding website
- Capital scaling to Phase 2

Long-term:
- Swing live deployment (after 30 days paper)
- Positional module
- Multi-broker support
- Mobile dashboard

## 12. KEY FILES READING ORDER

1. .kiro/steering/RULES.md
2. .kiro/steering/STATE.md
3. .kiro/steering/STRATEGY.md
4. .kiro/steering/LEARNING.md
5. .kiro/steering/GLOSSARY.md
6. .kiro/steering/BUSINESS_DOC.md
7. .kiro/steering/TECHNICAL_DOC.md (this file)
8. intraday/scanner.py
9. intraday/risk_manager.py
10. intraday/executor.py
11. fno/strategy_engine.py
12. swing/scanner.py
13. scripts/eod_summary.py
14. run_intraday.py
