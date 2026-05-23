# F&O CODE AUDIT — 8 Questions Answered
**Generated:** 2026-05-22 by Kiro from code inspection
**Scope:** Read-only. No code modified.

---

## What Exists (file inventory)

| File | Lines | Last Modified | Status |
|------|-------|---------------|--------|
| fno/strategy_engine.py | 854 | May 13 | COMPLETE — LLM-driven strategy selection with 7-strategy playbook |
| fno/quant_engine.py | 744 | Apr 22 | COMPLETE — 6 quant signals (IVP, OI velocity, IV skew, GEX, VRP, PCR) |
| fno/monitor.py | 660 | May 18 | COMPLETE — position monitoring + exit triggers + force exit |
| fno/option_chain.py | 523 | Apr 23 | COMPLETE — Dhan option chain fetcher + parser |
| fno/risk_manager.py | 258 | Apr 22 | COMPLETE — confluence gates, margin check, DTE rules |
| fno/executor.py | 300 | May 13 | COMPLETE — multi-leg order placement (SELL first, BUY second) |
| fno/reporter.py | 315 | May 8 | COMPLETE — strategy reporting |
| fno/symbols.py | 290 | Apr 22 | COMPLETE — tradingsymbol builder for Dhan F&O format |
| fno/greeks.py | 283 | Apr 22 | COMPLETE — Black-Scholes Greeks (delta, gamma, theta, vega, IV) |
| fno/paper_engine.py | 285 | May 13 | COMPLETE — virtual capital simulation |
| fno/dashboard.py | 270 | May 8 | COMPLETE — JSON writer for dashboard |
| fno/config.py | 218 | May 8 | COMPLETE — FnO_Config dataclass |
| fno/pnl_calculator.py | 157 | May 18 | COMPLETE — mark-to-market P&L from option chain |
| fno/models.py | 158 | Apr 21 | COMPLETE — dataclasses (FnOStrategySetup, QuantSignals, etc.) |
| fno/option_chain_cache.py | 81 | May 15 | COMPLETE — 5-min TTL cache layer |
| fno/__init__.py | 6 | Apr 21 | STUB — imports only |

**Total: 5,402 lines of F&O code across 16 files.**

---

## Strategy Implemented

**Answer: (c) Options selling with hedge (Iron Condor primary) + directional buys**

The code implements 7+ strategy types:
- IRON_CONDOR (4-leg hedged) — primary, most traded
- SHORT_STRANGLE (2-leg naked)
- SHORT_STRADDLE (2-leg naked)
- BULL_PUT_SPREAD (2-leg hedged)
- BEAR_CALL_SPREAD (2-leg hedged)
- DIRECTIONAL_CE_BUY (1-leg)
- DIRECTIONAL_PE_BUY (1-leg)

**Entry signal:** LLM-driven (same pattern as intraday). The quant_engine computes a confluence_score from 6 signals, then the LLM picks which strategy to deploy. Confluence gates:
- Hedged (Iron Condor, spreads): confluence >= 20
- Directional buy: confluence >= 60
- Naked selling: confluence >= 75

**Exit logic (fno/monitor.py):**
- IRON_CONDOR: 50% max profit OR 1.5x max loss OR <=1 day to expiry
- SHORT_STRADDLE/STRANGLE: 30% credit OR 2x credit loss OR expiry day 3 PM
- BULL_PUT/BEAR_CALL: 70% credit OR full loss OR <=2 days expiry
- DIRECTIONAL: 50% gain trail OR 30% loss OR before 2 PM if no movement
- Force exit at configured time (15:00 IST)

**Greeks:** Yes — Black-Scholes calculator in fno/greeks.py computes delta, gamma, theta, vega. Strategy-level net Greeks stored in fno_strategies table.

**IV used:** Yes — quant_engine.py computes IV percentile from 252-day history. IVP > 70 triggers premium selling strategies.

---

## Broker Integration Status

**COMPLETE for F&O orders.**

intraday/dhan_broker.py has dedicated F&O methods:
- `place_fno_order()` (line 349) — places with `exchangeSegment: "NSE_FNO"`
- `get_fno_positions()` (line 399) — filters positions for NSE_FNO segment
- `get_fno_margins()` (line 444) — fetches margin requirements
- `get_option_chain()` (line 481) — fetches full option chain from Dhan API

Multi-leg placement: fno/executor.py places SELL legs first, then BUY legs. Has rollback logic on partial failure (attempts to cancel placed legs if later legs fail).

**Margin calculation:** fno/risk_manager.py checks available margin before placement. Uses estimated margin from config (not real-time Dhan margin API).

---

## Data Available

| Data Source | Status | Evidence |
|-------------|--------|----------|
| Option chain (live strikes + premiums) | ✅ AVAILABLE | dhan_broker.py:481 get_option_chain() — verified working May 17+ |
| Option chain cache (5-min TTL) | ✅ AVAILABLE | fno/option_chain_cache.py |
| Greeks calculation | ✅ AVAILABLE | fno/greeks.py — full Black-Scholes |
| IV percentile (252-day) | ✅ AVAILABLE | fno/quant_engine.py — bootstraps from 30 days |
| OI velocity | ✅ AVAILABLE | fno/quant_engine.py |
| Historical option prices | ❌ NOT AVAILABLE | No historical option OHLC fetcher. Only current chain. |
| IV surface | ❌ NOT AVAILABLE | Only ATM IV computed, not full surface |

Dhan Data API subscription active for vishal account (Rs.499/month). Option chain returns 470 strikes with real data during market hours.

---

## Trade History

**96 F&O trades in vishal paper DB.** All PAPER mode. Zero live F&O trades.

Recent strategies (last 10):
- All IRON_CONDOR on NIFTY, BANKNIFTY, FINNIFTY
- Confluence scores: 27-45 range
- Status: mix of FORCE_EXITED and CLOSED
- P&L: mostly small positive (Rs.8-92K on one outlier — likely a bug in pnl_calculator)
- Net premiums: Rs.31-2717 per strategy

**Suspicious data:** Strategy id=16 (BANKNIFTY May 19) shows realized_pnl = Rs.92,025.90 on net_premium of Rs.216.15. This is almost certainly a P&L calculation bug (426x the premium collected is impossible for an Iron Condor).

**vishal-live:** Has fno_trades table but F&O cron was disabled (per Bug B fix session). No recent live F&O trades.

---

## Cron Schedule

```
50 3 * * 1-5 run_fno_daily.sh --profile vishal (9:20 AM IST)
```

Only vishal paper runs F&O daily. neha and vishal-live F&O crons were removed/disabled.

MTM update cron was added May 15 but may have been removed during crontab wipe on May 18.

---

## Iron Condor Gap Analysis

| Component | Status | Evidence |
|-----------|--------|----------|
| Option chain fetcher | ✅ EXISTS | dhan_broker.py:481, fno/option_chain_cache.py |
| Strike selection logic | ✅ EXISTS | strategy_engine.py — LLM selects strikes based on quant data |
| Multi-leg order placement | ✅ EXISTS | fno/executor.py — SELL first, BUY second, rollback on failure |
| Greeks calculation | ✅ EXISTS | fno/greeks.py — full Black-Scholes |
| P&L tracking per leg | ✅ EXISTS | fno/pnl_calculator.py + fno_trades table with strategy_id FK |
| Adjustment logic | ❌ MISSING | No code for adjusting positions when price approaches strikes |
| Exit logic (profit/loss) | ✅ EXISTS | fno/monitor.py — 50% profit, 1.5x loss, expiry proximity |
| Emergency exit | ✅ EXISTS | force_exit_all() in monitor.py |
| Margin calculator | ⚠️ PARTIAL | Uses config-based estimate, not real-time Dhan margin API |
| Expiry management | ✅ EXISTS | monitor.py checks DTE, expiry-day rules |
| Historical backtest | ❌ MISSING | No historical option data for backtesting |
| P&L accuracy | ❌ BROKEN | Strategy id=16 shows Rs.92K P&L on Rs.216 premium — calculation bug |

---

## Readiness Score

| Capability | Score |
|-----------|-------|
| (a) Paper trading Iron Condor on Nifty | **7/10** |
| (b) Live trading Iron Condor on Nifty | **4/10** |
| (c) Any F&O strategy at all | **6/10** |

**Why 7/10 for paper:** The code IS running daily and placing Iron Condor paper trades (96 trades in DB, strategies with real option chain prices since May 17). The pipeline works end-to-end. But P&L calculation has a confirmed bug (Rs.92K on Rs.216 premium), and the LLM-driven strategy selection has the same calibration issues as intraday.

**Why 4/10 for live:** No adjustment logic (if Nifty moves toward a strike, you need to roll or close). P&L bug means you can't trust reported numbers. No historical backtest to validate edge. Margin calculation is estimated, not real-time.

**Why 6/10 overall:** The infrastructure is surprisingly complete — 5,400 lines covering Greeks, quant signals, multi-leg execution, monitoring, exit rules. But it's LLM-driven for strategy selection (same weakness as intraday), and the P&L bug undermines trust in results.

---

## Top 3 Next Steps

1. **Fix P&L calculation bug** [S effort — 1-2 hours]
   Strategy id=16 shows Rs.92K on Rs.216 premium. Find and fix the calculation in fno/pnl_calculator.py or fno/monitor.py. Without accurate P&L, you can't evaluate if Iron Condors are profitable.

2. **Add adjustment logic** [M effort — 4-6 hours]
   When underlying moves within 1 std dev of a short strike, the system needs to either roll the tested side or close the position. Currently it only exits on hard thresholds. Real Iron Condor management requires dynamic adjustment.

3. **Replace LLM strategy selection with rules** [M effort — 4-6 hours]
   Same issue as intraday: the LLM picks which strategy to deploy. For Iron Condor specifically, the entry rule should be purely quantitative: IVP > 60 AND VIX 12-20 AND DTE 5-7 days AND no major event in next 5 days → deploy Iron Condor. No LLM needed for this decision.

---

## SUMMARY

The F&O module is more complete than expected — 5,400 lines of working code with Greeks, quant signals, multi-leg execution, and monitoring. It's been running daily paper trades since mid-May. The main issues are: (1) a P&L calculation bug that makes reported numbers untrustworthy, (2) LLM-driven strategy selection (same weakness as intraday), and (3) no adjustment logic for live trading. The infrastructure is 70% ready for a rules-driven Iron Condor — the missing pieces are fixable in 1-2 weekends.
