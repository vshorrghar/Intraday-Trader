# LEARNING.md — Business Journal

**Purpose**: What happened. What we learned. Money made/lost. 
**Update rule**: Append after every trading day. Never delete old entries.
**Audience**: Business decisions, not technical details. 
             (Technical details go in STRATEGY.md)

---

## WEEK 1 SUMMARY (May 12-16, 2026)

### Money (Real)
| Date | Profile | Stock | Result | Net P&L |
|------|---------|-------|--------|---------|
| May 12 | vishal-live | ONGC LONG | Loss | -₹53.80 |
| May 12 | vishal-live | WIPRO SHORT | Loss | -₹20.00 |
| May 13 | vishal-live | HINDZINC LONG | Loss | -₹28.30 |
| May 14 | vishal-live | VEDL LONG | Pending | TBD |
| May 14 | neha-live | SAIL LONG | Loss | -₹63 (approx) |

**Cumulative real money P&L: approximately -₹165**

### Key Learnings This Week

**Learning 1: Scanner picks wrong stocks**
System picked VEDL (+2.66%) when CIPLA (+6.52%), 
GODREJIND (+12.9%), NLCINDIA (+17.36%) were all available.
Root cause: Volume-dominated scoring. VEDL trades 38M volume daily.
Fix: RS-first scoring rewrite (in progress May 14).

**Learning 2: Bedrock Opus times out at market open**
9:26 AM cron → 25 min hang → missed best entry window.
Mid-morning same model responds in 4 min 18 sec.
Root cause: Peak Bedrock congestion at market open.
Fix needed: Timeout + fallback to Sonnet.

**Learning 3: Live P&L completely blind**
Monitor shows ₹0.00 P&L all day even on real positions.
Trailing SL never triggers because it needs P&L to work.
Root cause: _compute_current_premium not fetching live prices.
Fix needed: Wire NSE live price fetch into monitor.

**Learning 4: Two EC2s needed — Dhan IP rule**
Dhan refuses to whitelist same IP for two accounts.
Solution: Clone EC2 via AMI for neha-live.
Now each live account has dedicated EC2 + dedicated IP.

**Learning 5: NSE gainers API broken**
fetch_top_gainers() returns 0 every call.
Scanner runs blind — only Nifty500 API data available.
Impact: LLM gets incomplete market context.

### What The Market Taught Us This Week
- Metal sector strong May 14 (NIFTY METAL +1.79%)
- Pharma strong May 14 (CIPLA +6.52%)
- VIX hovering 18-19 — elevated, system correctly cautious
- PSU stocks (VEDL/ONGC/SAIL) have high volume but low momentum
- Best moves happening in mid-cap quality stocks

---

## PATTERN LIBRARY (grows over time)

### Patterns That Work (observed, not yet statistically proven)
- Metal sector leadership → HINDALCO tends to follow sector
- Pharma gap up + continuation → usually holds through session
- VIX spike + next day recovery → good long opportunities

### Patterns That Look Good But Fail
- High volume PSU stocks (VEDL/ONGC) → slow movers, bad R:R
- Gap up stocks at 11 AM → usually too late to enter
- Trading on red market days → system should skip more aggressively

### Market Condition Notes
- VIX > 20: Skip day or 1 trade max, tighter SL
- VIX 18-20: 1 trade max, 2% SL (currently implemented)
- VIX < 16: Normal trading, 2 trades allowed
- Market open 9:15-9:30: Most volatile, best moves start here
- 9:30-10:30: Best entry window — momentum confirmed
- After 11:30: Late entries risky, move usually done

---

## DECISIONS LOG

### 2026-05-14: Upgraded to Claude Opus 4.7
Previous: Claude Sonnet 4.5
Reason: Better stock analysis quality
Trade-off: Slower response, higher cost
Result: Timeout at 9:26 AM (Bug EE) — needs timeout fix

### 2026-05-14: Multi-EC2 architecture
Reason: Dhan IP whitelist rule — one IP per account
Cost: Extra ~₹1,500/month per live user
Alternative considered: VPN/proxy (rejected — Dhan would ban)

### 2026-05-13: Lowered min_confidence to 7 (was 8)
Reason: Too few trades being placed on paper
Result: More trades, more data, faster learning

### 2026-05-12: First real money trade
Capital: ₹10,000 vishal-live
Result: Small losses — system working, picks need improvement
Decision: Keep running, fix scanner before scaling capital

---

## MONTHLY TARGETS

### May 2026
- Target: Fix core bugs (scanner, P&L, timeout)
- Target: 20+ paper trades per profile
- Target: Establish baseline win rate
- Capital: Stay at ₹10K live until 60% win rate proven
- Success metric: Win rate > 50% on paper by end of month

### June 2026
- Target: RS-first scoring proven on paper (2 weeks data)
- Target: Continuous scanning live
- Target: Telegram alerts wired
- Capital: Consider ₹25K if May win rate > 55%
- Success metric: Consistent ₹200+/day on paper

### July-August 2026
- Target: Swing module live on paper
- Target: 50 profitable real trades milestone
- Capital: Scale to ₹50K after milestone hit
- Success metric: 3 months data, win rate documented

---

## NORTH STAR METRIC

**Goal**: ₹20,000-30,000 per day combined (all profiles)
**Reality check**: Needs ₹15-30L deployed + 12-18 months validation
**Where we are**: ₹20,000 deployed (₹10K each vishal+neha live)
**Path**: Fix picks quality → prove win rate → scale capital → reach goal

Every fix we make today = one step closer to that number.
