#!/usr/bin/env python3
"""Morning Brief Pipeline — Triggered at 8:45 AM IST (3:15 UTC).

Orchestrates: parse XLSX → fetch data → AI analysis → build HTML →
send email → archive to S3 → update dashboard → store to DB.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config_loader import load_config
from config.logging_config import setup_logging
from parsers.groww_stocks_parser import parse_stocks_xlsx
from parsers.groww_mf_parser import parse_mf_xlsx
from parsers.groww_pnl_parser import parse_pnl_xlsx
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.news_fetcher import fetch_news
from fetchers.market_indices import fetch_indices
from llm.bedrock_client import BedrockClient
from llm.portfolio_analyzer import analyze_portfolio
from reports.html_builder import build_morning_brief
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

    logger.info("=== Morning Brief Pipeline Started ===")
    try:
        # Parse portfolio
        holdings = parse_stocks_xlsx(config.stocks_xlsx)
        pnl_trades, pnl_scrips = parse_pnl_xlsx(config.pnl_xlsx)

        # Fetch market data
        bhavcopy = fetch_bhavcopy(config.cache_dir)
        fii_dii = fetch_fii_dii(config.cache_dir)
        news = fetch_news()
        indices = fetch_indices(config.cache_dir)

        # AI analysis
        client = BedrockClient(config.bedrock_region, config.bedrock_model_id)
        verdicts = analyze_portfolio(holdings, bhavcopy, {}, pnl_scrips, client)

        # Compute portfolio summary
        total_invested = sum(h.buy_value for h in holdings)
        current_value = sum(h.groww_closing_value for h in holdings)
        total_pnl = current_value - total_invested

        context = {
            "report_date": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
            "portfolio_summary": {
                "total_invested": total_invested,
                "current_value": current_value,
                "total_pnl": total_pnl,
            },
            "indices": indices,
            "fii_dii": fii_dii,
            "news": news,
            "verdicts": verdicts,
        }

        # Build and send report
        html = build_morning_brief(context)
        send_email(html, "Morning Brief", config.ses_sender, config.ses_recipient, config.aws_region)
        upload_report(html, "morning_brief", config.s3_bucket, config.aws_region)

        # Update dashboard and DB
        build_dashboard(context, config.dashboard_output_dir)
        db = DBManager(config.db_path)
        db.store_holdings(holdings)
        db.store_verdicts(verdicts)
        db.close()

        logger.info("=== Morning Brief Pipeline Completed ===")
    except Exception:
        logger.error("Morning Brief Pipeline failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
