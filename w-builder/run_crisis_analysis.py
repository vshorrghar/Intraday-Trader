#!/usr/bin/env python3
"""Crisis Portfolio Analysis Runner

Comprehensive analysis during market crash:
1. Real-time portfolio recommendations (BUY/SELL/HOLD/AVERAGE)
2. Crisis opportunity scanner (quality stocks on sale)
3. Enhanced intraday picks with smart money flows
4. Market intelligence with institutional activity

Usage:
    python3 run_crisis_analysis.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import yaml

from fetchers.amfi_nav_fetcher import fetch_nav_data
from fetchers.market_indices import fetch_indices
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_bulk_deals import fetch_bulk_deals
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.screener_fetcher import fetch_fundamentals_batch
from llm.bedrock_client import BedrockClient
from llm.crisis_opportunity_analyzer import analyze_crisis_opportunities
from llm.enhanced_intraday_engine import generate_enhanced_intraday_setups
from llm.realtime_portfolio_analyzer import analyze_realtime_portfolio
from parsers.groww_pnl_parser import parse_pnl_xlsx
from parsers.groww_stocks_parser import parse_stocks_xlsx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crisis_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Run comprehensive crisis analysis."""
    logger.info("=" * 80)
    logger.info("CRISIS PORTFOLIO ANALYSIS - Iran-USA War Market Impact")
    logger.info("=" * 80)

    # Paths
    input_dir = Path("input")
    cache_dir = Path("cache")
    output_dir = Path("output/crisis_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find latest files
    stocks_file = _find_latest_file(input_dir, "Stocks_Holdings_Statement*.xlsx")
    pnl_file = _find_latest_file(input_dir, "Stocks_PnL_Report*.xlsx")

    if not stocks_file:
        logger.error("No Stocks Holdings file found in input/")
        return 1

    logger.info("📂 Using files:")
    logger.info(f"  - Holdings: {stocks_file.name}")
    if pnl_file:
        logger.info(f"  - P&L: {pnl_file.name}")

    # Load config
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Initialize Bedrock client
    try:
        bedrock_region = config["aws"].get("bedrock_region", config["aws"]["region"])
        model_id = config["aws"]["bedrock_model_id"]
        client = BedrockClient(region=bedrock_region, model_id=model_id)
        logger.info("✅ Bedrock client initialized (region: %s, model: %s)", bedrock_region, model_id)
    except Exception as e:
        logger.error("Failed to initialize Bedrock: %s", e)
        return 1

    # Parse portfolio
    logger.info("\n📊 Parsing portfolio...")
    try:
        holdings = parse_stocks_xlsx(str(stocks_file))
        logger.info(f"  ✅ Parsed {len(holdings)} stock holdings")
    except Exception as e:
        logger.error("Failed to parse holdings: %s", e)
        return 1

    # Parse P&L if available
    pnl_data = []
    if pnl_file:
        try:
            _, pnl_data = parse_pnl_xlsx(str(pnl_file))
            logger.info(f"  ✅ Parsed P&L data for {len(pnl_data)} scrips")
        except Exception as e:
            logger.warning("Failed to parse P&L: %s", e)

    # Fetch live market data
    logger.info("\n🌐 Fetching live market data...")

    logger.info("  📈 NSE Bhavcopy...")
    bhavcopy = fetch_bhavcopy(str(cache_dir))
    logger.info(f"    ✅ {len(bhavcopy)} stocks")

    logger.info("  💰 FII/DII Flows...")
    fii_dii = fetch_fii_dii(str(cache_dir))
    logger.info(f"    ✅ FII Net: ₹{fii_dii.fii_net/10000000:.2f}Cr, DII Net: ₹{fii_dii.dii_net/10000000:.2f}Cr")

    logger.info("  📊 Market Indices...")
    indices = fetch_indices(str(cache_dir))
    logger.info(f"    ✅ {len(indices)} indices fetched")

    logger.info("  🏢 Bulk/Block Deals...")
    deals = fetch_bulk_deals()
    logger.info(f"    ✅ {len(deals)} deals")

    logger.info("  📉 Stock Fundamentals...")
    symbols = list(set([h.nse_symbol for h in holdings if h.nse_symbol] +
                      [h.name for h in holdings]))[:50]  # Limit to avoid rate limits
    fundamentals = fetch_fundamentals_batch(symbols, str(cache_dir))
    logger.info(f"    ✅ {len(fundamentals)} stocks with fundamental data")

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

    # Run analyses
    logger.info("\n" + "=" * 80)
    logger.info("🤖 AI ANALYSIS - Crisis Mode")
    logger.info("=" * 80)

    # 1. Real-time Portfolio Analysis
    logger.info("\n1️⃣ PORTFOLIO ANALYSIS - BUY/SELL/HOLD/AVERAGE Recommendations")
    try:
        portfolio_actions = analyze_realtime_portfolio(
            holdings=holdings,
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            fii_dii=fii_dii,
            pnl_data=pnl_data,
            indices_change=indices_change,
            client=client,
        )
        logger.info(f"  ✅ {len(portfolio_actions)} portfolio recommendations generated")

        # Print summary
        high_priority = [a for a in portfolio_actions if a.priority == "HIGH"]
        buy_more = [a for a in portfolio_actions if a.action in ["BUY_MORE", "AVERAGE_DOWN"]]
        exits = [a for a in portfolio_actions if a.action in ["EXIT", "BOOK_PARTIAL"]]

        logger.info(f"\n  📌 HIGH Priority Actions: {len(high_priority)}")
        logger.info(f"  🟢 Buy/Average Opportunities: {len(buy_more)}")
        logger.info(f"  🔴 Exit/Book Signals: {len(exits)}")

    except Exception as e:
        logger.error("Portfolio analysis failed: %s", e, exc_info=True)
        portfolio_actions = []

    # 2. Crisis Opportunity Scanner
    logger.info("\n2️⃣ CRISIS OPPORTUNITY SCANNER - Quality Stocks on Sale")
    try:
        crisis_opps = analyze_crisis_opportunities(
            bhavcopy=bhavcopy,
            deals=deals,
            fii_dii=fii_dii,
            fundamentals=fundamentals,
            indices_change=indices_change,
            client=client,
        )
        logger.info(f"  ✅ {len(crisis_opps)} crisis opportunities identified")

        # Categorize
        buy_now = [o for o in crisis_opps if o.action == "BUY_NOW"]
        high_reward = [o for o in crisis_opps if o.risk_reward == "high"]

        logger.info(f"\n  🔥 BUY NOW Signals: {len(buy_now)}")
        logger.info(f"  ⭐ High Risk-Reward: {len(high_reward)}")

    except Exception as e:
        logger.error("Crisis opportunity scan failed: %s", e, exc_info=True)
        crisis_opps = []

    # 3. Enhanced Intraday Picks
    logger.info("\n3️⃣ ENHANCED INTRADAY PICKS - Smart Money Analysis")
    try:
        intraday_setups = generate_enhanced_intraday_setups(
            bhavcopy=bhavcopy,
            deals=deals,
            fii_dii=fii_dii,
            fundamentals=fundamentals,
            indices=indices_change,
            client=client,
        )
        logger.info(f"  ✅ {len(intraday_setups)} intraday setups generated")

    except Exception as e:
        logger.error("Intraday analysis failed: %s", e, exc_info=True)
        intraday_setups = []

    # Save results
    logger.info("\n" + "=" * 80)
    logger.info("💾 SAVING RESULTS")
    logger.info("=" * 80)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save detailed JSON
    results = {
        "timestamp": timestamp,
        "market_context": {
            "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
            "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
            "indices_change": indices_change,
        },
        "portfolio_actions": [vars(a) for a in portfolio_actions],
        "crisis_opportunities": [vars(o) for o in crisis_opps],
        "intraday_setups": [vars(s) for s in intraday_setups],
    }

    json_file = output_dir / f"crisis_analysis_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"  ✅ JSON: {json_file}")

    # Generate human-readable report
    report_file = output_dir / f"crisis_report_{timestamp}.txt"
    _generate_text_report(report_file, portfolio_actions, crisis_opps, intraday_setups, fii_dii, indices_change)
    logger.info(f"  ✅ Report: {report_file}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("✨ ANALYSIS COMPLETE")
    logger.info("=" * 80)
    logger.info(f"\n📄 View full report: {report_file}")
    logger.info(f"📊 JSON data: {json_file}\n")

    return 0


def _find_latest_file(directory: Path, pattern: str) -> Path | None:
    """Find the most recent file matching pattern."""
    import glob
    files = glob.glob(str(directory / pattern))
    if not files:
        return None
    return Path(max(files, key=os.path.getmtime))


def _generate_text_report(
    output_path: Path,
    portfolio_actions,
    crisis_opps,
    intraday_setups,
    fii_dii,
    indices_change
):
    """Generate human-readable text report."""
    with open(output_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("CRISIS PORTFOLIO ANALYSIS REPORT\n")
        f.write("Iran-USA War Market Impact\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        # Market Context
        f.write("📊 MARKET CONTEXT\n")
        f.write("-" * 80 + "\n")
        f.write(f"FII Net Flow: ₹{fii_dii.fii_net/10000000:.2f} Cr\n")
        f.write(f"DII Net Flow: ₹{fii_dii.dii_net/10000000:.2f} Cr\n")
        f.write(f"\nIndex Changes:\n")
        for idx, change in indices_change.items():
            f.write(f"  {idx}: {change:+.2f}%\n")
        f.write("\n\n")

        # Portfolio Actions
        f.write("=" * 80 + "\n")
        f.write("1️⃣ YOUR PORTFOLIO - ACTION RECOMMENDATIONS\n")
        f.write("=" * 80 + "\n\n")

        if portfolio_actions:
            for i, action in enumerate(portfolio_actions, 1):
                f.write(f"{i}. {action.name}\n")
                f.write(f"   Action: {action.action} [{action.priority} Priority]\n")
                f.write(f"   Current: ₹{action.current_price:.2f} | Avg Cost: ₹{action.avg_cost:.2f}\n")
                f.write(f"   P&L: {action.current_pnl_pct:+.2f}%\n")
                f.write(f"   Target: ₹{action.target_price:.2f} | Stop: ₹{action.stop_loss:.2f}\n")
                if action.quantity_suggestion > 0:
                    f.write(f"   Suggested Qty: {action.quantity_suggestion} shares\n")
                if action.crisis_opportunity:
                    f.write(f"   🔥 CRISIS OPPORTUNITY\n")
                f.write(f"   Rationale: {action.rationale}\n\n")
        else:
            f.write("No portfolio actions generated.\n\n")

        # Crisis Opportunities
        f.write("=" * 80 + "\n")
        f.write("2️⃣ CRISIS OPPORTUNITIES - Quality Stocks on Sale\n")
        f.write("=" * 80 + "\n\n")

        if crisis_opps:
            for i, opp in enumerate(crisis_opps, 1):
                f.write(f"{i}. {opp.stock_name} ({opp.symbol})\n")
                f.write(f"   Category: {opp.crisis_category}\n")
                f.write(f"   Action: {opp.action} [Risk-Reward: {opp.risk_reward.upper()}]\n")
                f.write(f"   Current: ₹{opp.current_price:.2f} | Fair Value: ₹{opp.estimated_value:.2f}\n")
                f.write(f"   Upside Potential: {opp.upside_potential_pct:.1f}%\n")
                f.write(f"   Rationale: {opp.rationale}\n\n")
        else:
            f.write("No crisis opportunities found.\n\n")

        # Intraday Picks
        f.write("=" * 80 + "\n")
        f.write("3️⃣ TODAY'S INTRADAY PICKS - Smart Money Analysis\n")
        f.write("=" * 80 + "\n\n")

        if intraday_setups:
            for i, setup in enumerate(intraday_setups, 1):
                f.write(f"{i}. {setup.stock_name}\n")
                f.write(f"   Entry: ₹{setup.entry_price:.2f}\n")
                f.write(f"   Target: ₹{setup.target_price:.2f} | Stop: ₹{setup.stop_loss:.2f}\n")
                risk = setup.entry_price - setup.stop_loss
                reward = setup.target_price - setup.entry_price
                rr_ratio = reward / risk if risk > 0 else 0
                f.write(f"   Risk-Reward: 1:{rr_ratio:.2f}\n")
                f.write(f"   Rationale: {setup.rationale}\n\n")
        else:
            f.write("No intraday setups generated.\n\n")

        f.write("=" * 80 + "\n")
        f.write("END OF REPORT\n")
        f.write("=" * 80 + "\n")


if __name__ == "__main__":
    sys.exit(main())
