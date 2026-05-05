#!/usr/bin/env python3
"""Wealth Builder Pro — Full Portfolio Analysis.

Parses Groww XLSX files (stocks + MFs), sends ALL holdings to Claude
via Bedrock for verdicts, MF recommendations, and new stock picks.

Usage:
    export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
    export BEDROCK_MODEL_ID="us.anthropic.claude-sonnet-4-20250514-v1:0"
    python3 run_analysis.py
"""

import json
import os
import sys
from datetime import datetime

print("📂 Parsing portfolio files...")

from parsers.groww_stocks_parser import parse_stocks_xlsx
from parsers.groww_mf_parser import parse_mf_xlsx

STOCKS_FILE = "input/Stocks_Holdings_Statement.xlsx"
MF_FILE = "input/Mutual_Funds.xlsx"

if not os.path.exists(STOCKS_FILE):
    print(f"❌ {STOCKS_FILE} not found"); sys.exit(1)

stocks = parse_stocks_xlsx(STOCKS_FILE)
print(f"  ✅ {len(stocks)} stock holdings parsed")

mfs = []
if os.path.exists(MF_FILE):
    mfs = parse_mf_xlsx(MF_FILE)
    print(f"  ✅ {len(mfs)} MF schemes parsed")

total_stock_inv = sum(h.buy_value for h in stocks)
total_stock_cur = sum(h.groww_closing_value for h in stocks)
total_mf_inv = sum(h.invested_value for h in mfs)
total_mf_cur = sum(h.current_value for h in mfs)
total_inv = total_stock_inv + total_mf_inv
total_cur = total_stock_cur + total_mf_cur
total_pnl = total_cur - total_inv

print(f"\n💰 Portfolio: ₹{total_cur:,.0f} (P&L: ₹{total_pnl:,.0f}, {total_pnl/total_inv*100:.1f}%)")

if not os.environ.get("AWS_ACCESS_KEY_ID"):
    print("\n  ℹ️ No env creds — using IAM role")

print("\n🤖 Sending ALL holdings to Claude via Bedrock...")

from llm.bedrock_client import BedrockClient

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
client = BedrockClient(region=BEDROCK_REGION, model_id=MODEL_ID)

# ALL stocks
all_stocks = []
for h in stocks:
    all_stocks.append({
        "name": h.name, "isin": h.isin, "qty": h.quantity,
        "buy_price": round(h.avg_buy_price, 2),
        "buy_value": round(h.buy_value, 0),
        "current_price": round(h.groww_closing_price, 2),
        "current_value": round(h.groww_closing_value, 0),
        "pnl": round(h.unrealised_pnl, 0),
        "pnl_pct": h.pnl_percent,
        "type": h.holding_type,
    })

# ALL MFs
all_mfs = []
for h in mfs:
    all_mfs.append({
        "scheme": h.scheme_name, "amc": h.amc,
        "category": h.category, "sub_category": h.sub_category,
        "invested": round(h.invested_value, 0),
        "current": round(h.current_value, 0),
        "returns": round(h.returns_absolute, 0),
        "returns_pct": h.returns_percent,
        "xirr": h.xirr,
    })

system_prompt = """You are a senior Indian equity research analyst with 20+ years at top brokerages.
You specialize in Indian retail investor portfolio reviews, mutual fund analysis, and identifying future multibagger stocks.

Analyze the COMPLETE portfolio and respond with this EXACT JSON structure:

{
  "portfolio_health_score": <0-100>,
  "portfolio_summary": "<1 paragraph overall assessment>",

  "individual_stock_verdicts": [
    {"name": "", "verdict": "BUY|HOLD|SELL|EXIT", "action": "", "reason": ""}
  ],

  "mf_verdicts": [
    {"scheme": "", "verdict": "CONTINUE_SIP|HOLD|STOP_SIP|SWITCH", "action": "", "reason": ""}
  ],

  "new_stock_recommendations": [
    {
      "name": "", "nse_symbol": "", "sector": "",
      "why": "<specific thesis - not generic>",
      "entry_range": "₹X - ₹Y",
      "target_1yr": "₹X",
      "stop_loss": "₹X",
      "risk": "",
      "conviction": "HIGH|MEDIUM"
    }
  ],

  "future_multibaggers": [
    {
      "name": "", "nse_symbol": "", "sector": "",
      "market_cap": "",
      "thesis": "<why this can 3-5x in 3-5 years>",
      "key_metrics": "<revenue growth, ROE, debt ratio, promoter holding>",
      "entry_range": "₹X - ₹Y",
      "risk": "",
      "timeframe": "2-3 years | 3-5 years"
    }
  ],

  "top_5_urgent_actions": [""],
  "key_risks": [""],

  "sector_allocation_advice": {
    "overweight": ["sectors to reduce"],
    "underweight": ["sectors to add"],
    "recommendation": ""
  }
}

RULES:
- Give verdict for EVERY stock and EVERY MF scheme provided. Do not skip any.
- For stocks down >50% with no recovery thesis = EXIT
- For stocks up >100% = consider partial profit booking
- For MFs: compare XIRR to category average. Below average = SWITCH or STOP_SIP
- 269 stock positions is WAY too many. Be aggressive about cleanup.
- new_stock_recommendations: 10 stocks NOT in the portfolio that are good buys NOW
- future_multibaggers: 10 small/mid cap stocks that can 3-5x in 3-5 years
  Focus on: revenue CAGR >20%, ROE >15%, low debt, strong promoter, market cap <₹20,000 Cr
  Think beyond obvious names. Look at niche sectors: specialty chemicals, defence, EMS, API pharma, water treatment, data centers, green hydrogen
- Be brutally honest. Don't sugarcoat.
- Use ONLY real company names that trade on NSE/BSE."""

user_prompt = f"""COMPLETE PORTFOLIO ANALYSIS — {datetime.now().strftime('%d-%b-%Y')}

PORTFOLIO OVERVIEW:
- {len(stocks)} stocks, invested ₹{total_stock_inv:,.0f}, current ₹{total_stock_cur:,.0f}
- {len(mfs)} MF schemes, invested ₹{total_mf_inv:,.0f}, current ₹{total_mf_cur:,.0f}
- Total: ₹{total_cur:,.0f}, P&L: ₹{total_pnl:,.0f} ({total_pnl/total_inv*100:.1f}%)

ALL {len(stocks)} STOCK HOLDINGS:
{json.dumps(all_stocks, indent=1)}

ALL {len(mfs)} MUTUAL FUND HOLDINGS:
{json.dumps(all_mfs, indent=1)}"""

print(f"  Sending {len(all_stocks)} stocks + {len(all_mfs)} MFs to Claude...")
print(f"  Prompt size: ~{len(user_prompt)//1000}KB")

response = client.invoke(system_prompt, user_prompt)

if not response:
    print("❌ Bedrock returned empty response. Check creds/model access.")
    sys.exit(1)

# Count results
sv = response.get("individual_stock_verdicts", [])
mv = response.get("mf_verdicts", [])
nr = response.get("new_stock_recommendations", [])
fm = response.get("future_multibaggers", [])

print(f"\n{'='*70}")
print(f"🤖 ANALYSIS COMPLETE")
print(f"{'='*70}")
print(f"  Stock verdicts:    {len(sv)}")
print(f"  MF verdicts:       {len(mv)}")
print(f"  New stock picks:   {len(nr)}")
print(f"  Multibagger picks: {len(fm)}")
print(f"  Health score:      {response.get('portfolio_health_score', 'N/A')}/100")

# Save
os.makedirs("output", exist_ok=True)
output_path = "output/latest_analysis.json"
with open(output_path, "w") as f:
    json.dump(response, f, indent=2, ensure_ascii=False)
print(f"\n💾 Saved to {output_path}")
print(json.dumps(response, indent=2, ensure_ascii=False))
