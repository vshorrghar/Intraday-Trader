# LEARNING.md — Business Journal

**Purpose**: What happened. What we learned. Money made/lost. Decisions taken.
**Update rule**: Append after every trading day. Never delete old entries.
**This is business language — no code details. Code details go in STRATEGY.md.**

---

## WEEK 1 (May 12-16, 2026)

### May 14 — Full Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | VEDL LONG | TBD |
| neha-live | SAIL LONG | -Rs.63 approx |
| neha-live | BHARTIARTL | Rs.0 (never placed — Bug HH) |

Cumulative all real money: approximately -Rs.165

#### What The Market Did Today
- NLCINDIA ran +17% — we missed it
- GODREJIND ran +13% — we missed it
- CIPLA ran +6.5% — we missed it
- We bought VEDL which moved +2.7% and went nowhere
- Metal sector led all day (NIFTY METAL +1.79%)
- VIX stayed elevated 18.7-19.0 — system correctly cautious

#### What We Learned
1. Our scanner is a volume picker not a momentum picker
   VEDL trades 38M shares/day — always wins on volume score
   CIPLA trades 4.7M — loses on volume even though move was 3x better
   Fix: RS-first scoring — change_from_open is the key signal

2. Bedrock Opus is slow at market open
   9:26 AM = 25 min hang = missed best entry window
   10:57 AM = 4 min 18 sec = acceptable
   Market open is when everyone hits Bedrock simultaneously
   Fix needed: 60 second timeout

3. Live P&L is completely blind
   SAIL was losing Rs.63 but monitor showed Rs.0 all day
   Trailing stop loss never activates because it needs P&L
   Only safety was the Dhan SL order placed at entry
   This is the most dangerous open bug

4. Two EC2s working correctly
   neha-live on NEW EC2 placed real trade successfully
   Dhan IP whitelist confirmed — separate IP required per account

#### Decisions Made Today
- Keep Opus 4.7 (quality model) but add timeout
- Rewrite scanner scoring from volume-first to RS-first
- Build continuous 15-min scanning (catch intraday breakouts)
- Build onboarding website for new users (Kiro prompt ready)
- Created STRATEGY.md and LEARNING.md for institutional memory

#### What We Are Competing Against
- Millions of Indian retail traders checking charts every minute
- Our edge: scan 500 stocks simultaneously, zero emotion, perfect rule execution
- Our weakness today: scanning wrong stocks (volume bias)
- After RS-first fix: our edge becomes real

---

### May 14 — Evening Overhaul (7 commits, scanner fully rewritten)

#### What We Built (after market close)
Worked from 4 PM to 10 PM. Shipped 7 commits.
Scanner went from v1 (volume-dominated) to v3 (multi-signal momentum).

#### Money (no trading after market close — building only)
No trades placed. Building day, not trading day.

#### Commits Shipped
1. Bedrock 60s timeout (fixes 25-min hang at market open)
2. NSE gainers API fix (was returning 0, now returns 20)
3. Live P&L fallback (fetches NSE LTP when broker has none)
4. SHORT R:R direction-aware (was always 0.0, now correct)
5. Top 20 capture daily (with why-missed reasons)
6. War Room dashboard tab (live with scanner accuracy)
7. Scanner v2 + v3 (fade detector + sector rotation + time multiplier + trap detector)

#### What We Learned

1. Volume is confirmation, not signal
   VEDL had 38M volume daily — won every day on volume.
   But +2.66% with high volume on flat day is not the trade.
   +15% on lower volume IS the trade.
   Volume confirms a real move; it doesn't predict winners.

2. Penalizing "chasing" was killing real winners
   SAREGAMA at +13% from open got -4 chasing penalty.
   These are exactly the stocks we want — strength stays strong.
   Real chasing trap is pump-and-fade, not high gain.
   New rule: only penalize stocks falling FROM day high, not stocks AT day high.

3. Time of day matters more than expected
   Same setup at 9:30 AM has 5h 45min before force exit.
   Same setup at 12:30 PM has 3h 14min — too tight for 4% target.
   Brokerage eats short trades. Earlier = better expected return.
   Time multiplier: 1.5x first hour, 0.4x late session.

4. Sector rotation is half the trade
   Pharma stock in pharma sector +3% leading the market = strong.
   Same pharma stock when pharma sector is -1% = relative strength.
   Stock-only scoring missed this. Now sector rotation = 0-5 pts.

5. You can't fix what you don't measure
   We had no idea how many real winners we missed daily.
   Built top-20 capture to make this visible.
   30 days from now we'll have 600 data points to analyze.
   Without ground truth, scanner improvements are guesswork.

6. Direction-aware math or you bleed money on shorts
   Old code: risk = entry - stop_loss (LONG-only).
   For SHORT, this is negative, R:R = 0, sizing broke.
   Any formula that treats LONG/SHORT same will silently break.

7. Continuous scanning catches what fixed times miss
   Old: scan at 9:25 / 12:00 / 13:30 — 3 chances per day.
   New: scan every 15 min — catches mid-session breakouts.
   Late-session gates prevent revenge trading.
   Profile max-trades caps overtrading.

#### Decisions Made
- Raise vishal-live capital Rs.10K -> Rs.15K (more room for new scanner)
- Raise max trades 2 -> 3 per day per live profile
- Raise daily loss limit Rs.600 -> Rs.900
- VIX threshold raised 18 -> 20 (less skipping when scanner is better)
- Telegram module ready — set token and activate later

#### What This Means For Tomorrow
If scanner v3 works:
- Should pick SAREGAMA/CIPLA-type stocks (skipped by v1)
- Should skip VEDL-type slow stocks unless they're the best of the day
- Win rate may DROP short term (50-55% vs 60%) — bigger swings
- Average winner should grow 4-6% (vs 1.5% today)
- Net effect: higher P&L per winning day

If scanner v3 fails:
- We have data via top-20 capture to see exactly what it missed
- Why-missed reasons in War Room tab will tell us what to fix next

#### What We Are NOT Doing Tomorrow
- Not adding more scanner changes
- Not enabling Telegram alerts (need to validate scanner first)
- Not increasing capital beyond Rs.15K
- Not panicking if first day has a loss
- Not changing anything mid-session

#### Honest Self-Assessment End Of Day
- 7 commits is a lot in one day. Risk of subtle bugs.
- All imports tested and pass.
- All changes are direction-improvements based on real May 14 data.
- But this is theory until tomorrow's market opens.
- Real money only on vishal-live and neha-live — Rs.25K total exposure.
- Worst case: lose Rs.1,800 (Rs.900 each profile) — survivable.
- Best case: catch one SAREGAMA-type winner = Rs.1,500-2,500 profit.

---

### May 17 evening — Data API + Backtest Foundation (5-hour Sunday session)

#### Money
No new trades placed (Sunday — markets closed).

#### What We Built
1. Discovered + fixed 3 Dhan optionchain spec bugs (client-id header, securityId 26000→13, payload schema)
2. Subscribed Dhan Data API Rs.499/month for vishal account
3. Activated F&O segment on Dhan account
4. Added get_historical_ohlc() method to DhanBrokerClient
5. Built backtest module: data_loader + scanner_replay
6. Verified F&O Monday cron path end-to-end
7. First backtest test run: 5 stocks, 4 days

#### What We Learned

1. Data is paywall, not just code
   We spent weeks debugging "why doesn't F&O paper work?" The answer was simple: Dhan optionchain endpoint requires Rs.499/month Data API subscription. No amount of code fixing changes this.
   Lesson: when an external API returns 401, FIRST check if it's a subscription issue, not a spec issue. Would have saved Bug T saga days of confusion.

2. AI assistants are optimistic about their own work
   Kiro reported "75% hit rate" for backtest v0.1. Actual reading of the code shows the comparison fell back to self-referential ranking when DB top performers table was empty. The number is noise, not signal.
   Lesson: when AI quotes a metric, read the comparison logic. Numbers without methodology are theatre.

3. Foundation > polish
   v0.1 backtest has limitations (no sector data, omitted 52w signals, small universe). But the code path works end-to-end. Next iterations can add signals incrementally.
   Lesson: ship the foundation, document gaps honestly, iterate. Don't wait for perfect v1.0.

4. Data API enables much more than F&O
   ₹499/month was framed as "F&O cost." Actually unlocks:
   - Backtest engine (validate scanner changes before live)
   - Faster intraday LTP (replace flaky NSE)
   - Future: WebSocket real-time monitor
   - Future: bulk quotes for scanner reliability
   Real cost-per-capability is much lower than F&O-only framing suggested.

5. Multi-account API tier complications
   vishal/vishal-live share one Dhan account → Data API covered.
   neha/neha-live separate Dhan account → NOT covered.
   Lesson: account-level subscriptions don't propagate. If we want neha profiles to have real data too, need separate Rs.499/mo OR refactor to use vishal account for data fetching only (allowed since data is read-only).

6. Sunday-night cron verification matters
   F&O Monday verification today caught one issue: fno_mtm_run.py can't be run standalone. Caught now, not at 9:24 AM Monday.
   Lesson: dry-run cron paths Sunday before they fire Monday.

#### Decisions Made
- Subscribed Dhan Data API Rs.499/month (vishal account only)
- Did NOT subscribe for neha account (defer until intraday profitable for both)
- Did NOT enable any real-money F&O code path
- Did NOT modify scanner.py / executor.py / monitor.py / risk_manager.py
- Built backtest as separate module to avoid touching live trading code
- Accepted Kiro's 75% hit rate as theatre; documented limitations honestly

#### What Monday May 18 Will Tell Us
**Critical real-money tests:**
- Bug 5 (max_trades_per_day) holds under continuous scan
- Scanner v3.1 (Bugs 1, 2, 3) on first full live week
- Real money intraday outcome

**F&O paper observation (no real money, free learning):**
- F&O cron at 9:24 AM places strategies with REAL Dhan option prices for first time
- MTM cron updates every 30 min with real LTP
- First time we'll see legitimate strategy P&L numbers, not synthetic

**What we are NOT testing Monday:**
- Backtest accuracy (small universe, broken comparison)
- Telegram alerts (not wired)
- Dhan trade reconciliation (not built)
- Super order migration (not done)

#### Honest Self-Assessment
- 6 commits today, real infrastructure shipped
- Real money exposure unchanged: ~Rs.25K live, capped at Rs.1,800 max daily loss
- Data API subscription: Rs.499/month recurring cost. Justified IF intraday profitable + backtest extended + F&O eventually live.
- Risk Monday: Bug 5 has never been live-tested. Scanner v3.1 has 1 day of live data.
- Backtest engine: foundation only. Don't trust 75% number. Run with bigger universe before quoting any accuracy stats.

#### Next Session (Tuesday or next weekend)
Priority order:
1. Update backtest to full Nifty 50 universe (50 not 5)
2. Populate daily_top_performers from Dhan historical (not relying on capture cron alone)
3. Wire Telegram alerts (real-money safety priority)
4. Build Dhan trade reconciliation script
5. Decide on neha account Data API subscription based on Monday outcome

---

### May 16-17 — Bug T Sub-Bugs Discovered + Fixed

#### Money
No new trades placed (weekend Saturday + Sunday — markets closed).

#### What Happened
After Friday May 15 Bug T fix shipped, Kiro reviewed the code over the weekend
and found three sub-bugs that defeated the original fix:

T-1: MTM cron was a broken one-liner
- We embedded Python inside a shell -c string in the cron entry
- Worked when run manually, broke under cron's env
- Result: MTM cron silently did nothing
- Fix: proper script scripts/fno_mtm_run.py + wrapper sh

T-2: Paper mode never authed Dhan
- run_fno.py only called Dhan auth when --live flag was set
- Paper mode used DryRunBrokerClient
- option_chain_cache needed real Dhan client to fetch chains
- Result: every paper option chain request returned None silently
- Fix: paper mode now auths real Dhan (read-only calls only)

T-3: force_exit passed zero premium
- force_exit_all (called at expiry day 3 PM) logged P&L with current_premium=0
- This is the most important exit path for short premium strategies
- Defeated entire Bug T fix on exits
- Fix: compute current_premium from option chain before recording

Plus side fix Saturday May 16:
- neha-live dashboard password was missing from passwords.json
- index.html mapping for neha-live was broken
- Created proper separate password for neha-live

#### What We Learned
1. A "fix" isn't fixed until end-to-end runs prove it
   We thought Bug T was done Friday night.
   Three holes in the fix would have shown synthetic P&L Monday again.
   Lesson: every fix needs a validation path that exercises the full code path.
   Cron-driven fixes especially — running the script manually != cron context.

2. Cron context bites
   Inline shell -c with Python embedded is fragile.
   Cron env, Python path, working directory all differ from interactive shell.
   Always: write a script file, test it as cron-context (env -i), then schedule.

3. Paper mode drifting from live mode is dangerous
   Paper skipped Dhan auth as "optimization" — broke the data infrastructure.
   When paper and live diverge, paper data becomes worthless.
   Lesson: paper mode should differ from live ONLY at the order placement step.
   Everything else (auth, data fetch, monitoring) must be identical.

4. Audit ALL exit paths, not just one
   T-3 only addresses force_exit_all.
   Other exit paths (target hit, SL hit, manual close) may still have similar bugs.
   Lesson: when fixing P&L on exits, grep for every place P&L is recorded.

5. Weekend code review caught what Friday rush missed
   Friday session was 5+ hours, multiple streams. Tunnel vision.
   Saturday/Sunday calm review found 3 holes.
   Lesson: high-stakes fixes deserve next-day review before Monday opens.

#### Decisions Made
- All 4 commits accepted into main (3 Kiro + 1 doc sync)
- No capital changes
- Pillar docs synced to reflect new reality
- Monday validation now covers Bug T-1, T-2, T-3 in addition to original Bug T

#### What Monday May 18 Will Tell Us
If Bug T sub-bugs really fixed:
- logs/fno_pnl_update.log shows entries every 30 min during market
- fno_trades.current_price column populated with real values
- Force exits log non-zero P&L
- neha-live dashboard accessible from CloudFront

If still broken:
- T-1 fail mode: fno_pnl_update.log empty
- T-2 fail mode: option_chain cache files missing or empty
- T-3 fail mode: expiry-day exit P&L = 0 again
- Each is independently observable, easy to diagnose

#### Honest Self-Assessment
- Friday's fix wasn't actually fixed. Caught it in time.
- Real money exposure unchanged (F&O is paper).
- Pillar docs are now genuinely current (not just claiming to be).
- Bug T saga shows: complex fixes need post-session review.

---

### May 15 — Evening: F&O Bug T + Bug 6 + Bug 5 Discovery (5+ hour session)

#### Money (no new trades after market — building only)
- vishal-live: still showing INFY + HDFCBANK open from earlier (Bug 5 cost ~Rs.220)
- No additional real-money exposure

#### What We Built (after market close)
1. F&O real-price paper trading (Bug T fix)
   - option_chain_cache.py with 5-min TTL
   - pnl_calculator.py with callable data source pattern
   - update_all_open_strategies in monitor.py
   - Exit triggers per strategy type
   - Cron */30 during market hours
2. neha-live S3 sync (Bug 6 fix)
   - DB sync from NEW EC2 to S3 every 15 min
   - Dashboard JSON sync from NEW EC2 to S3 every 15 min
3. 4 new steering docs: BUSINESS_DOC, TECHNICAL_DOC, GLOSSARY, FNO_STRATEGY
4. Cleaned up 84 stale F&O trades (pre-fix synthetic data)

#### Critical Discovery: Bug 5
After Kiro built F&O fixes, EOD review revealed vishal-live placed 7 trades today.
Limit was 3. Lost ~Rs.223 from doubled-down INFY (4x) and HDFCBANK (2x).

Root cause: risk_manager only counted CLOSED trades. OPEN positions were not counted.
Continuous scanning every 15 min saw fresh slate every cycle.

Lesson: When you change architecture (single-scan -> continuous), you MUST audit every counter and gate. We added continuous scanning May 14 but did not re-audit risk_manager. The bug existed for 2 days before being noticed because Mon-Wed only had 1-2 trades anyway.

#### Lessons From This Session
1. Real money exposes architectural assumptions
   - Continuous scanning was always going to expose state-tracking bugs
   - Paper trading would have eventually shown it but slower

2. F&O paper without real prices is worthless data
   - 84 trades from May 14 are unusable
   - We had to throw them away
   - Should have built real-price tracking BEFORE running paper trades
   - Lesson for future modules: validate measurement infrastructure first

3. Dhan optionchain only works during market hours
   - Could not validate Bug T fix tonight
   - Code is right but unverified until Monday
   - Acceptable risk because it is paper money, but stressful

4. Multi-EC2 architecture creates data visibility problems
   - Bug 6 was about seeing neha-live from OLD EC2
   - Solution: S3 as shared state
   - This pattern will scale to more accounts later

5. Steering docs need to grow with complexity
   - Started with 3 (RULES, STATE, HISTORY)
   - Now 9 docs
   - Each AI session can pick relevant ones for context
   - GLOSSARY especially helps avoid term drift

#### Decisions Made
- Approved all 3 Kiro bug fixes (Bugs 1, 2, 3) at session start
- Approved Bug T architecture (real Dhan prices, callable pattern, 5-min cache)
- Approved Bug 6 architecture (NEW EC2 pushes to S3, OLD reads)
- Approved Bug 5 fix (count all non-rejected/cancelled BUYs)
- Did NOT change any capital limits or daily loss caps
- Did NOT push to NEW EC2 yet (Monday morning task)

#### What Monday May 18 Will Tell Us
If everything works:
- Bug 5: vishal-live max 3 trades, even with continuous scan attempts
- Bug T: F&O strategies have real entry prices, MTM updates every 30 min
- Bug 6: neha-live data visible in War Room from OLD EC2

If something fails:
- Bug 5: legitimate trades blocked falsely (would see "Daily limit reached" too early)
- Bug T: Dhan optionchain returns 401 even during market hours (need NSE bhavcopy fallback)
- Bug 6: S3 sync race or stale data displayed

#### Honest Self-Assessment
- 5+ commits over the day, complex architecture changes
- All imports clean, all heredoc patches verified
- Real money exposure today: ~Rs.220 lost to Bug 5 BEFORE we discovered it
- Going-forward exposure: bounded by Rs.900/day per profile (loss limit)
- F&O remains paper-only (zero real money)
- Worst case Monday: Rs.1800 loss across both live profiles (each hits limit)
- Best case: Bug 5 saves us money by enforcing limit, F&O shows real numbers

#### Next Decisions Pending
- Should dashboard neha-live tab be priority next session?
- Should we wire Telegram BEFORE more F&O work (phone alerts on real money)?
- After Monday F&O data: evaluate if Iron Condor strategies actually work
- After 7 days clean data: decide on F&O live deployment timeline

---

### May 15 — Day 1 Of Scanner v3 + Bugfix Session

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | INFY x4 @ 1124.10 | TBD (still open at session end) |
| vishal-live | HDFCBANK x5 @ 779.90 | TBD (still open at session end) |
| vishal-live | SAREGAMA x10 @ 411.90 | NEVER FILLED — 10s timeout |

Cumulative all real money: still ~-Rs.165 (no closed trades today)

#### What The Market Did Today
- TDPOWERSYS ran +8.75% on Rs.397 Cr value — we never even saw it
- SAREGAMA spiked +7.11% — scanner v3 caught it (good!) but order didn't fill
- INFY and HDFCBANK gave normal day trades — both still open at end of session
- NIFTY IT and Media sectors led — scanner v3 sector rotation working

#### What We Learned

1. Scanner universe was silently truncated to 169/500 stocks
   500K volume filter rejects stocks at 9:30 AM that haven't built volume yet.
   By end of day 239 stocks pass. At market open only 169 do.
   We were scoring 1/3 of our intended universe and didn't know.
   Fix: momentum-aware filter. If stock is up 4%+ with 100K+ volume, pass anyway.

2. NSE APIs change silently
   The ?index=losers endpoint stopped working at some point.
   Returned a string error instead of data, so our code accepted "0 losers" as valid.
   Half our scanning (SHORT candidates) was effectively broken for weeks.
   Lesson: log and alert on "fetched 0 of expected ~20" responses.

3. 10-second fill timeout kills high-momentum entries
   SAREGAMA was the perfect scanner v3 catch — confidence 8, R:R 2.2.
   But the stock was moving so fast the limit order at Rs.411.90 sat unfilled.
   We cancelled after 10s. Stock continued to Rs.428+.
   We picked the right stock and got nothing.
   Fix: +0.3% buffer on limit, MARKET fallback for confidence 8+ on fast movers.

4. Building diagnostic tools pays off Day 1
   The top performers cron we built yesterday wasn't due to fire yet.
   But the diagnostic scripts we built (NSE API testing, scanner inspection) 
   let us find all 4 bugs in one session.
   Without those tools we would have been guessing for weeks.

5. Real money exposes bugs that paper trading hides
   Paper trading doesn't care if a limit order fills in 10s — it simulates fills.
   Real money cares. SAREGAMA fill failure was invisible on paper.
   Lesson: real money is the only true validation.

6. SL bounds the risk of every "aggressive" fix
   I (the AI) was initially scared to add MARKET fallback — slippage risk!
   User pushed back: every trade has SL. Worst case is bounded.
   The fix went in. Lesson: trader mindset > coder mindset on bounded-risk decisions.

#### Decisions Made
- Approved all 3 bug fixes for live deployment Monday
- Buffer 0.3% applied to ALL limits (slippage tax accepted)
- MARKET fallback gated by confidence >= 8 only
- Did NOT change capital limits or daily loss caps
- STATE.md updated, May 14 archived to HISTORY.md

#### What Monday May 18 Will Tell Us
If fixes work:
- Scanner shows 250+ stocks (not 169)
- SHORT picks appear again
- Fast movers like SAREGAMA fill on first attempt or via MARKET fallback
- Win rate may not change immediately — small sample
- More candidates = more LLM picks = more shots at winners

If fixes fail:
- Bug 1 may flood scanner with low-quality momentum stocks
- LLM may pick worse setups due to noisier candidate list
- Buffer may cause more R:R rejections (less likely but possible)
- MARKET fallback may fill at terrible prices on volatile stocks

#### Honest Self-Assessment End Of Day
- Found and fixed 3 real bugs from one day of production data
- Each fix is targeted and reversible
- Committed and pushed clean (4 commits today)
- Both EC2s synced
- STATE.md and HISTORY.md properly maintained
- BUT: All 3 fixes are theory until Monday market opens
- Real risk: Rs.25K live capital across 2 profiles
- Worst case Monday: Rs.1,800 loss (Rs.900 each profile)
- Best case Monday: Catch one TDPOWERSYS-type winner = Rs.1,500-3,000 profit

#### Next Decisions Pending
- Should LEARNING.md and STRATEGY.md updates happen automatically per session? (Yes — going forward.)
- Should we add monitoring for "fetched 0 of expected" anomalies?
- After Monday data, evaluate if buffer 0.3% is right number


### May 13

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | HINDZINC LONG | -Rs.28.30 |
| vishal paper | multiple | +Rs.57.69 |
| neha paper | multiple | -Rs.401.53 |

#### What We Learned
- Charges matter more than we thought
  Paper showed +Rs.261 gross but +Rs.57.69 after charges
  neha paper showed -Rs.81 gross but -Rs.401.53 after charges
  Always look at net P&L not gross
- Dashboard was hiding charges (Bug A+D) — fixed today
- NSE tick size (Rs.0.05) caused Dhan order rejections (Bug H) — fixed today

---

### May 12 — First Real Money Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | ONGC LONG | -Rs.53.80 |
| vishal-live | WIPRO SHORT | -Rs.20.00 |

#### What We Learned
- System placed real orders — architecture works
- Lost money on first two trades — expected in learning phase
- Short direction needs more validation (WIPRO SHORT unclear)

---

## PATTERN LIBRARY (grows over time)

### Patterns That Work (building evidence)
- Metal sector leadership + HINDALCO/VEDL continuation = follow sector leader
- Pharma gap up + continuing from open = usually holds through session
- VIX spike day = skip or 1 trade max with tight SL

### Patterns That Fail
- High volume PSU stocks (VEDL/ONGC/SAIL) = slow movers, poor R:R
- Entering stocks already up 10%+ at 11 AM = chasing, always loses
- Trading when VIX > 20 = wide stops, bad fills, choppy exits

### Market Timing Observations
- 9:15-9:30 AM: Most volatile, best moves START here
- 9:30-10:30 AM: Best entry window — momentum confirmed
- 10:30-12:00 PM: Mid-session, some continuation plays
- After 12:00 PM: Late entries risky, most moves 70% done
- 2:30-3:15 PM: End of day volatility, system avoids (force exit 3:15)

### VIX Observations (NSE India)
- VIX < 14: Easy market, trend days, system should be aggressive
- VIX 14-18: Normal, current thresholds appropriate
- VIX 18-20: Elevated, reduce to 1 trade, wider SL — current state
- VIX > 20: Skip day or 1 micro trade only
- VIX > 25: Full skip, capital protection mode

---

## DECISIONS LOG (append only)

### 2026-05-14: RS-first scoring rewrite
Old system: volume dominated — wrong stocks picked
New system: change_from_open is primary signal
Expected result: CIPLA/HINDALCO type stocks score higher than VEDL
Status: Patch in progress

### 2026-05-14: Multi-EC2 architecture confirmed
Each live user needs dedicated EC2
Cost: Rs.1,500/month per user
Non-negotiable: Dhan IP whitelist rule

### 2026-05-14: Upgraded to Claude Opus 4.7
Better analysis quality than Sonnet 4.5
Trade-off: Slower, more expensive
Problem found: Times out at market open
Mitigation needed: 60s boto3 timeout

### 2026-05-13: Dashboard charges visibility fixed
Was hiding gross/net difference
Now shows: gross P&L, charges, net P&L separately
Lesson: Always verify what dashboard actually shows

### 2026-05-12: First real money trade
Decision: Start with Rs.10,000, max Rs.600 loss/day
Rationale: Prove system works before scaling
Current status: Small losses, fixing underlying issues

---

## MONTHLY TARGETS

### May 2026
Target: Fix core bugs, establish baseline
- Fix scanner (RS-first) ← in progress
- Fix live P&L visibility (Bug GG)
- Fix 0 orders bug (Bug HH)
- 20+ paper trades per profile
- Establish win rate baseline
Success metric: Win rate > 50% on paper by end of month

### June 2026
Target: Prove the system
- RS-first scoring proven (2 weeks data)
- Continuous 15-min scanning live
- Telegram alerts working
- Win rate > 55% on paper
Capital: Consider Rs.25K if May shows > 55% win rate

### July-August 2026
Target: Scale carefully
- 50 profitable real trades milestone
- Scale to Rs.50K after milestone
- Swing module live on paper
Success metric: 3 months data, consistent positive months

---

## NORTH STAR

Goal: Rs.20,000-30,000 per day combined
Reality: Needs Rs.15-30L deployed + 12-18 months validation
Today: Rs.20,000 deployed (Rs.10K each vishal + neha live)
Path: Fix picks quality -> prove win rate -> scale capital -> reach goal

Today we lost Rs.165 real money.
But we identified WHY the scanner picks wrong stocks.
And we know exactly how to fix it.
That knowledge is worth more than Rs.165.
