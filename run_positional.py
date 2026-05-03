#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           🏦 POSITIONAL TRADER — Dev Sandbox                 ║
║                                                              ║
║  AI-powered positional trading (hold 4-12 weeks)             ║
║  Weekly scan + weekly review                                 ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python run_positional.py scan          # Scan for new setups (weekly)
    python run_positional.py monitor       # Review positions (weekly)
    python run_positional.py report        # Show portfolio
    python run_positional.py --live        # Live trading
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("positional")


def parse_args():
    parser = argparse.ArgumentParser(description="Positional Trader")
    parser.add_argument("action", choices=["scan", "monitor", "report"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_positional_config():
    """Load positional config from config.yaml."""
    import yaml
    from positional.models import PositionalConfig

    with open("config/config.yaml") as f:
        data = yaml.safe_load(f)

    pos_data = data.get("positional", {})
    config = PositionalConfig()

    for key in PositionalConfig.__dataclass_fields__:
        if key in pos_data:
            setattr(config, key, pos_data[key])

    return config


def run_scan(config, dry_run: bool):
    """Scan for positional setups."""
    from config.config_loader import load_config
    from positional.scanner import PositionalScanner
    from positional.selector import select_positional_trades
    from llm.bedrock_client import BedrockClient
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🏦 POSITIONAL SCANNER — Weekly Scan                ║")
    print(f"║           Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    scanner = PositionalScanner(config)
    scan_data = scanner.scan()

    if not scan_data["candidates"]:
        print("❌ No candidates found")
        return

    bedrock = BedrockClient(
        region=app_config.bedrock_region,
        model_id=app_config.bedrock_model_id,
    )
    setups = select_positional_trades(
        candidates=scan_data["candidates"],
        sectors=scan_data["sectors"],
        fii_dii=scan_data["fii_dii"],
        config=config,
        bedrock_client=bedrock,
    )

    if not setups:
        print("❌ No suitable positional setups this week")
        return

    # Print picks
    print(f"✅ {len(setups)} positional picks:")
    for s in setups:
        print(f"   {s.nse_symbol} ({s.market_cap}): ₹{s.entry_price:.2f} → ₹{s.target_price:.2f} ({s.strategy_type}, ~{s.expected_hold_weeks}w)")
    print()

    # Update dashboard
    from positional.dashboard import write_positional_dashboard
    write_positional_dashboard(db)

    db.close()


def run_monitor(config):
    """Weekly position review."""
    from config.config_loader import load_config
    from positional.monitor import PositionalMonitor
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           📊 POSITIONAL REVIEW — Weekly Check                ║")
    print(f"║           Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    positions = db.get_positional_positions(status="OPEN")

    if not positions:
        print("No open positional positions")
        db.close()
        return

    monitor = PositionalMonitor(config, db=db)
    updated = monitor.review_positions(positions)

    open_count = sum(1 for p in updated if p.status == "OPEN")
    closed = [p for p in updated if p.status != "OPEN"]
    total_pnl = sum(p.pnl for p in closed)

    print(f"Open: {open_count} | Closed this week: {len(closed)} | P&L: ₹{total_pnl:+,.2f}")
    for p in updated:
        gain = (p.current_price - p.entry_price) / p.entry_price * 100 if p.current_price > 0 else 0
        print(f"   {p.nse_symbol}: {p.status} | {gain:+.1f}% | Week {p.weeks_held}/{config.max_hold_weeks}")
    print()

    db.close()


def run_report(config):
    """Show positional portfolio."""
    from config.config_loader import load_config
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    positions = db.get_positional_positions()
    open_pos = [p for p in positions if p.status == "OPEN"]
    closed_pos = [p for p in positions if p.status != "OPEN"]

    total_invested = sum(p.entry_price * p.quantity for p in open_pos)
    total_current = sum(p.current_price * p.quantity for p in open_pos if p.current_price > 0)
    realized_pnl = sum(p.pnl for p in closed_pos)

    print()
    print(f"🏦 Positional Portfolio: {len(open_pos)} open, {len(closed_pos)} closed")
    print(f"💰 Invested: ₹{total_invested:,.0f}")
    print(f"📊 Current value: ₹{total_current:,.0f}")
    print(f"📈 Unrealized: ₹{total_current - total_invested:+,.0f}")
    print(f"✅ Realized P&L: ₹{realized_pnl:+,.2f}")
    print()

    db.close()


def main():
    args = parse_args()
    config = load_positional_config()

    if args.action == "scan":
        run_scan(config, not args.live)
    elif args.action == "monitor":
        run_monitor(config)
    elif args.action == "report":
        run_report(config)


if __name__ == "__main__":
    main()
