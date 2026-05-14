# STATE.md — Current Project State

**Last Updated**: 2026-05-14, ~22:00 IST (end of session, 7 commits today)
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-14) — MASSIVE UPGRADE SESSION

### Session Outcome
7 commits, 30+ file changes. Scanner completely rewritten (RS-First v3).
Capital limits raised. Continuous scanning enabled. Top 20 capture live.
War Room dashboard tab live. Telegram module ready (needs token).

### Commits Today (newest first)
8fe6d03 — Sector rotation + time multiplier + trap detector (Scanner v3) 6ef8ab5 — Fade detector + reward huge winners (Scanner v2) 25361a5 — Top 20 movers + why_missed reasons in War Room cf80098 — Fix War Room JS (was rendering as text outside script block) ddac03e — War Room Top Movers tab with scanner accuracy 308e8b5 — Continuous scan + top10 capture + VIX + Telegram + SHORT RR + options 23a0261 — Bedrock 60s timeout + NSE gainers fix + live PnL + RS-first scanner

### Real Money Trades This Week
| Date | Profile | Stock | Direction | Net P&L |
|------|---------|-------|-----------|---------|
| May 12 | vishal-live | ONGC | LONG | -Rs.53.80 |
| May 12 | vishal-live | WIPRO | SHORT | -Rs.20.00 |
| May 13 | vishal-live | HINDZINC | LONG | -Rs.28.30 |
| May 14 | vishal-live | VEDL x10 @ 334.30 | LONG | TBD (manual run) |
| May 14 | neha-live | SAIL x19 @ 206.42 | LONG | -Rs.63 approx |

**Cumulative real money P&L**: ~-Rs.165 over 4 closed trades + 1 TBD

### Why Today's Real Money Picks Were Bad (Pre-Fix Scanner)
Real top movers May 14 that we missed:
- SAREGAMA +15.15% (at day high) — scanner penalized as "chasing"
- NLCINDIA +14.61% — chasing penalty -2
- CIPLA +8.09% (at day high) — scored lower than top 15
- ADANIENT +8.85% — chasing penalty -2

What scanner picked instead: VEDL +4.99% (won on volume 77M).

**Root cause**: Volume-dominated scoring + chasing penalty killed real winners.
**Fix**: 7 separate scanner improvements committed today (see Scanner Evolution).

---

## SCANNER EVOLUTION (today's changes)

### v1 (pre-May 14) — REPLACED
Volume-first scoring. VEDL won every day on 38M volume daily.

### v2 (commit 6ef8ab5) — Mid-day
- Removed chasing penalty (-4 if change_from_open > 8%)
- Added fade detector (-3 if fell >3% from day high)
- Boosted momentum: +15% = 8pts (was max 4pts)

### v3 (commit 8fe6d03) — End of day, LIVE TOMORROW
- Sector rotation bonus (top 3 sector +3, outperforming sector +2)
- Time-aware multiplier (first hour 1.5x, late session 0.4x)
- Trap detector (gap with no sector support, buying climax)

### Expected Tomorrow Scoring (validation test)
With 1.5x first-hour multiplier:
- SAREGAMA-type (+15%, at high, top sector): (5+8+2+2+1+3) x 1.5 = **31**
- CIPLA-type (+8%, at high, pharma top 5): (5+5+2+2+1+2) x 1.5 = **25**
- VEDL-type (+5%, at high, mid sector): (3+4+2+2+1+1) x 1.5 = **19**

Real gems should now beat slow movers by 30-60%.

---

## LIVE STATUS (2026-05-14, 22:00 IST)

### Both EC2s Running
| EC2 | IP | Profiles | Status |
|-----|----|----------|--------|
| OLD | 13.206.144.6 | vishal-live, vishal, neha paper, F&O | Running |
| NEW | 13.202.63.223 | neha-live only | Running |

### Continuous Scanning Active
Both EC2s now run `*/15 4-7 * * 1-5` cron — scans every 15 min from 9:30 AM to 1:00 PM IST.
Late session gates (after 11 AM) prevent revenge trading.

### New Capital Limits (effective tomorrow 9:30 AM)
| Profile | Capital | Max Trades | Loss Limit | VIX Threshold |
|---------|---------|------------|------------|---------------|
| vishal-live | Rs.15,000 (was 10K) | 3 (was 2) | Rs.900 (was 600) | 20 (was 18) |
| neha-live | Rs.10,000 | 3 (was 2) | Rs.900 (was 600) | 20 (was 16) |
| vishal paper | Rs.3,00,000 | 6 (was 5) | Rs.9,000 | 18 |
| neha paper | Rs.3,00,000 | 6 (was 5) | Rs.9,000 | 18 |

### VIX Logic (NEW)
- VIX > 25 → SKIP entire session
- VIX > 22 → reduce to 1 trade max
- VIX <= 22 → normal trading per profile max

---

## FIXED TODAY (priority order)

### Critical
| ID | Description | Commit | Status |
|----|-------------|--------|--------|
| EE | Bedrock Opus timeout 25 min at 9:26 AM | 23a0261 | FIXED — 60s read_timeout |
| FF | NSE gainers returns 0 every call | 23a0261 | FIXED — returns 20 now |
| GG | Live P&L stays Rs.0 in monitor | 23a0261 | FIXED — fetches NSE LTP fallback |
| SHORT-RR | SHORT R:R calculated as 0.0 | 308e8b5 | FIXED — direction-aware |
| WAR-ROOM | War Room tab missing/broken | ddac03e + cf80098 | FIXED — Top 20 + why_missed |
| SCANNER | RS-first not properly applied | 23a0261 | FIXED — verified grep |

### Built Today
| Feature | Description |
|---------|-------------|
| Continuous scanning | */15 min on both EC2s |
| Top 20 capture | scripts/capture_top_performers.py — runs 3:35 PM IST |
| Why missed reasons | Scanner accuracy tracking with diagnostics |
| Telegram module | Config-aware, 5 functions ready |
| Options fetcher | NSE option chain, ATM strike, IV percentile |
| Scanner v3 | Sector rotation + time multiplier + trap detector + huge winner rewards |
| daily_top_performers table | Added to all 5 profile DBs with why_missed column |

---

## OPEN BUGS / PENDING WORK

### High Priority
| ID | Description | File | Impact |
|----|-------------|------|--------|
| HH | 0 orders placed at 12:03 PM neha-live (May 14) | intraday/executor.py | Real money — orders not placed despite sizing OK |
| TELEGRAM-WIRE | Module ready but not called from monitor.py/executor.py | alerts/telegram.py | Phone alerts blocked |
| SL-TIMING | SL placed before BUY confirmed fill | intraday/executor.py | Could fail on limit orders |

### Medium
| ID | Description | File |
|----|-------------|------|
| L | F&O legs_json missing expiry_date | fno/strategy_engine.py |
| T | F&O live P&L never updates | fno/monitor.py |
| G | Dhan credentials rotation needed | profile yamls |
| I | AWS keys rotation needed | ~/.aws/credentials |

### Low / Future
- Backtest engine (replay 30 days through new scanner)
- News fetcher (per-stock sentiment)
- Fundamentals fetcher (positional module prep)
- Swing module
- Positional module
- Per-profile S3 prefixes (NEW EC2 dashboard sync)

---

## TOMORROW MORNING CHECKLIST (2026-05-15, Friday)

### Pre-Market (before 9:15 AM IST)
1. SSH to OLD EC2 — verify time sync: `timedatectl`
2. SSH to NEW EC2 — verify time sync: `timedatectl`
3. Check git in sync: `git log --oneline -3` on both EC2s

### Market Open Validation (9:30 AM IST)
1. Watch live: `tail -f ~/dev-sandbox/logs/intraday_vishal-live_2026-05-15.log`
2. Confirm Bedrock responds in time (not 25 min timeout)
3. Note which stocks scanner picks
4. Compare to NSE top gainers — does scanner now catch SAREGAMA-type movers?

### Mid-Session (11:00 AM IST)
1. Check War Room tab: https://d2q1cy3ph7jbd0.cloudfront.net?profile=vishal-live
2. Note scanner accuracy — did we catch any real winners?
3. Check if continuous scanning placed multiple trades (max 3 limit)

### EOD (3:35 PM IST)
1. Top performers capture cron should run automatically
2. Verify: `cat ~/dev-sandbox/logs/top_performers.log`
3. Check accuracy: was today's scanner v3 better than yesterday's v1?

### Watch For
- Bedrock timeout regression (should NOT happen with 60s timeout)
- VIX > 22 → only 1 trade (test the new fixed thresholds)
- Late session gate triggers after 11 AM
- Continuous cron firing every 15 min as expected

---

## DASHBOARD STATUS

### Live Tabs
- Overview, Intraday, F&O, Swing, Positional, **War Room** (with Top Movers sub-tab)

### War Room Tab Shows
- Top 20 movers today (SAREGAMA, NLCINDIA, CIPLA, ...)
- Green check if we picked, red X if missed
- Why missed reason for each (chasing penalty, sector miss, etc.)
- Scanner accuracy: X/20 caught
- VIX, market mood, our picks today
- 30-day history

### URLs
- Main: https://d2q1cy3ph7jbd0.cloudfront.net
- vishal-live: https://d2q1cy3ph7jbd0.cloudfront.net?profile=vishal-live
- neha-live: https://d2q1cy3ph7jbd0.cloudfront.net?profile=neha-live

---

## INFRASTRUCTURE (unchanged)

| Item | Value |
|------|-------|
| OLD EC2 | 13.206.144.6 (i-0256713c061011a5f) |
| NEW EC2 | 13.202.63.223 (i-0233c705c9104383e) |
| Dashboard | https://d2q1cy3ph7jbd0.cloudfront.net |
| GitHub | https://github.com/vshorrghar/Intraday-Trader.git |
| Bedrock Model | Claude Opus 4.7 (us.anthropic.claude-opus-4-7) |
| AWS Profile | vishal-admin |
| Latest commit | 8fe6d03 |

---

## CAPITAL SCALING REMINDER

We are in **Phase 1**: Rs.10K-15K live capital.

Phase 2 unlocks at: 50 profitable trades on real money.
Current: ~5 real money trades, 4 losing (-Rs.165 cumulative).

**Don't scale capital until win rate proves on the new scanner.**
Wait for at least 20 trades on RS-First v3 before evaluating.

---

## HOW TO RESUME ANY CHAT

Paste RULES.md + STATE.md (this file) + your question.

Any AI that lectures without reading both docs is wasting your time.

End of STATE.md
