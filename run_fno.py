#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           🎯 F&O AUTO-TRADER — Wealth Builder Pro            ║
║                                                              ║
║  AI-powered Nifty/BankNifty/FinNifty options trading         ║
║  Claude Sonnet + Quant Edge Engine select strategies          ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python run_fno.py                  # Paper mode (default)
    python run_fno.py --live           # Live trading (real money!)
    python run_fno.py --force          # Skip time-of-day checks
    python run_fno.py --skip-scan      # Use cached option chain data
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fno")


def ist_now() -> datetime:
    return datetime.now(IST)


def phase_log(phase: str, status: str = "START") -> None:
    ts = ist_now().strftime("%H:%M:%S")
    emoji = "🟢" if status == "START" else ("✅" if status == "DONE" else "❌")
    logger.info(f"{emoji} [{ts}] Phase: {phase} — {status}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="F&O Auto-Trader")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading (real money)")
    parser.add_argument("--skip-scan", action="store_true", help="Skip option chain fetch, use cached data")
    parser.add_argument("--force", action="store_true", help="Ignore time-of-day checks")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Time-of-day check
# ---------------------------------------------------------------------------

def check_trading_hours(force: bool) -> bool:
    """Verify we're within trading hours (8:30 AM – 3:30 PM IST, weekday)."""
    if force:
        logger.info("--force: skipping time-of-day check")
        return True

    now = ist_now()
    weekday = now.weekday()
    if weekday >= 5:
        print(f"\n⚠️  Today is {now.strftime('%A')} — markets are closed. Use --force to override.\n")
        return False

    hour, minute = now.hour, now.minute
    if hour < 8 or (hour == 8 and minute < 30) or hour > 15 or (hour == 15 and minute > 30):
        print(f"\n⚠️  Current time {now.strftime('%H:%M IST')} is outside trading hours (8:30–15:30). Use --force to override.\n")
        return False

    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    is_live = args.live

    # ── Banner ──
    mode_str = "🔴 LIVE TRADING" if is_live else "🧪 PAPER MODE"
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🎯 F&O AUTO-TRADER — Wealth Builder Pro            ║")
    print(f"║           Mode: {mode_str:<42} ║")
    print(f"║           Time: {ist_now().strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Phase 1: Time check ──
    if not check_trading_hours(args.force):
        sys.exit(1)

    # ── Phase 2: Load config ──
    phase_log("Configuration", "START")
    try:
        import yaml
        from fno.config import load_fno_config

        with open("config/config.yaml") as f:
            raw_config = yaml.safe_load(f)

        config = load_fno_config(raw_config)

        # Override mode if --live
        if is_live:
            config.mode = "live"

        phase_log("Configuration", "DONE")
        logger.info(
            "Config: broker=%s, mode=%s, capital=₹%.0f, max_positions=%d",
            config.broker, config.mode, config.paper_capital, config.max_positions,
        )
    except Exception as exc:
        phase_log("Configuration", "FAIL")
        logger.error("Config load failed: %s", exc)
        sys.exit(1)

    # ── Phase 3: Database ──
    phase_log("Database", "START")
    try:
        from database.db_manager import DBManager
        db_path = raw_config.get("database", {}).get("path", "database/portfolio.db")
        db = DBManager(db_path)
        phase_log("Database", "DONE")
    except Exception as exc:
        phase_log("Database", "FAIL")
        logger.error("DB init failed: %s", exc)
        sys.exit(1)

    # ── Phase 4: Verify paper history for live mode ──
    if config.mode == "live":
        phase_log("Paper History Check", "START")
        from fno.config import verify_paper_history
        if not verify_paper_history(db, config.paper_trading_weeks):
            print(
                f"\n⚠️  Live mode requires {config.paper_trading_weeks} weeks of "
                f"profitable paper trading history. Run in paper mode first.\n"
            )
            db.close()
            sys.exit(1)
        phase_log("Paper History Check", "DONE")

    # ── Phase 5: Broker auth ──
    # Uses same TOTP auth as intraday. Paper mode uses DryRunBrokerClient.
    phase_log("Broker Authentication", "START")
    try:
        from intraday.auth_server import authenticate_broker

        broker_config = raw_config.get(config.broker, {})
        is_paper = config.mode == "paper"

        broker = authenticate_broker(
            broker_name=config.broker,
            broker_config=broker_config,
            dry_run=is_paper,  # Paper mode → DryRunBrokerClient, Live → real TOTP auth
        )
        phase_log("Broker Authentication", "DONE")
        logger.info(
            "Broker: %s, mode=%s, auth=%s",
            config.broker,
            config.mode,
            "DryRun" if is_paper else "TOTP/OAuth",
        )
    except Exception as exc:
        phase_log("Broker Authentication", "FAIL")
        logger.error("Auth failed: %s", exc)
        db.close()
        sys.exit(1)

    # ── Phase 6: Fetch option chains ──
    phase_log("Option Chain Fetch", "START")
    try:
        from fno.option_chain import OptionChainFetcher

        fetcher = OptionChainFetcher()
        chains: dict = {}

        for index in config.allowed_indices:
            snapshots = fetcher.fetch_option_chain(
                index, broker_client=broker, demo=(config.mode == "paper"),
            )
            if snapshots:
                chains[index] = snapshots[0]  # Current expiry
                logger.info(
                    "%s: spot=%.2f, ATM=%s, PCR=%.2f, MaxPain=%s",
                    index, snapshots[0].spot_price, snapshots[0].atm_strike,
                    snapshots[0].pcr if snapshots[0].pcr != float("inf") else 99.99,
                    snapshots[0].max_pain,
                )

        if not chains:
            raise RuntimeError("No option chains fetched")

        db.insert_audit_log("FNO_SCAN", json.dumps({"indices": list(chains.keys())}))
        phase_log("Option Chain Fetch", "DONE")
    except Exception as exc:
        phase_log("Option Chain Fetch", "FAIL")
        logger.error("Option chain fetch failed: %s", exc)
        db.close()
        sys.exit(1)

    # ── Phase 7: Compute Greeks ──
    phase_log("Greeks Computation", "START")
    from fno.greeks import FnO_Greeks_Calculator
    greeks_calc = FnO_Greeks_Calculator()
    phase_log("Greeks Computation", "DONE")

    # ── Phase 8: Compute quant signals ──
    phase_log("Quant Edge Engine", "START")
    try:
        from fno.quant_engine import Quant_Edge_Engine

        quant = Quant_Edge_Engine(db, config)
        quant_signals: dict = {}

        for index, chain in chains.items():
            snapshots = fetcher.get_snapshot_buffer(index)
            signals = quant.compute_all_signals(chain, greeks_calc, snapshots)
            quant_signals[index] = signals
            logger.info(
                "%s quant: IVP=%.1f%%, VRP=%.2f, GEX=%s, Confluence=%.0f",
                index, signals.iv_percentile, signals.vrp,
                signals.gex_regime, signals.confluence_score,
            )

        db.insert_audit_log(
            "FNO_QUANT_SIGNALS",
            json.dumps({
                idx: {"ivp": s.iv_percentile, "vrp": s.vrp, "confluence": s.confluence_score}
                for idx, s in quant_signals.items()
            }),
        )
        phase_log("Quant Edge Engine", "DONE")
    except Exception as exc:
        phase_log("Quant Edge Engine", "FAIL")
        logger.error("Quant engine failed: %s", exc)
        db.close()
        sys.exit(1)

    # ── Phase 9: LLM strategy selection ──
    phase_log("Strategy Selection", "START")
    try:
        from fno.strategy_engine import FnO_Strategy_Engine

        strategy_engine = FnO_Strategy_Engine(config, db, greeks_calc)
        vix = 15.0  # Default VIX for paper mode

        strategies = strategy_engine.select_strategies(
            chains=chains,
            quant_signals=quant_signals,
            vix=vix,
            current_time=ist_now(),
        )

        if not strategies:
            logger.warning("No strategies selected — session ends")
            phase_log("Strategy Selection", "DONE")
            _generate_partial_report(config, db)
            db.close()
            sys.exit(0)

        logger.info("Selected %d strategies", len(strategies))
        for s in strategies:
            logger.info(
                "  %s %s: %d legs, max_loss=₹%.0f, confidence=%d, confluence=%.0f",
                s.strategy_type, s.index, len(s.legs),
                s.max_loss, s.confidence_score, s.confluence_score,
            )
        phase_log("Strategy Selection", "DONE")
    except Exception as exc:
        phase_log("Strategy Selection", "FAIL")
        logger.error("Strategy selection failed: %s", exc)
        _generate_partial_report(config, db)
        db.close()
        sys.exit(1)

    # ── Phase 10: Risk validation ──
    phase_log("Risk Validation", "START")
    from fno.risk_manager import FnO_Risk_Manager
    from fno.paper_engine import Paper_Trade_Engine

    paper_engine = Paper_Trade_Engine(config, db) if config.mode == "paper" else None
    risk_mgr = FnO_Risk_Manager(config, db, broker=broker, paper_engine=paper_engine)

    approved: list = []
    for s in strategies:
        ok, reason = risk_mgr.validate_strategy(s, vix=vix)
        if ok:
            approved.append(s)
            logger.info("✅ Approved: %s %s", s.strategy_type, s.index)
        else:
            logger.warning("❌ Rejected: %s %s — %s", s.strategy_type, s.index, reason)

    if not approved:
        logger.warning("No strategies approved by risk manager")
        _generate_partial_report(config, db)
        db.close()
        sys.exit(0)

    phase_log("Risk Validation", "DONE")

    # ── Phase 11: Order execution ──
    phase_log("Order Execution", "START")
    from fno.executor import FnO_Order_Executor

    executor = FnO_Order_Executor(config, db, broker=broker)
    placed_ids: list[int] = []

    for s in approved:
        if config.mode == "paper" and paper_engine:
            sid = paper_engine.simulate_fill(s, chain=chains.get(s.index))
        else:
            sid = executor.execute_strategy(s, broker=broker)

        if sid:
            placed_ids.append(sid)
            logger.info("Placed strategy %d: %s %s", sid, s.strategy_type, s.index)

    if not placed_ids:
        logger.warning("No strategies could be placed")

    phase_log("Order Execution", "DONE")

    # ── Phase 12: Position monitoring loop ──
    phase_log("Position Monitoring", "START")
    from fno.monitor import FnO_Position_Monitor

    monitor = FnO_Position_Monitor(
        config, db, greeks_calc, broker=broker, paper_engine=paper_engine,
    )

    # Both paper and live mode: monitor continuously until force exit time
    try:
        fe_parts = config.force_exit_time.split(":")
        force_exit_dt = ist_now().replace(
            hour=int(fe_parts[0]), minute=int(fe_parts[1]),
            second=0, microsecond=0,
        )
    except Exception:
        force_exit_dt = ist_now().replace(hour=15, minute=15, second=0, microsecond=0)

    if ist_now() >= force_exit_dt:
        # Already past force exit time — just run one cycle
        logger.info("Past force exit time %s — running single monitor cycle", config.force_exit_time)
        result = monitor.monitor_cycle()
        logger.info(
            "Monitor: checked=%d, exits=%d, warnings=%d",
            result["checked"], result["exits"], len(result["warnings"]),
        )
    else:
        # Continuous monitoring loop until force exit time
        cycle = 0
        interval = config.monitor_interval_seconds
        logger.info(
            "Monitoring every %ds until %s IST (%s mode)",
            interval, config.force_exit_time, config.mode,
        )
        while ist_now() < force_exit_dt:
            cycle += 1
            result = monitor.monitor_cycle()
            open_count = result["checked"] - result["exits"]
            if result["checked"] == 0:
                logger.info("No open positions — exiting monitor loop")
                break
            if cycle % 10 == 0 or result["exits"] > 0:
                logger.info(
                    "Monitor cycle %d: open=%d, exits=%d, warnings=%d",
                    cycle, open_count, result["exits"], len(result["warnings"]),
                )
            time.sleep(interval)

    phase_log("Position Monitoring", "DONE")

    # ── Phase 13: Force exit ──
    phase_log("Force Exit", "START")
    exits = monitor.force_exit_all()
    logger.info("Force exited %d strategies", exits)
    phase_log("Force Exit", "DONE")

    # ── Phase 14: EOD Report ──
    phase_log("EOD Report", "START")
    from fno.reporter import FnO_Reporter

    reporter = FnO_Reporter(config, db)
    report = reporter.generate_eod_report()
    logger.info(
        "EOD: P&L=₹%.2f, Win rate=%.1f%%, Strategies=%d",
        report.get("total_pnl", 0),
        report.get("win_rate", 0),
        report.get("total_strategies", 0),
    )
    phase_log("EOD Report", "DONE")

    # ── Phase 15: Dashboard update ──
    phase_log("Dashboard Update", "START")
    # Already done by reporter
    phase_log("Dashboard Update", "DONE")

    # ── Persist risk state ──
    risk_mgr.persist_daily_loss()

    # ── Cleanup ──
    db.close()

    print()
    print("🏁 F&O session complete!")
    print()


def _generate_partial_report(config, db) -> None:
    """Generate a partial report when session ends early."""
    try:
        from fno.reporter import FnO_Reporter
        reporter = FnO_Reporter(config, db)
        reporter.generate_eod_report()
    except Exception:
        logger.error("Failed to generate partial report", exc_info=True)


if __name__ == "__main__":
    main()
