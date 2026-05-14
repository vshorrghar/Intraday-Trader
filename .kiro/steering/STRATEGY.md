# STRATEGY.md — Technical Evolution Log

**Purpose**: How the system makes decisions. What changed. What's planned.
**Update rule**: Update CURRENT SYSTEM whenever code changes. Append to EVOLUTION LOG.

---

## CURRENT SYSTEM (as of 2026-05-14)

### Scanner (intraday/scanner.py)
- Source: NSE Nifty 500 API
- Scoring: Volume-first model (BEING REPLACED today with RS-first)
- Output: Top 15 LONG + 15 SHORT = 30 candidates
- Known issue: High volume PSU stocks dominate (VEDL/ONGC always win)
- Bug FF: NSE gainers/losers API returns 0 — scanner runs on partial data

### Selector (intraday/selector.py)
- Pre-filter: 30 → 20 candidates (price range, volume, high_volatility flag)
- LLM: Claude Opus 4.7 via AWS Bedrock (us-east-1)
- Validation: R:R >= 2.0, confidence >= threshold, direction logic
- Timeout issue: Opus slow at 9:26 AM market open (Bug EE)

### Risk Manager (intraday/risk_manager.py)
- VIX gate: > threshold → reduce max trades to 1
- Daily loss cap: ₹600 (vishal-live/neha-live)
- Per trade max: ₹4,000
- Late session gates: after 11 AM IST

### Executor (intraday/executor.py)
- Entry order → wait for fill → SL order
- Tick-aligned prices (₹0.05 NSE tick)
- Direction-aware (LONG=BUY, SHORT=SELL)

### Monitor (intraday/monitor.py)
- 5-min cycles
- Trailing SL after 0.5% profit
- 50% partial book at target
- Force exit 15:15 IST
- Bug GG: Live P&L stays ₹0 (compute_current_premium not fetching live prices)

### Cron Schedule
- 9:26 AM: vishal-live (real money)
- 9:28 AM: neha-live (real money, NEW EC2)
- 9:25/12:00/13:30: vishal paper
- 9:27/12:02/13:32: neha paper

---

## EVOLUTION LOG (append only — newest at top)

### v1.2 — 2026-05-14 (IN PROGRESS)
- Diagnosing: Bug EE (Bedrock timeout), Bug FF (NSE gainers 0), Bug GG (P&L=0)
- Planning: RS-first scanner scoring rewrite
- Planning: Continuous 15-min scanning
- Planning: Bedrock timeout + Sonnet fallback

### v1.1 — 2026-05-13
- Added: NSE tick size rounding (Bug H fixed — Dhan was rejecting orders)
- Added: Force exit waits for fill before logging P&L (Bug J fixed)
- Added: SL hit + target hit broker orders (Bug K fixed)
- Added: Dashboard shows real exit_price + charges (Bug A+D fixed)
- Added: Rule 11 — heredoc only edits for .py files
- Added: Multi-EC2 architecture (Rule 20) — neha-live on NEW EC2

### v1.0 — 2026-05-12
- First real money trade: ONGC LONG (vishal-live)
- System live with basic volume-first scanner
- Paper trading active on vishal + neha profiles
- F&O paper active (iron condors, but P&L synthetic)

---

## KNOWN BUGS (active)

| ID | Severity | Description | File |
|----|----------|-------------|------|
| EE | HIGH | Bedrock Opus timeout at 9:26 AM market open | llm/bedrock_client.py |
| FF | HIGH | NSE gainers/losers returns 0 stocks | fetchers/nse_market_movers.py |
| GG | HIGH | Live P&L stays ₹0 in monitor | intraday/monitor.py |
| HH | HIGH | 0 orders placed after sizing (new, 2026-05-14) | intraday/executor.py |
| T  | HIGH | _compute_current_premium returns entry price always | fno/monitor.py |
| L  | HIGH | F&O legs_json missing expiry_date | fno/strategy_engine.py |
| NEW| MED  | SHORT R:R calculated wrong in risk_manager sizing | intraday/risk_manager.py |

---

## WHAT WE BUILD NEXT (prioritized)

### This Week
1. RS-first scanner scoring (HINDALCO/CIPLA over VEDL)
2. Continuous 15-min scanning (catch intraday breakouts)
3. Fix Bug FF (NSE gainers API)
4. Fix Bug GG (live P&L)
5. Fix Bug HH (0 orders placed)
6. Bedrock timeout + fallback

### Next Week
1. Swing module foundation
2. Telegram alerts wired
3. Backtest framework start
4. Pre-market intelligence (SGX/FII/pre-open)

### This Month
1. Positional module
2. Dashboard per-user improvements
3. Onboarding site live
4. Scale to ₹50K after 50 profitable trades

---

## SCORING MODEL COMPARISON

### Old Model (volume-first) — BROKEN
| Signal | Weight | Problem |
|--------|--------|---------|
| change_pct > 0 | +2 | Flat +2 for any green — +0.1% = +3% same score |
| volume > 2M | +2 | Dominates — VEDL always wins |
| volume > 5M | +1 | More volume bias |
| change_from_open > 0 | +1 | Flat — no strength measure |
| high_volatility | -3 | Penalizes best movers (NLCINDIA +17% gets -3) |

### New Model (RS-first) — BUILDING TODAY
| Signal | Weight | Logic |
|--------|--------|-------|
| change_from_open (tiered) | 0-5 | Are buyers STILL buying? Most important |
| change_pct (tiered) | 0-4 | How strong is the move? |
| near day high | 0-2 | Price at high = no resistance |
| volume (capped) | 0-2 | Confirms only, doesn't lead |
| sector tailwind | 0-2 | Trade with the wind |
| hot sector bonus | 0-2 | What worked in last 45 min today |
| chasing penalty | -2 to -4 | change_from_open > 6% = too late |
| gap fade penalty | -3 | Gapped up but now selling = avoid |
