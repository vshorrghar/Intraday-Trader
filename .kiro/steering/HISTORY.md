# HISTORY.md — Archived state entries (older than 7 days)

Append-only archive. STATE.md entries older than 7 days move here.

(empty for now)

---

## ARCHIVED FROM 2026-05-14 — MASSIVE UPGRADE SESSION

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

## ARCHIVED FROM 2026-05-15 — TRIPLE-STREAM SESSION

### Session Outcome
8 commits across 3 work streams:
- Stream 1: Scanner v3 bugfixes (Bugs 1, 2, 3)
- Stream 2: F&O Bug T fix — real Dhan price MTM
- Stream 3: Bug 6 — neha-live S3 sync
- Stream 4: 4 new steering docs

### Commits
- 6b8de75 — feat: Bug T fix
- 5d79c29 — docs: add FNO_STRATEGY.md
- 3f3fdbe — docs: add BUSINESS_DOC + TECHNICAL_DOC + GLOSSARY
- 7777382 — feat: live_status + eod_summary + Bug 5 status fix + Bug 6
- abb236e — fix: Bug 6 sync neha-live.db OLD<->NEW via S3
- a0ec15e — fix: Bug 3 buffered limit + MARKET fallback
- 68e910c — fix: Bug 2 NSE losers SecLwr20
- a9df59b — fix: Bug 1 momentum-aware filter

### Critical Discovery EOD
Bug 5: max_trades_per_day not enforced during continuous scanning.
vishal-live placed 7 trades vs limit 3. Lost ~Rs.223.
Fixed in code, needs Monday validation.

### F&O Status Change
Before: 84 paper trades with synthetic P&L (unusable).
After: Real Dhan price infrastructure built, 84 stale trades cleaned, ready for Monday validation.

### Real Money Outcome
Cumulative: ~-Rs.165 closed + Bug 5 cost ~Rs.220 today.
Open EOD: INFY, HDFCBANK on vishal-live.

### Steering Docs
Grew from 3 (RULES, STATE, HISTORY) to 9 docs total.
