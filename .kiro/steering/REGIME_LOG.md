# REGIME_LOG.md — Daily Market Regime Capture

**Purpose:** Daily snapshot of market regime conditions (Nifty, VIX, sectors, FII flows, news). Builds pattern recognition over months: which regimes our strategies make money in, which they lose in.

**Update rule:** Daily, before market open and after market close. ~10 min/day total.

**Reading order:** RULES.md, STATE.md, EDGE.md, REGIME_LOG.md (when reviewing regime patterns)

**Author:** Vishal (founder, principal trader)
**Last updated:** 2026-05-19 (initial template; daily entries start 2026-05-20)

---

## DOCUMENT PURPOSE

After 3 months of daily regime logs, you will see patterns invisible in real-time:
- "Our intraday wins more in pharma-led days than IT-led days"
- "VIX 18-20 is killing our edge, not 22-25 as we thought"
- "FII selling > Rs.3000 Cr makes scanner picks fail"

These insights compound into edge improvements that pure code can't deliver.

---

## DAILY TEMPLATE (copy this for each day)

### YYYY-MM-DD (DAY-OF-WEEK)

#### Pre-Market State (8:30 AM IST)

- Nifty 50 close (yesterday): _____
- Nifty vs 50-DMA: ABOVE / BELOW (gap _____ %)
- Nifty vs 200-DMA: ABOVE / BELOW (gap _____ %)
- VIX level: _____ (yesterday close)
- VIX trend (5 days): RISING / FALLING / FLAT
- USD/INR: _____ (stable/strengthening dollar/weakening dollar)
- US S&P 500 close: ABOVE / BELOW its 50-DMA
- SGX Nifty / GIFT Nifty: _____ % indication
- Crude oil: $_____ (rising/falling/stable)
- 10Y Indian bond yield: _____ %

#### Regime Score (current 3-signal version)

- Nifty above 50-DMA: 0/1
- Nifty above 200-DMA: 0/1
- VIX below 20: 0/1

Total: ___/3
- 3/3: AGGRESSIVE (full sizing per Phase rules)
- 2/3: NORMAL
- 1/3: DEFENSIVE (halve sizes, defensive sectors only)
- 0/3: PAUSE (no new positions)

#### News Headlines Affecting Markets

(2-3 lines; major events only)

- Geopolitical: _____
- Domestic policy: _____
- Earnings season: _____
- Macro events ahead: _____

#### Market Session Summary (4 PM EOD update)

- Nifty close: _____ (___ %)
- Day range: _____ to _____ (_____ pts)
- Top 3 sectors today: _____ , _____ , _____
- Bottom 3 sectors today: _____ , _____ , _____
- Advance/Decline ratio: _____
- VIX close: _____ (change from yesterday: _____)
- FII net flow (if available): Rs. _____ Cr (buy/sell)
- DII net flow (if available): Rs. _____ Cr (buy/sell)

#### Today's Trades vs Regime

| Profile | Setup | Sector | Regime Match? | Win/Loss |
|---------|-------|--------|---------------|----------|
| vishal-live | _____ | _____ | YES/NO | _____ |
| swing-vishal-live | _____ | _____ | YES/NO | _____ |

#### Regime Lessons (Today)

(1-3 lines on what regime taught us)

- _____
- _____

---

## SAMPLE FILLED DAY (2026-05-20)

This is what a complete entry looks like. Use as reference.

### 2026-05-20 (Tuesday)

#### Pre-Market State (8:30 AM IST)

- Nifty 50 close (yesterday): 24,150
- Nifty vs 50-DMA: ABOVE (gap +1.2%)
- Nifty vs 200-DMA: ABOVE (gap +5.8%)
- VIX level: 18.5 (yesterday)
- VIX trend (5 days): SLIGHTLY RISING
- USD/INR: 83.20 (stable)
- US S&P 500: ABOVE 50-DMA
- SGX Nifty: -0.3% (mildly negative open expected)
- Crude oil: $89 (stable)
- 10Y Indian bond: 7.05%

#### Regime Score

- Nifty above 50-DMA: 1
- Nifty above 200-DMA: 1
- VIX below 20: 1

Total: 3/3 = AGGRESSIVE (but still cautious mode this week per Bug 1 validation)

#### News Headlines

- Geopolitical: Iran-Israel tensions ongoing, low immediate volatility
- Domestic: RBI policy meeting in 2 weeks
- Earnings: Q1 results season starting
- Macro: US Fed Powell speaking 7 PM IST (post-market for India)

#### Market Session Summary (TBD by EOD)

(Fill at 4 PM IST after close)

---

## WEEKLY REGIME SUMMARY (every Sunday)

### Week of YYYY-MM-DD to YYYY-MM-DD

#### Average Regime Score: ___/3

#### Dominant Sectors

- Top 3 of week: _____, _____, _____
- Bottom 3 of week: _____, _____, _____

#### Key Events Of Week

- _____
- _____

#### Our Performance vs Regime

- Wins this week: _____
- Losses this week: _____
- Win rate: _____ %
- Best regime day for us: _____
- Worst regime day for us: _____

#### Pattern Hypothesis

(After 4 weeks of data, look for patterns)

- _____

---

## MONTHLY REGIME REVIEW (end of each month)

### Month: YYYY-MM

#### Days by Regime Score

- 3/3 days: ___ (AGGRESSIVE)
- 2/3 days: ___ (NORMAL)
- 1/3 days: ___ (DEFENSIVE)
- 0/3 days: ___ (PAUSE)

#### Win Rate by Regime

- AGGRESSIVE days: ___ % win rate, ___ trades
- NORMAL days: ___ % win rate, ___ trades
- DEFENSIVE days: ___ % win rate, ___ trades
- PAUSE days: 0 trades (correct discipline if any)

#### Sector Win Rate

- Best sector this month: _____ (___ % win rate)
- Worst sector this month: _____ (___ % win rate)

#### Lessons For Next Month

- _____
- _____
- _____

#### Action Items

- _____
- _____

---

## SAMPLE PATTERNS TO WATCH FOR

After 30+ daily entries, look for these:

### Pattern 1: VIX dead zone
"On days with VIX between 18.0 and 19.5, our win rate drops to 30% (vs 60% other ranges). Why?"

### Pattern 2: Sector momentum lag
"When pharma is top sector, we win 70% of pharma trades. But scanner picks pharma only after sector is already top — by then move is half done."

### Pattern 3: FII selling correlation
"FII net selling > Rs.3000 Cr correlates with our win rate dropping 15 points the next day."

### Pattern 4: Day-of-week effect
"Mondays: 65% win rate. Fridays: 45%. Why?"

### Pattern 5: Earnings adjacency
"3 days before/after results: 30% win rate. Other times: 60%."

### Pattern 6: Currency correlation
"USD strengthening > 0.5% week: 40% win rate. USD stable: 60%."

When you see ANY of these, document in STRATEGY.md and adjust scoring/gates.

---

## TIPS FOR EFFICIENT DAILY UPDATES

1. **Pre-market check (5 min):** Open economictimes.indiatimes.com or moneycontrol.com main page. Most fields available there.

2. **Use shortcuts in entries:** Instead of "Above 50-DMA" type just "above". You'll know what it means.

3. **Skip sections if no data:** If FII data not yet released, write "TBD" not blank. Easier to identify gaps.

4. **EOD entry needs only 3 minutes:** Just close prices, top/bottom sectors, your trade results.

5. **Don't perfect, document:** A messy daily entry beats a perfect missing one.

---

## ANNUAL REVIEW

End of each year:
1. Re-read all daily entries
2. Identify dominant regime patterns
3. Update EDGE.md with regime-specific edge insights
4. Adjust scanner/risk_manager based on regime data
5. Document lessons in HISTORY.md

Last review: N/A (project less than 1 year)
Next review due: 2026-12-31

---

## SIGNATURE

I commit to daily regime entries (5-10 min/day) because:
- Pattern recognition compounds over months
- Future me cannot remember 90 days of regimes
- Code optimization without regime context is incomplete
- Real fund managers do this; I will too

Vishal | 2026-05-19 | Founder, Principal Trader

