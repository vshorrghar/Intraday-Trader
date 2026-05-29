# V3 REDESIGN — Full Context Prompt for AI Session

**Purpose:** Paste this into a fresh AI session to redesign the trading app into V3.
**Created:** 2026-05-26 (after V2 first live day produced 0 trades)
**Author:** Vishal Shorghe

---

## PROJECT SUMMARY (STAR FORMAT)

### S — Situation

I have built an algo trading app for Indian stock market (NSE, Nifty 500 universe). The app is functional and can place real money trades via Dhan broker API.

**Version 1 (V1) — LLM-based selector:**
- Architecture: Scanner (Nifty 500) → Pre-filter (20 candidates) → Claude Sonnet 4.6 ranks top 3-5 → executor places orders
- Capital: ₹15,000 total, ~₹4,500 per trade
- Behavior: 2-3 trades/day, operationally stable
- Problem: Strategy was reasonable (59% WR on paper) but ₹4,500/trade means charges (₹60/round-trip) consume 1.5% of trade value. Net result: -₹378 over 29 trades on live. Paper (₹35K/trade) was +₹6,809 over 92 trades.
- Root cause of live loss: NOT bad picks. Charges at small capital.

**Version 2 (V2) — Rules-based selector:**
- Architecture: Scanner → Pre-filter → selector_v2.py (V6 gap+ORB + V4 ORB+VWAP) → executor
- Capital: ₹30,000 total, ~₹10,000 per trade
- Deployed: May 25, 2026 (first live run May 26)
- Behavior: V6 requires gap > 1.5% + ORB breakout + volume > 1.5x + above VWAP + Nifty up
- Problem: **Trades only on strong bullish days.** May 26 (first day): market was FLAT SIDEWAYS → V2 ran 16 times (every 15 min) → 0 signals → 0 trades → ₹0 made.
- Backtest showed V6 fires on ~39% of trading days. Remaining 61% = dead money.

**Additional critical issue discovered May 26:**
- NSE Nifty500 API returned HTTP 404 all day
- Scanner fell back to gainers/losers/active (mostly Nifty50 names)
- Fallback doesn't populate OHLC data → candidates arrive with Open=₹0, Volume=0
- V1 paper also skipped because Claude correctly refused to trade on zero data
- BOTH V1 and V2 were dead today — not because of strategy, but because of data pipeline failure

**One month spent fixing bugs instead of improving strategy:**
- Bug A: Indent causing 2-4x duplicate orders (fixed)
- Bug B: Orphan SL orders (fixed)
- Bug T: F&O synthetic P&L (fixed)
- Crontab accidentally wiped (fixed)
- Auth session conflicts (fixed)
- IntraConfig selector field missing (fixed)
- Total: 14 commits of bug fixes, 0 commits of strategy improvement

### T — Task

Redesign into V3 that:
1. Trades more consistently (target: 80%+ of trading days, not 39%)
2. Handles all market regimes (bullish, sideways, bearish)
3. Uses reliable data source (DHAN API, not flaky NSE endpoints)
4. Reduces charge impact (larger position sizes, fewer tiny trades)
5. Combines V1 intelligence with V2 discipline
6. Uses broader stock universe correctly (actual 500, not just Nifty50)

### A — Analysis / Root Causes

| # | Root Cause | Evidence |
|---|-----------|----------|
| 1 | V2 over-filtered — only works in bullish regime | May 26: 16 scans, 0 signals, market was FLAT |
| 2 | No strategy for sideways or bearish days | VWAP_RECLAIM skips on FLAT, TREND_CONT skips on FLAT |
| 3 | NSE API unreliable — 404 today | `Nifty500 fetch failed: 404` in every scan cycle |
| 4 | Fallback data doesn't populate OHLC | Candidates arrive with Open=₹0, Volume=0 |
| 5 | Universe narrows to Nifty50 on fallback | gainers/losers/active = mostly large caps |
| 6 | Capital too small on V1 made charges kill edge | ₹60 charges on ₹4,500 trade = 1.3% tax per trade |
| 7 | V4 disabled in V2 | Log shows "V6=0 (V4 disabled)" — half the strategy turned off |
| 8 | No hybrid fallback | V2 silent → nothing happens. Should trigger V1 as backup. |

### R — Required Solution (V3 Architecture)

---

## V3 ARCHITECTURE — 10 STEPS

### Step 1: Force exact Nifty500 universe from static file

Do NOT rely on NSE API for universe. Load from `config/nifty500_constituents.csv` (updated monthly).

System must confirm at startup: `Universe loaded = 500 symbols`

Source for CSV: NSE website downloads section (manual monthly update) or DHAN instrument master.

### Step 2: DHAN as single data source (Rule 26 enforcement)

Remove ALL NSE bhav copy / NSE API dependencies for live data:
- Live OHLC candles: DHAN `/v2/charts/intraday` (5-min candles)
- Live LTP: DHAN market quotes API
- Historical data: DHAN `/v2/charts/intraday` (already working for backtest)
- Option chain: DHAN optionchain endpoint (already subscribed ₹499/mo)

Keep NSE only for: index values (Nifty50 level, VIX) — these are public and reliable.

Validate every scan cycle:
- At least 400/500 stocks have valid OHLC (Open > 0, Volume > 0)
- If < 300 valid → log `DATA_UNHEALTHY` and skip cycle (don't waste Claude calls)

### Step 3: Full funnel logging every scan cycle

Every 15-min cycle must log:
```
[FUNNEL] Universe: 500 | Data valid: 487 | Liquidity pass: 312 | Momentum pass: 45 | ORB pass: 8 | Final picks: 3
```

This makes it instantly visible WHERE stocks disappear.

### Step 4: Stock diversity enforcement

Prevent Nifty50 domination:
- Max 2 stocks per sector in final picks
- Market cap distribution target: 40% large / 30% mid / 30% small
- If all picks are large-cap, force include 1 mid-cap candidate

Requires: market cap classification per stock in the static universe file.

### Step 5: Hybrid V2 + V1 fallback (MOST IMPORTANT)

```
09:30 - 10:30 IST: Run V2 Strategy 1 (Morning ORB — V6+V4)
10:30 - 10:45 IST: If V2 produced 0 trades → trigger V1 fallback
                    Send top 20 candidates to Claude: "Rank top 3"
11:00 - 13:00 IST: Run V2 Strategy 2 (VWAP Reclaim — sideways)
13:00 - 14:30 IST: Run V2 Strategy 3 (Trend Continuation)
14:30 IST:         If still 0 trades all day → V1 final attempt
```

Rules:
- V2 is primary. V1 is fallback only.
- V1 fallback uses same 20 pre-filtered candidates (not raw 500)
- Claude is ranker (pick best 3 from 20), never screener (pick from 500)
- Max 1 V1 fallback trigger per day (avoid overtrading)

### Step 6: Market regime detection

Detect regime at 9:45 IST (after 30 min of trading):

| Regime | Detection | Strategy |
|--------|-----------|----------|
| BULLISH | Nifty > prev close + 0.3%, breadth > 60% green | V6 ORB momentum |
| SIDEWAYS | Nifty within ±0.3% of prev close, breadth 40-60% | VWAP reclaim, mean reversion |
| BEARISH | Nifty < prev close - 0.3%, breadth < 40% green | SHORT setups or selective LONG on relative strength |

V2 currently only has BULLISH strategy. Need SIDEWAYS and BEARISH.

### Step 7: Reduce brokerage impact

- Minimum position size: ₹10,000 per trade (not ₹4,500)
- Target: 1-2 quality trades/day (not 3-7 small trades)
- At ₹10K/trade, charges = 0.6% (manageable)
- At ₹25K/trade, charges = 0.24% (negligible)
- Prefer fewer, larger, higher-conviction trades

### Step 8: Enable V4 signal

V4 is currently disabled in V2. Re-enable it:
- V4: ORB breakout + VWAP confirmation + market direction (any direction, not just bullish)
- V4 backtest: 47% WR, PF 1.37 — marginal but adds trade frequency
- Use V4 as secondary signal when V6 is silent

### Step 9: Data health gate

Before any strategy runs each cycle:
```python
valid_count = sum(1 for c in candidates if c.open > 0 and c.volume > 0 and c.ltp > 0)
if valid_count < 15:
    log("DATA_UNHEALTHY: only {valid_count}/20 candidates have valid data")
    return []  # skip this cycle
```

Never send zero-data candidates to Claude. Never trade on ₹0 prices.

### Step 10: Freeze after implementation

After V3 ships:
- 7 days observation only
- No code changes
- Only: run → observe → log → measure
- Review after 7 days with real data

---

## DELIVERABLES

1. Refactor scanner to use DHAN + static universe (not NSE API)
2. Add funnel logging to every scan cycle
3. Enable V4 signal alongside V6
4. Build VWAP reclaim strategy for sideways days
5. Build hybrid V2→V1 fallback logic
6. Add regime detection (BULLISH/SIDEWAYS/BEARISH)
7. Add data health gate
8. Add diversity enforcement (sector + market cap)
9. Update cron to support new flow
10. Keep code modular — each strategy in its own function

---

## WHAT NOT TO CHANGE

- intraday/executor.py (Bug A fix is stable)
- intraday/monitor.py (Bug B fix is stable)
- intraday/dhan_broker.py (working, has historical OHLC)
- config/profiles/*.yaml (real money configs)
- F&O module (separate concern)
- Swing module (separate concern)

---

## SUCCESS CRITERIA

After V3 deployed + 7 days observation:
- Trades on 80%+ of trading days (not 39%)
- Average 1.5 trades/day (not 0 or 7)
- Win rate > 50% (V6 backtest = 61%, V4 = 47%, blend target 52%+)
- Charge ratio < 30% of gross P&L (currently 99% on live)
- No silent days due to data failure
- No duplicate orders (Bug A stays fixed)

---

## CURRENT FILE LOCATIONS (EC2-OLD)

```
~/dev-sandbox/intraday/scanner.py          — universe fetch + scoring
~/dev-sandbox/intraday/selector_v2.py      — V2 rules engine
~/dev-sandbox/intraday/selector.py         — V1 LLM selector
~/dev-sandbox/backtest/rule_engine.py      — V6/V4 signal logic
~/dev-sandbox/intraday/risk_manager.py     — position sizing + gates
~/dev-sandbox/run_intraday.py              — main orchestrator
~/dev-sandbox/config/profiles/vishal-live-v2.yaml — live config
~/dev-sandbox/fetchers/nse_market_movers.py — NSE API (REPLACE)
~/dev-sandbox/intraday/dhan_broker.py      — DHAN API (KEEP)
```

---

## HONEST CONTEXT

- Total real money lost since May 12: ~₹378 (small, bounded by loss limits)
- Total paper profit (V1): +₹6,809 (inflated by one anomaly day May 6)
- V2 has literally 0 live trades (deployed May 25, first run May 26 = flat market)
- F&O paper: +₹4,084 cumulative (Iron Condors, 79% WR — promising)
- Swing: not deployed (CRABEL backtest marginal)
- Infrastructure is solid (2 EC2s, DHAN API, Bedrock, dashboard, audit system)
- The problem is NOT infrastructure. It's strategy coverage + data reliability.
