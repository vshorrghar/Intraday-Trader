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
