# MASTER RESUME CONTEXT — 2026-05-26
**Purpose:** Paste at start of any new AI session to resume with zero context loss.
**Last updated:** 2026-05-26 (Monday evening CET — V2 first live day, 0 trades, V3 redesign drafted)

---

## Section 1: Project Identity

- **Owner:** Vishal Shorghe, Denmark (CET timezone)
- **Project:** AI-augmented multi-strategy auto-trader for NSE India
- **EC2 OLD:** 13.206.144.6 (i-0256713c061011a5f, t3.medium, ap-south-1)
- **EC2 NEW:** 13.202.63.223 (neha-live — currently STOPPED)
- **AWS Profile:** vishal-admin
- **Broker:** Dhan REST API v2 (Rs.499/month Data API subscription)
- **AI Model:** Claude Sonnet 4.6 via AWS Bedrock us-east-1 (post-trade analysis ONLY)
- **GitHub:** https://github.com/vshorrghar/Intraday-Trader.git
- **Dashboard:** https://d2q1cy3ph7jbd0.cloudfront.net

**Capital:**
- vishal-live-v2: Rs.30,000 (REAL MONEY, rules-based V2)
- vishal paper: Rs.3,00,000
- neha paper: Rs.3,00,000
- F&O paper: Rs.50,000

**Goal:** Rs.50K-1L/month passive income from algo trading

---

## Section 2: Current Running State

### Crontab (verbatim, OLD EC2):
```
*/15 4-7 * * 1-5  vishal-live-v2 --live (V2 rules, Rs.30K)
*/15 4-7 * * 1-5  vishal paper
*/15 4-7 * * 1-5  neha paper
50 3 * * 1-5      F&O vishal paper (9:20 AM IST)
*/5 4-9 * * 1-5   Dhan live sync (every 5 min)
10 10 * * 1-5     EOD Dhan sync + reconciliation (3:40 PM IST)
0 3-10 * * 1-5    Dashboard S3 sync (hourly)
30 22 * * *       Crontab backup (daily)
30 11 * * 1-5     Crontab backup (midday)
```

### V1 vs V2 Status:
- **V1 (LLM-based):** PAUSED on live. Still runs on vishal/neha paper. Also skipped May 26 due to data failure (NSE 404 → candidates had Open=₹0).
- **V2 (rules-based):** LIVE on vishal-live-v2 since May 24. First real run May 26 = 0 trades (market FLAT SIDEWAYS all day, V6 requires bullish).
- **V3 (hybrid):** DESIGNED May 26. See `vishal-docs/V3_REDESIGN_PROMPT.md`. Not yet built.
- **Critical fix:** Commit 2f13e22 added `selector` field to IntraConfig — without it V2 silently fell back to V1.

### May 26 — First V2 Live Day (ZERO TRADES)
- V2 ran 16 times (every 15 min, 9:30-13:15 IST)
- All 16 cycles: "V6=0 (V4 disabled)" → "No signals (market: FLAT SIDEWAYS)"
- V1 paper also skipped: NSE Nifty500 API returned 404 all day
- Fallback data had Open=₹0, Volume=0 for 17/20 candidates
- Claude correctly refused: "Entering any trade with zero open price would be fabricating data"
- Root causes identified: (1) V2 bullish-only bias, (2) NSE API unreliable, (3) V4 disabled, (4) no sideways strategy
- Decision: Design V3 hybrid architecture (V2 primary + V1 fallback + regime detection)

### Tests: 135 passing in 1.11s

---

## Section 3: V2 Intraday Strategy

### Architecture:
```
Scanner (Nifty 500) → Pre-filter (20 candidates) → selector_v2.py → executor → monitor
```

### Signals (from backtest/rule_engine.py):
- **V6 (primary):** Gap > 1.5% + ORB breakout + volume > 1.5x avg + above VWAP + Nifty up
  - Backtest: 61% WR, PF 3.61
- **V4 (fill):** ORB breakout + VWAP confirmation + market direction
  - Backtest: 47% WR, PF 1.37

### Capital Config (vishal-live-v2.yaml):
- daily_capital_limit: 30,000
- per_trade_max_capital: 10,000
- max_trades_per_day: 3
- daily_loss_limit: 1,000
- selector: "v2"
- price_range_max: 100,000 (no ceiling)
- min_confidence_score: 0 (disabled — rules decide)
- LONG only (SHORT disabled)

### Dynamic Suspension List (reviewed every 2 weeks, next: 2026-06-07):
MRF (permanent — Rs.1.4L/share), SAIL, LAURUSLABS, IPCALAB, CONCOR, PRESTIGE, GNFC, BSE, SONACOMS, ANGELONE, PVRINOX, PIIND, MCDOWELL-N, GODREJCP, UBL, TATASTEEL, BPCL, ASIANPAINT, HINDUNILVR, TATACONSUM, HDFCLIFE, ADANIPOWER, BEL, COFORGE, IREDA, NAUKRI, BDL, CANBK, MAZDOCK, ASTRAL, FEDERALBNK, OFSS, BAJAJFINSV, BAJFINANCE, HEROMOTOCO, BAJAJ-AUTO, JSWSTEEL, INDIGO, COCHINSHIP

### Priority Whitelist (proven winners):
HINDZINC, NESTLEIND, PNBHOUSING, BHEL, ADANIENSOL, NTPC, SHRIRAMFIN, GRANULES, ULTRACEMCO, GRASIM, GAIL, BOSCHLTD, DRREDDY, MOTHERSON, PFC, LICI, POWERGRID, CHOLAFIN, TATACHEM, IIFLSEC, TIINDIA, IRCON, MARUTI

### NEXT WORK:
- Strategy 2: VWAP reclaim (11:00-13:00 IST window) — NOT YET BUILT
- Strategy 3: Trend continuation (13:00-14:30 IST) — NOT YET BUILT

---

## Section 4: Swing Strategy

### Best Variant: CRABEL_RSI2 (Larry Connors style)
- RSI(2) < 5 + above 200-DMA + 5-day max hold
- Backtest (2 months): 42.4% WR, PF 1.16, +Rs.2,155 net
- Verdict: PAPER_ONLY (marginal edge, needs longer validation)

### Other variants tested (all DO_NOT_DEPLOY):
- PULLBACK_TIGHT: 27% WR, PF 0.68, -Rs.7,520
- PULLBACK_WIDE: 40% WR, PF 0.98, -Rs.192
- DEFENSIVE_SECTORS: 40% WR, PF 0.90, -Rs.836
- HIGH_SCORE: 28.6% WR, PF 1.15, +Rs.1,861
- VOLUME_SURGE: 28% WR, PF 0.75, -Rs.5,262

### What is built:
- swing/scanner.py (308 lines) — 20-DMA pullback scoring
- swing/rules_selector.py (306 lines) — deterministic picker
- swing/executor.py (239 lines) — CNC delivery orders
- swing/monitor.py (301 lines) — daily position check
- backtest/fetch_swing_data.py (156 lines) — Dhan daily OHLC fetcher
- backtest/run_swing_backtest.py (439 lines) — backtest simulator
- backtest/run_swing_multi.py — 6-strategy comparison runner
- cache/swing_daily/ — 188 stocks × 246 daily candles

### What is missing for paper deployment:
1. Wire run_swing.py to cron (3:35 PM IST scan, 9:35 AM monitor)
2. Longer backtest (need 2+ years data — currently only 1 year)
3. Confirm CRABEL edge on 6+ months before deploying

---

## Section 5: F&O Strategy

### Current State: Paper trading Iron Condors daily
- 27 strategies placed (all IRON_CONDOR)
- Recent P&L: mostly positive (Rs.8-290 per strategy)
- Running via cron at 9:20 AM IST

### Rules Engine (fno/rules_strategy_engine.py):
- Rule 1: VIX > 20 → NO TRADE
- Rule 2: Sideways + IVP >= 65 + VRP >= 2 + GEX pinned → IRON_CONDOR
- Rule 3: Trending up + IVP >= 55 + bullish skew → BULL_PUT_SPREAD
- Rule 4: Trending down + IVP >= 55 + bearish skew → BEAR_CALL_SPREAD
- Rule 5: Event day + low IVP → LONG_STRADDLE
- Rule 6: Default → NO TRADE

### Bugs Fixed (commit cfe8291, 80e6e0c, 8b74321):
1. P&L calculation using wrong premium direction
2. Force exit computing P&L on stale prices
3. MTM update not handling closed strategies
4. Confluence threshold raised to 60 (65 for BANKNIFTY)

### What is NOT done:
- F&O backtest impossible without historical option chain data (Dhan doesn't provide it)
- Adjustment logic (rolling tested sides) — missing
- Live deployment — needs 30+ clean paper trades first

---

## Section 6: Dashboard State

### Existing pages:
- dashboard/v2/risk.html, universe.html (old style, mediocre)
- dashboard/v2/components/header.html (profile switcher)
- dashboard/v2/css/design.css, components.css (design system)

### Backend data (working):
- dashboard/api/v2/{profile}/audit/*.json (24 audits with AI narratives)
- dashboard/api/v2/{profile}/daily_pnl/*.json (38 daily P&L metrics)
- dashboard/api/v2/{profile}/audit/*.validation.json (trust scores)

### NOT built yet:
- audit.html frontend (deferred for capital readiness)
- Telegram alerts (scripts ready, not wired to cron)

---

## Section 7: What Kiro Built (this session cluster May 21-25)

| Commit | File | Status |
|--------|------|--------|
| d76df34 | scripts/eod_summary.py, capture_top_performers.py, sync_top_performers.py | ✅ SHORT fix |
| 3fc695c | scripts/build_daily_audit.py + 24 audit JSONs | ✅ Working |
| f9d4998 | intraday/monitor.py (Bug B fix) | ✅ Deployed |
| 3b8f88b | scripts/validate_narrative.py (strict validator) | ✅ Working |
| 38676cc | scripts/compute_daily_pnl.py + 38 JSONs | ✅ Working |
| 6b7ce44 | .kiro/steering/SYSTEM_AUDIT_PLAN.md (2.4-bis) | ✅ Committed |
| b3f3fa6 | .kiro/steering/RULES.md (Rule 26) | ✅ Committed |
| e8bfe46 | swing/rules_selector.py, fno/rules_strategy_engine.py | ✅ Validated |
| 1a71023 | backtest/fetch_swing_data.py, intraday/dhan_broker.py (get_daily_ohlc) | ✅ Working |
| efeb3ba | intraday/selector_v2.py, run_intraday.py V2 switch | ✅ LIVE |
| d6a5886 | selector_v2.py dynamic suspension + whitelist | ✅ LIVE |
| 070d3e8 | run_fno.py Phase 9 V2 switch | ✅ Running |
| 2f13e22 | IntraConfig selector field fix | ✅ Critical fix |
| cfe8291 | fno/monitor.py 4 P&L bugs + confluence threshold | ✅ Running |

---

## Section 8: All Bugs and Status

| Bug | Status | Impact |
|-----|--------|--------|
| Bug A (indent/duplicate orders) | ✅ FIXED (a2e5d66) | Was causing 2-4x position sizes |
| Bug B (orphan SL) | ✅ FIXED (f9d4998) | Cancel SL on exit, modify on trail |
| Bug C (RR data integrity) | ⚠️ PENDING | SL stored above entry for LONG |
| F&O P&L bugs (4) | ✅ FIXED (cfe8291) | Wrong premium direction, stale prices |
| IntraConfig selector field | ✅ FIXED (2f13e22) | V2 was silently falling back to V1 |
| SHORT strategies | ✅ DISABLED | 10-20% WR — removed from V2 |

---

## Section 9: Test Suite

- **Total:** 135 tests passing in 1.11s
- **Location:** tests/intraday/test_v6_strategy.py + others
- **Coverage:** V6 rule engine, ATR calculation, ORB detection, market direction
- **Run:** `.venv/bin/python -m pytest tests/ -q`

---

## Section 10: Rules for AI Assistants

1. Git flow: Edit on EC2 only. Push from EC2. Mac is read-only.
2. File edits: Python heredoc or SCP for new files. Never nano/vim/sed on .py.
3. Verification: Done = command output proving it works.
4. Real money: vishal-live-v2 changes need explicit approval.
5. One problem at a time.
6. Every command states where to run: [EC2-OLD] or [MAC].
7. After any push: Remind to pull on NEW EC2.
8. SHORT trades: Always handle symmetrically with LONG.
9. No LLM for trade decisions. LLM is for analysis only.
10. Backtest before deploy. 6-month minimum.
11. **Rule 25:** Use scripts/safe_crontab_edit.sh. Never pipe to crontab directly.
12. **Rule 26 (GOLDEN):** Dhan Data API is primary data source. Use it for everything. Never skip backtesting because "no data" — we have data.

---

## Section 11: Exact Next Session Priorities

### P0 — V3 Build (HIGHEST PRIORITY)
- Use `vishal-docs/V3_REDESIGN_PROMPT.md` as the spec
- Step 1: Replace NSE Nifty500 API with static CSV + DHAN live data
- Step 2: Re-enable V4 signal in selector_v2.py
- Step 3: Build VWAP reclaim strategy for sideways days
- Step 4: Add hybrid V2→V1 fallback (if V2 silent by 10:30 → Claude ranks top 20)
- Step 5: Add regime detection (BULLISH/SIDEWAYS/BEARISH)
- Step 6: Add funnel logging + data health gate

### P1 — Dashboard (executive overview)
- Finish and deploy `dashboard/v2/app.html` with business intelligence view
- Add compute_daily_pnl.py to cron (currently not scheduled)
- Show charge ratios, anomalies, cross-profile comparison

### P2 — Observation (after V3 ships)
- 7 days freeze: no code changes, only observe
- Daily check: did V3 trade? What regime? What signal?
- Target: trades on 80%+ of days (not 39%)

### P3 — F&O validation
- Target: 30 clean paper trades with accurate P&L
- Currently at 27 strategies — need 3 more clean ones

### P4 — Capital scaling
- If V3 shows 52%+ WR over 30 trades → scale to ₹50K
- Never scale without proof

---

## Section 12: How To Start Next Session

### If building V3:
Paste `vishal-docs/V3_REDESIGN_PROMPT.md` — it has the full architecture spec.

### If debugging/monitoring:
Paste this MASTER_RESUME file.

### Commands to run first:
```bash
# [EC2-OLD]
cd ~/dev-sandbox
git log --oneline -5
export AWS_PROFILE=vishal-admin

# Check if V3 is deployed (after build)
grep "V3\|regime\|hybrid\|fallback" intraday/selector_v2.py | head -5

# Check today's log
tail -20 logs/intraday_vishal-live-v2_$(date +%Y-%m-%d).log
grep "FUNNEL\|V6\|V4\|VWAP\|regime\|fallback\|DATA_UNHEALTHY" logs/intraday_vishal-live-v2_$(date +%Y-%m-%d).log | tail -10

# Check F&O ran
tail -10 logs/cron_fno_vishal.log

# Quick DB check
sqlite3 database/vishal-live-v2.db "SELECT COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) FROM intraday_trades"
```

### What to paste:
This entire document (MASTER_RESUME) at session start. For V3 build specifically, paste `vishal-docs/V3_REDESIGN_PROMPT.md`.

### Key files added May 26:
- `vishal-docs/V3_REDESIGN_PROMPT.md` — Full V3 architecture spec with root cause analysis
- `vishal-docs/V3_CONTEXT_RESPONSE.md` — Complete answers to Opus Part 1 (A-E) questions, paste back to continue V3 build
- `dashboard/v2/app.html` — New executive dashboard (deployed to CloudFront)
- `scripts/compute_daily_pnl.py` — patched to include vishal-live-v2 profile

### What NOT to touch:
- V1 selector.py (legacy, still used by paper profiles)
- intraday/monitor.py (Bug B fix shipped, leave alone)
- intraday/executor.py (Bug A fix shipped)
- Any live cron entry
- config/profiles/vishal-live-v2.yaml (real money config)
