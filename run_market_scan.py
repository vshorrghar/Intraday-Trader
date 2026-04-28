#!/usr/bin/env python3
"""Market Crash Opportunity Scanner.

Runs Screener.in fundamental queries to find quality stocks trading
at a discount, then uses Bedrock Claude to analyze your portfolio
and suggest dip-buying opportunities.

Usage: python run_market_scan.py
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta

from config.config_loader import load_config
from parsers.groww_stocks_parser import parse_stocks_xlsx
from parsers.groww_mf_parser import parse_mf_xlsx
from fetchers.screener_query import run_all_screens, format_screen_results, QUERIES
from llm.bedrock_client import BedrockClient

IST = timezone(timedelta(hours=5, minutes=30))


def main():
    config_path = os.environ.get("WBP_CONFIG", "config/config.yaml")
    config = load_config(config_path)

    print("\n🔍 Market Crash Opportunity Scanner")
    print("=" * 60)
    print(f"  Date: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")

    # Parse current portfolio
    print("\n📊 Parsing your portfolio...")
    holdings = parse_stocks_xlsx(config.stocks_xlsx)
    mf_holdings = parse_mf_xlsx(config.mf_xlsx)

    total_invested = sum(h.buy_value for h in holdings)
    total_current = sum(h.groww_closing_value for h in holdings)
    total_pnl = total_current - total_invested
    pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    stocks = [h for h in holdings if h.holding_type == "stock"]
    etfs = [h for h in holdings if h.holding_type == "etf"]
    invits = [h for h in holdings if h.holding_type == "invit"]

    print(f"  Stocks: {len(stocks)} | ETFs: {len(etfs)} | InvITs: {len(invits)}")
    print(f"  Invested: ₹{total_invested:,.0f}")
    print(f"  Current:  ₹{total_current:,.0f}")
    print(f"  P&L:      ₹{total_pnl:,.0f} ({pnl_pct:+.1f}%)")
    print(f"  MF Schemes: {len(mf_holdings)}")

    # Stocks in loss (potential tax harvesting / averaging down)
    losers = sorted(
        [h for h in holdings if h.unrealised_pnl < 0],
        key=lambda h: h.unrealised_pnl,
    )
    if losers:
        print(f"\n  📉 Holdings in loss ({len(losers)}):")
        for h in losers[:10]:
            pct = (h.unrealised_pnl / h.buy_value * 100) if h.buy_value > 0 else 0
            print(f"    {h.name}: ₹{h.unrealised_pnl:,.0f} ({pct:+.1f}%)")

    # Run Screener queries
    print("\n🔎 Running Screener.in fundamental queries...")
    screen_results = run_all_screens()
    report = format_screen_results(screen_results)
    print(report)

    # Count total opportunities
    total_picks = sum(len(r) for r in screen_results.values())
    if total_picks == 0:
        print("\n⚠️  Screener queries returned 0 results.")
        print("  This may be because Screener.in requires login for query API.")
        print("  Falling back to Bedrock Claude for analysis...")

    # Use Bedrock Claude for AI analysis
    print("\n🤖 Running Bedrock Claude analysis...")
    try:
        client = BedrockClient(config.bedrock_region, config.bedrock_model_id)

        # Send only top 30 losers + top 20 winners + summary (not full 252 stocks)
        sorted_by_pnl = sorted(holdings, key=lambda h: h.unrealised_pnl)
        top_losers = sorted_by_pnl[:30]
        top_winners = sorted(holdings, key=lambda h: h.unrealised_pnl, reverse=True)[:20]
        selected = top_losers + top_winners

        portfolio_data = []
        for h in selected:
            pct = (h.unrealised_pnl / h.buy_value * 100) if h.buy_value > 0 else 0
            portfolio_data.append({
                "name": h.name,
                "type": h.holding_type,
                "qty": h.quantity,
                "avg_buy": round(h.avg_buy_price, 2),
                "current": round(h.groww_closing_price, 2),
                "pnl": round(h.unrealised_pnl, 2),
                "pnl_pct": round(pct, 1),
            })

        # Only top 10 MFs by value
        top_mfs = sorted(mf_holdings, key=lambda m: m.invested_value, reverse=True)[:10]
        mf_data = []
        for m in top_mfs:
            mf_data.append({
                "scheme": m.scheme_name,
                "category": m.category,
                "invested": round(m.invested_value, 2),
                "current": round(m.current_value, 2),
                "xirr": round(m.xirr, 1),
            })

        # Build screener results context
        screener_context = ""
        for qtype, results in screen_results.items():
            if results:
                screener_context += f"\n{qtype}: {len(results)} stocks found\n"
                for r in results[:15]:
                    screener_context += f"  - {r.name} ({r.symbol}): Price={r.current_price}, MCap={r.market_cap}, PE={r.pe_ratio}, ROCE={r.roce}\n"

        system_prompt = """You are an expert Indian stock market analyst. The market has crashed significantly.
Analyze the investor's portfolio and the screener results to provide actionable advice.

Your response MUST be valid JSON with this structure:
{
  "market_assessment": "Brief assessment of current market conditions",
  "portfolio_actions": [
    {"stock": "NAME", "action": "buy_more/hold/exit/tax_harvest", "reason": "..."}
  ],
  "new_opportunities": [
    {"stock": "NAME", "type": "stock/etf", "reason": "...", "suggested_allocation": "..."}
  ],
  "etf_recommendations": [
    {"etf": "NAME", "reason": "...", "sip_or_lumpsum": "..."}
  ],
  "risk_warnings": ["..."]
}

Focus on:
1. Which existing holdings to average down on (buy more at lower prices)
2. Tax loss harvesting opportunities (sell losers, buy similar stocks)
3. New quality stocks from screener results that are available at crash prices
4. ETF recommendations for diversified crash-buying (Nifty 50, Nifty Next 50, Midcap 150)
5. Risk management - don't put all money in at once, suggest staggered buying"""

        user_prompt = f"""PORTFOLIO SUMMARY:
Total holdings: {len(holdings)} stocks, {len(etfs)} ETFs, {len(invits)} InvITs
Total invested: ₹{total_invested:,.0f} | Current: ₹{total_current:,.0f} | P&L: ₹{total_pnl:,.0f} ({pnl_pct:+.1f}%)
Holdings in loss: {len(losers)} out of {len(holdings)}

TOP 30 LOSERS (best candidates for averaging down or tax harvesting):
{json.dumps(portfolio_data[:30], indent=1)}

TOP 20 WINNERS (strong holdings):
{json.dumps(portfolio_data[30:], indent=1)}

TOP 10 MUTUAL FUNDS:
{json.dumps(mf_data, indent=1)}

{screener_context if screener_context else "Screener data unavailable — provide general crash-buying advice for Indian market."}

Provide crash-buying analysis: which losers to average down, tax harvesting opportunities, new stocks/ETFs to buy in this dip, and risk warnings."""

        print("  Sending to Bedrock Claude...")
        response = client.invoke(system_prompt, user_prompt)

        # Display results
        print(f"\n{'='*60}")
        print("  🤖 AI CRASH-BUYING ANALYSIS")
        print(f"{'='*60}")

        if isinstance(response, dict):
            # Market assessment
            assessment = response.get("market_assessment", "")
            if assessment:
                print(f"\n  📊 Market Assessment:")
                print(f"  {assessment}")

            # Portfolio actions
            actions = response.get("portfolio_actions", [])
            if actions:
                print(f"\n  📋 Portfolio Actions ({len(actions)}):")
                for a in actions:
                    emoji = {"buy_more": "🟢", "hold": "🟡", "exit": "🔴", "tax_harvest": "💰"}.get(a.get("action", ""), "•")
                    print(f"  {emoji} {a.get('stock', 'N/A')} → {a.get('action', 'N/A').upper()}")
                    print(f"     {a.get('reason', '')}")

            # New opportunities
            opps = response.get("new_opportunities", [])
            if opps:
                print(f"\n  🚀 New Crash Opportunities ({len(opps)}):")
                for o in opps:
                    print(f"  • {o.get('stock', 'N/A')} ({o.get('type', 'stock')})")
                    print(f"    {o.get('reason', '')}")
                    if o.get("suggested_allocation"):
                        print(f"    Allocation: {o['suggested_allocation']}")

            # ETF recommendations
            etfs_rec = response.get("etf_recommendations", [])
            if etfs_rec:
                print(f"\n  📈 ETF Recommendations ({len(etfs_rec)}):")
                for e in etfs_rec:
                    mode = e.get("sip_or_lumpsum", "SIP")
                    print(f"  • {e.get('etf', 'N/A')} [{mode}]")
                    print(f"    {e.get('reason', '')}")

            # Risk warnings
            warnings = response.get("risk_warnings", [])
            if warnings:
                print(f"\n  ⚠️  Risk Warnings:")
                for w in warnings:
                    print(f"  • {w}")
        else:
            print(f"  Raw response: {response}")

    except Exception as exc:
        print(f"\n  ❌ Bedrock analysis failed: {exc}")
        print("  Make sure AWS credentials are set and Bedrock access is enabled in ap-south-1")

    print(f"\n{'='*60}")
    print("  ✅ Scan complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
