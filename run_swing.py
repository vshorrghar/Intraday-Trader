#!/usr/bin/env python3
"""
Swing trading pipeline orchestrator.

Actions:
  --action scan:    Run scanner + selector + executor (place paper trades)
  --action monitor: Check open positions for exits (SL/target/time stops)

Usage:
    python run_swing.py --profile vishal --action scan
    python run_swing.py --profile vishal --action monitor
    python run_swing.py --profile vishal-live --action scan --live  (REAL MONEY)
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
    parser.add_argument("--action", required=True, choices=["scan", "monitor"], help="Action to run")
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


def run_scan(profile_name: str, profile_data: dict, config: SwingConfig, broker, live: bool):
    """Run the scan pipeline: load data → scanner → selector → risk → execute."""
    from swing.data_loader import load_universe_for_scanner, get_universe_with_data
    from swing.scanner import scan_universe
    from swing.rules_selector import select_swing_trades
    from swing.risk_manager import SwingRiskManager
    from swing.executor import SwingExecutor
    from database.db_manager import DBManager

    now = datetime.now(IST)
    logger.info("=== SWING SCAN — %s — %s ===", profile_name, now.strftime("%Y-%m-%d %H:%M IST"))

    # Phase 1: Load universe from cache
    symbols = get_universe_with_data(min_candles=200)
    logger.info("Phase 1: Universe loaded — %d stocks with data", len(symbols))
    if len(symbols) < 50:
        logger.warning("Too few stocks with data (%d). Run refresh first.", len(symbols))
        return

    universe_data = load_universe_for_scanner(min_candles=200)
    logger.info("Phase 2: Scanner-ready — %d stocks", len(universe_data))

    # Phase 2: Run scanner
    candidates = scan_universe(universe_data, min_score=config.swing_min_score)
    logger.info("Phase 3: Scanner produced %d candidates (score >= %d)",
                len(candidates), config.swing_min_score)

    if not candidates:
        logger.info("No candidates today. Exiting scan.")
        return

    # Phase 3: Run rules_selector
    trades = select_swing_trades(candidates, config, live_mode=live)
    logger.info("Phase 4: Rules selector picked %d trades", len(trades))

    if not trades:
        logger.info("No trades passed rules filter. Exiting scan.")
        return

    # Phase 4: Risk manager gates
    db = DBManager(f"database/{profile_name}.db")
    risk_mgr = SwingRiskManager(config, db=db)
    risk_mgr.load_state()

    approved_trades = []
    for trade in trades:
        allowed, reason = risk_mgr.can_enter_trade(trade)
        if allowed is False:
            logger.info("BLOCKED %s: %s", trade.nse_symbol, reason)
            continue
        reduce = (allowed == "REDUCE")
        if reduce:
            logger.info("REDUCE size for %s: %s", trade.nse_symbol, reason)
        qty = risk_mgr.size_position(trade, reduce=reduce)
        trade.quantity = qty
        approved_trades.append(trade)

    logger.info("Phase 5: Risk manager approved %d / %d trades", len(approved_trades), len(trades))

    if not approved_trades:
        logger.info("All trades blocked by risk manager. Exiting scan.")
        return

    # Phase 5: Execute trades
    executor = SwingExecutor(config, broker=broker, db=db, dry_run=(not live))
    placed = executor.execute_trades(approved_trades, risk_manager=risk_mgr)
    logger.info("Phase 6: Executed %d trades", len(placed))

    for p in placed:
        logger.info("  PLACED: %s qty=%s entry=%.2f sl=%.2f target=%.2f",
                    p.get("symbol", "?"), p.get("quantity", "?"),
                    p.get("entry_price", 0), p.get("stop_loss_price", 0), p.get("target_price", 0))

    # Write dashboard JSON
    _write_dashboard(profile_name, config, db, now, live)
    logger.info("✅ Swing scan complete for %s. %d trades placed.", profile_name, len(placed))


def run_monitor(profile_name: str, profile_data: dict, config: SwingConfig, broker, live: bool):
    """Run the monitor pipeline: load positions → check exits → close as needed."""
    from swing.monitor import SwingMonitor
    from database.db_manager import DBManager

    now = datetime.now(IST)
    logger.info("=== SWING MONITOR — %s — %s ===", profile_name, now.strftime("%Y-%m-%d %H:%M IST"))

    db = DBManager(f"database/{profile_name}.db")
    monitor = SwingMonitor(config, broker=broker, db=db)

    # Load open positions
    monitor.load_open_positions()
    open_count = len(monitor._active_trades) if hasattr(monitor, "_active_trades") else 0
    logger.info("Phase 1: Loaded %d open positions", open_count)

    if open_count == 0:
        logger.info("No open positions. Nothing to monitor.")
        _write_dashboard(profile_name, config, db, now, live)
        return

    # Run monitor cycle (checks SL/target/time stops, places exit orders)
    monitor.run_monitor_cycle()

    # Write dashboard JSON
    _write_dashboard(profile_name, config, db, now, live)
    logger.info("✅ Swing monitor complete for %s.", profile_name)


def _write_dashboard(profile_name: str, config: SwingConfig, db, now, live: bool):
    """Write dashboard JSON files for the swing module."""
    dashboard_dir = Path(f"dashboard/api/{profile_name}/swing")
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    # Get open positions from DB
    try:
        open_positions = db.get_swing_trades(status="OPEN") or []
    except Exception:
        open_positions = []

    # Get today's closed trades
    try:
        all_trades = db.get_swing_trades() or []
        today_str = now.strftime("%Y-%m-%d")
        today_closed = [t for t in all_trades
                        if t.get("exit_date", "") == today_str and t.get("status") != "OPEN"]
        today_pnl = sum(t.get("pnl", 0) for t in today_closed)
    except Exception:
        today_pnl = 0
        today_closed = []

    deployed = sum(
        (p.get("entry_price", 0) * p.get("quantity", 0)) for p in open_positions
    )

    portfolio_json = {
        "total_value": config.swing_capital_limit + today_pnl,
        "cash_balance": config.swing_capital_limit - deployed,
        "deployed_capital": deployed,
        "capital_limit": config.swing_capital_limit,
        "starting_capital": config.swing_capital_limit,
        "unrealized_pnl": 0,
        "today_pnl": today_pnl,
        "positions": open_positions,
        "last_updated": now.isoformat(),
        "environment": "LIVE" if live else "PAPER",
        "currency": "INR",
    }
    (dashboard_dir / "portfolio.json").write_text(json.dumps(portfolio_json, indent=2))

    # Candidates from last scan (read from log — simplified)
    (dashboard_dir / "candidates.json").write_text("[]")
    (dashboard_dir / "history.json").write_text(json.dumps(today_closed, indent=2, default=str))

    logger.debug("Dashboard JSONs written to %s", dashboard_dir)


def run():
    args = parse_args()
    now = datetime.now(IST)

    print(f"=== SWING PIPELINE ({args.action.upper()}) ===")
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

    # Check swing enabled
    if not profile_data.get("swing", {}).get("enabled", False):
        logger.info("Swing not enabled for profile %s — exiting", args.profile)
        return

    # Select broker
    broker = select_broker(profile_data, args.profile, args.live)
    print(f"Broker: {type(broker).__name__}")

    # Dispatch action
    if args.action == "scan":
        run_scan(args.profile, profile_data, config, broker, args.live)
    elif args.action == "monitor":
        run_monitor(args.profile, profile_data, config, broker, args.live)


if __name__ == "__main__":
    run()
