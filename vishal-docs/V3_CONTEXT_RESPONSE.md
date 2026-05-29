# V3 Context Response — Answers to All Part 1 Questions

Paste this back to Claude Opus. It answers every question from Part 1 (A-E) with real data from the repo.

---

## A. Repository Structure

### 1. Folder layout — SINGLE REPO, same branch (main)

```
~/dev-sandbox/                    ← project root
├── intraday/                     ← V1 + V2 intraday module (LIVE)
│   ├── scanner.py                ← universe fetch + scoring (calls NSE API)
│   ├── selector.py               ← V1 LLM selector (Claude ranks top 20→5)
│   ├── selector_v2.py            ← V2 rules selector (V6+V4 signals)
│   ├── executor.py               ← order placement (Dhan API)
│   ├── monitor.py                ← position tracking, trailing SL, force exit
│   ├── risk_manager.py           ← position sizing, daily loss cap, VIX gate
│   ├── dhan_broker.py            ← Dhan REST API v2 client
│   ├── auth_server.py            ← TOTP auth, per-profile sessions
│   ├── models.py                 ← TradeSetup, IntraConfig dataclasses
│   └── charges.py                ← brokerage calculator
├── backtest/
│   ├── rule_engine.py            ← V6/V4/VWAP signal generation (pure math)
│   ├── trade_simulator.py        ← backtest execution engine
│   ├── data_loader.py            ← Dhan historical OHLC fetcher
│   └── universe_500.json         ← 50 stocks (Nifty50 only — NOT 500!)
├── fno/                          ← F&O module (paper only)
├── swing/                        ← Swing module (not deployed)
├── fetchers/
│   ├── nse_market_movers.py      ← NSE gainers/losers API (UNRELIABLE)
│   ├── nse_bhavcopy.py           ← NSE bhav copy (historical)
│   ├── dhan_api.py               ← Dhan data fetcher
│   └── options_fetcher.py        ← NSE option chain
├── config/
│   ├── profiles/                 ← per-profile YAML (gitignored, has TOTP/PIN)
│   │   ├── vishal-live-v2.yaml   ← REAL MONEY V2 config
│   │   ├── vishal-live.yaml      ← REAL MONEY V1 (paused)
│   │   ├── vishal.yaml           ← paper
│   │   └── neha.yaml             ← paper
│   ├── nse_security_ids.json     ← symbol → Dhan securityId mapping
│   └── config.yaml               ← global config
├── database/
│   └── db_manager.py             ← SQLite per-profile (one .db per profile)
├── scripts/                      ← operational scripts
├── dashboard/                    ← S3-hosted web dashboard
├── logs/                         ← daily log files per profile
├── run_intraday.py               ← MAIN ENTRY POINT (14-phase pipeline)
├── run_daily.sh                  ← cron wrapper (parses --profile, --live)
└── tests/                        ← 135 tests passing
```

### 2. Entry point: `run_daily.sh` → `run_intraday.py`

Cron calls `run_daily.sh --profile vishal-live-v2 --live` every 15 min.
`run_daily.sh` sets up env, then calls `.venv/bin/python run_intraday.py --profile X [--live]`.
`run_intraday.py` orchestrates 14 phases: auth → scan → pre-filter → select (V1 or V2) → risk → execute → monitor.

The `selector` field in profile YAML determines V1 vs V2:
- `selector: "v2"` → uses `intraday/selector_v2.py`
- `selector: "v1"` or missing → uses `intraday/selector.py` (Claude)

### 3. Config files

- API keys + TOTP: `config/profiles/*.yaml` (gitignored)
- Capital limits: same YAML files
- Universe: NO static CSV exists. Currently fetched live from NSE API (broken today).
- `backtest/universe_500.json` exists but only has 50 stocks (Nifty50).

### 4. Scheduler: cron (every 15 min, 9:30-13:00 IST)

```cron
*/15 4-7 * * 1-5  run_daily.sh --profile vishal-live-v2 --live
*/15 4-7 * * 1-5  run_daily.sh --profile vishal (paper)
*/15 4-7 * * 1-5  run_daily.sh --profile neha (paper)
50 3 * * 1-5      run_fno_daily.sh --profile vishal (F&O paper)
```

---

## B. Data Layer

### 1. Files calling NSE (bhav/nseindia):

**Active in live trading path:**
- `intraday/scanner.py` — calls `nseindia.com/api/equity-stockIndices?index=NIFTY%20500` (BROKEN TODAY — 404)
- `fetchers/nse_market_movers.py` — gainers/losers/active (fallback when Nifty500 fails)
- `intraday/monitor.py` — NSE LTP fallback when Dhan has no price
- `fetchers/options_fetcher.py` — NSE option chain for F&O
- `scripts/capture_top_performers.py` — EOD top movers

**Not in live path (legacy/analysis):**
- `fetchers/nse_bhavcopy.py`, `fetchers/nse_fii_dii.py`, `fetchers/nse_bulk_deals.py`
- Various `llm/*.py` files (old portfolio analyzers)

### 2. Files calling DHAN API:

**Active in live trading path:**
- `intraday/dhan_broker.py` — order placement, positions, order list, historical OHLC
- `intraday/auth_server.py` — TOTP authentication
- `scripts/sync_dhan_live.py` — pulls live positions/orders for reconciliation
- `scripts/reconcile_dhan_db.py` — compares Dhan vs DB

**Backtest/data:**
- `backtest/data_loader.py` — `get_historical_ohlc()` for 5-min candles
- `backtest/fetch_swing_data.py` — daily OHLC for swing backtest

### 3. Timeframes pulled:

- NSE API: real-time snapshot (no candles, just current OHLC/volume)
- DHAN `/v2/charts/intraday`: 5-min candles (used by backtest + V2 rule engine)
- DHAN `/v2/charts/historical`: daily candles (used by swing backtest)
- DHAN `/v2/orders`, `/v2/positions`, `/v2/fundlimit`: live account state

### 4. Cache/storage:

- SQLite: `database/{profile}.db` — trade records, audit log, daily summaries
- JSON cache: `cache/historical/{symbol}_{interval}min_{from}_{to}.json` (backtest data)
- No Parquet. No Redis. All file-based.
- Live calls every scan cycle (no caching of live data between 15-min runs)

---

## C. Universe Loading (the Nifty50 bias bug)

### 1. Current function: `intraday/scanner.py::_fetch_nifty500_candidates()`

```python
def _fetch_nifty500_candidates(...):
    s = _get_nse_session()
    r = s.get("https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500")
    r.raise_for_status()
    raw = r.json().get("data", [])
    # ... score each stock ...
```

**Problem:** This endpoint returned 404 ALL DAY on May 26. When it fails, scanner falls back to:
```python
# Fallback: gainers + losers + most active
gainers = fetch_top_gainers()   # ~20 stocks (mostly Nifty50)
losers = fetch_top_losers()     # ~20 stocks
active = fetch_most_active()    # ~20 stocks
```

This fallback gives ~60 stocks, mostly large-cap Nifty50 names. That's the "Nifty50 bias."

### 2. Ranking: by score (momentum + volume + sector), NOT by market cap

The scoring is fine. The problem is the INPUT — when NSE API fails, only 60 large-cap stocks enter the scoring pipeline instead of 500.

### 3. Where cutoff kills mid/small caps:

- `min_volume: 500_000` — kills small caps at 9:30 AM (volume hasn't built)
- `price_min: 50, price_max: 5000` — reasonable, not the issue
- The real killer: **NSE API failure → fallback = only top gainers/losers = only Nifty50**

### 4. `backtest/universe_500.json` is misnamed — only has 50 stocks (Nifty50)

---

## D. Strategy Layer

### 1. V6 screener (from `backtest/rule_engine.py::generate_orb_signals()`):

**V6 = "Gap + ORB" — catalyst stocks only:**
- Gap > 1.5% from previous close (MANDATORY for V6)
- Opening range breakout (high of first 15-min candle broken)
- Price above VWAP at breakout
- Relative volume >= 1.5x average
- Market direction = BULL (if FLAT → return empty, if BEAR → SHORT only)
- Opening range width: 0.3% to 3.0%
- Breakout must happen before 11:00 AM IST

**V4 = "ORB + VWAP" — no gap requirement:**
- Same as V6 but WITHOUT the 1.5% gap filter
- Fires on any ORB breakout with VWAP confirmation
- Currently DISABLED in production (log shows "V4 disabled")

### 2. ORB parameters:
- Opening range: first 15-min candle (9:15-9:30 IST)
- Breakout: price exceeds OR high (LONG) or OR low (SHORT)
- Volume confirmation: relative volume >= 1.5x 20-day average
- Time window: breakout must occur 9:30-11:00 IST

### 3. Risk engine (`intraday/risk_manager.py`):
- SL: entry - (1.5 × ATR) for LONG, entry + (1.5 × ATR) for SHORT
- Target: entry + (3.0 × ATR) — gives R:R of 2:1
- Position sizing: `qty = per_trade_max_capital / entry_price`
- Daily loss cap: ₹1,000 (vishal-live-v2)
- Max trades/day: 3
- VIX gate: > 25 = skip, > 22 = reduce to 1 trade

### 4. V1 Claude prompt (exact, from `intraday/selector.py`):

```
You are an expert NSE intraday trader. Your goal is maximum profit with strict capital protection.

STEP 1: READ THE MARKET FIRST
- >12 green sectors → BULLISH → trade aggressively, up to {max_trades} picks
- 8-12 green → NEUTRAL → 2-3 picks only
- <8 green → BEARISH → 1 pick max
- VIX > 20 AND red → 1 pick max with tighter SL

STEP 2: STOCK SELECTION CRITERIA
MUST HAVE ALL:
- Volume > 2,000,000
- Price between ₹{min} and ₹{max}
- Moving WITH its sector
- Clear reason for move
- high_volatility = FALSE

AVOID:
- Already up >3% from open
- high_volatility = True
- Two stocks from same sector
- Volume < 2,000,000

STEP 3: ENTRY, TARGET, STOP LOSS
LONG: SL = entry × 0.982, Target = entry × 1.036+
SHORT: SL = entry × 1.018, Target = entry × 0.964+
R:R >= 2.0 always
```

Claude receives 20 pre-filtered candidates with: symbol, LTP, open, prev_close, volume, change_pct, sector, high_volatility flag, setup_type (LONG/SHORT).

---

## E. Logging & Observability

### 1. What's logged today:

- Full pipeline phases (scan, pre-filter, select, execute, monitor)
- Per-stock scoring in scanner
- LLM prompt + response (V1)
- V2 signal detection ("V6=0", "market: FLAT SIDEWAYS")
- Order placement + fill status
- P&L on exit
- **NOT logged: full funnel counts (how many stocks passed each filter)**

### 2. Log destination:

- File: `logs/intraday_{profile}_{date}.log` (one per profile per day)
- Format: `2026-05-26 05:15:11 [INFO] intraday.selector_v2: V2: No signals...`
- Rotation: daily, kept indefinitely
- Also: `logs/cron_{profile}.log` (cron wrapper output)
- DB: `intraday_audit_log` table (events + trade_id)

---

## Additional Context for Opus

### Constraints:
- Broker: Dhan REST API v2 (MIS product for intraday)
- Square-off: 15:15 IST (forced by our code, not broker)
- IP whitelist: 13.206.144.6 (one IP per Dhan account)
- DHAN Data API: subscribed ₹499/month (client_id 1110941563)
- Bedrock: Claude Sonnet 4.6, us-east-1 (for V1 selector + post-trade analysis)
- Git: push from EC2 only (Mac is corporate, read-only)

### What's confirmed working:
- Executor (Bug A indent fix — stable since May 19)
- Monitor (Bug B orphan SL fix — stable since May 22)
- Dhan auth (per-profile sessions — stable since May 18)
- Backtest engine (rule_engine.py — 135 tests passing)
- F&O paper (Iron Condors, 79% WR, +₹4,084 cumulative)

### Architecture in Part 3 — CONFIRMED, with one addition:
- Add: continuous scanning every 15 min (not just one shot at 9:30)
- V2 already does this. V3 should maintain it.
- The 10:30 fallback is ONE check. But V2 strategies should keep scanning until 13:00.

### Constraint you missed:
- SHORT trades are DISABLED in V2 (10-20% WR historically — too risky)
- V3 should keep SHORT disabled unless regime detection proves bearish strategy works on paper first
- Force exit at 15:15 IST (not 15:30 — we exit 15 min before market close)
