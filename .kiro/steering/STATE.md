# STATE.md — Current Project State

**Last Updated**: 2026-05-14, ~15:30 IST (end of trading day)
**Update Protocol**: Replace TODAY section at end of each session.

---

## TODAY (2026-05-14) — FULL DAY SUMMARY

### Real Money Trades
| Profile | Stock | Entry | Result | P&L |
|---------|-------|-------|--------|-----|
| neha-live | SAIL x19 @ Rs.206.42 | 9:31 AM | Closed (SL/force exit) | -Rs.63 approx |
| vishal-live | VEDL x10 @ Rs.334.30 | 10:57 AM manual | Closed | TBD (DB query failed) |
| neha-live noon | BHARTIARTL sized | 12:03 PM | 0 orders placed (Bug HH) | Rs.0 |

### Why vishal-live Missed 9:26 AM Cron
- Bedrock Opus 4.7 timed out — 25 min hang (03:56 to 04:21 UTC)
- Root cause: Peak Bedrock congestion at market open
- Mid-morning same model responded in 4 min 18 sec
- Fix needed: 60s timeout on boto3 client (not done yet)

### Key Discovery Today — Scanner Picks Wrong Stocks
Real market at 11 AM showed:
- NLCINDIA  +17.36% from_open +9.84%  — scanner missed
- GODREJIND +12.90% from_open +11.62% — scanner missed
- CIPLA      +6.52% from_open +3.82%  — scanner missed
- VEDL       +2.66% from_open +0.90%  — THIS is what we picked
Root cause: Volume-dominated scoring. VEDL wins on 38M volume daily.
Fix: RS-first scoring rewrite — PARTIALLY APPLIED (see below)

### Scanner RS-First Scoring — Status Unknown
- Patch attempted but SyntaxError on final line (nested quotes issue)
- Need to verify: is "RS-FIRST SCORING" in scanner.py or not?
- Check command: grep "RS-FIRST" intraday/scanner.py

### What We Built Today
- STRATEGY.md created (.kiro/steering/STRATEGY.md)
- LEARNING.md created (.kiro/steering/LEARNING.md)
- War Room tab added to dashboard (tab works, label may be missing)
- sync_docs.py created (syncs steering docs to dashboard API)
- docs.json synced to S3
- Onboarding website Kiro prompt written (complete, ready to use)
- Multi-EC2 architecture confirmed live

### Onboarding Website — Ready For Kiro
Complete prompt written for 7-page Hindi onboarding site.
Dark futuristic theme. Separate S3 + CloudFront from trading dashboard.
Give prompt to Kiro when ready.

---

## LIVE STATUS (2026-05-14, 15:30 IST)

### Both EC2s Running
| EC2 | IP | Profiles | Status |
|-----|----|----------|--------|
| OLD | 13.206.144.6 | vishal-live, vishal, neha paper, F&O | Running |
| NEW | 13.202.63.223 | neha-live only | Running |

### Today Crons Fired
- 9:26 AM vishal-live: FAILED (Bedrock timeout 25 min)
- 9:28 AM neha-live: SUCCESS (SAIL trade placed)
- 10:57 AM vishal-live: MANUAL RUN (VEDL placed)
- 12:03 PM neha-live: PARTIAL (sized but 0 orders — Bug HH)

---

## ACTIVE BUGS (priority order)

### Critical — Real Money Impact
| ID | Description | File | Status |
|----|-------------|------|--------|
| EE | Bedrock Opus timeout at 9:26 AM market open | llm/bedrock_client.py | FIXED 23a0261 |
| FF | NSE gainers/losers returns 0 every call | fetchers/nse_market_movers.py | FIXED 23a0261 |
| GG | Live P&L stays Rs.0 in monitor all day | intraday/monitor.py | PARTIAL FIX 23a0261 |
| HH | 0 orders placed after sizing (12:03 PM) | intraday/executor.py | OPEN |

### High
| ID | Description | File | Status |
|----|-------------|------|--------|
| SCANNER | RS-first scoring patch status unknown | intraday/scanner.py | VERIFY |
| SHORT-RR | SHORT R:R calculated 0.0 in risk_manager | intraday/risk_manager.py | OPEN |
| L | F&O legs_json missing expiry_date | fno/strategy_engine.py | OPEN |
| T | F&O live P&L never changes | fno/monitor.py | OPEN |

### Medium
| ID | Description | Status |
|----|-------------|--------|
| WAR-ROOM | War Room tab label missing in dashboard | FIXED 23a0261 |
| E | Telegram alerts not wired | OPEN |
| G | Dhan credentials rotation needed | OPEN |
| I | AWS keys rotation needed | OPEN |

---

## REAL TRADES TO DATE

### vishal-live
| Date | Stock | Direction | Net P&L |
|------|-------|-----------|---------|
| May 12 | ONGC | LONG | -Rs.53.80 |
| May 12 | WIPRO | SHORT | -Rs.20.00 |
| May 13 | HINDZINC | LONG | -Rs.28.30 |
| May 14 | VEDL | LONG | TBD |

### neha-live
| Date | Stock | Direction | Net P&L |
|------|-------|-----------|---------|
| May 14 | SAIL | LONG | -Rs.63 approx |

### Cumulative Real Money P&L
vishal-live: approximately -Rs.102 (May 12+13, May 14 TBD)
neha-live: -Rs.63

---

## WHAT KIRO NEEDS TO DO (one at a time)

### Task 1: Verify Scanner Patch
SSH ec2-user@13.206.144.6 key ~/Downloads/wealth-builder-pro.pem
Run: grep "RS-FIRST" ~/dev-sandbox/intraday/scanner.py
If found: scoring is done, report back
If not found: full scoring replacement needed (see STRATEGY.md)

### Task 2: Fix Bug HH (after Task 1 confirmed)
Find why 0 orders placed after sizing at 12:03 PM
grep -E "Placed|max_trades|limit|skip|gate" ~/dev-sandbox/logs/intraday_neha-live_2026-05-14.log | tail -20
Report cause before fixing

### Task 3: Fix Bug FF (after Task 2 done)
Test NSE gainers API response structure
Fix fetch_top_gainers() in fetchers/nse_market_movers.py

### Task 4: Add Bedrock Timeout (after Task 3 done)
Add 60s read_timeout to boto3 client in llm/bedrock_client.py

### Task 5: Fix War Room Label (after Task 4 done)
grep -n "warroom" ~/dev-sandbox/dashboard/index.html
Ensure button text reads: >🧠 War Room
Deploy to S3 after fix

### Commit Only After ALL Tasks Verified
git add intraday/scanner.py intraday/executor.py fetchers/nse_market_movers.py llm/bedrock_client.py dashboard/index.html
git commit -m "RS-first scanner + Bug FF + Bug HH + Bedrock timeout + War Room label"
git push

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

---

## TOMORROW MORNING CHECKLIST (2026-05-15)

1. SSH OLD EC2 — verify scanner RS-first patch applied
2. SSH NEW EC2 — verify time sync (timedatectl)
3. 9:26 AM: tail -f logs/intraday_vishal-live_2026-05-15.log
4. 9:28 AM: tail -f logs/intraday_neha-live_2026-05-15.log (on NEW EC2)
5. Watch: do CIPLA/HINDALCO type stocks appear in candidates now?
6. Watch: does Bedrock respond in time or timeout again?
7. Have Dhan apps open for both vishal + neha
