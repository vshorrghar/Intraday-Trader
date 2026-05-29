# Swing Deployment Verification

**Date**: 2026-05-28
**Purpose**: Pre-deployment audit answering 6 planning questions.
**Status**: READ-ONLY verification. No code modified.

---

## 1. CONFIRMED CURRENT RELAXED FILTERS

### swing/rules_selector.py — Active Filter Values (lines 87-99)

| Filter | Value | Hardcoded In |
|--------|-------|--------------|
| delta_from_20dma | [-4.0%, +2.0%] | Line 87 |
| rsi2 | < 60 | Line 91 |
| last_5d_return | > -10.0% | Line 95 |
| avg_turnover | >= 3.0 Cr | Line 99 |
| min_score | from config (default 6) | Line 73 via `config.swing_min_score` |
| min_rr | from config (default 1.8) | Line 155 via `config.swing_min_rr` |

### swing/models.py — SwingConfig Defaults

| Field | Default | Note |
|-------|---------|------|
| swing_capital_limit | 50,000 | |
| swing_per_trade_max | 5,000 | |
| swing_max_open_positions | **8** | relaxed from 5 (2026-05-28) |
| swing_daily_loss_limit | 1,000 | |
| swing_weekly_loss_limit_pct | 5.0 | |
| sector_concentration_max | 2 | |
| swing_min_score | **6** | relaxed from 8 (2026-05-28) |
| swing_min_confidence | **5** | lowered to match score=6 mapping |
| swing_min_confidence_live | 7 | |
| swing_min_rr | **1.8** | relaxed from 2.0 (2026-05-28) |
| swing_max_holding_days | 30 | |

### vishal.yaml Override (on EC2, gitignored)

```yaml
swing:
  enabled: true
  swing_capital_limit: 100000
  swing_per_trade_max: 10000
  swing_max_open_positions: 8
  swing_daily_loss_limit: 2000
```

Note: YAML overrides code defaults. Vishal paper uses ₹1L capital (not ₹50K default).

---

## 2. DEPLOYMENT STATE CHECK

| Question | Answer |
|----------|--------|
| Cron entries active? | **YES** — 3 entries verified via `crontab -l` |
| run_swing.py updated from placeholders? | **YES** — real scan + monitor logic (Phase 4) |
| Manual test runs successful? | **YES** — all 3 modes (refresh/scan/monitor) tested |
| First scheduled scan time? | **Tomorrow (Thu May 29) at 4:30 PM IST** (0 11 UTC) |
| First scheduled monitor? | **Tomorrow (Thu May 29) at 9:35 AM IST** (5 4 UTC) |
| First scheduled refresh? | **Tomorrow (Thu May 29) at 4:00 PM IST** (30 10 UTC) |

Cron entries (verbatim from `crontab -l`):
```
30 10 * * 1-5 cd /home/ec2-user/dev-sandbox && bash run_swing_paper.sh --profile vishal --mode refresh
0 11 * * 1-5 cd /home/ec2-user/dev-sandbox && bash run_swing_paper.sh --profile vishal --mode scan
5 4 * * 1-5 cd /home/ec2-user/dev-sandbox && bash run_swing_paper.sh --profile vishal --mode monitor
```

---

## 3. INTEGRATION CONCERNS

| Question | Answer |
|----------|--------|
| Swing shares code with V3 intraday? | **NO** — zero cross-imports. `grep -r "from swing" intraday/` = nothing. `grep -r "from intraday" swing/` = nothing. |
| Swing shares code with F&O? | **NO** — zero cross-imports. `grep -r "from swing" fno/` = nothing. `grep -r "from fno" swing/` = nothing. |
| Will relaxing V3 or F&O affect swing? | **NO** — completely isolated modules. Different scanner, different selector, different executor, different DB tables. |

### Shared dependencies (non-module):
- `fetchers/swing_earnings_list.py` — used by swing scanner + monitor for earnings blackout
- `database/db_manager.py` — shared DB class (but separate tables: `swing_trades` vs `intraday_trades` vs `fno_trades`)
- `intraday/auth_server.py` — used by `run_swing.py` for broker auth (shared utility, not trading logic)
- `intraday/dhan_broker.py` — used for `get_daily_ohlc()` in data fetcher (shared utility)

**Conclusion**: Modules are fully isolated at the trading logic level. Shared utilities (auth, broker API, DB) are read-only or table-separated. No filter change in one module can affect another.

---

## 4. ADDITIONAL RELAXATION OPPORTUNITIES (Opinion)

### Could min_score go from 6 to 5?
**Maybe, but marginal.** Score 5 means only 1-2 signals firing. At score 6, you get at least a pullback signal (3-5 pts) plus one confirmation. Score 5 would admit stocks with only volume confirmation + a weak pullback — likely noise. Risk: more flat exits (already 26% of trades). Reward: maybe 10-15 more trades over 6 months. **Verdict: not worth it yet. Wait for Day 30 data.**

### Could max_holding_days extend from 30 to 45?
**Yes, safely.** The time stops at 7/10/15/21 days already kill losers and flat trades. Extending to 45 only affects winners that are still running at Day 30. Currently 0 trades hit the 30-day hard limit in backtest (max was 29 days). This change would have zero effect on backtest results. **Verdict: safe to extend but no impact expected. Low priority.**

### Silent filters in scanner.py worth examining:

| Filter | Line | Current | Concern |
|--------|------|---------|---------|
| Price range | 157 | Rs.50-5000 | Fine. Covers Nifty 500. |
| Avg turnover >= Rs.5 Cr | 164 | Rs.5 Cr in scanner | **DUPLICATE with selector's Rs.3 Cr.** Scanner gates at 5 Cr, selector relaxed to 3 Cr. The scanner's 5 Cr gate is MORE restrictive than the selector's 3 Cr. Stocks between 3-5 Cr turnover never reach the selector. **This is a hidden bottleneck.** |
| Must be above 200-DMA | 182 | `close < dma_200 → None` | Correct for uptrend strategy. Don't relax. |
| Must be above 50-DMA | 188 | `close < dma_50 → None` | **Aggressive.** A stock pulling back to 20-DMA might temporarily dip below 50-DMA. This gate kills legitimate deep pullbacks. **Could relax to "above 200-DMA only" and let 50-DMA be a penalty instead of a gate.** |
| ATR% between 1.5 and 5 | 192-196 | Hard gate | The upper bound (5%) blocks volatile stocks. The lower bound (1.5%) blocks low-vol stocks. Both are reasonable for swing. |
| Earnings within 5 days | 196 | Hard gate | Correct — avoid earnings surprise risk. |

**Key finding**: Scanner's Rs.5 Cr turnover gate contradicts selector's relaxed Rs.3 Cr. And the 50-DMA gate may be too aggressive for a pullback strategy.

---

## 5. PHASE 5 (STATUS REPORTER) READINESS

| Question | Answer |
|----------|--------|
| Blocked on anything? | **Partially.** The DB insert bug means paper trades aren't persisted to `swing_trades` table. Status reporter reads from DB. |
| Depends on actual paper trades in DB? | **YES** — it reads `swing_trades` table for open/closed positions. |
| When will first trades be available? | **After DB insert bug is fixed.** The bug is a keyword argument mismatch in `swing/executor.py` calling `db.insert_swing_trade(symbol=...)` when the method expects positional args. ~15 min fix. |

**Options for Phase 5:**
1. Fix DB insert bug first (15 min), then Phase 5 has real data to display
2. Build Phase 5 now with graceful "no trades yet" handling, fix DB later

**Recommendation**: Fix DB insert bug first. It's trivial and unblocks both Phase 5 AND the actual paper trading persistence.

---

## 6. DAY 30 EVALUATION CRITERIA

### Metrics Tracked Automatically (via DB + dashboard)

| Metric | Source | Tracked? |
|--------|--------|----------|
| Total trades | swing_trades table | ✅ (after DB fix) |
| Win rate | computed from exit P&L | ✅ |
| Profit factor | gross_wins / gross_losses | ✅ |
| Cumulative P&L | sum of net P&L | ✅ |
| Max drawdown | peak-to-trough equity | ✅ |
| Avg holding days | avg(exit_date - entry_date) | ✅ |
| Exit reason distribution | status column | ✅ |
| Entries per day | count by entry_date | ✅ |

### Comparison: Paper vs Backtest Predictions

| Backtest Metric | Backtest Value | Paper Target (Day 30) |
|-----------------|----------------|----------------------|
| Trades | 54 / 125 days = 0.43/day | Expect 10-15 trades in 30 days |
| Win rate | 44.4% | Accept if >= 35% (noise margin) |
| Profit factor | 2.03 | Accept if >= 1.3 |
| Max drawdown | ₹2,732 | Accept if <= ₹4,000 (scaled for ₹1L capital) |
| Avg holding | 9.8 days | Accept if 7-15 days |

### Kill Criteria (Day 30 Review)

| Condition | Action |
|-----------|--------|
| WR < 30% AND PF < 1.0 | **KILL** — strategy broken in live market |
| WR 30-35% AND PF 1.0-1.3 | **PAUSE** — reduce to 4 positions, observe 15 more days |
| WR 35-40% AND PF >= 1.3 | **CONTINUE** — within noise of backtest |
| WR >= 40% AND PF >= 1.5 | **SCALE** — consider live deployment discussion |
| Max DD > ₹5,000 (5% of ₹1L) | **PAUSE** regardless of WR — risk too high |
| 0 trades in 30 days | **INVESTIGATE** — scanner/selector/DB pipeline broken |

### How to Compare

Run at Day 30:
```bash
.venv/bin/python scripts/swing_paper_status.py --profile vishal --summary
```

Compare output against backtest JSON:
```bash
.venv/bin/python scripts/print_swing_backtest_summary.py
```

Side-by-side table in LEARNING.md entry for that date.

---

## SUMMARY

| Area | Status | Risk |
|------|--------|------|
| Filters relaxed correctly | ✅ Confirmed | None |
| Cron active | ✅ 3 entries | None |
| Code updated | ✅ No placeholders | None |
| Module isolation | ✅ Zero cross-imports | None |
| DB persistence | ⚠️ Insert bug blocks paper tracking | Low — 15 min fix |
| Scanner hidden bottleneck | ⚠️ 5 Cr turnover gate in scanner contradicts 3 Cr in selector | Medium — may reduce trade count |
| 50-DMA gate | ⚠️ May be too aggressive for pullback strategy | Medium — worth testing |

**Recommendation**: Fix DB insert bug → proceed to Phase 5 → let cron run for 30 days → evaluate.
