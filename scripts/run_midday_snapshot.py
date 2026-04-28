#!/usr/bin/env python3
"""Midday Snapshot Pipeline — Triggered at 12:30 PM IST (7:00 UTC).

Orchestrates: fetch data → AI market scan, intraday setups → build HTML →
send email → archive → update dashboard → store to DB.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config_loader import load_config
from config.logging_config import setup_logging
from parsers.groww_stocks_parser import parse_stocks_xlsx
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_bulk_deals import fetch_bulk_deals
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.screener_fetcher import fetch_fundamentals
from fetchers.market_indices import fetch_indices
from llm.bedrock_client import BedrockClient
from llm.market_scanner import scan_opportunities
from llm.intraday_engine import generate_intraday_setups
from reports.html_builder import build_midday_snapshot
from reports.ses_sender import send_email
from reports.s3_uploader import upload_report
from reports.dashboard_builder import build_dashboard
from database.db_manager import DBManager

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def main() -> None:
    config_path = os.environ.get("WBP_CONFIG", "config/config.yaml")
    config = load_config(config_path)
    setup_logging(log_dir=os.path.dirname(config.db_path).replace("data", "logs"))

    logger.info("=== Midday Snapshot Pipeline Started ===")
    try:
        holdings = parse_stocks_xlsx(config.stocks_xlsx)
        bhavcopy = fetch_bhavcopy(config.cache_dir)
        deals = fetch_bulk_deals()
        fii_dii = fetch_fii_dii(config.cache_dir)
        indices = fetch_indices(config.cache_dir)

        # Fetch fundamentals for portfolio stocks
        fundamentals = {}
        for h in holdings:
            if h.nse_symbol:
                try:
                    fundamentals[h.nse_symbol] = fetch_fundamentals(h.nse_symbol)
                except Exception:
                    logger.warning("Failed to fetch fundamentals for %s", h.nse_symbol)

        # AI analysis
        client = BedrockClient(config.bedrock_region, config.bedrock_model_id)
        opportunities = scan_opportunities(deals, fii_dii, fundamentals, client)
        market_data = {"indices": indices, "bhavcopy": bhavcopy, "deals": deals}
        intraday_setups = generate_intraday_setups(market_data, client)

        # Portfolio summary
        total_invested = sum(h.buy_value for h in holdings)
        current_value = sum(h.groww_closing_value for h in holdings)

        context = {
            "report_date": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
            "intraday_setups": intraday_setups,
            "portfolio_summary": {
                "current_value": current_value,
                "day_pnl": current_value - total_invested,
            },
            "deals": deals,
            "verdicts": [],
            "mf_recommendations": [],
            "fii_dii": fii_dii,
        }

        html = build_midday_snapshot(context)
        send_email(html, "Midday Snapshot", config.ses_sender, config.ses_recipient, config.aws_region)
        upload_report(html, "midday_snapshot", config.s3_bucket, config.aws_region)
        build_dashboard(context, config.dashboard_output_dir)

        db = DBManager(config.db_path)
        db.store_holdings(holdings)
        db.close()

        logger.info("=== Midday Snapshot Pipeline Completed ===")
    except Exception:
        logger.error("Midday Snapshot Pipeline failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
