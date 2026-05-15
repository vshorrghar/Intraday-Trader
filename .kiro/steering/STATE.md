# STATE.md — Current Project State

**Last Updated**: 2026-05-14, ~22:00 IST (end of session, 7 commits today)
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-15) — POST-V3 LAUNCH BUGFIX SESSION

### Session Outcome
3 commits today. Diagnosed and fixed 4 bugs found from Day 1 of scanner v3 in production.
Bugs were: scanner universe truncated, NSE losers API dead, fast movers don't fill, top performers cron missing.
1 was not actually a bug (cron just hadn't fired yet).

### Commits Today (newest first)
a0ec15e — fix: buffered limit (+0.3% tick-aligned) + MARKET fallback for conf>=8 fast movers (Bug 3)
68e910c — fix: NSE losers endpoint dead — use SecLwr20 from gainers response (Bug 2)
a9df59b — fix: momentum-aware volume filter — pass big movers (>=4%) with 100K+ volume (Bug 1)

### Real Money Trades This Week
| Date | Profile | Stock | Direction | Net P&L |
|------|---------|-------|-----------|---------|
| May 12 | vishal-live | ONGC | LONG | -Rs.53.80 |
| May 12 | vishal-live | WIPRO | SHORT | -Rs.20.00 |
| May 13 | vishal-live | HINDZINC | LONG | -Rs.28.30 |
| May 14 | vishal-live | VEDL x10 @ 334.30 | LONG | TBD |
| May 14 | neha-live | SAIL x19 @ 206.42 | LONG | -Rs.63 approx |
| May 15 | vishal-live | INFY x4 @ 1124.10 | LONG | TBD (still open at session end) |
| May 15 | vishal-live | HDFCBANK x5 @ 779.90 | LONG | TBD (still open at session end) |
| May 15 | vishal-live | SAREGAMA x10 @ 411.90 | LONG | NEVER FILLED — 10s timeout |

**Cumulative real money P&L**: ~-Rs.165 over closed trades + several pending

### Bugs Found and Fixed Today

**Bug 1 (CRITICAL): Scanner only saw 169 stocks instead of 500**
- Root cause: 500K volume filter rejected stocks at 9:30 AM that hadn't built volume yet
- Diagnostic: NSE returned 501 stocks. 209 failed volume filter at scan time.
- Fix: Added momentum bypass — if change_pct >= 4% AND volume >= 100K, pass anyway
- Result: TDPOWERSYS-type early breakouts will now reach scanner

**Bug 2 (HIGH): NSE losers API dead**
- Root cause: ?index=losers endpoint returns "Missing index or key." error
- Diagnostic: Tested 4 alternative endpoints, all dead. Found losers under SecLwr20 in gainers response.
- Fix: fetch_top_losers() now calls gainers endpoint and extracts SecLwr20 (20 items confirmed)
- Result: SHORT candidates restored

**Bug 3 (HIGH): Limit orders don't fill on fast movers**
- Root cause: SAREGAMA +7% surging, limit at LTP didn't fill in 10s, cancelled
- Fix:
  * +0.3% buffer on entry limit (LONG: 1.003x, SHORT: 0.997x)
  * NSE tick alignment to ₹0.05 (round * 20 / 20)
  * MARKET fallback after 10s timeout if confidence_score >= 8
- Result: Fast movers like SAREGAMA should fill or fall back to MARKET on high-confidence picks

**Bug 4 (NOT A BUG): Top performers cron missing**
- Reason: Cron was added today, scheduled for 3:35 PM IST. Hadn't fired yet at diagnostic time.
- Status: Resolved without code change

**Bug 5 (CRITICAL — DISCOVERED EOD): max_trades_per_day not enforced during the day**
- Root cause: _restore_daily_state in risk_manager.py only counted trades with CLOSED statuses (STOPPED_OUT, TARGET_HIT, FORCE_EXITED, CLOSED, PARTIAL_BOOKED). OPEN positions weren't counted.
- Effect: During continuous scanning (every 15 min), every scan saw "0 trades placed today" because trades were still OPEN. Counter never advanced. Daily limit bypassed.
- Real cost today: vishal-live placed 7 trades (limit was 3). Doubled down on INFY 4 times, HDFCBANK 2 times. Lost Rs.223.
- Diagnostic: Simulated new logic on today's DB — would have blocked all trades after 11:00 AM, saving approx Rs.220 of today's loss.
- Fix: Inverted logic. Now counts ALL BUY trades except those with status REJECTED/CANCELLED/FAILED/ABANDONED/PENDING. OPEN positions count toward limit.
- File: intraday/risk_manager.py
- Same bug also exists in neha-live but neha got lucky picks (SAREGAMA winners) so didn't notice
- Validation needed Monday: confirm trade counter increments correctly across continuous scans

### Validation Plan for Tomorrow Morning (May 16)

Pre-market (before 9:15 AM IST):
1. SSH OLD EC2: timedatectl (verify time sync)
2. SSH NEW EC2: timedatectl (verify time sync)
3. Both EC2s git log: should show a0ec15e or later as latest

Market open (9:30 AM IST = 4:00 UTC):
1. Watch live: tail -f logs/intraday_vishal-live_2026-05-16.log
2. Look for "Nifty500 scan: 250+ total" (was 169)
3. Look for losers fetched count > 0
4. If fast mover picked, look for "buffered" or "MARKET retry" in logs

EOD (3:35 PM IST):
1. Top performers cron should fire automatically
2. Check: cat logs/top_performers.log
3. Check War Room dashboard for scanner accuracy %

### Bug 3 Real Money Risk Assessment
- Buffer +0.3% adds slippage tax on every trade
  * On HDFCBANK at ₹779.90: ₹2.34/share = ₹11.70 per 5-share trade
- MARKET fallback could fill at +1-2% above LTP on fast movers
  * Worst case bounded by SL: max ~₹150-200 loss per failed fast mover
- Mitigations: Only conf>=8 gets MARKET fallback. SL exists on every trade.
- Net assessment: Acceptable. Missing winners is a certain cost; bad fills are bounded by SL.

### Open Questions for Tomorrow
1. Will Bug 1 fix actually catch TDPOWERSYS-type stocks at 10:30 AM with 200-400K volume?
2. Will Bug 3 buffered limit fill on fast movers at 0.3% above LTP?
3. Will MARKET fallback ever trigger? On which type of stock?
4. Will scanner accuracy on War Room improve after these fixes?

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
