#!/usr/bin/env python3
"""Morning Portfolio Analysis - Runs at 9:00 AM IST daily.

Comprehensive morning intelligence report:
1. AWS Cost Check (keep bills in check)
2. 10 Intraday Picks (smart money analysis)
3. Multibagger Opportunities (hidden gems, NO top 50)
4. Brutal Portfolio Assessment (honest truth about your holdings)
5. Crisis Opportunities (if market crashing)

Usage:
    python3 run_morning_analysis.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml

from aws_cost_monitor import AWSCostMonitor
from fetchers.market_indices import fetch_indices
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_bulk_deals import fetch_bulk_deals
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.screener_fetcher import fetch_fundamentals_batch
from llm.bedrock_client import BedrockClient
from llm.brutal_portfolio_analyzer import analyze_portfolio_brutally
from llm.crisis_opportunity_analyzer import analyze_crisis_opportunities
from llm.enhanced_intraday_engine import generate_enhanced_intraday_setups
from llm.multibagger_scanner import scan_multibaggers
from llm.realtime_portfolio_analyzer import analyze_realtime_portfolio
from parsers.groww_pnl_parser import parse_pnl_xlsx
from parsers.groww_stocks_parser import parse_stocks_xlsx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('morning_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Run comprehensive morning analysis."""
    logger.info("=" * 80)
    logger.info("MORNING PORTFOLIO INTELLIGENCE - %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"))
    logger.info("=" * 80)

    # Paths
    input_dir = Path("input")
    cache_dir = Path("cache")
    output_dir = Path("output/morning_reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Find latest portfolio files
    stocks_file = _find_latest_file(input_dir, "Stocks_Holdings_Statement*.xlsx")
    pnl_file = _find_latest_file(input_dir, "Stocks_PnL_Report*.xlsx")

    if not stocks_file:
        logger.error("No Stocks Holdings file found in input/")
        return 1

    logger.info("📂 Portfolio files:")
    logger.info("  - Holdings: %s", stocks_file.name)
    if pnl_file:
        logger.info("  - P&L: %s", pnl_file.name)

    # Initialize Bedrock client
    try:
        bedrock_region = config["aws"].get("bedrock_region", config["aws"]["region"])
        model_id = config["aws"]["bedrock_model_id"]
        client = BedrockClient(region=bedrock_region, model_id=model_id)
        logger.info("✅ Bedrock client initialized")
    except Exception as e:
        logger.error("Failed to initialize Bedrock: %s", e)
        return 1

    # === 1. AWS COST CHECK ===
    logger.info("\n" + "=" * 80)
    logger.info("1️⃣ AWS COST CHECK")
    logger.info("=" * 80)

    try:
        cost_monitor = AWSCostMonitor(region=config["aws"]["region"])
        mtd_cost = cost_monitor.get_month_to_date_cost()
        forecast = cost_monitor.get_forecast_month_end()
        service_costs = cost_monitor.get_costs_by_service(days=7)  # Last week

        logger.info("  Month-to-Date: $%.2f", mtd_cost)
        logger.info("  Forecast Month-End: $%.2f", forecast)

        top_service = max(service_costs, key=service_costs.get) if service_costs else "Unknown"
        top_cost = service_costs.get(top_service, 0)
        logger.info("  Top Service: %s ($%.2f)", top_service, top_cost)

    except Exception as e:
        logger.warning("Cost monitoring unavailable: %s", e)
        mtd_cost = forecast = 0.0
        service_costs = {}

    # Parse portfolio
    logger.info("\n📊 Parsing portfolio...")
    try:
        holdings = parse_stocks_xlsx(str(stocks_file))
        logger.info("  ✅ %d stock holdings", len(holdings))
    except Exception as e:
        logger.error("Failed to parse holdings: %s", e)
        return 1

    pnl_data = []
    if pnl_file:
        try:
            _, pnl_data = parse_pnl_xlsx(str(pnl_file))
            logger.info("  ✅ P&L data for %d scrips", len(pnl_data))
        except Exception as e:
            logger.warning("Failed to parse P&L: %s", e)

    # Fetch market data
    logger.info("\n🌐 Fetching live market data...")

    logger.info("  📈 NSE Bhavcopy...")
    bhavcopy = fetch_bhavcopy(str(cache_dir))
    logger.info("    ✅ %d stocks", len(bhavcopy))

    logger.info("  💰 FII/DII Flows...")
    fii_dii = fetch_fii_dii(str(cache_dir))
    logger.info("    ✅ FII: ₹%.2fCr, DII: ₹%.2fCr", fii_dii.fii_net/10000000, fii_dii.dii_net/10000000)

    logger.info("  📊 Market Indices...")
    indices = fetch_indices(str(cache_dir))
    logger.info("    ✅ %d indices", len(indices))

    logger.info("  🏢 Bulk/Block Deals...")
    deals = fetch_bulk_deals()
    logger.info("    ✅ %d deals", len(deals))

    logger.info("  📉 Stock Fundamentals...")
    symbols = list(set([h.nse_symbol for h in holdings if h.nse_symbol] +
                      [h.name for h in holdings]))[:100]  # Top 100 to avoid rate limits
    fundamentals = fetch_fundamentals_batch(symbols, str(cache_dir))
    logger.info("    ✅ %d stocks", len(fundamentals))

    # Calculate index changes
    indices_change = {}
    if isinstance(indices, list):
        # fetch_indices returns a list of IndexData objects
        for index_data in indices:
            indices_change[index_data.name] = index_data.change_percent
    elif isinstance(indices, dict):
        # Legacy format support
        for name, data in indices.items():
            if isinstance(data, dict) and "change_pct" in data:
                indices_change[name] = data["change_pct"]
            else:
                indices_change[name] = 0.0

    # Determine if market is crashing
    is_crisis = any(v < -2 for v in indices_change.values())

    # === 2. 10 INTRADAY PICKS ===
    logger.info("\n" + "=" * 80)
    logger.info("2️⃣ TODAY'S 10 INTRADAY PICKS")
    logger.info("=" * 80)

    try:
        intraday_setups = generate_enhanced_intraday_setups(
            bhavcopy=bhavcopy,
            deals=deals,
            fii_dii=fii_dii,
            fundamentals=fundamentals,
            indices=indices_change,
            client=client,
        )
        logger.info("  ✅ %d intraday setups generated", len(intraday_setups))
    except Exception as e:
        logger.error("Intraday analysis failed: %s", e)
        intraday_setups = []

    # === 3. MULTIBAGGER OPPORTUNITIES ===
    logger.info("\n" + "=" * 80)
    logger.info("3️⃣ MULTIBAGGER OPPORTUNITIES (Hidden Gems)")
    logger.info("=" * 80)

    try:
        multibaggers = scan_multibaggers(
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            deals=deals,
            fii_dii=fii_dii,
            client=client,
        )
        logger.info("  ✅ %d multibagger candidates", len(multibaggers))
    except Exception as e:
        logger.error("Multibagger scan failed: %s", e)
        multibaggers = []

    # === 4. BRUTAL PORTFOLIO ASSESSMENT ===
    logger.info("\n" + "=" * 80)
    logger.info("4️⃣ BRUTAL PORTFOLIO ASSESSMENT")
    logger.info("=" * 80)

    try:
        brutal_assessments = analyze_portfolio_brutally(
            holdings=holdings,
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            client=client,
        )
        logger.info("  ✅ %d stocks assessed", len(brutal_assessments))

        # Count by verdict
        junk_count = len([a for a in brutal_assessments if a.verdict == "JUNK"])
        weak_count = len([a for a in brutal_assessments if a.verdict == "WEAK"])
        quality_count = len([a for a in brutal_assessments if a.verdict == "QUALITY"])

        logger.info(f"  🟢 Quality: {quality_count}")
        logger.info(f"  🟡 Weak: {weak_count}")
        logger.info(f"  🔴 Junk: {junk_count}")

    except Exception as e:
        logger.error("Brutal assessment failed: %s", e)
        brutal_assessments = []

    # === 5. CRISIS OPPORTUNITIES (if market crashing) ===
    crisis_opps = []
    if is_crisis:
        logger.info("\n" + "=" * 80)
        logger.info("5️⃣ CRISIS OPPORTUNITIES (Market Crash Detected)")
        logger.info("=" * 80)

        try:
            crisis_opps = analyze_crisis_opportunities(
                bhavcopy=bhavcopy,
                deals=deals,
                fii_dii=fii_dii,
                fundamentals=fundamentals,
                indices_change=indices_change,
                client=client,
            )
            logger.info("  ✅ %d crisis opportunities", len(crisis_opps))
        except Exception as e:
            logger.error("Crisis scan failed: %s", e)

    # Save results
    logger.info("\n" + "=" * 80)
    logger.info("💾 SAVING MORNING REPORT")
    logger.info("=" * 80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON data
    results = {
        "timestamp": timestamp,
        "aws_costs": {
            "month_to_date": mtd_cost,
            "forecast_month_end": forecast,
            "top_service": max(service_costs, key=service_costs.get) if service_costs else None,
            "top_service_cost": service_costs.get(max(service_costs, key=service_costs.get), 0) if service_costs else 0,
        },
        "market_context": {
            "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
            "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
            "indices_change": indices_change,
            "is_crisis": is_crisis,
        },
        "intraday_setups": [vars(s) for s in intraday_setups],
        "multibaggers": [vars(m) for m in multibaggers],
        "brutal_assessments": [vars(a) for a in brutal_assessments],
        "crisis_opportunities": [vars(o) for o in crisis_opps] if crisis_opps else [],
    }

    json_file = output_dir / f"morning_report_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("  ✅ JSON: %s", json_file)

    # Human-readable report
    report_file = output_dir / f"morning_report_{timestamp}.txt"
    _generate_morning_report(
        report_file, mtd_cost, forecast, service_costs, fii_dii, indices_change,
        intraday_setups, multibaggers, brutal_assessments, crisis_opps
    )
    logger.info("  ✅ Report: %s", report_file)

    logger.info("\n" + "=" * 80)
    logger.info("✨ MORNING ANALYSIS COMPLETE")
    logger.info("=" * 80)
    logger.info(f"\n📄 Read: {report_file}\n")

    return 0


def _find_latest_file(directory: Path, pattern: str):
    """Find most recent file matching pattern."""
    import glob
    files = glob.glob(str(directory / pattern))
    if not files:
        return None
    return Path(max(files, key=os.path.getmtime))


def _generate_morning_report(
    output_path, mtd_cost, forecast, service_costs, fii_dii, indices_change,
    intraday_setups, multibaggers, brutal_assessments, crisis_opps
):
    """Generate human-readable morning report."""
    with open(output_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("MORNING PORTFOLIO INTELLIGENCE REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n")
        f.write("=" * 80 + "\n\n")

        # AWS Costs
        f.write("💰 AWS COST CHECK\n")
        f.write("-" * 80 + "\n")
        f.write(f"Month-to-Date:       ${mtd_cost:.2f}\n")
        f.write(f"Forecast Month-End:  ${forecast:.2f}\n")
        if service_costs:
            top_svc = max(service_costs, key=service_costs.get)
            f.write(f"Top Service:         {top_svc} (${service_costs[top_svc]:.2f})\n")
        f.write("\n\n")

        # Market Context
        f.write("📊 MARKET CONTEXT\n")
        f.write("-" * 80 + "\n")
        f.write(f"FII Net: ₹{fii_dii.fii_net/10000000:.2f}Cr | DII Net: ₹{fii_dii.dii_net/10000000:.2f}Cr\n")
        for idx, chg in indices_change.items():
            f.write(f"{idx}: {chg:+.2f}%\n")
        f.write("\n\n")

        # Intraday Picks
        f.write("=" * 80 + "\n")
        f.write("🚀 TODAY'S 10 INTRADAY PICKS\n")
        f.write("=" * 80 + "\n\n")
        for i, setup in enumerate(intraday_setups, 1):
            f.write(f"{i}. {setup.stock_name}\n")
            f.write(f"   Entry: ₹{setup.entry_price:.2f} | Target: ₹{setup.target_price:.2f} | Stop: ₹{setup.stop_loss:.2f}\n")
            risk = setup.entry_price - setup.stop_loss
            reward = setup.target_price - setup.entry_price
            rr = reward / risk if risk > 0 else 0
            f.write(f"   Risk-Reward: 1:{rr:.2f}\n")
            f.write(f"   {setup.rationale}\n\n")

        # Multibaggers
        f.write("=" * 80 + "\n")
        f.write("💎 MULTIBAGGER OPPORTUNITIES (NO Nifty 50)\n")
        f.write("=" * 80 + "\n\n")
        for i, mb in enumerate(multibaggers[:10], 1):
            f.write(f"{i}. {mb.stock_name} ({mb.symbol}) - {mb.category.upper()}\n")
            f.write(f"   Score: {mb.multibagger_score}/10 | Market Cap: ₹{mb.market_cap_cr:.0f}Cr\n")
            f.write(f"   Current: ₹{mb.current_price:.2f} → 3Y Target: ₹{mb.estimated_target_3yr:.2f} (+{mb.upside_potential_pct:.1f}%)\n")
            f.write(f"   Growth Drivers: {', '.join(mb.growth_drivers)}\n")
            f.write(f"   {mb.rationale}\n\n")

        # Brutal Assessment
        f.write("=" * 80 + "\n")
        f.write("🔥 BRUTAL PORTFOLIO ASSESSMENT\n")
        f.write("=" * 80 + "\n\n")

        # Show junk/weak first
        for assessment in brutal_assessments:
            if assessment.verdict in ["JUNK", "WEAK"]:
                f.write(f"❌ {assessment.name} - {assessment.verdict} (Score: {assessment.quality_score}/10)\n")
                f.write(f"   Position: ₹{assessment.position_value:,.0f} @ ₹{assessment.current_price:.2f}\n")
                if assessment.is_penny_position:
                    f.write(f"   💸 PENNY POSITION (< ₹5K)\n")
                f.write(f"   Action: {assessment.action_recommendation}\n")
                f.write(f"   Red Flags: {', '.join(assessment.red_flags)}\n")
                f.write(f"   Truth: {assessment.brutal_truth}\n\n")

        # Crisis Opportunities
        if crisis_opps:
            f.write("=" * 80 + "\n")
            f.write("🚨 CRISIS OPPORTUNITIES (Market Crash)\n")
            f.write("=" * 80 + "\n\n")
            for i, opp in enumerate(crisis_opps, 1):
                f.write(f"{i}. {opp.stock_name} ({opp.symbol})\n")
                f.write(f"   Category: {opp.crisis_category}\n")
                f.write(f"   Current: ₹{opp.current_price:.2f} → Value: ₹{opp.estimated_value:.2f} (+{opp.upside_potential_pct:.1f}%)\n")
                f.write(f"   Action: {opp.action} | Risk-Reward: {opp.risk_reward.upper()}\n")
                f.write(f"   {opp.rationale}\n\n")

        f.write("=" * 80 + "\n")
        f.write("END OF MORNING REPORT\n")
        f.write("=" * 80 + "\n")


if __name__ == "__main__":
    sys.exit(main())
