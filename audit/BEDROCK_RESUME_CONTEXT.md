# PROJECT RESUME CONTEXT — For Bedrock Claude
**Last updated:** 2026-05-23
**Purpose:** Paste this at the start of any new Bedrock chat to resume project work.

---

## WHO YOU ARE WORKING WITH
- **Owner:** Vishal Shorghe, Denmark (CET timezone)
- **EC2:** ip-172-31-32-94 | /home/ec2-user/dev-sandbox (OLD EC2, 13.206.144.6)
- **AWS Profile:** vishal-admin
- **Broker:** Dhan REST API v2 (real money on vishal-live)
- **AI Model:** Claude Sonnet 4.6 via AWS Bedrock us-east-1

---

## WHAT THIS PROJECT IS
AI-augmented intraday + swing + F&O trading system for NSE India.
- **Live since:** May 12, 2026
- **Real money:** ₹15K on vishal-live (29 trades, 28% WR, -₹412 net)
- **Paper:** vishal ₹3L (92 trades, 62% WR, +₹8,137), neha ₹3L (81 trades, 46% WR, -₹3,687)
- **Goal:** ₹50K-1L/month passive income from algo trading

---

## CRITICAL FINDING (May 22-23, 2026)

**The system was audited and found to be LLM-DRIVEN, not rules-driven.**

Key problems discovered:
1. **LLM makes ALL trade decisions** — scanner narrows to 20, then Claude picks stocks, sets prices, assigns confidence and strategy labels
2. **Confidence score is LLM self-report** — inversely correlated with wins (conf 6 = 71% WR best, conf 8 = 46% WR worst)
3. **Strategy labels are descriptive, not causal** — VWAP/ORB/MOMENTUM are LLM opinions, no actual VWAP computed
4. **Live vs paper run different systems** — price_range_max 2000 vs 3000, capital 4500 vs 50000 per trade
5. **SHORT strategies catastrophic** — 10-20% WR across all profiles
6. **No backtest before deployment** — real money deployed without historical validation

**Decision:** Rebuild as genuinely rules-driven. LLM stays for post-trade analysis only.

---

## THREE TRADING STREAMS (new architecture)

### Stream 1: Intraday V6 (ORB + Gap)
- **Strategy:** Opening Range Breakout + market direction + relative volume
- **Status:** Design complete (SONNET_LOGICS.md), backtest built, initial results: 52% WR, PF 1.16
- **Entry:** Price breaks 15-min opening range high + volume > 1.5x avg + above VWAP + Nifty up
- **Exit:** 2:1 R:R target, SL at opening range low, time stop 14:30 IST
- **Universe:** ~250 F&O eligible stocks, no price ceiling
- **Key files:** backtest/rule_engine.py, backtest/trade_simulator.py, vishal-docs/SONNET_LOGICS.md

### Stream 2: Swing (20-DMA Pullback)
- **Strategy:** Buy stocks pulling back to 20-day moving average in uptrend
- **Status:** Code complete (1,620 lines), never run, 0 trades
- **Entry:** Price near 20-DMA + RSI(2) oversold + reversal candle + sector support
- **Exit:** 8% target, 4% SL, max 15 days hold
- **Order type:** CNC (delivery, you own shares)
- **Key files:** swing/scanner.py, swing/selector.py, swing/executor.py, swing/monitor.py

### Stream 3: F&O Iron Condor (options selling with hedge)
- **Strategy:** Sell OTM call + put, buy further OTM protection. Profit from theta decay.
- **Status:** 5,400 lines built, running daily paper (96 trades), P&L bug exists
- **Entry:** LLM-driven currently (needs rules replacement). Confluence score from 6 quant signals.
- **Exit:** 50% profit, 1.5x loss, or 1 day before expiry
- **Key files:** fno/strategy_engine.py, fno/quant_engine.py, fno/executor.py, fno/monitor.py

---

## INFRASTRUCTURE (keep — working well)

| Component | Status | Key File |
|-----------|--------|----------|
| Order executor (Dhan) | ✅ Working | intraday/dhan_broker.py (place_order, cancel_order, modify_order, place_fno_order) |
| Risk manager | ✅ Working | intraday/risk_manager.py (VIX gates, position sizing, daily limits) |
| Trade monitor | ✅ Working | intraday/monitor.py (trailing SL, target/SL exit, force exit 15:15) |
| Bug B fix | ✅ Shipped | Cancel SL on exit, trailing SL modifies Dhan order (commit f9d4998) |
| Daily audit | ✅ Working | scripts/build_daily_audit.py (DB + Dhan merge, drift detection) |
| AI narrative | ✅ Working | scripts/build_audit_narrative.py (Bedrock post-trade analysis) |
| Narrative validator | ✅ Working | scripts/validate_narrative.py (trust scoring) |
| Daily P&L metrics | ✅ Working | scripts/compute_daily_pnl.py (capital deployed, charges, returns) |
| Dhan live sync | ✅ Working | scripts/sync_dhan_live.py (5-min cron) |
| Reconciliation | ✅ Working | scripts/reconcile_dhan_db.py (DB vs Dhan drift) |
| Dashboard (v1) | ⚠️ Outdated | dashboard/index.html (lies about P&L — uses DB not Dhan) |
| Dashboard (v2 audit) | ✅ Backend only | dashboard/api/v2/{profile}/audit/*.json (24 audits + narratives) |
| Backtest engine | ✅ Working | backtest/rule_engine.py, trade_simulator.py |
| Crontab safety | ✅ Working | scripts/safe_crontab_edit.sh (Rule 25) |
| Multi-profile | ✅ Working | vishal-live, vishal, neha (separate DBs, configs, crons) |

---

## ACTIVE CRON SCHEDULE (OLD EC2)

```
*/15 4-7 * * 1-5  intraday vishal-live --live (every 15 min, 9:30 AM - 1:00 PM IST)
*/15 4-7 * * 1-5  intraday vishal paper
*/15 4-7 * * 1-5  intraday neha paper
50 3 * * 1-5      F&O vishal paper (9:20 AM IST)
*/5 4-9 * * 1-5   Dhan live sync (every 5 min during market)
10 10 * * 1-5     EOD Dhan sync + reconciliation (3:40 PM IST)
0 3-10 * * 1-5    Dashboard S3 sync (hourly)
30 22 * * *       Crontab backup (daily)
```

---

## BUGS CATALOG (from BUGS_AND_FIXES.md)

| Bug | Status | Impact |
|-----|--------|--------|
| Bug A (indent) | ✅ FIXED (a2e5d66) | Duplicate orders when MARKET retry fired |
| Bug B (orphan SL) | ✅ FIXED (f9d4998) | Phantom SHORT when SL fires after exit |
| Bug C (RR data) | ⚠️ PENDING | SL stored above entry for LONG trades → rr_planned=0 |
| F&O P&L bug | ⚠️ PENDING | Strategy id=16 shows ₹92K profit on ₹216 premium |

---

## KEY CONFIG (vishal-live)

```yaml
intraday:
  daily_capital_limit: 15000
  per_trade_max_capital: 4500
  max_trades_per_day: 3
  daily_loss_limit: 500
  min_confidence_score: 7
  vix_threshold: 20
  price_range_min: 100
  price_range_max: 2000
```

---

## WHAT NEEDS TO HAPPEN NEXT (priority order)

### P0 — Before any more real money
1. Replace LLM selector with rules-based V6 (ORB + gap + relative volume)
2. Backtest V6 on 6+ months data, prove edge > charges
3. Fix Bug C (RR data integrity)
4. Align live config with paper (remove price_range_max: 2000 ceiling)

### P1 — Capital scaling prerequisites
1. Capital scalability audit (Section 2.4-bis in SYSTEM_AUDIT_PLAN.md)
2. Position sizing as % of capital (not hardcoded ₹4500)
3. Remove SHORT strategies until bear regime detector built
4. Wire swing module to cron (paper first)

### P2 — After edge proven
1. Scale vishal-live to ₹50K (after 50 profitable V6 trades)
2. F&O Iron Condor: replace LLM with quantitative entry rule
3. Dashboard v2 frontend (audit.html with narrative display)
4. Telegram alerts on drift/bugs

---

## RULES FOR AI ASSISTANTS

1. **Git flow:** Edit on EC2 only. Push from EC2. Mac is read-only.
2. **File edits:** Use Python heredoc (PYEOF), never nano/vim/sed on .py files.
3. **Verification:** Done = command output proving it works. Never say "should work."
4. **Real money:** vishal-live changes need explicit approval.
5. **One problem at a time.** Fix what's asked, report other bugs, don't fix without approval.
6. **Every command states where to run:** [EC2-OLD] or [EC2-NEW] or [MAC].
7. **After any push:** Remind to pull on NEW EC2 (13.202.63.223).
8. **SHORT trades:** Always handle symmetrically with LONG. Bug history proves this matters.
9. **No LLM for trade decisions.** LLM is for analysis, code review, pattern discovery only.
10. **Backtest before deploy.** No strategy goes live without 6-month historical validation.

---

## FILE READING ORDER (for new session)

**Minimum context:** This file + SONNET_LOGICS.md
**For intraday work:** + intraday/selector.py, intraday/risk_manager.py
**For F&O work:** + fno/strategy_engine.py, fno/quant_engine.py
**For swing work:** + swing/scanner.py, swing/selector.py
**For backtest work:** + backtest/rule_engine.py, backtest/trade_simulator.py
**For infrastructure:** + .kiro/steering/RULES.md, .kiro/steering/STATE.md

---

## HOW TO RESUME

Paste this document at the start of a new Bedrock chat. Then state what you need help with. The AI should NOT:
- Suggest rebuilding what already works
- Run a general audit (already done)
- Question whether infrastructure exists (it does)
- Propose LLM-based trade decisions (explicitly rejected)

The AI SHOULD:
- Read the specific files relevant to the task
- Write deterministic, backtestable code
- Cite file:line for every claim
- Stop after each deliverable for approval
