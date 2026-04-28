#!/usr/bin/env python3
"""End-of-Day Report Pipeline — Triggered at 4:15 PM IST (10:45 UTC).

Orchestrates: full parse + fetch → AI analysis → build HTML →
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
from parsers.groww_mf_parser import parse_mf_xlsx
from parsers.groww_pnl_parser import parse_pnl_xlsx
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.nse_bulk_deals import fetch_bulk_deals
from fetchers.screener_fetcher import fetch_fundamentals
from fetchers.amfi_nav_fetcher import fetch_amfi_nav
from fetchers.ipo_fetcher import fetch_ipo_gmp
from fetchers.news_fetcher import fetch_news
from fetchers.market_indices import fetch_indices
from llm.bedrock_client import BedrockClient
from llm.portfolio_analyzer import analyze_portfolio
from llm.market_scanner import scan_opportunities
from llm.mf_analyzer import analyze_mutual_funds
from reports.html_builder import build_eod_report
from reports.ses_sender import send_email
from reports.s3_uploader import upload_report, upload_xlsx
from reports.dashboard_builder import build_dashboard
from database.db_manager import DBManager

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def main() -> None:
    config_path = os.environ.get("WBP_CONFIG", "config/config.yaml")
    config = load_config(config_path)
    setup_logging(log_dir=os.path.dirname(config.db_path).replace("data", "logs"))

    logger.info("=== EOD Report Pipeline Started ===")
    try:
        # Full parse
        holdings = parse_stocks_xlsx(config.stocks_xlsx)
        mf_holdings = parse_mf_xlsx(config.mf_xlsx)
        pnl_trades, pnl_scrips = parse_pnl_xlsx(config.pnl_xlsx)

        # Full fetch
        bhavcopy = fetch_bhavcopy(config.cache_dir)
        fii_dii = fetch_fii_dii(config.cache_dir)
        deals = fetch_bulk_deals()
        nav_data = fetch_amfi_nav(config.cache_dir)
        ipo_data = fetch_ipo_gmp()
        news = fetch_news()
        indices = fetch_indices(config.cache_dir)

        fundamentals = {}
        for h in holdings:
            if h.nse_symbol:
                try:
                    fundamentals[h.nse_symbol] = fetch_fundamentals(h.nse_symbol)
                except Exception:
                    logger.warning("Failed to fetch fundamentals for %s", h.nse_symbol)

        # AI analysis
        client = BedrockClient(config.bedrock_region, config.bedrock_model_id)
        verdicts = analyze_portfolio(holdings, bhavcopy, fundamentals, pnl_scrips, client)
        opportunities = scan_opportunities(deals, fii_dii, fundamentals, client)
        mf_recs = analyze_mutual_funds(mf_holdings, nav_data, client)

        # Tax harvesting candidates
        tax_candidates = [
            h for h in holdings
            if h.unrealised_pnl < 0
        ]

        # Portfolio summary
        total_invested = sum(h.buy_value for h in holdings)
        current_value = sum(h.groww_closing_value for h in holdings)

        context = {
            "report_date": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
            "portfolio_summary": {
                "total_invested": total_invested,
                "current_value": current_value,
                "total_pnl": current_value - total_invested,
                "day_pnl": current_value - total_invested,
            },
            "verdicts": verdicts,
            "mf_recommendations": mf_recs,
            "tax_harvest_candidates": tax_candidates,
            "ipo_data": ipo_data,
            "fii_dii": fii_dii,
        }

        html = build_eod_report(context)
        send_email(html, "EOD Report", config.ses_sender, config.ses_recipient, config.aws_region)
        upload_report(html, "eod_report", config.s3_bucket, config.aws_region)

        # Archive XLSX files
        for xlsx_path in [config.stocks_xlsx, config.mf_xlsx, config.pnl_xlsx]:
            upload_xlsx(xlsx_path, config.s3_bucket, config.aws_region)

        build_dashboard(context, config.dashboard_output_dir)

        db = DBManager(config.db_path)
        db.store_holdings(holdings)
        db.store_mf_holdings(mf_holdings)
        db.store_verdicts(verdicts)
        db.store_mf_recommendations(mf_recs)
        db.close()

        logger.info("=== EOD Report Pipeline Completed ===")
    except Exception:
        logger.error("EOD Report Pipeline failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
