SONNET_LOGICS.md — Trading System Design Document
================================================================
SONNET_LOGICS.md
Version: 0.1 (created 2026-05-23)
Status: DESIGN ONLY — no code yet
Purpose: Single source of truth for new strategy design
================================================================

================================================================
SECTION 1 — ROOT CAUSE ANALYSIS (what went wrong)
================================================================

PROBLEM 1: LLM in the wrong seat
The previous system used Claude (LLM) to make trade decisions.
LLMs are text predictors, not market predictors.
LLMs self-report confidence — higher confidence = worse outcomes (proven by data).
Strategy type labels (VWAP, ORB, MOMENTUM) were LLM descriptions, not computed conditions.
No real VWAP line was ever calculated.
No opening range was ever tracked.
The "strategy" was: ask AI what to trade, AI makes up a reason.

PROBLEM 2: Price ceiling too restrictive
vishal-live: price_range_max = 2000
This made Hero MotoCorp (₹5,220), Apollo Hospitals (₹8,967),
Bharti Airtel (₹2,041) completely invisible.
Scanner allowed ₹5,000 but selector.py killed them at ₹2,000.
Two layers with different limits — no one noticed the conflict.

PROBLEM 3: Wrong volume metric
System used absolute volume (is this in NSE most-active list?)
Should use relative volume (is today's volume unusual FOR THIS STOCK?)
Saregama on a normal day: 600K shares → filtered out
Saregama on a big day: 3M shares (5x normal) → should be top candidate
Absolute volume made Vedanta look active (it always trades high volume)
while missing Saregama breaking out on genuine unusual activity.

PROBLEM 4: Live and paper not running the same system
vishal-paper: price_range_max 3000-5000, ₹50K per trade, 6 trades/day
vishal-live: price_range_max 2000, ₹4,500 per trade, 3 trades/day
These were not two sizes of the same strategy.
They were structurally different systems.
Comparing their win rates was meaningless.

PROBLEM 5: No backtest before deployment
Real money deployed before any historical validation.
Correct order: idea → backtest → paper → live (small) → scale
Actual order: idea → live → discover it doesn't work → investigate

PROBLEM 6: Confidence score was noise not signal
LLM self-reported confidence 1-10.
Data showed: confidence 6 = 71% WR (best), confidence 8 = 46% WR (worst).
Higher LLM confidence = more certain about a wrong answer.
min_confidence_score: 7 filter was actively removing the best trades.

PROBLEM 7: SHORT strategies were catastrophic
SHORT_MOMENTUM: 10-20% WR across all profiles.
The market has been in a broad uptrend.
Going short in an uptrending market = fighting the dominant force.
No regime detection — system shorted stocks on days when market was up.

================================================================
SECTION 2 — WHAT SUCCESSFUL ALGO TRADERS DO
================================================================

KEY PRINCIPLE (from research):
"The world's most legendary traders do not rely on secret indicators.
They master ONE specific structural anomaly and execute it with
flawless risk management."

WHAT WORKS AT RETAIL SCALE:
- Mean reversion (Toby Crabel style — ORB, NR7)
- Trend following with strict rules (Turtle Trading)
- Catalyst + market alignment (institutional approach)
- One strategy, deeply understood, ruthlessly executed

WHAT DOES NOT WORK AT RETAIL SCALE:
- LLM making real-time trade decisions (latency, no edge)
- Intraday trend following (charges eat the edge)
- Complex multi-strategy systems (dilutes focus)
- HIGH confidence = better trades (disproven by our own data)
- Copying US strategies without adapting for Indian charges

WHAT SUCCESSFUL RETAIL TRADERS USE:
- Deterministic mathematical rules
- Backtest on 2-5 years before deploying
- Paper trade 1-3 months before real money
- Start small, scale only after proven
- One strategy type, not eight

THE LLM'S CORRECT ROLE:
- Help write and review strategy code (in IDE)
- Analyze past trades to find patterns
- Debug logic errors
- NOT: make real-time trade decisions
- NOT: self-report confidence scores as signals

================================================================
SECTION 3 — UNIVERSE DESIGN
================================================================

TIER 1 — PRIMARY TRADING UNIVERSE (~250 stocks)
  Full automated strategy rules apply
  Includes:
    - All NSE F&O eligible stocks (~200)
    - Top 50 non-F&O by daily volume (to reach 250)
  Covers:
    - Nifty 50 (elephants — trade only on catalyst days)
    - Nifty Next 50 (sweet spot — your proven winners)
    - Best Midcap F&O names (HFCL, BHEL, Suzlon territory)
  Price range: ₹50 to ₹10,000 (no artificial ceiling)
  Must be: Listed > 1 year, no recent manipulation history

TIER 2 — WATCHLIST (stocks 251-500)
  Alerts only — NO automated trades ever
  Manual review required before any action
  Includes Nifty Smallcap 250 quality names
  Minimum criteria: price > ₹30, volume > 1M/day, listed > 1 year
  Purpose: Discovery pipeline for Tier 1 promotion

OUT OF SCOPE (never trade):
  - Stocks below ₹20
  - Daily volume < 1M shares consistently
  - Listed < 6 months
  - Known circuit hitters
  - Penny stocks / Z-category / suspended

TIER MOVEMENT RULES:
  Tier 2 → Tier 1 promotion:
    F&O approval granted by NSE, OR
    30-day avg volume exceeds 10M shares, OR
    Manual review and approval
  Tier 1 → Tier 2 demotion:
    3 consecutive losses on this specific stock, OR
    F&O eligibility withdrawn, OR
    Volume drops below 3M for 20 consecutive days

PROVEN SWEET SPOT (from your own trade data):
  Nifty Next 50 stocks:
    HFCL, BHEL, Suzlon, Adani Power, Bharti Airtel
  These showed: high relative volume, clean price moves,
  genuine catalysts, 2-5% intraday moves
  NOT the slow Nifty 50 giants on normal days

================================================================
SECTION 4 — DAILY SELECTION LOGIC (from 250 to 5-10 candidates)
================================================================

THREE DIMENSIONS (all must score positively):

DIMENSION 1 — PRICE MOVEMENT (is it actually moving?)
  Minimum: stock moved > 1.5% from previous close by 9:30 AM
  OR gapped > 1% at open
  OR broke above yesterday's high within first 30 minutes
  Eliminates: flat stocks, slow movers, elephants on normal days

DIMENSION 2 — RELATIVE VOLUME (is there real interest?)
  NOT absolute volume — each stock compared to its own average
  Formula: today_volume > (20_day_avg_volume × 2.0)
  By 9:45 AM: volume already > 50% of yesterday's full day
  Eliminates: normal background trading (catches Saregama on big days)
  Eliminates: Vedanta on normal days (always high absolute but low relative)

DIMENSION 3 — QUALITY OF MOVE (is it clean and sustained?)
  3+ consecutive candles in same direction
  Each candle closing in upper 70% of its range (for longs)
  No single-candle spike that immediately reversed
  Spread normal, not suddenly wide
  Eliminates: manipulated spikes, random noise, thin volume games

SCORING SYSTEM (0-10):
  Price score (0-4):
    +1 if gap > 1%
    +1 if gap > 2%
    +1 if already moved > 1.5% by 9:30 AM
    +1 if breaking above yesterday's high
  Volume score (0-3):
    +1 if relative volume > 1.5x
    +1 if relative volume > 2.5x
    +1 if relative volume > 4x
  Momentum quality score (0-3):
    +1 if 3 consecutive candles same direction
    +1 if candles closing in upper 30% of range
    +1 if sector also moving in same direction

  MINIMUM TO TRADE: Score ≥ 6
  IDEAL CANDIDATES: Score ≥ 8
  VEDANTA normal day: scores 2-3 (correctly filtered out)
  HFCL on its best day: scores 9-10 (correctly included)

================================================================
SECTION 5 — MARKET CONTEXT LAYER (the macro filter)
================================================================

INSIGHT FROM TODAY'S DATA (2026-05-23):
  Dr Reddy's +9.7%, Bharti Airtel +9.1%, ICICI +8.4%
  Apollo +7.2%, JSW Steel +7%, Reliance +6.9%
  These moved because: individual catalyst + market cooperating
  TCS -10.9%, SBI -4.6% moved against the trend

TWO TYPES OF BIG MOVES:
  TYPE 1 — Market-driven (whole market moves):
    High-beta stocks amplify Nifty's move
    Predictability: Medium
    Trade: Trend following on strong market days

  TYPE 2 — Stock-specific catalyst (earnings/news):
    Gap up/down at open regardless of market
    Predictability: HIGH after the gap forms
    Trade: Opening range breakout or gap continuation

CORE EDGE HYPOTHESIS:
  "Trade stocks that have a specific catalyst (results, news)
  on days when the broader market is also moving in their direction"
  When BOTH exist → highest probability moves
  When only one exists → lower probability, reduce size

MARKET DIRECTION FILTER:
  Check Nifty direction by 9:30 AM:
  Nifty up > 0.5% → BULLISH day → long trades only
  Nifty down > 0.5% → BEARISH day → short trades only
  Nifty flat ±0.5% → CHOPPY day → reduce to 1 trade max
  Nifty up > 1.5% → STRONG BULL → full allocation, aggressive
  Nifty down > 1.5% → STRONG BEAR → defensive, 1 trade max

CATALYST DETECTION:
  A stock qualifies as having a catalyst if:
  - Gapped > 2% at open (results/news announced after hours)
  - Results announced in last 24 hours
  - 52-week high/low broken
  - Sector is leading/lagging today by > 2x market move

  ONLY TRADE when catalyst + market direction align:
  LONG: stock catalyst UP + Nifty UP
  SHORT: stock catalyst DOWN + Nifty DOWN
  SKIP: catalyst and market pointing different directions

================================================================
SECTION 6 — ENTRY SIGNAL DESIGN (the actual trigger)
================================================================

PRIMARY ENTRY: OPENING RANGE BREAKOUT (ORB)
  Opening range = high/low of first 15 candles (9:15-9:30 IST)
  Entry trigger: price breaks above OR high (for longs)
  Volume confirmation: breakout candle volume > 1.5x average
  VWAP confirmation: price must be ABOVE VWAP at breakout moment
  Market confirmation: Nifty must be UP on the day

  Entry rule (long):
    opening_range_high = max(candles[9:15 to 9:30].high)
    opening_range_low = min(candles[9:15 to 9:30].low)
    IF price > opening_range_high
    AND volume > 1.5x avg
    AND price > VWAP
    AND Nifty up on the day
    THEN enter long

SUPPORTING INDICATORS (filters, not triggers):
  EMA(20) on 15-min chart:
    Use as trend confirmation only
    Long only if price > EMA(20)
    NOT as entry trigger itself

  RSI(14):
    Avoid entries when RSI > 70 (overbought)
    Avoid entries when RSI < 30 (oversold — wrong direction)
    NOT as entry trigger itself

  VWAP:
    Calculated from market open every day
    Formula: cumulative(price × volume) / cumulative(volume)
    Use as confirmation: long entries above VWAP only
    NOT as entry trigger itself

WHY ORB + VWAP + MARKET ALIGNMENT:
  ORB: gives the mathematical entry point
  VWAP: confirms institutional trend direction
  Market alignment: removes trades against the dominant force
  All three together eliminates most false signals

================================================================
SECTION 7 — EXIT AND RISK RULES
================================================================

POSITION SIZING:
  Risk per trade: 1% of available capital
  Stop loss: opening range LOW (for long trades)
  Position size = (capital × 0.01) / (entry - stop_loss)
  Example: ₹50,000 capital, entry ₹1,310, SL ₹1,270
    Risk = ₹500 (1% of ₹50K)
    SL distance = ₹40
    Qty = 500/40 = 12 shares
    Position = ₹15,720

EXIT RULES:
  Primary target: entry + 2x (entry - stop_loss) [2:1 R:R minimum]
  Trailing stop: activate at +1.5%, trail by 0.5%
  Hard stop: opening range LOW (never moved)
  Time stop: exit ALL positions by 14:30 IST regardless
  Re-entry: NOT allowed on same stock same day

DAILY LIMITS:
  Maximum trades per day: 3 (keep current limit)
  Daily loss limit: 2% of capital (adjust from current ₹500 — too tight)
  Stop trading if daily loss limit hit
  No revenge trades after stop-out

WHAT WE NEVER DO:
  Never move stop loss further away once set
  Never hold past 14:30 IST
  Never take a trade without both signals (ORB + market direction)
  Never trade a stock on its circuit limit day
  Never go short on a strong bull day

================================================================
SECTION 8 — WHAT REPLACES THE LLM
================================================================

OLD FLOW:
  Scanner → 20 candidates → LLM picks → trade

NEW FLOW:
  Nifty 500 → Tier 1 filter → Relative volume filter →
  3-dimension score → Market direction check →
  Catalyst check → ORB signal computation →
  Risk manager → Execute

EVERY STEP IS:
  Deterministic (same input = same output always)
  Backtestable (can replay any historical day)
  Explainable (you can describe exactly why each trade was taken)
  Free (no API cost per decision)
  Fast (<10ms vs 1-3 seconds for LLM)

THE LLM'S NEW ROLE (Claude stays in the project):
  Post-trade analysis: "why did this trade lose?"
  Code review: "check this backtest function for bugs"
  Pattern discovery: "look at last 30 losers, what do they share?"
  Strategy improvement: "suggest modifications to the ORB rule"
  NOT: real-time trade decisions
  NOT: confidence scoring
  NOT: strategy type labeling

================================================================
SECTION 9 — WHAT WE KEEP FROM CURRENT SYSTEM
================================================================

KEEP (working well):
  ✅ Risk manager (position sizing, daily limits, loss stops)
  ✅ Order executor (Dhan integration, order placement)
  ✅ Trade monitoring (SL management, exit logic)
  ✅ Database architecture (SQLite per profile)
  ✅ Audit and observability layer (genuinely excellent)
  ✅ Multi-profile architecture (vishal/neha/live/paper)
  ✅ Cron scheduling infrastructure
  ✅ Dashboard reporting

REPLACE (broken):
  ❌ LLM trade picker (selector.py select_trades_llm function)
  ❌ Confidence score as signal
  ❌ Strategy type labels from LLM
  ❌ Price ceiling of ₹2,000 on live
  ❌ Absolute volume filter
  ❌ SHORT strategies (until bear market regime detected)

ADD (missing):
  ➕ Real VWAP calculation from price data
  ➕ Opening range computation (first 15 candles)
  ➕ Relative volume calculation (vs stock's own 20-day avg)
  ➕ Market direction filter (Nifty up/down check)
  ➕ Catalyst detection (gap% + volume surge)
  ➕ Scoring system (0-10 per candidate)
  ➕ Backtest infrastructure
  ➕ EMA(20) computation on 15-min chart
  ➕ RSI(14) as overbought/oversold filter

================================================================
SECTION 10 — STOCKS PROVEN TO WORK / AVOID
================================================================

YOUR PROVEN WINNERS (from actual trade data):
  HFCL — telecom infra, news-driven, moves 3-8% on catalyst days
  BHEL — PSU, government orders, strong relative moves
  Suzlon — renewable energy, retail favorite, high beta
  Adani Power — high beta, moves with Adani group sentiment
  Bharti Airtel — telecom, moves on tariff/results news
  Tech Mahindra — IT, moves on sector days

YOUR PROVEN LOSERS (explicitly watch/reduce):
  HDFC Bank — 5 trades, 0 wins, -₹2,445 total
              Always shows up, never performs
              Consider dynamic blacklist after 3 losses
  TCS — slow mover on normal days, today -10.9% on bad results
        Only tradeable on extreme earnings days
  Wipro — consistent loser in your data
  Infosys — 4 trades, mostly losses

STOCKS YOU OBSERVED BUT MISSED:
  Hero MotoCorp — was blocked by ₹2,000 ceiling (₹5,220 price)
                  Made +5.11% today — would have been a winner
  Apollo Hospitals — blocked by ceiling (₹8,967 price)
                     Made +7.23% today
  Dr Reddy's — ₹1,434, within range but LLM never picked it
               Made +9.70% today — catalyst: strong results
  Saregama — filtered by absolute volume
              Quality price action when it moves

================================================================
SECTION 11 — OPEN DESIGN QUESTIONS (to resolve)
================================================================

Q1: SHORT STRATEGY DESIGN
  When do we go short?
  Proposal: Only on STRONG BEAR days (Nifty down > 1.5%)
  AND only on stocks with specific negative catalyst
  For now: focus on LONG only, add SHORT later

Q2: TIMEFRAME
  Currently: intraday only (exit by 14:30)
  Question: Should we allow overnight holds on very strong setups?
  Proposal: Start intraday only, add swing capability later

Q3: SECTOR ROTATION LOGIC
  Today showed sector-led moves (pharma up, IT down)
  Should we add sector momentum as a filter?
  Proposal: Yes — add as bonus score point, not hard filter

Q4: EARNINGS CALENDAR INTEGRATION
  Dr Reddy's +9.7% was results-driven
  Should we check NSE earnings calendar nightly?
  Proposal: Yes — flag stocks with results in last 24 hours
  as automatic catalyst candidates next morning

Q5: BACKTESTING INFRASTRUCTURE
  Need historical 15-min OHLCV data
  Source options: Dhan API, yfinance, NSE bhavcopy
  Need to decide before building backtest engine

Q6: WHEN TO RE-ENABLE LLM
  After real rules are proven in backtest + paper
  LLM could then act as a FILTER on top of rules
  "Rule says trade, LLM confirms or rejects"
  Only re-add after 100+ clean trades with real rules

================================================================
SECTION 12 — SUCCESS CRITERIA
================================================================

WHEN DO WE KNOW THE NEW STRATEGY WORKS?

Backtest criteria (before deploying live):
  - Tested on minimum 6 months of data
  - Minimum 100 trade signals
  - Win rate > 45%
  - Profit factor > 1.3
  - Max drawdown < 15% of capital
  - Charge ratio < 30% of gross profit

Paper trade criteria (before scaling capital):
  - 30+ trades in paper with real rules
  - Win rate > 45% matches backtest within 10%
  - No systematic bugs in entry/exit
  - Live execution matches paper signals

Live deployment gate (before increasing capital):
  - 50 clean live trades
  - Win rate > 45%
  - Daily loss limit never breached
  - All P0 bugs fixed

Capital scaling gate:
  - 100 clean live trades
  - Consistent win rate > 50%
  - Profit factor > 1.2
  - Only then: ₹15K → ₹50K → ₹1L
================================================================
END OF SONNET_LOGICS.md v0.1
================================================================
🤝 What This Document Is
This is your design contract. Every question we answered tonight lives here. When we build code, we build exactly this — nothing more, nothing less.

Sections completed tonight:

✅ Root cause analysis (why the old system failed)
✅ Universe design (Tier 1/Tier 2)
✅ Daily selection logic (3-dimension filter + scoring)
✅ Market context layer (catalyst + direction alignment)
✅ Entry signal design (ORB + VWAP + EMA)
✅ Risk rules
✅ What replaces the LLM
✅ What to keep vs replace vs add
Sections still open:

Short strategy (Q1)
Earnings calendar integration (Q4)
Backtest data source (Q5)

================================================================
SECTION 13 — ATR-BASED POSITION SIZING (added 2026-05-24)
================================================================

SOURCE: r/algotrading community list — ATR mentioned as basic
but powerful indicator for position sizing

WHAT ATR IS:
  Average True Range — measures typical candle size for each stock
  Not a direction indicator — a volatility indicator
  Calculated over last 14 candles (standard)
  Formula: average of max(high-low, abs(high-prev_close),
           abs(low-prev_close)) over 14 periods

WHY WE USE ATR FOR STOPS (not fixed %):
  Fixed 1.8% stop: ignores each stock's actual behavior
  ATR stop: adjusts to each stock's real volatility

  Example on 15-min chart:
    HFCL ATR = ₹4.50 → stop = 1.5 × ₹4.50 = ₹6.75 below entry
    ITC ATR  = ₹1.20 → stop = 1.5 × ₹1.20 = ₹1.80 below entry
    Each stock's stop matches its own volatility profile

ATR-BASED STOP FORMULA:
  stop_loss = entry_price - (ATR_multiplier × ATR_14)
  ATR_multiplier = 1.5 (start here, adjust after backtesting)
  For shorts: stop_loss = entry_price + (ATR_multiplier × ATR_14)

ATR-BASED POSITION SIZING:
  risk_per_trade = capital × 0.01  (1% of capital)
  stop_distance = ATR_multiplier × ATR_14
  quantity = floor(risk_per_trade / stop_distance)

  Example at ₹50,000 capital:
    Risk = ₹500
    HFCL ATR = ₹4.50 → stop distance ₹6.75
    Qty = floor(500/6.75) = 74 shares
    Position = 74 × entry_price

    ITC ATR = ₹1.20 → stop distance ₹1.80
    Qty = floor(500/1.80) = 277 shares
    Position = 277 × entry_price

  Both trades risk exactly ₹500 regardless of stock

ATR ALSO USEFUL FOR:
  - Filtering out low-volatility days
    If ATR < 0.5% of stock price → skip (not enough movement)
  - Setting realistic targets
    Target = entry + (2 × stop_distance) [2:1 R:R maintained]
  - Identifying when market is unusually volatile
    If ATR > 3x its 20-day average → reduce position size

INTEGRATION WITH ORB SIGNAL:
  Step 1: Calculate opening range (first 15 candles)
  Step 2: Calculate ATR(14) on 15-min chart
  Step 3: If opening range width < 0.5 × ATR → skip today
          (too quiet, ORB won't produce meaningful move)
  Step 4: If opening range width > 2 × ATR → be cautious
          (unusually wide, likely news-driven, higher risk)
  Step 5: Normal range (0.5-2x ATR) → proceed with entry
  Step 6: Set stop at entry - 1.5 × ATR
  Step 7: Set target at entry + 3 × ATR (2:1 R:R)

UPDATE TO SECTION 7 (EXIT AND RISK RULES):
  REPLACES: fixed stop loss percentage
  WITH: ATR-based stop = entry - (1.5 × ATR_14)
  REPLACES: fixed 2:1 target
  WITH: target = entry + (3 × ATR_14) [still 2:1 since stop=1.5×ATR]

================================================================

================================================================
SECTION 14 — BACKTEST INFRASTRUCTURE (documented 2026-05-24)
================================================================

THE PROBLEM WE'RE SOLVING:
  We deployed real money before testing if the strategy works.
  We fixed bugs daily instead of validating the edge first.
  We paid for Dhan API but used it only for live trading,
  not for the historical research it enables.

  Correct order we should have followed:
  IDEA → BACKTEST → PAPER → LIVE (small) → SCALE
  
  What we actually did:
  IDEA → LIVE → DISCOVER LOSS → INVESTIGATE → NOW FIXING

================================================================
DATA SOURCE
================================================================

PRIMARY: Dhan Historical API
  Endpoint: /v2/charts/intraday
  File: intraday/dhan_broker.py → get_historical_ohlc()
  
  What it provides:
  - OHLCV candles (open, high, low, close, volume)
  - Timeframes: 1min, 5min, 15min, 25min, 60min
  - Any date range (API limit: ~90 days per call)
  - All NSE equities + indices
  - Already authenticated via your Dhan subscription
  
  Cost: Already paying for this — ₹0 additional cost
  
  How data is fetched:
  backtest/data_loader.py → fetch_and_cache_historical()
  - First call: fetches from Dhan API
  - Subsequent calls: reads from local cache (no API call)
  - Cache location: cache/historical/
  - Cache format: JSON files per symbol per date range
  - Rate limit: 200ms between calls (built in)

UNIVERSE DEFINITIONS (already in data_loader.py):
  load_nifty50_universe()    → 50 stocks with Dhan security IDs
  load_nifty500_universe()   → ~400-500 equities filtered from
                               config/nse_security_ids.json
  
  NOTE: These need expanding to include our Tier 1 universe
  (Nifty Next 50, F&O eligible midcaps)
  This is a config change, not a code change.

================================================================
BACKTEST COMPONENTS (what already exists)
================================================================

COMPONENT 1: data_loader.py (COMPLETE ✅)
  Purpose: Fetch and cache historical OHLC data
  Status: Working, tested, production-ready
  Key functions:
    fetch_and_cache_historical() → fetch multiple stocks
    fetch_universe_for_dates()   → fetch for specific dates
    load_nifty50_universe()      → get symbol→ID mapping
    load_nifty500_universe()     → get broader universe
  What it does well:
    - Caches to disk (run once, use many times)
    - Rate limiting built in
    - Handles API failures gracefully

COMPONENT 2: day_stratifier.py (COMPLETE ✅)
  Purpose: Pick representative test days from history
  Status: Working
  Key function: stratify_past_days()
  What it does:
    - Fetches Nifty 50 daily data for past 30 days
    - Categorizes each day: strong_up, strong_down,
      sideways, high_volatility, normal
    - Picks 8 representative days (2 strong_up,
      2 strong_down, 2 sideways, 1 volatile, 1 normal)
  Why this matters:
    - Prevents testing only on good days
    - Forces strategy to prove itself across conditions
    - Standard practice in professional backtesting

COMPONENT 3: trade_simulator.py (EXISTS, NEEDS REVIEW 🔍)
  Purpose: Simulate trade P&L from OHLC data
  Status: Exists but built for old LLM system
  Needs: Review to confirm it handles our new rules correctly
  Key question: Does it simulate realistic fills?
                Does it apply charges correctly?

COMPONENT 4: scanner_replay.py (EXISTS, PARTIAL USE 🔍)
  Purpose: Replay the scanner on historical data
  Status: Built for old system
  Needs: Understand what it does before deciding to reuse

COMPONENT 5: llm_replay.py (EXISTS, REPLACE ❌)
  Purpose: Replay LLM decisions on historical data
  Status: This is what we are REPLACING
  Action: Keep file but write new rule_engine.py instead
  New file will: Apply ORB + VWAP + ATR rules deterministically

COMPONENT 6: run_v1.py (EXISTS, ORCHESTRATOR 🔍)
  Purpose: Main backtest runner tying all components together
  Status: Exists, need to understand flow
  Needs: Review before deciding to reuse or rewrite

COMPONENT 7: results/ directory (EXISTS ✅)
  Purpose: Store backtest output
  Status: Empty, ready to use

================================================================
WHAT IS MISSING (what we need to build)
================================================================

MISSING 1: rule_engine.py (THE MAIN WORK)
  This is the core of the new system.
  Replaces llm_replay.py entirely.
  
  What it must do:
  For each 15-min candle in historical data:
    1. Calculate VWAP from market open
    2. Calculate ATR(14) on 15-min chart
    3. Track opening range (first 15 candles = 9:15-9:30)
    4. Detect ORB signal: price breaks above OR high
    5. Check VWAP confirmation: price above VWAP
    6. Check volume confirmation: 1.5x relative volume
    7. Check market direction: Nifty up on the day
    8. If all conditions met: generate trade signal
    9. Set stop = entry - (1.5 × ATR)
    10. Set target = entry + (3 × ATR)
    11. Record outcome when stop or target hit
  
  Output per trade:
    symbol, date, entry_time, entry_price,
    stop_loss, target, exit_time, exit_price,
    outcome (WIN/LOSS/TIME_STOP), pnl_gross,
    charges, pnl_net, strategy_type, signal_details

MISSING 2: Universe expansion
  data_loader.py currently has Nifty 50 only
  Need to add: Nifty Next 50 + F&O eligible midcaps
  This is a data change (add symbol→ID mappings)
  Source: config/nse_security_ids.json already has all IDs

MISSING 3: Relative volume calculation
  Need 20-day average volume per stock per time of day
  This requires fetching enough history first
  Then calculating baseline for comparison

MISSING 4: Backtest report
  After running, need clear output:
    Total trades, Win rate, Profit factor
    Avg win, Avg loss, Max drawdown
    Results by stock, by market condition
    Comparison: with charges vs without

================================================================
THE PLAN — THIS SATURDAY
================================================================

PHASE 1 (Morning — 1 hour):
  Review trade_simulator.py and run_v1.py
  Understand exactly what they do
  Decide: reuse or rewrite?

PHASE 2 (Late morning — 2 hours):
  Write rule_engine.py
  Pure math, no LLM
  ORB + VWAP + ATR rules only

PHASE 3 (Afternoon — 2 hours):
  Run backtest on last 3 months
  Nifty 50 first (data already available)
  See real win rate of real rules

PHASE 4 (Evening — 1 hour):
  Read results honestly
  If edge exists → plan paper deployment
  If no edge → adjust rules, try again next week
  Either way: document findings in SONNET_LOGICS.md

================================================================
SUCCESS DEFINITION FOR TODAY
================================================================

By end of Saturday we need to answer ONE question:

  "Does the ORB + VWAP + ATR strategy produce
   win rate > 45% and profit factor > 1.3
   on Nifty 50 stocks over the last 3 months?"

YES → Paper trade Monday, build confidence
NO  → Adjust parameters, test again, do not deploy

This answer is worth more than any amount of bug fixing.
It tells us if we have something worth fixing bugs FOR.

================================================================
WHY WE STOPPED BUG FIXING TO DO THIS
================================================================

The audit found 5 P0 bugs.
We have been fixing bugs for weeks.
But here is the truth:

  If the strategy has no edge:
    Perfect bug-free code still loses money
    Every bug fix is wasted effort
    
  If the strategy has edge:
    Bugs are worth fixing because there is profit to protect
    Bug fixes have clear ROI

  We cannot know which situation we are in
  until we backtest the REAL rules.

  That is why today's backtest comes before
  any more bug fixing.
  
  After today, we will know:
  - If strategy has edge → fix bugs, deploy carefully
  - If no edge → redesign strategy, then fix bugs

================================================================

================================================================
SECTION 15 — BACKTEST FRAMEWORK DESIGN (added 2026-05-24)
================================================================

GOAL:
  6 months of data, multiple scenarios, honest results
  Answer: "Does our strategy make money across real conditions?"
  Not cherry-picked days — every trading day Dec 2025-May 2026

DATA SCOPE:
  Period: 6 months (Dec 2025 — May 2026)
  Trading days: ~125
  Universe: Nifty 50 + Next 50 (100 stocks)
  Candle size: 15-minute OHLC
  Source: Dhan API (already paying for it)
  Cache: Local JSON files (fetch once, use forever)

10 MARKET SCENARIOS TO TEST:
  1. Bull run days (Nifty > +1%)
  2. Bear days (Nifty < -1%)
  3. Sideways/choppy (Nifty ±0.5%)
  4. High volatility (VIX > 18)
  5. Low volatility (VIX < 13)
  6. F&O expiry days (last Thursday)
  7. Result season (Jan-Feb, Apr-May)
  8. Macro event days (RBI, budget, US Fed)
  9. Monday opens (gap from weekend)
  10. Friday closes (unwinding behavior)

5 UNIVERSE VARIANTS TO TEST:
  A. Nifty 50 only
  B. Nifty Next 50 only
  C. Top 10 by relative volume that day
  D. Sector leaders (top 2 from top 3 sectors)
  E. Catalyst stocks (gapped > 2% at open)

6 STRATEGY VARIATIONS TO TEST:
  V1. Pure ORB (baseline)
  V2. ORB + VWAP filter
  V3. ORB + VWAP + ATR sizing
  V4. ORB + VWAP + ATR + Market direction
  V5. VWAP reclaim only
  V6. Gap + ORB (catalyst stocks only)

4 POSITION SIZING VARIANTS:
  A. Fixed ₹15,000 per trade
  B. Fixed ₹50,000 per trade
  C. 1% risk per trade with ATR stop
  D. 2% risk per trade with ATR stop

REPORT MUST SHOW:
  Per strategy/universe/scenario combination:
  - Win rate, profit factor, avg win/loss
  - Net P&L after real charges
  - Max drawdown
  - Best/worst stocks
  - Best/worst time of day
  - Best/worst market condition
  - Monthly breakdown

FILES TO BUILD:
  rule_engine.py      — ORB/VWAP/ATR signal generation
  scenario_runner.py  — runs all combinations
  report_generator.py — formats results
  universes.py        — universe definitions

FILES TO REUSE:
  data_loader.py      — already works
  day_stratifier.py   — already works
  trade_simulator.py  — reuse execution logic
  charges.py          — real Dhan charges

SUCCESS CRITERIA:
  At least ONE strategy/universe combination shows:
  - Win rate > 45%
  - Profit factor > 1.3
  - Positive net P&L over 6 months
  - Works in at least 3 of 5 market scenarios
  
  If nothing passes → strategy needs redesign before deployment
  If something passes → deploy that specific combination

================================================================

================================================================
SECTION 17 — BACKTEST BUGS FOUND AND FIXED (2026-05-24)
================================================================

BUG 1: Exit direction wrong (CRITICAL)
  File: backtest/run_big_test.py
  Problem: Exit loop walked ALL candles including pre-entry ones
           Stop loss used c["close"] <= sl instead of c["low"] <= sl
           String time comparison caused wrong candle selection
  Effect:  47 of 52 "STOPPED_OUT" trades were actually profitable
           Inflated WR from real ~50% to fake 76%
           Inflated net P&L from real ~₹8-12K to fake ₹38K
  Fix:     Find entry candle index first
           Walk only candles AFTER entry
           Use c["low"] <= sl for stop (not close)
           Use c["high"] >= target for target (correct already)

BUG 2: F&O capital not constrained
  File: backtest/run_big_test.py
  Problem: Deployed ₹14,40,000 in premium on ₹2,00,000 capital
           No check against total capital used
  Effect:  F&O results completely meaningless
  Fix:     Add premium_deployed check vs FNO_CAPITAL limit

LESSON: Always verify backtest results by:
  1. Check exit reason distribution (mix of TARGET/STOP/TIME)
  2. Verify STOPPED_OUT trades are losses, not profits
  3. Verify TARGET_HIT trades are profits
  4. Check capital constraints are respected
  5. 76%+ WR is always suspicious — investigate immediately

REAL EXPECTED RESULTS (after fix):
  WR: 45-55% (not 76%)
  PF: 1.2-2.0 (not 8.54)
  Net: ₹5,000-15,000 per 6 months at ₹2L capital
================================================================
