#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           🚀 INTRADAY AUTO-TRADER — Wealth Builder Pro      ║
║                                                              ║
║  AI-powered intraday trading on NSE equity cash segment      ║
║  Claude Sonnet 4.5 selects trades • Python executes them     ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python run_intraday.py                  # Dry-run (default)
    python run_intraday.py --live           # Live trading (real money!)
    python run_intraday.py --force          # Skip time-of-day checks
    python run_intraday.py --skip-scan      # Use cached scan data
"""

from __future__ import annotations

import argparse
import json
import logging
import os
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
logger = logging.getLogger("intraday")


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
    parser = argparse.ArgumentParser(description="Intraday Auto-Trader")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading (real money)")
    parser.add_argument("--skip-scan", action="store_true", help="Skip pre-market scan, use cached data")
    parser.add_argument("--force", action="store_true", help="Ignore time-of-day checks")
    parser.add_argument("--demo", action="store_true", help="Demo mode: simulate today's trading with REAL NSE closing data")
    parser.add_argument("--profile", type=str, default=None, help="User profile name (e.g. vishal, neha). Uses config/profiles/<name>.yaml")
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
    weekday = now.weekday()  # 0=Mon, 6=Sun
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

    # Demo mode runs its own pipeline
    if args.demo:
        return run_demo_mode()

    dry_run = not args.live

    # ── Banner ──
    mode_str = "🧪 DRY-RUN" if dry_run else "🔴 LIVE TRADING"
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🚀 INTRADAY AUTO-TRADER — Wealth Builder Pro      ║")
    print(f"║           Mode: {mode_str:<42} ║")
    print(f"║           Time: {ist_now().strftime('%Y-%m-%d %H:%M IST'):<42} ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    if args.live:
        print("\033[91m" + "⚠️  WARNING: LIVE MODE — REAL MONEY IS AT RISK!" + "\033[0m")
        print()

    # ── Phase 1: Time check ──
    if not check_trading_hours(args.force):
        sys.exit(1)

    # ── Phase 2: Load config ──
    phase_log("Configuration", "START")
    try:
        from config.config_loader import load_config, load_intraday_config
        import yaml

        # Profile support: load profile-specific config if --profile given
        profile_name = args.profile
        profile_config = None
        if profile_name:
            from config.profile_loader import load_profile
            profile_config = load_profile(profile_name)
            logger.info("Using profile: %s", profile_name)

        app_config = load_config("config/config.yaml")
        intra_config = load_intraday_config("config/config.yaml")

        # Apply profile overrides
        if profile_config:
            intra_overrides = profile_config.get("intraday", {})
            for k, v in intra_overrides.items():
                if hasattr(intra_config, k):
                    setattr(intra_config, k, v)
            # Override DB path
            db_path_override = profile_config.get("database", {}).get("path")
            if db_path_override:
                app_config.db_path = db_path_override

        phase_log("Configuration", "DONE")
    except Exception as exc:
        phase_log("Configuration", "FAIL")
        logger.error("Config load failed: %s", exc)
        sys.exit(1)

    # ── Phase 3: Database ──
    phase_log("Database", "START")
    try:
        from database.db_manager import DBManager
        db = DBManager(app_config.db_path)
        phase_log("Database", "DONE")
    except Exception as exc:
        phase_log("Database", "FAIL")
        logger.error("DB init failed: %s", exc)
        db = None

    # ── Phase 4: Broker auth ──
    phase_log("Broker Authentication", "START")
    try:
        from intraday.auth_server import authenticate_broker, DryRunBrokerClient
        import yaml

        with open("config/config.yaml") as f:
            raw_config = yaml.safe_load(f)

        # Use profile-specific Dhan creds if available
        if profile_config:
            broker_config = profile_config.get(intra_config.broker, {})
        else:
            broker_config = raw_config.get(intra_config.broker, {})
        broker = authenticate_broker(intra_config.broker, broker_config, dry_run=dry_run)
        phase_log("Broker Authentication", "DONE")
    except Exception as exc:
        phase_log("Broker Authentication", "FAIL")
        logger.error("Auth failed: %s", exc)
        if not dry_run:
            sys.exit(1)
        broker = DryRunBrokerClient(intra_config.daily_capital_limit)

    # ── Phase 5: Pre-market scan ──
    scan_result = None
    if not args.skip_scan:
        phase_log("Pre-Market Scan", "START")
        try:
            from intraday.scanner import Pre_Market_Scanner
            scanner = Pre_Market_Scanner()
            scan_result = scanner.scan()
            if scan_result is None:
                phase_log("Pre-Market Scan", "FAIL")
                logger.error("Scan failed after retry — aborting")
                sys.exit(1)
            logger.info(
                "Scan: %d candidates, %d sectors, VIX %.2f",
                len(scan_result.candidates), len(scan_result.sectors), scan_result.vix_value,
            )
            phase_log("Pre-Market Scan", "DONE")
        except Exception as exc:
            phase_log("Pre-Market Scan", "FAIL")
            logger.error("Scan error: %s", exc)
            sys.exit(1)
    else:
        logger.info("--skip-scan: using cached data")
        # Try loading from cache
        phase_log("Load Cached Scan", "START")
        try:
            from intraday.scanner import ScanResult
            today = ist_now().strftime("%Y-%m-%d")
            cache_path = f"cache/market_movers_{today}.json"
            if os.path.exists(cache_path):
                with open(cache_path) as f:
                    cached = json.load(f)
                scan_result = ScanResult(
                    candidates=[],
                    sectors=cached.get("sectors", []),
                    vix_value=0,
                    gainers=cached.get("gainers", []),
                    losers=cached.get("losers", []),
                )
                # Build candidates from gainers + losers
                seen = set()
                for item in cached.get("gainers", []) + cached.get("losers", []):
                    sym = item.get("symbol", "")
                    if sym and sym not in seen:
                        seen.add(sym)
                        scan_result.candidates.append(item)
                phase_log("Load Cached Scan", "DONE")
            else:
                logger.warning("No cache file found for today — running fresh scan")
                from intraday.scanner import Pre_Market_Scanner
                scanner = Pre_Market_Scanner()
                scan_result = scanner.scan()
                phase_log("Load Cached Scan", "DONE")
        except Exception as exc:
            phase_log("Load Cached Scan", "FAIL")
            logger.error("Cache load failed: %s", exc)
            sys.exit(1)

    if scan_result is None:
        logger.error("No scan data available — aborting")
        sys.exit(1)

    # ── Phase 6: Rule-based pre-filter ──
    phase_log("Pre-Filter", "START")
    from intraday.selector import pre_filter_candidates
    filtered = pre_filter_candidates(
        scan_result.candidates, intra_config, scan_result.sectors,
    )
    logger.info("Pre-filter: %d candidates passed", len(filtered))
    phase_log("Pre-Filter", "DONE")

    if not filtered:
        logger.error("Zero candidates after pre-filter — aborting")
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(1)

    # ── Phase 7: LLM trade selection ──
    phase_log("LLM Trade Selection", "START")
    try:
        from llm.bedrock_client import BedrockClient
        from intraday.selector import select_trades_llm

        bedrock = BedrockClient(
            region=app_config.bedrock_region,
            model_id=app_config.bedrock_model_id,
        )
        trades = select_trades_llm(
            candidates=filtered,
            sectors=scan_result.sectors,
            vix_value=scan_result.vix_value,
            config=intra_config,
            bedrock_client=bedrock,
            gainers=scan_result.gainers,
            losers=scan_result.losers,
            dry_run=dry_run,
        )
        if not trades:
            phase_log("LLM Trade Selection", "FAIL")
            logger.error("LLM returned zero valid picks — aborting")
            _generate_partial_report([], db, intra_config, dry_run)
            sys.exit(1)

        phase_log("LLM Trade Selection", "DONE")
    except Exception as exc:
        phase_log("LLM Trade Selection", "FAIL")
        logger.error("LLM selection failed: %s", exc)
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(1)

    # ── Print morning picks ──
    _print_morning_picks(trades, scan_result.vix_value, intra_config)

    # ── Phase 8: Position sizing ──
    phase_log("Position Sizing", "START")
    from intraday.risk_manager import Risk_Manager
    risk_mgr = Risk_Manager(intra_config, db=db)

    margins = broker.get_margins()
    available = margins.get("available_cash") or intra_config.daily_capital_limit

    # Account for capital already used in earlier sessions today
    capital_remaining = min(available, intra_config.daily_capital_limit - risk_mgr.capital_used_today)
    if capital_remaining <= 0:
        logger.warning("No capital remaining today (used ₹%.0f) — skipping", risk_mgr.capital_used_today)
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(0)

    # ── Gate conditions for non-morning sessions ──
    now_ist = ist_now()
    is_late_session = now_ist.hour >= 11  # after 11 AM = midday or afternoon
    if is_late_session:
        # Gate 1: Skip if already hit max trades today
        if risk_mgr._trades_placed_today >= intra_config.max_trades_per_day:
            logger.info(
                "Late session gate: max trades already placed today (%d/%d) — skipping",
                risk_mgr._trades_placed_today, intra_config.max_trades_per_day,
            )
            _generate_partial_report([], db, intra_config, dry_run)
            sys.exit(0)

        # Gate 2: Skip if loss > 50% of daily limit — protect capital, no revenge trading
        if intra_config.daily_loss_limit > 0:
            loss_pct = risk_mgr._realized_loss_today / intra_config.daily_loss_limit * 100
            if loss_pct > 50:
                logger.warning(
                    "Late session gate: loss ₹%.0f is %.0f%% of daily limit — skipping to protect capital",
                    risk_mgr._realized_loss_today, loss_pct,
                )
                _generate_partial_report([], db, intra_config, dry_run)
                sys.exit(0)

        # Gate 3: Skip if market breadth < 25% green — too bearish for late entry
        # Paper profiles skip this gate — they need experience on bearish days
        total_stocks = len(scan_result.gainers) + len(scan_result.losers)
        breadth_pct = len(scan_result.gainers) / total_stocks * 100 if total_stocks > 0 else 0
        if breadth_pct < 25 and not dry_run:
            logger.warning(
                "Late session gate: only %.0f%% stocks green — market too bearish for late entry",
                breadth_pct,
            )
            _generate_partial_report([], db, intra_config, dry_run)
            sys.exit(0)
        elif breadth_pct < 25 and dry_run:
            logger.info(
                "Late session gate: breadth %.0f%% — bearish but continuing (paper mode)",
                breadth_pct,
            )

        logger.info(
            "Late session gate passed: trades=%d/%d, loss=%.0f%%, breadth=%.0f%% green",
            risk_mgr._trades_placed_today, intra_config.max_trades_per_day,
            risk_mgr._realized_loss_today / intra_config.daily_loss_limit * 100 if intra_config.daily_loss_limit > 0 else 0,
            breadth_pct,
        )

    sized_trades = risk_mgr.size_trades(trades, available_margin=capital_remaining)
    if not sized_trades:
        logger.error("No trades could be sized — aborting")
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(1)
    phase_log("Position Sizing", "DONE")

    # ── Phase 9: VIX check ──
    phase_log("VIX Check", "START")
    vix_result = risk_mgr.check_vix(scan_result.vix_value)
    if vix_result["action"] == "SKIP":
        logger.warning("VIX too high — skipping session")
        print(f"\n⚠️  {vix_result['reason']}\n")
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(0)
    if vix_result["action"] == "REDUCE":
        max_trades = vix_result["effective_max_trades"]
        sized_trades = sized_trades[:max_trades]
        logger.info("VIX elevated — reduced to %d trades", max_trades)
    phase_log("VIX Check", "DONE")

    # ── Phase 10: Order execution ──
    phase_log("Order Execution", "START")
    from intraday.executor import Order_Executor
    executor = Order_Executor(broker, intra_config, db=db, dry_run=dry_run)
    placed = executor.execute_trades(sized_trades, risk_manager=risk_mgr, force=args.force)
    if not placed:
        logger.error("No orders placed — aborting")
        _generate_partial_report([], db, intra_config, dry_run)
        sys.exit(1)
    phase_log("Order Execution", "DONE")

    # ── Phase 11: Position monitoring ──
    phase_log("Position Monitoring", "START")
    from intraday.monitor import Position_Monitor
    monitor = Position_Monitor(broker, intra_config, db=db, risk_manager=risk_mgr, dry_run=dry_run)
    monitor.set_trades(placed)
    final_trades = monitor.run_monitoring_loop()
    phase_log("Position Monitoring", "DONE")

    # ── Phase 12: EOD Report ──
    phase_log("EOD Report", "START")
    from intraday.reporter import Performance_Tracker
    reporter = Performance_Tracker(
        db=db,
        broker_name=intra_config.broker,
        mode="DRY_RUN" if dry_run else "LIVE",
    )
    report = reporter.generate_eod_report(final_trades)
    reporter.print_summary(report)
    phase_log("EOD Report", "DONE")

    # ── Phase 13: Dashboard update ──
    phase_log("Dashboard Update", "START")
    from intraday.dashboard import write_dashboard_json
    dashboard_dir = None
    if profile_config:
        dashboard_dir = profile_config.get("dashboard", {}).get("api_dir")
    write_dashboard_json(
        trades=final_trades,
        config=intra_config,
        db=db,
        mode="DRY_RUN" if dry_run else "LIVE",
        broker=intra_config.broker,
        session_active=False,
        api_dir=dashboard_dir,
    )
    phase_log("Dashboard Update", "DONE")

    # ── Cleanup ──
    if db:
        db.close()

    print()
    print("🏁 Intraday session complete!")
    print()


# ---------------------------------------------------------------------------
# Demo mode pipeline
# ---------------------------------------------------------------------------

def run_demo_mode() -> None:
    """Run the full intraday pipeline in demo mode using cached NSE closing data.

    Loads candidates from cache/demo_candidates.json (real OHLCV data),
    fetches live sector indices from NSE, sends to Claude for trade selection,
    then simulates realistic intraday price movement using actual day's range.
    """
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        🎬 DEMO MODE — Simulating Today's Trading            ║")
    print("║        Using REAL NSE closing data + Claude AI picks         ║")
    print(f"║        Time: {ist_now().strftime('%Y-%m-%d %H:%M IST'):<44} ║")
    print("║        Capital: ₹1,00,000 (1 Lakh)                          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print("  📡 Loading real stock data from cache/demo_candidates.json")
    print("  and simulating what would have happened today.")
    print()

    # ── Phase 1: Load config ──
    phase_log("Configuration", "START")
    try:
        from config.config_loader import load_config, load_intraday_config
        app_config = load_config("config/config.yaml")
        intra_config = load_intraday_config("config/config.yaml")

        # Override capital to ₹1,00,000 for demo mode
        intra_config.daily_capital_limit = 100_000.0
        intra_config.per_trade_max_capital = 35_000.0

        phase_log("Configuration", "DONE")
    except Exception as exc:
        phase_log("Configuration", "FAIL")
        logger.error("Config load failed: %s", exc)
        sys.exit(1)

    # ── Phase 2: Database (optional) ──
    phase_log("Database", "START")
    try:
        from database.db_manager import DBManager
        db = DBManager(app_config.db_path)
        phase_log("Database", "DONE")
    except Exception:
        db = None
        phase_log("Database", "DONE")

    # ── Phase 3: Load candidates from cache + fetch live sectors ──
    phase_log("Load Demo Data", "START")
    try:
        demo_cache_path = "cache/demo_candidates.json"
        if not os.path.exists(demo_cache_path):
            phase_log("Load Demo Data", "FAIL")
            print(f"\n❌ Demo data file not found: {demo_cache_path}\n")
            sys.exit(1)

        with open(demo_cache_path) as f:
            raw_candidates = json.load(f)

        # Build proper candidate dicts with gap_pct
        stock_data: list[dict] = []
        for item in raw_candidates:
            open_price = float(item.get("open", 0))
            prev_close = float(item.get("prev_close", 0))
            gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

            stock_data.append({
                "symbol": item["symbol"],
                "name": item["symbol"],
                "ltp": float(item.get("ltp", 0)),
                "open_price": open_price,
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "close": float(item.get("ltp", 0)),
                "prev_close": prev_close,
                "volume": int(item.get("volume", 0)),
                "change_pct": float(item.get("change_pct", 0)),
                "gap_pct": round(gap_pct, 2),
                "category": "demo",
            })

        # Fetch live sector indices from NSE (works after hours)
        from intraday.demo_data import extract_sectors_from_nse, extract_vix_from_nse
        sectors = extract_sectors_from_nse()
        vix_value = extract_vix_from_nse()

        # Fallback if NSE is unreachable
        if not sectors:
            sectors = [
                {"name": "NIFTY 50", "last_price": 24000, "change": 200, "change_pct": 0.84},
                {"name": "NIFTY BANK", "last_price": 52000, "change": 400, "change_pct": 0.77},
                {"name": "NIFTY ENERGY", "last_price": 35000, "change": 500, "change_pct": 1.45},
                {"name": "NIFTY PSU BANK", "last_price": 7200, "change": 100, "change_pct": 1.41},
                {"name": "NIFTY METAL", "last_price": 9500, "change": -50, "change_pct": -0.53},
            ]
        if vix_value <= 0:
            vix_value = 14.0

        print(f"  📊 Loaded {len(stock_data)} stocks from demo cache")
        print(f"  📈 India VIX: {vix_value:.2f}")
        print(f"  🏭 {len(sectors)} sector indices loaded")
        print()
        phase_log("Load Demo Data", "DONE")
    except Exception as exc:
        phase_log("Load Demo Data", "FAIL")
        logger.error("Demo data load failed: %s", exc)
        sys.exit(1)

    # ── Phase 4: Pre-filter with REAL prices ──
    phase_log("Pre-Filter (Real Data)", "START")
    from intraday.selector import pre_filter_candidates
    filtered = pre_filter_candidates(stock_data, intra_config, sectors)
    logger.info("Pre-filter: %d candidates passed", len(filtered))
    phase_log("Pre-Filter (Real Data)", "DONE")

    if not filtered:
        print("\n❌ Zero candidates after pre-filter — no tradeable stocks today.\n")
        sys.exit(1)

    # Build gainers/losers summaries for LLM prompt
    gainers = [s for s in stock_data if s["change_pct"] > 0][:10]
    losers = [s for s in stock_data if s["change_pct"] < 0][:10]
    gainers_summary = [{"symbol": g["symbol"], "name": g["symbol"], "ltp": g["ltp"],
                        "change_pct": g["change_pct"], "volume": g["volume"]} for g in gainers]
    losers_summary = [{"symbol": lo["symbol"], "name": lo["symbol"], "ltp": lo["ltp"],
                       "change_pct": lo["change_pct"], "volume": lo["volume"]} for lo in losers]

    # ── Phase 5: LLM trade selection with REAL data ──
    phase_log("LLM Trade Selection (Real Data)", "START")
    try:
        from llm.bedrock_client import BedrockClient
        from intraday.selector import select_trades_llm

        bedrock = BedrockClient(
            region=app_config.bedrock_region,
            model_id=app_config.bedrock_model_id,
        )
        trades = select_trades_llm(
            candidates=filtered,
            sectors=sectors,
            vix_value=vix_value,
            config=intra_config,
            bedrock_client=bedrock,
            gainers=gainers_summary,
            losers=losers_summary,
            dry_run=dry_run,
        )
        if not trades:
            phase_log("LLM Trade Selection (Real Data)", "FAIL")
            print("\n❌ Claude found no suitable trades in today's market.\n")
            sys.exit(1)

        phase_log("LLM Trade Selection (Real Data)", "DONE")
    except Exception as exc:
        phase_log("LLM Trade Selection (Real Data)", "FAIL")
        logger.error("LLM selection failed: %s", exc)
        sys.exit(1)

    # ── Print morning picks ──
    _print_morning_picks(trades, vix_value, intra_config)

    # ── Phase 6: Position sizing ──
    phase_log("Position Sizing", "START")
    from intraday.risk_manager import Risk_Manager
    risk_mgr = Risk_Manager(intra_config, db=db)
    sized_trades = risk_mgr.size_trades(trades, available_margin=intra_config.daily_capital_limit)
    if not sized_trades:
        print("\n❌ No trades could be sized within capital limits.\n")
        sys.exit(1)
    phase_log("Position Sizing", "DONE")

    # ── Phase 7: Execute (dry-run) ──
    phase_log("Order Execution (Simulated)", "START")
    from intraday.auth_server import DryRunBrokerClient
    from intraday.executor import Order_Executor
    broker = DryRunBrokerClient(intra_config.daily_capital_limit)
    executor = Order_Executor(broker, intra_config, db=db, dry_run=True)
    placed = executor.execute_trades(sized_trades, risk_manager=risk_mgr, force=True)
    if not placed:
        print("\n❌ No orders could be placed.\n")
        sys.exit(1)
    phase_log("Order Execution (Simulated)", "DONE")

    # ── Phase 8: Attach OHLCV data to placed trades for realistic monitoring ──
    # Build stock lookup
    stock_map = {s["symbol"]: s for s in stock_data}
    for t in placed:
        sym = t.get("nse_symbol") or t.get("tradingsymbol", "")
        ohlcv = stock_map.get(sym, {})
        t["demo_high"] = ohlcv.get("high", 0)
        t["demo_low"] = ohlcv.get("low", 0)
        t["demo_ltp"] = ohlcv.get("ltp", 0) or ohlcv.get("close", 0)
        t["demo_open"] = ohlcv.get("open_price", 0)
        t["demo_change_pct"] = ohlcv.get("change_pct", 0)

    # ── Phase 9: Position monitoring with realistic OHLCV simulation ──
    phase_log("Position Monitoring (OHLCV Sim)", "START")
    from intraday.monitor import Position_Monitor
    monitor = Position_Monitor(broker, intra_config, db=db, risk_manager=risk_mgr, dry_run=True)
    monitor.set_trades(placed)
    final_trades = monitor.run_monitoring_loop()
    phase_log("Position Monitoring (OHLCV Sim)", "DONE")

    # Add OHLCV context for display
    for t in final_trades:
        sym = t.get("nse_symbol") or t.get("tradingsymbol", "")
        ohlcv = stock_map.get(sym, {})
        t["day_high"] = ohlcv.get("high", 0)
        t["day_low"] = ohlcv.get("low", 0)
        t["day_close"] = ohlcv.get("ltp", 0) or ohlcv.get("close", 0)
        t["day_open"] = ohlcv.get("open_price", 0)
        if "sim_note" not in t:
            status = t.get("status", "")
            t["sim_note"] = {
                "CLOSED": "🎯 Target reached!",
                "STOPPED_OUT": "🛑 Stop loss triggered",
                "FORCE_EXITED": "⏰ Force exit at close",
            }.get(status, "")

    # ── Phase 10: Print beautiful demo results ──
    _print_demo_results(final_trades, stock_data, vix_value, intra_config)

    # ── Phase 11: EOD Report ──
    phase_log("EOD Report", "START")
    from intraday.reporter import Performance_Tracker
    reporter = Performance_Tracker(db=db, broker_name="demo", mode="DEMO")
    today_str = ist_now().strftime("%Y-%m-%d")
    report = reporter.generate_eod_report(final_trades, trade_date=today_str, report_prefix="intraday_demo")
    reporter.print_summary(report)
    phase_log("EOD Report", "DONE")

    # ── Phase 12: Dashboard update ──
    phase_log("Dashboard Update", "START")
    from intraday.dashboard import write_dashboard_json
    write_dashboard_json(
        trades=final_trades,
        config=intra_config,
        db=db,
        mode="DEMO",
        broker="demo",
        session_active=False,
    )
    phase_log("Dashboard Update", "DONE")

    if db:
        db.close()

    print()
    print("🏁 Demo simulation complete! This is what would have happened today.")
    print()


def _print_demo_results(
    trades: list[dict],
    stock_data: list[dict],
    vix_value: float,
    config,
) -> None:
    """Print beautiful demo simulation results with emojis."""
    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    total_capital = sum(t.get("entry_price", 0) * t.get("quantity", 0) for t in trades)
    pnl_pct = (total_pnl / total_capital * 100) if total_capital > 0 else 0

    pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
    reset = "\033[0m"

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          📊 DEMO SIMULATION RESULTS — End of Day            ║")
    print("║          Using REAL NSE OHLCV data for today                ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    for i, t in enumerate(trades, 1):
        status = t.get("status", "?")
        status_emoji = {
            "CLOSED": "🎯",
            "STOPPED_OUT": "🛑",
            "FORCE_EXITED": "⏰",
        }.get(status, "❓")

        pnl = t.get("pnl", 0) or 0
        entry = t.get("entry_price", 0)
        exit_p = t.get("exit_price", 0)
        qty = t.get("quantity", 0)
        sym = t.get("tradingsymbol", t.get("nse_symbol", "?"))
        note = t.get("sim_note", "")

        trade_capital = entry * qty
        trade_pnl_pct = (pnl / trade_capital * 100) if trade_capital > 0 else 0

        if pnl >= 0:
            pnl_str = f"\033[92m+₹{pnl:,.0f}\033[0m"
        else:
            pnl_str = f"\033[91m-₹{abs(pnl):,.0f}\033[0m"

        print(f"║                                                              ║")
        print(f"║  {status_emoji} Trade {i}: {sym:<12}  [{t.get('strategy_type', '?')}]")
        print(f"║     📍 Entry: ₹{entry:,.2f}  →  Exit: ₹{exit_p:,.2f}")
        print(f"║     🎯 Target: ₹{t.get('target_price', 0):,.2f}  🛑 SL: ₹{t.get('stop_loss_price', 0):,.2f}")
        print(f"║     📦 Qty: {qty}  💰 Capital: ₹{trade_capital:,.0f}")

        # Show day's OHLCV context
        day_h = t.get("day_high", 0)
        day_l = t.get("day_low", 0)
        day_o = t.get("day_open", 0)
        day_c = t.get("day_close", 0)
        if day_h > 0:
            print(f"║     📈 Day OHLC: O ₹{day_o:,.2f} | H ₹{day_h:,.2f} | L ₹{day_l:,.2f} | C ₹{day_c:,.2f}")

        print(f"║     {note}")
        print(f"║     💵 P&L: {pnl_str} ({trade_pnl_pct:+.2f}%)")

    print(f"║                                                              ║")
    print("╠══════════════════════════════════════════════════════════════╣")

    # Summary
    winners = [t for t in trades if (t.get("pnl", 0) or 0) > 0]
    losers = [t for t in trades if (t.get("pnl", 0) or 0) < 0]
    flat = [t for t in trades if (t.get("pnl", 0) or 0) == 0]

    big_emoji = "🟢" if total_pnl >= 0 else "🔴"
    print(f"║                                                              ║")
    print(f"║  {big_emoji} TOTAL P&L: {pnl_color}₹{total_pnl:+,.2f}{reset} ({pnl_pct:+.2f}%)")
    print(f"║  📊 Capital Deployed: ₹{total_capital:,.0f} / ₹{config.daily_capital_limit:,.0f}")
    print(f"║  ✅ Winners: {len(winners)}  🛑 Losers: {len(losers)}  ⏰ Flat: {len(flat)}")
    print(f"║  📈 VIX: {vix_value:.2f}")
    print(f"║                                                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_morning_picks(trades, vix_value: float, config) -> None:
    """Print the morning picks in a beautiful format."""
    print()
    print("┌──────────────────────────────────────────────────────────────┐")
    print("│              🌅 MORNING PICKS — Claude's Selections          │")
    print(f"│              VIX: {vix_value:.2f} | Budget: ₹{config.daily_capital_limit:,.0f}              │")
    print("├──────────────────────────────────────────────────────────────┤")

    for i, t in enumerate(trades, 1):
        rr = t.risk_reward_ratio
        risk_per_share = t.entry_price - t.stop_loss_price
        print(f"│  {i}. {t.stock_name} ({t.nse_symbol})")
        print(f"│     📍 Entry: ₹{t.entry_price:.2f}  🎯 Target: ₹{t.target_price:.2f}  🛑 SL: ₹{t.stop_loss_price:.2f}")
        print(f"│     📊 R:R {rr:.1f}:1  ⭐ Confidence: {t.confidence_score}/10  🏷️ {t.strategy_type}")
        print(f"│     💡 {t.rationale[:70]}{'…' if len(t.rationale) > 70 else ''}")
        print("│")

    print("└──────────────────────────────────────────────────────────────┘")
    print()


def _generate_partial_report(trades: list, db, config, dry_run: bool, profile_config: dict | None = None) -> None:
    """Generate a partial report when session aborts early."""
    if not trades:
        logger.info("No trades to report")
    else:
        try:
            from intraday.reporter import Performance_Tracker
            reporter = Performance_Tracker(
                db=db,
                broker_name=config.broker,
                mode="DRY_RUN" if dry_run else "LIVE",
            )
            report = reporter.generate_eod_report(trades)
            reporter.print_summary(report)
        except Exception:
            logger.error("Failed to generate partial report", exc_info=True)

    # Always write dashboard even on early abort — so dashboard shows current state
    try:
        from intraday.dashboard import write_dashboard_json
        dashboard_dir = None
        if profile_config:
            dashboard_dir = profile_config.get("dashboard", {}).get("api_dir")
        write_dashboard_json(
            trades=trades,
            config=config,
            db=db,
            mode="DRY_RUN" if dry_run else "LIVE",
            broker=config.broker,
            session_active=False,
            api_dir=dashboard_dir,
        )
    except Exception:
        logger.error("Failed to write dashboard on partial report", exc_info=True)


if __name__ == "__main__":
    main()
