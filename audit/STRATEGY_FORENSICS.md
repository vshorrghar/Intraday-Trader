# STRATEGY FORENSICS — 7 Questions Answered
**Generated:** 2026-05-22 by Kiro from code inspection
**Scope:** Read-only. No code modified. No fixes proposed.

---

## Question 1: Who Decides to Trade?

**Answer: (a) LLM-DRIVEN**

The decision chain is:
1. Scanner (intraday/scanner.py) scores 500 stocks on 6 signals → top 30
2. Pre-filter (selector.py:50-135) applies price range, volume, high_volatility flag → 20 candidates
3. **LLM (selector.py:200-320)** receives all 20 candidates + sector data + VIX + trade history
4. **LLM picks which stocks to trade, sets entry/target/SL prices, assigns confidence_score AND strategy_type**
5. Validator (selector.py:420-480) checks R:R >= 2.0, confidence >= threshold, direction logic
6. If valid → executor places order

**Critical finding:** The LLM decides EVERYTHING that matters:
- Which stocks (from the 20 candidates)
- Entry price, target, stop loss
- Confidence score (self-reported, see Q3)
- Strategy type label (see Q4)
- Whether to skip the day entirely

The scanner/pre-filter only narrows the universe. The LLM makes the actual trade decision.

**Evidence:**
- selector.py:200-320 — system prompt tells LLM to pick stocks and assign strategy_type
- selector.py:530-560 — LLM response parsed, picks extracted
- selector.py:570-600 — validated picks become TradeSetup objects

**For VWAP/ORB specifically:** There is NO mathematical VWAP calculation or opening range breakout detection in the code. The system prompt (selector.py:270-285) merely DESCRIBES what VWAP/ORB/MOMENTUM/GAP mean as text labels. The LLM decides if a candidate "looks like" a VWAP setup based on the prompt description. There is no actual VWAP line computed, no opening range tracked, no breakout detection.

**For MOMENTUM/GAP:** Same — these are LLM-assigned labels, not computed conditions.

---

## Question 2: Why Does vishal-live Never Take VWAP or ORB Trades?

**Ranked answers (by evidence strength):**

**(c) price_range_max = 2000 is the primary filter — STRONG EVIDENCE**

Config diff:
- vishal-live: price_range_max = 2000 (config/profiles/vishal-live.yaml)
- vishal paper: NO explicit price_range in profile yaml → falls back to config/config.yaml line 43: price_range_max = 3000

Many VWAP/ORB candidates (large-cap stocks like HDFC Bank, Reliance, TCS, Infosys) trade above Rs.2000. vishal-live's price cap of Rs.2000 excludes them at the pre-filter stage (selector.py:85-88). They never reach the LLM.

**(a) per_trade_max_capital = 4500 compounds the issue — MODERATE EVIDENCE**

At Rs.4500 max per trade and price_range_max Rs.2000, the system can only buy 2-3 shares of stocks above Rs.1500. This makes large-cap VWAP/ORB setups impractical (tiny position, charges eat profit).

The LLM prompt includes: "Budget: Rs.15,000 total, Rs.4,500 per trade" — the LLM likely self-selects away from expensive stocks knowing position will be tiny.

**(d) Cron timing is NOT the issue**

All 3 profiles run on identical cron: */15 4-7 * * 1-5 (every 15 min, 9:30 AM - 1:00 PM IST). Same timing.

**(b) VIX threshold is NOT the primary cause**

vishal-live vix_threshold=20, vishal paper vix_threshold=18. Both would skip on VIX>20. This affects ALL strategies equally, not VWAP/ORB specifically.

---

## Question 3: Is Confidence Score a Real Signal or LLM Self-Report?

**Answer: (a) SELF-REPORT**

The confidence_score is entirely LLM-generated. The system prompt (selector.py:300) includes this in the expected JSON output:

```
"confidence_score": 8,
```

The LLM is asked to rate its own confidence 1-10 as part of its pick response. There is NO computed confidence from technical indicators anywhere in the codebase.

**Evidence:**
- selector.py:300 — example JSON shows confidence_score as LLM output field
- selector.py:37 — REQUIRED_PICK_FIELDS includes confidence_score as (int, float) from LLM response
- selector.py:440 — validate_pick checks `confidence < config.min_confidence_score` but the VALUE comes from LLM

**This explains the confidence inversion:** LLMs are known to be overconfident on plausible-sounding wrong answers. Higher self-reported confidence correlates with the LLM being MORE certain about a narrative it constructed — not with actual market edge. The LLM says "8" when it has a compelling story, not when the setup is statistically better.

---

## Question 4: Are strategy_type Labels Causal or Descriptive?

**Answer: DESCRIPTIVE (post-hoc labeling by LLM)**

The strategy_type is assigned by the LLM as part of its pick response. There is NO pre-entry rule that says "this IS a momentum setup, therefore enter." The LLM looks at the candidate data and labels it.

**Evidence:**
- selector.py:270-285 — system prompt DESCRIBES strategy types as text:
  ```
  MOMENTUM : Strong gap up + volume surge + sector leading
  ORB      : Price breaking above first 15min high with volume
  VWAP     : Price reclaiming VWAP after dip with volume support
  ```
- These are DESCRIPTIONS for the LLM to use as labels, not computed conditions
- No code anywhere computes VWAP, tracks opening range, or detects momentum mathematically
- The LLM assigns the label based on pattern-matching the description to the data it sees

**Implication:** "MOMENTUM being unprofitable" means "trades the LLM labeled as momentum are unprofitable" — it does NOT mean a momentum strategy is broken, because there IS no momentum strategy. There's only an LLM making picks and labeling them.

---

## Question 5: How Is HDFC Bank Passing Screening?

**Findings:**

1. **No blacklist mechanism exists.** grep for blacklist/exclude/block/banned across intraday/ returns nothing relevant.

2. **No per-stock performance learning loop.** The _fetch_trade_history function (selector.py:153-195) feeds past 30 days of trade history to the LLM as context, including per-stock win rate. But this is ADVISORY — the LLM can ignore it. There is no hard rule that says "if stock X has 0% win rate over N trades, exclude it."

3. **HDFC Bank passes screening because:** it has high volume (always > 2M), is in a positive sector (Banking), and its price is within range. The scanner scores it, pre-filter passes it, and the LLM picks it despite poor history.

4. **The trade history IS fed to the LLM** (selector.py:530: `history = _fetch_trade_history(db)`). But the LLM clearly doesn't weight it heavily enough to avoid repeat losers.

**Conclusion:** No hard exclusion mechanism. The system relies entirely on the LLM to learn from history context. The LLM doesn't learn.

---

## Question 6: Steering Doc Reconciliation

### STRATEGY.md claims:
- (a) Edge: "RS-First v3" scanner scoring with 6 signals. Claims scanner picks better stocks than v1.
- (b) Strategies: describes scanner signals (momentum, sector rotation, volume). Does NOT claim VWAP/ORB as primary.
- (c) Confidence: mentioned only as "confidence >= threshold" filter. No claim about what confidence MEANS.
- (d) VWAP/ORB: NOT mentioned anywhere in STRATEGY.md. Primary focus is scanner scoring.
- (e) min_confidence_score=7: documented as config value, no rationale for WHY 7.

### EDGE.md claims:
- (a) Edge: "High-conviction setups (confidence 8+, multi-signal alignment)" — line 86
- (b) Strategies: does not name specific strategy types as edge sources
- (c) Confidence: "High-conviction setups (confidence 8+)" implies higher confidence = better. **DATA CONTRADICTS THIS.**
- (d) VWAP/ORB: not mentioned
- (e) Target win rate: 60% for profitability, 65%+ for "money machine" — line 128-129

### WIN_RATE_TRACKING.md claims:
- Contains SQL queries for per-strategy win rate analysis
- Does not make claims about which strategies should work
- Notes "Most losses are bug-related not strategy-related" — line 473. **DATA CONTRADICTS: SHORT_MOMENTUM 10-20% WR is not a bug.**

### RULES.md claims:
- min_confidence_score: 7 for paper, 7 for vishal-live, 8 for neha-live (Section 5)
- No rationale for these specific numbers

### CONTRADICTIONS:
| Doc says | Data shows |
|----------|-----------|
| EDGE.md: "confidence 8+ = high conviction = better" | Confidence 8 = 46% WR, confidence 6 = 71% WR |
| WIN_RATE: "losses are bug-related" | SHORT_MOMENTUM 10-20% WR across ALL profiles = strategy failure |
| RULES: min_confidence=7 filters out conf 6 | Confidence 6 is the MOST profitable bucket |
| EDGE.md: "60% win rate target" | vishal-live at 28% WR after 29 trades |

---

## Question 7: vishal-paper vs vishal-live Config Drift

| Setting | vishal-live | vishal-paper | Impact |
|---------|-------------|--------------|--------|
| daily_capital_limit | 15,000 | 300,000 | 20x more capital on paper |
| per_trade_max_capital | 4,500 | 50,000 | 11x more per trade |
| max_trades_per_day | 3 | 6 | Paper gets 2x more shots |
| daily_loss_limit | 500 | 9,000 | Paper absorbs 18x more loss |
| vix_threshold | 20 | 18 | Live trades VIX 18-20 zone where paper skips |
| price_range_min | 100 | 50 (default) | Live excludes Rs.50-100 stocks |
| price_range_max | 2000 | 3000 (config.yaml) | **CRITICAL: Live excludes Rs.2000-3000 stocks** |
| min_confidence_score | 7 | 7 | Same |

**Impact analysis:**

(a) **Which strategies fire:** price_range_max=2000 on live excludes large-cap stocks (TCS Rs.4000+, Reliance Rs.2900+, Infosys Rs.1500+). These are typical VWAP/ORB candidates on paper. Paper sees them, live doesn't.

(b) **Which stocks become candidates:** At Rs.4500 per trade max, live can only buy 2-3 shares of stocks above Rs.1500. The LLM prompt says "Budget: Rs.15,000 total, Rs.4,500 per trade" — LLM self-selects toward cheaper stocks.

(c) **Which trades get filtered out:** The combination of price_range_max=2000 + per_trade_max_capital=4500 creates a fundamentally different trading universe than paper. Paper and live are NOT running the same strategy on the same stocks.

---

## SUMMARY: WHAT THE OWNER NEEDS TO KNOW

1. **The system has no strategy.** It has an LLM that picks stocks and labels them. VWAP/ORB/MOMENTUM are descriptive tags, not computed entry conditions. The "edge" is entirely LLM judgment quality — which the data shows is INVERSELY correlated with its self-reported confidence.

2. **vishal-live is structurally handicapped vs paper.** price_range_max=2000 + per_trade_max_capital=4500 excludes the large-cap setups where paper profits. The two profiles are not running the same strategy — they're running different universes with different position sizes. Comparing their win rates is comparing apples to oranges.

3. **Confidence score is noise, not signal.** It's LLM self-report with no calibration. The min_confidence_score=7 filter actively excludes the most profitable bucket (conf 6 = 71% WR). The system would likely improve by LOWERING the threshold or removing it entirely.
