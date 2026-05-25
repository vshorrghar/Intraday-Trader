# 🚨 Crisis Portfolio Analysis Guide

## What's New - Enhanced Features

Your w-builder app now has **3 powerful new AI modules** specifically designed for crisis situations:

### 1️⃣ **Real-Time Portfolio Analyzer**
- **BUY_MORE**: Quality stocks on sale - add to position
- **AVERAGE_DOWN**: Smart averaging strategy with quantity suggestions
- **HOLD_TIGHT**: Don't panic sell, ride it out
- **BOOK_PARTIAL**: Take some profits/reduce exposure
- **EXIT**: Cut losses on weak stocks
- **SWITCH**: Better opportunities available

**Features**:
- Specific quantity recommendations for averaging
- Priority levels (HIGH/MEDIUM/LOW) for each action
- Crisis opportunity flags for best buys
- Real-time P&L calculations

### 2️⃣ **Crisis Opportunity Scanner**
Finds gems during market crashes in 4 categories:

- **DEFENSIVE_QUALITY**: Pharma, FMCG, IT, Healthcare (crisis-proof sectors)
- **SMART_MONEY_BUY**: FII/DII buying despite crash (follow the institutions)
- **OVERSOLD_GEM**: Quality stocks down >15% but fundamentals intact
- **CRISIS_BENEFICIARY**: Defense, oil & gas, logistics (benefit from war)

**Gives you**:
- Current price vs estimated fair value
- Upside potential %
- Risk-reward rating (high/medium/low)
- Specific action (BUY_NOW / ACCUMULATE_ON_DIP / WATCH)

### 3️⃣ **Enhanced Intraday Engine**
Not just any stocks - **smart money picks** with:

- FII/DII flow analysis (where institutions are buying)
- Volume spike detection
- Defensive sector filtering during crisis
- Technical + fundamental screening
- Tight risk-reward ratios (min 1:2)

**Better than before because**:
- Uses institutional flow data (FII/DII)
- Prioritizes defensive sectors during war
- Volume + momentum confirmation
- Cites SPECIFIC evidence (not generic)

## How to Run

### Step 1: Refresh AWS Credentials

```bash
cd ~/kiro/websites/w-builder

# Get fresh credentials from AWS (Isengard or Console)
# Export them:
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# Verify they work:
aws sts get-caller-identity
```

### Step 2: Run Crisis Analysis

```bash
python3 run_crisis_analysis.py
```

### Step 3: View Results

Results saved in `output/crisis_analysis/`:
- `crisis_report_YYYYMMDD_HHMMSS.txt` - Human-readable report
- `crisis_analysis_YYYYMMDD_HHMMSS.json` - Detailed JSON data

## What You'll Get

### Example Output Structure:

```
📊 MARKET CONTEXT
FII Net Flow: ₹-1,234.56 Cr  (SELLING - panic mode)
DII Net Flow: ₹+567.89 Cr    (BUYING - opportunity)

1️⃣ YOUR PORTFOLIO - 45 stocks analyzed

HIGH PRIORITY ACTIONS (5):
- Dr. Reddy's Lab → BUY_MORE (crisis opportunity, defensive pharma)
- Infosys → AVERAGE_DOWN (IT holding strong, down 18%)
- HDFC Bank → HOLD_TIGHT (quality name, temporary weakness)
- DLF → EXIT (real estate risk, high debt)
- Vedanta → SWITCH (better opportunities in defense)

2️⃣ CRISIS OPPORTUNITIES (12 found)

BUY NOW (3):
- Sun Pharma: DEFENSIVE_QUALITY, ₹1,450 → Fair Value ₹1,950 (34% upside)
- TCS: SMART_MONEY_BUY, FII buying despite -12% crash
- HAL: CRISIS_BENEFICIARY, defense stock, war tailwind

ACCUMULATE ON DIP (4):
- Cipla, Titan, Asian Paints, Maruti

3️⃣ TODAY'S INTRADAY PICKS (5 setups)

1. Dr. Reddy's Lab (DRREDDY)
   Entry: ₹6,150 | Target: ₹6,320 | Stop: ₹6,080
   Risk-Reward: 1:2.4
   Rationale: FII net buying ₹45Cr in bulk deals, defensive pharma,
              volume spike 180%, holding above VWAP despite Nifty -2%

[... 4 more setups]
```

## Crisis Investing Tips

During Iran-USA war market crash:

✅ **DO**:
- Buy quality defensive stocks (pharma, FMCG, IT)
- Follow FII/DII buying (smart money)
- Average down on fundamentally strong stocks
- Focus on low debt, high ROCE companies
- Look for defense, oil & gas beneficiaries

❌ **DON'T**:
- Average down on weak stocks (high debt, poor management)
- Panic sell quality names
- Buy high-beta cyclicals (real estate, NBFCs)
- Ignore stop losses
- Over-leverage

## Comparison: Old vs New

### Old Intraday Engine:
```
"Generate 5 intraday setups based on market data"
→ Generic picks, no institutional flow analysis
→ No sector filtering for crisis
→ No evidence cited
```

### New Enhanced Engine:
```
"Generate setups using FII/DII flows, volume spikes, defensive sectors"
→ Smart money analysis (where FII/DII buying)
→ Defensive priority during crisis
→ Cites specific evidence (FII net, volume %, PE)
```

## Integration with Existing Workflow

Your existing `go.sh` workflow still works. The new crisis analysis is **ADDITIONAL**:

```bash
# Regular daily analysis (morning/midday/EOD)
./go.sh

# Crisis mode analysis (run when markets crashing)
python3 run_crisis_analysis.py
```

## Files Created

New modules:
- `llm/crisis_opportunity_analyzer.py` - Crisis opportunity scanner
- `llm/enhanced_intraday_engine.py` - Smart money intraday engine
- `llm/realtime_portfolio_analyzer.py` - Portfolio action recommender
- `llm/models.py` - Updated with CrisisOpportunity dataclass
- `run_crisis_analysis.py` - Main runner script

## Next Steps

1. **Get fresh AWS credentials** (required for Bedrock AI)
2. **Run the analysis**: `python3 run_crisis_analysis.py`
3. **Review the report** in `output/crisis_analysis/`
4. **Act on HIGH priority recommendations**

---

## Troubleshooting

**"ExpiredToken" error**:
- Get fresh AWS credentials from Isengard
- Run `aws sts get-caller-identity` to verify

**"No Stocks Holdings file found"**:
- Copy latest Groww XLSX to `input/` directory
- Or run `python3 pick_latest_files.py`

**"Bedrock throttled"**:
- Script auto-retries 3 times with backoff
- If persists, wait 1 minute and re-run

**Empty results**:
- Check if bhavcopy/FII/DII data fetched successfully
- NSE websites may block non-Indian IPs (use EC2 Mumbai)

---

🚀 **You now have a crisis-aware portfolio intelligence system!**
