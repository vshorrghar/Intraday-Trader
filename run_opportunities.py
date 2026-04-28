#!/usr/bin/env python3
"""🔥 Crash Opportunity Scanner — finds stocks & ETFs to buy NOW.

Fetches real-time NSE data (gainers, losers, most active, sectors, FII/DII),
sends to Bedrock Claude with a 30-year analyst prompt, and outputs
detailed picks with explanations across all market caps and sectors.

Usage: python3 run_opportunities.py
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

from config.config_loader import load_config
from parsers.groww_stocks_parser import parse_stocks_xlsx
from fetchers.nse_market_movers import fetch_all_market_data
from fetchers.nse_fii_dii import fetch_fii_dii
from llm.bedrock_client import BedrockClient
from llm.opportunity_analyzer import analyze_opportunities

IST = timezone(timedelta(hours=5, minutes=30))


def main():
    config = load_config("config/config.yaml")

    print("\n🔥 CRASH OPPORTUNITY SCANNER")
    print("=" * 70)
    print(f"  {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")

    # Get existing holdings to exclude from recommendations
    print("\n📊 Loading your portfolio...")
    try:
        holdings = parse_stocks_xlsx(config.stocks_xlsx)
        existing = list(set(h.name for h in holdings))
        print(f"  {len(holdings)} holdings loaded (will exclude from new picks)")
    except Exception:
        existing = []
        print("  Could not load holdings — will recommend without exclusions")

    # Fetch real-time market data
    print("\n📡 Fetching live NSE data...")
    market_data = fetch_all_market_data(config.cache_dir)
    g = len(market_data.get("gainers", []))
    l = len(market_data.get("losers", []))
    s = len(market_data.get("sectors", []))
    a = len(market_data.get("most_active", []))
    print(f"  Gainers: {g} | Losers: {l} | Most Active: {a} | Sectors: {s}")

    # Show sector snapshot
    sectors = market_data.get("sectors", [])
    if sectors:
        print("\n📊 Sector Snapshot:")
        for sec in sectors[:15]:
            emoji = "🟢" if sec.get("change_pct", 0) > 0 else "🔴"
            print(f"  {emoji} {sec['name']:30s} {sec.get('change_pct',0):+6.2f}%")

    # Fetch FII/DII
    fii_dii = None
    try:
        from fetchers.models import FIIDIIFlow
        fii_obj = fetch_fii_dii(config.cache_dir)
        if fii_obj:
            fii_dii = {"fii_buy": fii_obj.fii_buy, "fii_sell": fii_obj.fii_sell,
                       "fii_net": fii_obj.fii_net, "dii_buy": fii_obj.dii_buy,
                       "dii_sell": fii_obj.dii_sell, "dii_net": fii_obj.dii_net}
            print(f"\n💰 FII/DII: FII Net ₹{fii_obj.fii_net:+,.0f}Cr | DII Net ₹{fii_obj.dii_net:+,.0f}Cr")
    except Exception as e:
        print(f"\n  FII/DII fetch failed: {e}")

    # Run AI analysis
    print("\n🤖 Sending to Bedrock Claude for expert analysis...")
    print("  (This takes 30-60 seconds — analyzing across all caps & sectors)")
    try:
        client = BedrockClient(config.bedrock_region, config.bedrock_model_id)
        result = analyze_opportunities(market_data, fii_dii, existing, client)
    except Exception as e:
        print(f"\n  ❌ Bedrock failed: {e}")
        print("  Make sure AWS creds are active.")
        return

    if not result:
        print("\n  ❌ No results from Claude.")
        return

    # Display results
    print(f"\n{'='*70}")
    print("  🤖 EXPERT ANALYSIS RESULTS")
    print(f"{'='*70}")

    regime = result.get("market_regime", "unknown")
    print(f"\n  Market Regime: {regime.upper()}")
    if result.get("vix_assessment"):
        print(f"  VIX Assessment: {result['vix_assessment']}")
    if result.get("sector_rotation"):
        print(f"  Sector Rotation: {result['sector_rotation']}")

    # Stock picks
    picks = result.get("stock_picks", [])
    if picks:
        print(f"\n{'─'*70}")
        print(f"  📈 STOCK PICKS ({len(picks)} recommendations)")
        print(f"{'─'*70}")
        for i, p in enumerate(picks, 1):
            action_emoji = {"strong_buy": "🟢🟢", "buy": "🟢", "accumulate": "🔵", "watch": "👀"}.get(p.get("action",""), "•")
            conv = p.get("conviction", "medium")
            conv_emoji = {"high": "⭐⭐⭐", "medium": "⭐⭐", "low": "⭐"}.get(conv, "")
            sym = p.get("symbol", "")
            # Check if already in portfolio
            in_portfolio = any(sym.upper() in h.upper() for h in existing) if existing else False
            portfolio_tag = " 📌 ALREADY IN YOUR PORTFOLIO" if in_portfolio else ""
            print(f"\n  {i}. {action_emoji} {p.get('name', sym)} ({sym}){portfolio_tag}")
            print(f"     Sector: {p.get('sector','')} | Score: {p.get('score',0)}/100 | Conviction: {conv} {conv_emoji}")
            print(f"     CMP: ₹{p.get('current_price',0):,.1f} → Target: ₹{p.get('target_price',0):,.1f} | SL: ₹{p.get('stop_loss',0):,.1f}")
            print(f"     Horizon: {p.get('time_horizon','')}")
            print(f"     📝 {p.get('rationale','')}")
            if p.get("risk_factors"):
                print(f"     ⚠️  Risks: {p['risk_factors']}")

    # ETF picks
    etfs = result.get("etf_picks", [])
    if etfs:
        print(f"\n{'─'*70}")
        print(f"  📊 ETF PICKS ({len(etfs)} recommendations)")
        print(f"{'─'*70}")
        for i, e in enumerate(etfs, 1):
            print(f"\n  {i}. 🟢 {e.get('name', e.get('symbol',''))} ({e.get('symbol','')})")
            print(f"     Score: {e.get('score',0)}/100 | Action: {e.get('action','buy').upper()}")
            print(f"     CMP: ₹{e.get('current_price',0):,.1f} → Target: ₹{e.get('target_price',0):,.1f}")
            print(f"     📝 {e.get('rationale','')}")

    # Avoid list
    avoid = result.get("avoid_list", [])
    if avoid:
        print(f"\n{'─'*70}")
        print(f"  🚫 AVOID LIST")
        print(f"{'─'*70}")
        for item in avoid:
            print(f"  ❌ {item}")

    # Allocation advice
    alloc = result.get("portfolio_allocation_advice", "")
    if alloc:
        print(f"\n{'─'*70}")
        print(f"  💰 ALLOCATION ADVICE (for ₹5 lakh fresh capital)")
        print(f"{'─'*70}")
        print(f"  {alloc}")

    # Save to file
    out_path = "output/reports/opportunities.json"
    os.makedirs("output/reports", exist_ok=True)
    result["generated_at"] = datetime.now(IST).isoformat()
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  💾 Saved to {out_path}")

    print(f"\n{'='*70}")
    print("  ✅ Scan complete!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
