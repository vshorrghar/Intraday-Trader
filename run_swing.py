#!/usr/bin/env python3
"""
Swing trading pipeline orchestrator.
Runs daily after market close (4 PM IST).

Usage:
    python run_swing.py --profile vishal              (paper)
    python run_swing.py --profile vishal-live         (paper, even on live profile)
    python run_swing.py --profile vishal-live --live  (REAL MONEY CNC orders)
    python run_swing.py --profile vishal --force      (skip entry delay)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from swing.models import SwingConfig
from swing.manual_override import is_paused

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("swing")


def parse_args():
    parser = argparse.ArgumentParser(description="Swing Trading Pipeline")
    parser.add_argument("--profile", required=True, help="Profile name")
    parser.add_argument("--live", action="store_true", help="Real money mode (CNC orders via Dhan)")
    parser.add_argument("--force", action="store_true", help="Skip time checks")
    return parser.parse_args()


def load_profile(profile_name: str) -> dict:
    """Load profile YAML."""
    path = Path(f"config/profiles/{profile_name}.yaml")
    if not path.exists():
        logger.error("Profile not found: %s", path)
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def select_broker(profile_data: dict, profile_name: str, live: bool):
    """Select broker based on mode."""
    from intraday.auth_server import authenticate_broker, DryRunBrokerClient

    # Paper profiles always get DryRun regardless of --live flag
    paper_profiles = {"vishal", "neha"}
    if profile_name in paper_profiles and live:
        logger.warning("%s is paper profile, --live ignored. Using DryRun.", profile_name)
        live = False

    if live:
        dhan_cfg = profile_data.get("dhan", {})
        if not dhan_cfg.get("client_id"):
            logger.error("No Dhan client_id for %s — cannot go live", profile_name)
            sys.exit(1)
        broker = authenticate_broker("dhan", dhan_cfg, dry_run=False, profile=profile_name)
        return broker
    else:
        return DryRunBrokerClient()


def run():
    args = parse_args()
    now = datetime.now(IST)

    print("=== SWING PIPELINE ===")
    print(f"Profile: {args.profile}")
    print(f"Mode: {'LIVE (REAL MONEY)' if args.live else 'PAPER (DryRun)'}")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S IST')}")

    # Load profile
    profile_data = load_profile(args.profile)
    config = SwingConfig.from_yaml(profile_data, args.profile)

    # Check manual pause
    paused, reason = is_paused(args.profile)
    if paused:
        logger.info("⏸️ Swing trading PAUSED for %s: %s — exiting", args.profile, reason)
        return

    # Select broker
    broker = select_broker(profile_data, args.profile, args.live)
    print(f"Broker: {type(broker).__name__}")

    # Check swing enabled
    if not profile_data.get("swing", {}).get("enabled", False):
        logger.info("Swing not enabled for profile %s — exiting", args.profile)
        return

    logger.info("🟢 Swing pipeline starting for %s", args.profile)

    # Phase 6-7: Fetch universe + score candidates
    # For Phase 1, we log placeholder and write empty dashboard JSONs
    logger.info("Phase 6: Fetching universe (placeholder — full scanner in Phase 2 build)")
    logger.info("Phase 7: Scoring candidates (placeholder)")
    logger.info("Phase 8: Regime check (placeholder)")
    logger.info("Phase 9-16: LLM selection + execution (placeholder)")

    # Write placeholder dashboard JSONs
    dashboard_dir = Path(f"dashboard/api/{args.profile}/swing")
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    portfolio_json = {
        "total_value": 0,
        "cash_balance": config.swing_capital_limit,
        "deployed_capital": 0,
        "capital_limit": config.swing_capital_limit,
        "starting_capital": config.swing_capital_limit,
        "unrealized_pnl": 0,
        "today_pnl": 0,
        "weekly_pnl": 0,
        "max_drawdown_pct": 0,
        "regime_score": 5,
        "regime_status": "NORMAL",
        "positions": [],
        "last_updated": now.isoformat(),
        "environment": "LIVE" if args.live else "PAPER",
        "currency": "INR",
    }
    (dashboard_dir / "portfolio.json").write_text(json.dumps(portfolio_json, indent=2))
    (dashboard_dir / "signals.json").write_text("[]")
    (dashboard_dir / "candidates.json").write_text("[]")

    # History from DB (placeholder)
    (dashboard_dir / "history.json").write_text("[]")

    logger.info("✅ Swing pipeline complete for %s. Dashboard JSONs written.", args.profile)
    logger.info("📊 Mode: %s | Capital: Rs.%.0f | Max positions: %d",
                "LIVE" if args.live else "PAPER", config.swing_capital_limit,
                config.swing_max_open_positions)


if __name__ == "__main__":
    run()
