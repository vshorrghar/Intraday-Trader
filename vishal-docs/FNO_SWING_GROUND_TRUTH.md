# F&O + SWING MODULE GROUND TRUTH
**Generated:** 2026-05-27 by Kiro (READ-ONLY code inspection)
**Purpose:** V3 Phase 8 integration planning

---

# ═══════════════════════════════════════════════════════════════
# F&O MODULE
# ═══════════════════════════════════════════════════════════════

## 1. Architecture

### Main Entry Point
- `run_fno.py` — 15-phase pipeline orchestrator (config → auth → chain → quant → LLM → risk → execute → monitor → force exit → report)

### Strategy Files
| File | Lines | Role |
|------|-------|------|
| `fno/strategy_engine.py` | 854 | LLM-driven 7-strategy playbook + market regime classifier |
| `fno/quant_engine.py` | 744 | 6 institutional quant signals (IVP, OI velocity, IV skew, GEX, VRP, confluence) |
| `fno/monitor.py` | 660 | Position monitoring + exit triggers + force exit + MTM update |
| `fno/option_chain.py` | 523 | Dhan option chain fetcher + parser |
| `fno/executor.py` | 300 | Multi-leg order placement (SELL first, BUY second, rollback on failure) |
| `fno/reporter.py` | 315 | EOD strategy reporting |
| `fno/symbols.py` | 290 | Tradingsymbol builder for Dhan F&O format |
| `fno/greeks.py` | 283 | Black-Scholes Greeks (delta, gamma, theta, vega, IV) |
| `fno/paper_engine.py` | 285 | Virtual capital simulation for paper mode |
| `fno/dashboard.py` | 270 | JSON writer for dashboard |
| `fno/config.py` | 218 | FnO_Config dataclass |
| `fno/pnl_calculator.py` | 157 | Mark-to-market P&L from option chain (data-source agnostic) |
| `fno/risk_manager.py` | 258 | Confluence gates, margin check, DTE rules, VIX session control |
| `fno/models.py` | 158 | Dataclasses (FnOStrategySetup, QuantSignals, StrategyLeg, etc.) |
| `fno/option_chain_cache.py` | 81 | 5-min TTL cache layer |
| `fno/__init__.py` | 6 | Stub |

**Total: 5,402 lines across 16 files.**

### Cron Schedule
```
50 3 * * 1-5  run_fno_daily.sh --profile vishal     (9:20 AM IST)
52 3 * * 1-5  run_fno_daily.sh --profile neha       (9:22 AM IST)
# vishal-live F&O cron DISABLED (real money safety)
```

MTM update (may need restoration after May 18 crontab wipe):
```
*/30 4-9 * * 1-5  scripts/fno_mtm_update.sh >> logs/fno_pnl_update.log 2>&1
```

### Capital Config Per Profile
| Profile | Paper Capital | Daily Limit | Per-Trade Max | Daily Loss | Max Lots | Confidence | VIX |
|---------|--------------|-------------|---------------|------------|----------|------------|-----|
| vishal (paper) | ₹50,000 | ₹50,000 | ₹25,000 | ₹5,000 | 1 | 8 | 22 |
| neha (paper) | ₹50,000 | ₹50,000 | ₹25,000 | ₹5,000 | 1 | 8 | 22 |
| vishal-live | DISABLED | — | — | — | — | — | — |

---

## 2. Current State (as of last run)

### Trade Count
- **96 paper trades** in vishal DB (all IRON_CONDOR on NIFTY/BANKNIFTY/FINNIFTY)
- **0 live F&O trades** (cron disabled for real money)

### Performance (UNRELIABLE — P&L bug confirmed)
- Win rate: Cannot trust — strategy id=16 shows ₹92,025 P&L on ₹216 premium (426x, impossible)
- Cumulative P&L: Corrupted by above bug
- Profit factor: Cannot compute reliably

### Known Bugs / Limitations
1. **P&L calculation bug** — Strategy id=16 shows ₹92K on ₹216 premium. Root cause in pnl_calculator or monitor exit logic.
2. **Paper mode premium simulation** — Uses random theta decay + noise, not real option chain prices for monitoring (only MTM cron uses real prices).
3. **No adjustment logic** — If underlying moves toward short strike, no rolling/hedging.
4. **No historical option backtest** — Only current chain available, no historical option OHLC.
5. **LLM-driven strategy selection** — Same uncalibrated judgment problem as intraday.
6. **Crontab wiped May 18** — MTM cron may not be running.

---

## 3. Decision Logic

### Strategy Selection Flow
1. **Option chain fetch** — Dhan API for NIFTY, BANKNIFTY, FINNIFTY
2. **Quant signals computed** — 6 signals per index
3. **Market regime classified** — SIDEWAYS / TRENDING_UP / TRENDING_DOWN / HIGH_VOLATILITY
4. **LLM prompt built** — System prompt with quant data + user prompt with chain table
5. **Claude Sonnet 4.5** selects strategy type + strikes + lots
6. **Validation** — Confluence gates, time-of-day rules, expiry rules, confidence threshold

### Inputs to Decision
| Signal | Source | Weight in Confluence |
|--------|--------|---------------------|
| IV Percentile (IVP) | 252-day ATM IV history from `fno_iv_history` table | 20/100 |
| OI Velocity | 30-min snapshot comparison (support/resistance walls) | 20/100 |
| IV Skew | 25-delta put IV minus 25-delta call IV | 15/100 |
| GEX (Gamma Exposure) | Net gamma at each strike × OI × lot_size | 15/100 |
| VRP | ATM IV minus 20-day realized volatility | 15/100 |
| PCR + Max Pain | Put-Call ratio + distance from max pain | 15/100 |

### Confluence Score Thresholds
| Strategy Type | Min Confluence |
|---------------|---------------|
| Hedged (Iron Condor, spreads) | >= 20 |
| Directional buy (CE/PE buy) | >= 60 |
| Naked selling (straddle, strangle) | >= 75 |

### Position Sizing
- Max lots per trade: 1 (config)
- Max positions: from config (typically 3)
- Margin check: estimated SPAN + exposure (not real-time Dhan margin API)
- 2-sigma margin check for naked selling

---

## 4. Risk Management

### Stop Loss Logic Per Strategy
| Strategy | Profit Target | Stop Loss | Time Exit |
|----------|--------------|-----------|-----------|
| IRON_CONDOR | 50% of max profit | 1.5× max profit loss | ≤1 day to expiry |
| SHORT_STRADDLE | 30% of credit | 2× credit loss | Expiry day 3:30 PM |
| SHORT_STRANGLE | 50% of max profit | 1.5× max profit loss | ≤1 day to expiry |
| BULL_PUT_SPREAD | 70% of credit | Full loss (max loss) | ≤2 days to expiry |
| BEAR_CALL_SPREAD | 70% of credit | Full loss (max loss) | ≤2 days to expiry |
| DIRECTIONAL_CE/PE_BUY | 50% gain trail | 30% premium loss | Before 2 PM if no movement |

### Force Exit Time
- Configured per profile (default 15:00 IST)
- `force_exit_all()` closes all OPEN/PARTIAL_BOOKED strategies

### Daily Loss Limit
- ₹5,000 per profile (paper)
- On breach: cancels all pending, closes all open, sets `_loss_cap_breached` flag

### VIX Session Control
- VIX > 1.5× threshold (33 for paper): SKIP entire session
- VIX > threshold (22 for paper): HALVE max positions
- VIX ≤ threshold: NORMAL

### Adjustment Logic
- **NOT BUILT** — No rolling, no hedging, no dynamic strike adjustment
- Only hard exit triggers exist

---

## 5. Data Dependencies

### Option Chain Source
- **Dhan API** endpoint: `get_option_chain()` in `intraday/dhan_broker.py` line 481
- Returns: 470 strikes with LTP, OI, IV, bid/ask for NIFTY/BANKNIFTY/FINNIFTY
- Requires: Dhan Data API subscription (₹499/month, active for vishal account only)
- Cache: `fno/option_chain_cache.py` — 5-min TTL, 2s rate limit between calls

### Greeks Calculation
- **Black-Scholes** in `fno/greeks.py`
- Computes: delta, gamma, theta, vega
- Input: spot, strike, time-to-expiry, IV (from chain), option_type

### IV/IVP Calculation
- ATM IV: Average of ATM CE and PE IV from live chain
- IVP: Percentile rank of today's ATM IV vs last 252 days stored in `fno_iv_history` table
- Bootstraps from 30 days on first run, returns 50.0 (neutral) if < 1 day history

---

## 6. Live Readiness Assessment

### Ready for real money? **NO**

### Why Not
1. **P&L bug** — Cannot trust reported numbers (₹92K on ₹216 premium)
2. **No adjustment logic** — Real Iron Condors need rolling when tested
3. **LLM strategy selection** — Uncalibrated, same weakness as intraday
4. **No backtest** — Zero historical validation of edge
5. **Paper mode uses simulated premium** — Monitor cycle uses random theta decay, not real prices
6. **Margin estimation** — Uses config-based estimate, not real-time Dhan margin API

### What's Missing for Live
1. Fix P&L calculation bug
2. Build adjustment logic (roll tested side when underlying within 1σ of short strike)
3. Replace LLM strategy selection with pure rules (IVP > 60 + VIX 12-20 + DTE 5-7 → Iron Condor)
4. Run 30+ paper trades with ACCURATE P&L tracking
5. Validate 60%+ win rate on Iron Condors specifically
6. Build real-time margin check via Dhan API

### Estimated Margin Per Trade
| Index | Strategy | Estimated Margin |
|-------|----------|-----------------|
| NIFTY Iron Condor (1 lot, 25 qty) | 4-leg hedged | ~₹40,000 |
| BANKNIFTY Iron Condor (1 lot, 15 qty) | 4-leg hedged | ~₹55,000 |
| NIFTY Short Strangle (1 lot) | 2-leg naked | ~₹120,000 |

---

# ═══════════════════════════════════════════════════════════════
# SWING MODULE
# ═══════════════════════════════════════════════════════════════

## 1. Architecture

### Main Entry Point
- `run_swing.py` — Pipeline orchestrator (currently placeholder phases 6-16)

### Strategy Files
| File | Lines | Role |
|------|-------|------|
| `swing/scanner.py` | 308 | 20-DMA pullback scoring (5 signals + 2 penalties) |
| `swing/selector.py` | 254 | LLM-based final pick (Claude Sonnet 4.5) |
| `swing/rules_selector.py` | 280 | **Deterministic rules-based selector** (no LLM) |
| `swing/executor.py` | 239 | CNC delivery BUY orders, LONG only |
| `swing/monitor.py` | 301 | Daily position check, trailing SL, smart time stop |
| `swing/risk_manager.py` | 159 | Position sizing, sector caps, regime check, loss limits |
| `swing/manual_override.py` | 122 | Pause/resume + manual exit queue |
| `swing/dashboard.py` | 86 | JSON writer for dashboard |
| `swing/models.py` | 77 | SwingTradeSetup, SwingConfig dataclasses |
| `swing/sector_map.py` | 73 | NSE sector classification + defensive sectors |
| `swing/__init__.py` | 1 | Stub |

**Total: 1,900 lines across 11 files.**

### Cron Schedule
- **NOT SCHEDULED** — No cron entry exists for swing
- Planned per TECHNICAL_DOC.md:
  - `5 10 * * 1-5` — scan at 3:35 PM IST
  - `5 4 * * 1-5` — monitor at 9:35 AM IST

### Universe
- Nifty 500 (via NSE API, same as intraday)
- Filtered by: price ₹50-5000, 20-day avg turnover ≥ ₹5 Cr, above 200-DMA, above 50-DMA
- Sector map: 80+ stocks hardcoded in `swing/sector_map.py`

---

## 2. Backtest Results

### **NO BACKTEST EXISTS FOR SWING**

- Zero backtest runs
- Zero historical data for swing-specific signals
- The `backtest/` module only covers intraday scanner replay
- Swing scanner needs 200+ days of daily OHLC candles per stock (for 200-DMA computation)
- This data is NOT currently fetched or cached

### What Would Be Needed
- Daily OHLC for Nifty 500 (200+ trading days per stock)
- Dhan historical API provides intraday candles; daily candles need separate endpoint or aggregation
- Estimated data fetch: 500 stocks × 200 days = 100,000 data points

---

## 3. Decision Logic

### Scanner Signals (computed, NOT LLM)
| Signal | Points | Logic |
|--------|--------|-------|
| 20-DMA pullback proximity | 0-5 | How close price is to 20-DMA (touch = 5pts) |
| RSI(2) oversold | 0-3 | RSI(2) < 5 = 3pts, < 10 = 2pts, < 15 = 1pt |
| Bullish reversal candle | 0-3 | Hammer = 3, engulfing = 3, inside day = 2, doji = 1 |
| Defensive sector bonus | 0-3 | FMCG/Pharma/Healthcare = 3pts |
| Liquidity confirmation | 0-2 | Turnover > ₹20 Cr = 2pts |

### Penalties
| Penalty | Points | Logic |
|---------|--------|-------|
| Falling knife | -3 | Last 5 days return < -8% |
| Weakening trend | -2 | Price above 200-DMA but below 50-DMA |

### Entry Rules (rules_selector.py — deterministic, no LLM)
1. Score >= 8 (min_score)
2. Delta from 20-DMA: -2% to +1%
3. RSI(2) < 50
4. Last 5-day return > -8%
5. Avg turnover >= ₹5 Cr
6. SL = max(4%, 1.5×ATR%), capped at 8%
7. Target = 2.5× SL distance, capped at 15%
8. R:R >= 2.0

### Exit Rules (monitor.py)
| Trigger | Action |
|---------|--------|
| Price ≤ SL | EXIT (STOPPED_OUT) |
| Price ≥ Target | Partial book 50%, trail rest at 50% of gain |
| 30 days held | EXIT (hard limit) |
| 21 days + P&L < 3% | EXIT (low progress) |
| 15 days + losing | EXIT |
| 10 days + flat (±1%) | EXIT |
| 7 days + drawdown > 3% | EXIT |
| Earnings within 1 day | EXIT |
| Winning trade | HOLD (never auto-sells winners before target) |

### Position Sizing
- 1% risk per trade (flat rule)
- Risk per share = entry - SL
- Quantity = (capital × 0.01) / risk_per_share
- Capped at 10% of capital in one stock

### Max Concurrent Positions
- 5 (configurable via `swing_max_open_positions`)

---

## 4. Risk Management

### Stop Loss Per Trade
- Computed: max(4%, 1.5×ATR(14)%), capped at 8%
- Typical: 4-6% below entry
- NO broker SL order at entry — monitor checks daily

### Max Drawdown Per Position
- 7-day drawdown > 3% → EXIT
- Weekly portfolio loss > 5% of capital → HALVE all new position sizes

### Overnight Risk Handling
- CNC delivery = you own the shares overnight
- No overnight hedge
- Earnings blackout: exit if earnings within 1 day (via `fetchers/swing_earnings_list.py`)

### Regime Check (3-signal)
- VIX > 25: SKIP all swing entries
- Nifty below 200-DMA: SKIP (bear regime)
- VIX > 22: HALVE position sizes
- Nifty below 50-DMA: HALVE position sizes

---

## 5. Live Readiness

### Wired to cron? **NO**
- `run_swing.py` exists but is placeholder (phases 6-16 log "placeholder")
- No cron entry on either EC2

### Data Window Sufficient? **NO**
- Scanner needs 200+ days daily OHLC per stock
- This data is NOT fetched or cached
- Dhan historical API provides intraday candles; daily candles need verification

### Confidence Level for Paper Deployment: **4/10**
- Code is structurally complete (scanner → selector → executor → monitor → risk)
- `rules_selector.py` provides deterministic selection (no LLM dependency)
- But: never been run, zero trades in DB, no daily OHLC data fetcher, no cron

---

## 6. Capital and Product

### Order Type
- **CNC (Cash and Carry)** — delivery, you own shares
- NOT MIS (intraday) — positions carry overnight

### Estimated Capital Per Position
- At ₹50,000 capital with 1% risk and 5% SL:
  - Risk amount = ₹500
  - If stock at ₹1000, SL at ₹950 (₹50 risk/share)
  - Quantity = 500/50 = 10 shares
  - Capital deployed = 10 × ₹1000 = ₹10,000 per position

### Max Positions Concurrent
- 5 (default config)
- Max capital deployed: ~₹50,000 across 5 positions

### Config Defaults (from SwingConfig)
| Setting | Value |
|---------|-------|
| swing_capital_limit | ₹50,000 |
| swing_per_trade_max | ₹5,000 |
| swing_max_open_positions | 5 |
| swing_daily_loss_limit | ₹1,000 |
| swing_weekly_loss_limit_pct | 5% |
| sector_concentration_max | 2 per sector |
| swing_min_score | 8 |
| swing_min_confidence | 7 (paper) / 8 (live) |
| swing_min_rr | 2.0 |
| swing_max_holding_days | 30 |

---

# ═══════════════════════════════════════════════════════════════
# INTEGRATION QUESTIONS
# ═══════════════════════════════════════════════════════════════

## 1. Can V3 Intraday + F&O + Swing Share:

### Universe Loader?
**PARTIALLY — needs work.**
- Intraday: fetches Nifty 500 live quotes from NSE API (intraday prices)
- Swing: needs 200+ days daily OHLC per stock (different data shape)
- F&O: uses index option chains (NIFTY/BANKNIFTY/FINNIFTY), not equity universe
- **Shared:** NSE Nifty 500 symbol list. **Not shared:** data format, timeframe, endpoints.

### Regime Detector?
**YES — strong candidate for sharing.**
- F&O has: `MarketRegimeClassifier` (VIX + 3-day spot + OI support/resistance → 4 regimes)
- Swing has: `check_regime()` (VIX + Nifty vs 50-DMA + Nifty vs 200-DMA → 3 signals)
- Intraday has: VIX gates in risk_manager (VIX > 25 skip, > 22 reduce)
- **V3 opportunity:** Unified regime detector that feeds all three modules with consistent market state.

### Trip Wire System?
**YES — can share.**
- F&O has: daily loss cap breach → force close all + flag
- Swing has: daily loss limit + weekly loss limit
- Intraday has: daily loss limit + max trades
- **V3 opportunity:** Single trip wire service that monitors aggregate exposure across all modules.

### Dhan Auth Session?
**YES — already shared.**
- `intraday/auth_server.py` handles TOTP auth for all modules
- F&O `run_fno.py` calls `authenticate_broker()` from same auth_server
- Swing `run_swing.py` calls same `authenticate_broker()`
- Per-profile session files (`.broker_session_{profile}.json`) already support multi-module access
- **Constraint:** One IP per Dhan account (OLD EC2 = vishal, NEW EC2 = neha)

---

## 2. Conflicts to Handle

### Same Stock in V3 Intraday AND Swing on Same Day?
**YES — real conflict.**
- Intraday: BUY MIS (intraday margin, auto-squared at 3:15 PM)
- Swing: BUY CNC (delivery, holds overnight)
- Same stock, same direction = doubled exposure
- Same stock, opposite direction = hedged but confusing
- **Resolution needed:** Cross-module position check before entry. If swing holds RELIANCE LONG, intraday should not SHORT RELIANCE same day.

### Capital Allocation Conflicts?
**YES — different margin pools.**
- MIS (intraday): uses intraday margin (5× leverage on equity)
- CNC (swing): uses full cash (no leverage)
- NRML (F&O): uses SPAN + exposure margin
- **Resolution needed:** Capital allocator that reserves pools per module. Example: ₹15K intraday + ₹50K swing + ₹50K F&O = ₹115K total, each module sees only its pool.

### Cron Timing Collisions?
**MINIMAL — different times.**
- Intraday: `*/15 4-7 * * 1-5` (9:30 AM - 1:00 PM IST, every 15 min)
- F&O: `50 3 * * 1-5` (9:20 AM IST, single run)
- Swing scan: `5 10 * * 1-5` (3:35 PM IST, after market close)
- Swing monitor: `5 4 * * 1-5` (9:35 AM IST, post-open)
- **Potential collision:** Swing monitor at 9:35 AM overlaps with intraday scan at 9:30/9:45. Both hit Dhan API. Rate limiting needed.

---

## 3. Shared Infrastructure

### Database
**Currently: ONE DB per profile** (e.g., `database/vishal.db`)
- Contains: `intraday_trades`, `fno_trades`, `fno_strategies`, `swing_trades`, `positional_trades`
- All modules write to same SQLite file
- **V3 decision:** Keep single DB per profile (simpler) OR split per module (isolation)?
- **Recommendation:** Keep single DB — cross-module queries (e.g., "total exposure across all strategies") are easier.

### Logging
**Currently: Separate log files per module per day**
- `logs/intraday_{profile}_{date}.log`
- `logs/fno_{profile}_{date}.log`
- `logs/swing_cron.log`
- **V3 opportunity:** Unified structured logging with module tag. Single log file per profile per day, filterable by module.

### Audit System
**Currently: Single `intraday_audit_log` table**
- F&O writes to same table (event_type prefix: `FNO_*`)
- Swing has separate `insert_swing_audit()` method
- **V3 opportunity:** Unified audit table with module column.

### Dashboard
**Currently: Separate JSON files per module**
- `dashboard/api/{profile}/intraday_latest.json`
- `dashboard/api/{profile}/fno_latest.json`
- `dashboard/api/{profile}/swing/portfolio.json`
- **V3 opportunity:** Unified dashboard API with module tabs. Already partially exists in current dashboard HTML.

---

# ═══════════════════════════════════════════════════════════════
# SUMMARY: READINESS SCORES
# ═══════════════════════════════════════════════════════════════

| Module | Paper Ready | Live Ready | Key Blocker |
|--------|-------------|------------|-------------|
| F&O Iron Condor | 7/10 | 4/10 | P&L bug + no adjustment logic |
| F&O Directional | 5/10 | 2/10 | LLM-driven + no backtest |
| Swing (rules) | 4/10 | 2/10 | No daily OHLC data + never run |
| Swing (LLM) | 3/10 | 1/10 | Same LLM weakness + no data |

### Priority for V3 Integration
1. **Fix F&O P&L bug** (1-2 hours) — unblocks trust in paper results
2. **Build daily OHLC fetcher** (4-6 hours) — unblocks swing scanner
3. **Wire swing cron** (1 hour) — unblocks paper trading
4. **Unified regime detector** (4-6 hours) — shared across all modules
5. **Cross-module position check** (2-4 hours) — prevents doubled exposure
6. **Capital allocator** (4-6 hours) — reserves pools per module
