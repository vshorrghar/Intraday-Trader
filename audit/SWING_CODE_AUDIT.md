# SWING CODE AUDIT
**Generated:** 2026-05-23 by Kiro from code inspection
**Scope:** Read-only. No code modified.

---

## What Exists (file inventory)

| File | Lines | Last Modified | Status |
|------|-------|---------------|--------|
| swing/scanner.py | 308 | May 19 | COMPLETE — 20-DMA pullback scoring with 5 signals + 2 penalties |
| swing/selector.py | 254 | May 19 | COMPLETE — LLM-based final pick (same pattern as intraday) |
| swing/executor.py | 239 | May 19 | COMPLETE — CNC delivery BUY orders, LONG only |
| swing/monitor.py | 301 | May 19 | COMPLETE — daily position check, trailing SL, exit logic |
| swing/risk_manager.py | 159 | May 19 | COMPLETE — position sizing, sector concentration, loss limits |
| swing/manual_override.py | 122 | May 19 | COMPLETE — manual entry/exit commands |
| swing/dashboard.py | 86 | May 22 | PARTIAL — JSON writer (recently modified, may be the rewrite in working tree) |
| swing/models.py | 77 | May 19 | COMPLETE — SwingTradeSetup, SwingConfig dataclasses |
| swing/sector_map.py | 73 | May 19 | COMPLETE — NSE sector classification + defensive sectors |
| swing/__init__.py | 1 | May 19 | STUB |

**Total: 1,620 lines across 10 files.**

---

## Strategy Implemented

**20-DMA Pullback (Investors Way Strategy 3) — LONG ONLY**

This is a REAL rules-based strategy (unlike intraday):

**Scanner signals (computed, not LLM):**
1. 20-DMA pullback proximity (0-5 pts) — how close price is to 20-day moving average
2. RSI(2) oversold (0-3 pts) — 2-period RSI below 10 = max score
3. Bullish reversal candle (0-3 pts) — hammer/engulfing pattern detection
4. Defensive sector bonus (0-3 pts) — FMCG, Pharma, IT get bonus
5. Liquidity confirmation (0-2 pts) — volume above average

**Penalties:**
1. Falling knife (-3 pts) — stock down >10% in 5 days
2. Weakening trend (-2 pts) — 20-DMA slope negative

**Entry:** Price near 20-DMA + RSI(2) oversold + reversal candle = BUY
**Exit:** Target 8% above entry OR SL 4% below entry OR max 15 days hold
**Order type:** CNC (delivery) — you own the shares

**LLM involvement:** selector.py still uses Claude for final pick from scanner candidates (same weakness as intraday — LLM decides which of the scored candidates to actually trade).

---

## What's Different From Intraday

| Aspect | Intraday | Swing |
|--------|----------|-------|
| Scanner | LLM-labeled strategies | Real computed signals (SMA, RSI, candle patterns) |
| Hold time | Same day | 2-15 days |
| Order type | MIS (intraday) | CNC (delivery) |
| Direction | LONG + SHORT | LONG only |
| SL placement | At entry | Monitor checks daily |
| Target | 3-4% | 8% |
| Stop loss | 1.8-2% | 4% |

**Key insight:** The swing scanner is MORE rules-driven than intraday. It computes actual technical indicators (SMA, EMA, RSI, ATR). The intraday scanner only scores on price movement and volume — no actual indicator computation.

---

## Database State

- Schema: `swing_trades` table exists with proper columns (symbol, entry_price, target, SL, status, pnl, strategy_type, confidence_score)
- **Trade count: 0** — never been run in production
- **Cron: NONE** — no swing cron entry exists

---

## What's Missing / TODO (from code comments)

From scanner.py:
- "TODO Week 3: Replace flat sector bonus with full correlation matrix"
- "TODO Week 3: Add 8-signal regime detector"
- "TODO Week 4: Add news sentiment signal"
- "TODO Week 4: Add FII/DII flow integration"

From selector.py:
- "TODO Week 3: Add half-Kelly position sizing"
- "TODO Week 3: Add slippage modeling per stock liquidity tier"

From executor.py:
- "TODO Week 3: Slice large orders (TWAP) for low turnover stocks"
- "TODO Week 3: Add VWAP-based entry timing"

---

## Readiness Score

| Capability | Score |
|-----------|-------|
| Paper trading swing (20-DMA pullback) | **5/10** |
| Live trading swing | **3/10** |

**Why 5/10 for paper:** Code is structurally complete (scanner → selector → executor → monitor → risk_manager). But it's never been run. Zero trades in DB. No cron. No historical data fetcher for computing 20-DMA (needs daily OHLC candles — does the system have this?). The selector still uses LLM for final pick.

**Why 3/10 for live:** Same as paper issues PLUS: no backtest, no validation data, CNC orders are real money with 2-15 day exposure, no adjustment logic.

---

## Top 3 To Enable Swing Paper Trading

1. **Daily OHLC data fetcher** [M effort] — scanner needs 20+ days of daily candles to compute SMA/EMA/RSI. Need to verify if Dhan historical API provides daily candles or only intraday.

2. **Wire cron + run_swing.py** [S effort] — create entry point script and add cron (3:35 PM IST scan, 9:35 AM IST monitor per TECHNICAL_DOC.md).

3. **Remove LLM from selector OR validate it** [M effort] — the scanner already scores candidates with real math. The LLM in selector.py adds the same uncalibrated judgment problem as intraday. For swing, the scanner score alone could drive entry decisions.

---

## F&O CLARIFICATION: Selling or Buying?

**Answer: PRIMARILY SELLING (premium collection) with protective BUY legs.**

The F&O module is an **options SELLING** system:

- **Iron Condor:** SELL OTM call + SELL OTM put (collect premium), BUY further OTM call + BUY further OTM put (protection/hedge)
- **Short Strangle:** SELL OTM call + SELL OTM put (naked, no hedge)
- **Short Straddle:** SELL ATM call + SELL ATM put (naked)
- **Bull Put Spread:** SELL higher put + BUY lower put (hedged)
- **Bear Call Spread:** SELL lower call + BUY higher call (hedged)

The BUY legs in Iron Condor and spreads are HEDGES (protection), not directional bets. The profit comes from time decay (theta) eating the premium you sold.

**Exception:** DIRECTIONAL_CE_BUY and DIRECTIONAL_PE_BUY are pure option BUYING strategies (limited risk, unlimited reward). But these are secondary — the primary strategy is Iron Condor (premium selling with hedge).

**Executor confirms:** fno/executor.py line 57: "Places SELL legs first, then BUY legs" — SELL legs are the money-makers, BUY legs are protection.

**In simple terms:** The F&O system is a premium seller that hedges its risk. It makes money when the market stays sideways (theta decay). It loses when the market moves big (beyond the sold strikes).
