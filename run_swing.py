#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           📈 SWING TRADER — Dev Sandbox                      ║
║                                                              ║
║  AI-powered swing trading (hold 2-15 days)                   ║
║  Scans after market close, monitors daily at open            ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python run_swing.py scan              # Scan for new setups (run after 3:30 PM)
    python run_swing.py monitor           # Check open positions (run at 9:30 AM)
    python run_swing.py report            # Show current positions and P&L
    python run_swing.py --live            # Live trading (real money!)
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
logger = logging.getLogger("swing")


def parse_args():
    parser = argparse.ArgumentParser(description="Swing Trader")
    parser.add_argument("action", choices=["scan", "monitor", "report"], help="Action to perform")
    parser.add_argument("--live", action="store_true", help="Live trading mode")
    parser.add_argument("--force", action="store_true", help="Skip time checks")
    return parser.parse_args()


def load_swing_config():
    """Load swing config from config.yaml."""
    import yaml
    from swing.models import SwingConfig

    with open("config/config.yaml") as f:
        data = yaml.safe_load(f)

    swing_data = data.get("swing", {})
    config = SwingConfig()

    for key in SwingConfig.__dataclass_fields__:
        if key in swing_data:
            setattr(config, key, swing_data[key])

    return config


def run_scan(config, dry_run: bool):
    """Scan for new swing trade setups."""
    from config.config_loader import load_config
    from swing.scanner import SwingScanner
    from swing.selector import select_swing_trades
    from swing.executor import SwingExecutor
    from llm.bedrock_client import BedrockClient
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           📈 SWING SCANNER — Looking for setups              ║")
    print(f"║           Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Scan
    scanner = SwingScanner(config)
    scan_data = scanner.scan()

    if not scan_data["candidates"]:
        print("❌ No candidates found")
        return

    # LLM selection
    bedrock = BedrockClient(
        region=app_config.bedrock_region,
        model_id=app_config.bedrock_model_id,
    )
    setups = select_swing_trades(
        candidates=scan_data["candidates"],
        sectors=scan_data["sectors"],
        config=config,
        bedrock_client=bedrock,
    )

    if not setups:
        print("❌ LLM found no suitable swing setups today")
        return

    # Execute
    executor = SwingExecutor(config, db=db, dry_run=dry_run)
    positions = executor.execute_trades(setups, config.daily_capital_limit)

    # Update dashboard
    from swing.dashboard import write_swing_dashboard
    write_swing_dashboard(db)

    # Print results
    print()
    print(f"✅ {len(positions)} swing positions opened:")
    for p in positions:
        print(f"   {p.nse_symbol}: ₹{p.entry_price:.2f} → ₹{p.target_price:.2f} (SL ₹{p.stop_loss_price:.2f}) [{p.strategy_type}]")
    print()

    db.close()


def run_monitor(config):
    """Check open swing positions."""
    from config.config_loader import load_config
    from swing.monitor import SwingMonitor
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           📊 SWING MONITOR — Checking positions              ║")
    print(f"║           Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Get open positions from DB
    positions = db.get_swing_positions(status="OPEN")

    if not positions:
        print("No open swing positions")
        db.close()
        return

    monitor = SwingMonitor(config, db=db)
    updated = monitor.check_positions(positions)

    # Update dashboard
    from swing.dashboard import write_swing_dashboard
    write_swing_dashboard(db)

    # Print summary
    open_count = sum(1 for p in updated if p.status == "OPEN")
    closed = [p for p in updated if p.status != "OPEN"]

    print(f"Open: {open_count} | Closed today: {len(closed)}")
    for p in updated:
        pnl_str = f"₹{p.pnl:+.2f}" if p.pnl else f"₹{(p.current_price - p.entry_price) * p.quantity:+.2f}"
        print(f"   {p.nse_symbol}: {p.status} | {pnl_str} | Day {p.days_held}")
    print()

    db.close()


def run_report(config):
    """Show current swing portfolio."""
    from config.config_loader import load_config
    from database.db_manager import DBManager

    app_config = load_config("config/config.yaml")
    db = DBManager(app_config.db_path)

    positions = db.get_swing_positions()
    open_pos = [p for p in positions if p.status == "OPEN"]
    closed_pos = [p for p in positions if p.status != "OPEN"]

    total_pnl = sum(p.pnl for p in closed_pos)
    unrealized = sum((p.current_price - p.entry_price) * p.quantity for p in open_pos if p.current_price > 0)

    print()
    print(f"📈 Swing Portfolio: {len(open_pos)} open, {len(closed_pos)} closed")
    print(f"💰 Realized P&L: ₹{total_pnl:+,.2f}")
    print(f"📊 Unrealized P&L: ₹{unrealized:+,.2f}")
    print()

    db.close()


def main():
    args = parse_args()
    config = load_swing_config()
    dry_run = not args.live

    if args.action == "scan":
        run_scan(config, dry_run)
    elif args.action == "monitor":
        run_monitor(config)
    elif args.action == "report":
        run_report(config)


if __name__ == "__main__":
    main()
