"""V3 Orchestrator — main entry point for V3 intraday trading cycle.

Runs every 15 min via cron. Orchestrates:
  Trip wires → Auth → Universe → Data → Health → Regime → Strategy → Diversify → Rank → Execute

Usage:
    from intraday.v3.orchestrator import run_v3_cycle
    result = run_v3_cycle("vishal-live-v2", dry_run=True)
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).parent.parent.parent

# Claude call tracking table
CREATE_CLAUDE_TABLE = """
CREATE TABLE IF NOT EXISTS v3_claude_calls (
    date TEXT PRIMARY KEY,
    called_at TEXT
)
"""


def run_v3_cycle(profile: str, dry_run: bool = False) -> dict:
    """Main V3 cycle — runs every 15 min via cron.

    Args:
        profile: Profile name (e.g., "vishal-live-v2", "vishal")
        dry_run: If True, skip auth/orders/Claude (for testing)

    Returns:
        Summary dict with regime, candidates, trades_placed, etc.
    """
    from intraday.v3.funnel_logger import FunnelLogger

    today = datetime.now(IST).strftime("%Y-%m-%d")
    now_ist = datetime.now(IST)
    funnel = FunnelLogger(date=today, profile=profile)

    logger.info("V3 cycle START — profile=%s, dry_run=%s, time=%s IST",
                profile, dry_run, now_ist.strftime("%H:%M"))

    # ── Step 0: SETUP ──
    cfg = _load_profile_config(profile)
    if not cfg:
        logger.error("V3: Failed to load profile config for %s", profile)
        return {"error": "config_load_failed"}

    db_path = cfg.get("database", {}).get("path", f"database/{profile}.db")
    if not Path(ROOT / db_path).is_absolute():
        db_path = str(ROOT / db_path)

    # ── Step 1: TRIP WIRE CHECK ──
    from intraday.v3.trip_wires import TripWireMonitor

    monitor = TripWireMonitor(db_path)
    all_clear, tripped = monitor.all_clear()
    if not all_clear:
        logger.warning("V3 HALTED: trip wires tripped: %s", tripped)
        funnel.log_stage("trip_wires", 0, drop_reasons={w: 1 for w in tripped})
        funnel.write_daily_json()
        return {"halted": True, "tripped_wires": tripped, "regime": None, "trades_placed": 0}

    funnel.log_stage("trip_wires_clear", 1)

    # ── Step 2: AUTHENTICATION ──
    broker = None
    if not dry_run:
        try:
            from intraday.auth_server import authenticate_broker
            dhan_cfg = cfg.get("dhan", {})
            broker = authenticate_broker("dhan", dhan_cfg, dry_run=False, profile=profile)
            logger.info("V3: Authenticated broker for %s", profile)
        except Exception as exc:
            logger.error("V3: Auth failed: %s", exc)
            funnel.log_stage("auth_failed", 0, drop_reasons={"auth_error": 1})
            funnel.write_daily_json()
            return {"error": "auth_failed", "detail": str(exc)}

    # ── Step 2.5: HARD LOSS CAP CHECK (Dhan truth) ──
    if not dry_run and broker:
        from intraday.v3.safety import check_hard_loss_cap, emergency_square_off_all
        intra_cfg_local = cfg.get("intraday", {})
        daily_cap = intra_cfg_local.get("daily_loss_limit", 1000)
        cap_result = check_hard_loss_cap(broker, daily_cap)
        if cap_result["breached"]:
            logger.critical("V3: HARD LOSS CAP BREACHED (Dhan truth: Rs%.2f) - EMERGENCY SQUARE OFF",
                            cap_result["total_pnl"])
            square_result = emergency_square_off_all(broker)
            funnel.log_stage("hard_cap_breached", 0,
                             drop_reasons={"dhan_pnl": cap_result["total_pnl"],
                                           "squared_off": square_result["squared_off"]})
            funnel.write_daily_json()
            return {"halted": True, "reason": "HARD_CAP_BREACHED",
                    "dhan_pnl": cap_result["total_pnl"],
                    "squared_off": square_result["squared_off"],
                    "regime": None, "trades_placed": 0}

    # ── Step 3: UNIVERSE LOAD ──
    from intraday.v3.universe import load_universe, get_tradeable_universe

    universe = load_universe()
    funnel.log_stage("universe_loaded", len(universe))

    tradeable = get_tradeable_universe()
    suspended_count = sum(1 for v in universe.values() if v.get("is_suspended"))
    no_id_count = sum(1 for v in universe.values() if not v.get("security_id"))
    funnel.log_stage("tradeable_filtered", len(tradeable),
                     drop_reasons={"suspended": suspended_count, "no_dhan_id": no_id_count})

    # ── Step 4: BULK LTP FETCH ──
    ltp_data = {}
    if not dry_run and broker:
        from intraday.v3.dhan_data import fetch_bulk_ltp
        security_ids = [v["security_id"] for v in tradeable.values() if v.get("security_id")]
        ltp_data = fetch_bulk_ltp(broker, security_ids)
        funnel.log_stage("data_fetched", len(ltp_data))
    else:
        # Dry run: simulate 400 valid candidates
        funnel.log_stage("data_fetched", 0, drop_reasons={"dry_run": 1})

    # ── Step 5: DATA HEALTH GATE ──
    from intraday.v3.data_health import check_data_health

    # Merge tradeable universe with LTP data
    candidates_with_data = []
    for sym, info in tradeable.items():
        sec_id = info.get("security_id", "")
        quote = ltp_data.get(sec_id, {})
        candidates_with_data.append({
            "symbol": sym,
            "security_id": sec_id,
            "sector": info.get("sector", "Unknown"),
            "mcap_bucket": info.get("mcap_bucket", "LARGE"),
            "open": quote.get("open", 0),
            "ltp": quote.get("ltp", 0),
            "volume": quote.get("volume", 0),
            "prev_close": quote.get("prev_close", 0),
        })

    health = check_data_health(candidates_with_data)
    funnel.log_stage("data_healthy", health["valid_count"], drop_reasons=health["drop_reasons"])

    if not health["healthy"] and not dry_run:
        logger.warning("V3: DATA_UNHEALTHY — skipping cycle (%d/%d valid)",
                       health["valid_count"], health["total"])
        funnel.write_daily_json()
        return {"halted": False, "regime": None, "reason": "data_unhealthy",
                "valid_data": health["valid_count"], "trades_placed": 0}

    # ── Step 6: REGIME DETECTION ──
    from intraday.v3.regime import detect_regime, TRENDING_UP, RANGING

    if dry_run:
        regime = TRENDING_UP
        regime_result = {"regime": TRENDING_UP, "reasoning": "dry_run default"}
    else:
        # Compute inputs from LTP data
        nifty_change = _compute_nifty_change(ltp_data, tradeable)
        breadth = _compute_breadth(candidates_with_data)
        vix = 16.0  # Default — TODO: fetch from Dhan/NSE
        regime_result = detect_regime(
            nifty_change_pct=nifty_change,
            nifty_30min_range_pct=0.5,  # Approximation
            breadth_pct=breadth,
            vix=vix,
            date=today,
        )
        regime = regime_result["regime"]

    funnel.set_regime(regime)
    logger.info("V3: Regime = %s (%s)", regime, regime_result.get("reasoning", ""))

    # ── Step 7: STRATEGY ROUTER ──
    from intraday.v3.strategies.orb_v6 import detect_v6_signals
    from intraday.v3.strategies.orb_v4 import detect_v4_signals
    from intraday.v3.strategies.vwap_mean_reversion import detect_vwap_mr_signals

    signals = []
    intra_cfg = cfg.get("intraday", {})
    strategy_config = {"per_trade_max_capital": intra_cfg.get("per_trade_max_capital", 10000)}

    # Build historical data dict for strategies (empty in dry_run)
    historical_data = {}  # Strategies need candle data — populated from fetch_intraday_candles in live
    universe_ids = {sym: info["security_id"] for sym, info in tradeable.items() if info.get("security_id")}

    if regime == TRENDING_UP:
        v6_signals = detect_v6_signals(historical_data, universe_ids, strategy_config, today, nifty_data=None)
        v4_signals = detect_v4_signals(historical_data, universe_ids, strategy_config, today, nifty_data=None)
        signals = v6_signals + v4_signals
        logger.info("V3: TRENDING_UP — V6=%d, V4=%d signals", len(v6_signals), len(v4_signals))
    elif regime == RANGING:
        vwap_signals = detect_vwap_mr_signals(historical_data, universe_ids, strategy_config, today, regime=RANGING)
        v4_signals = detect_v4_signals(historical_data, universe_ids, strategy_config, today, nifty_data=None)
        signals = vwap_signals + v4_signals
        logger.info("V3: RANGING — VWAP_MR=%d, V4=%d signals", len(vwap_signals), len(v4_signals))
    else:
        logger.info("V3: STAY_FLAT — regime=%s, no strategies active", regime)
        funnel.log_stage("strategies_skipped", 0, drop_reasons={"regime_no_trade": 1})
        funnel.write_daily_json()
        return {"halted": False, "regime": regime, "reason": f"stay_flat_{regime}",
                "trades_placed": 0, "fallback_triggered": False}

    funnel.log_stage("strategy_signals", len(signals))

    # ── Step 8: DIVERSIFICATION ──
    from intraday.v3.diversifier import apply_diversification

    diversified = apply_diversification(signals, universe, max_per_sector=2)
    funnel.log_stage("diversified", len(diversified))

    # ── Step 9: CLAUDE RANKING ──
    top_3 = diversified[:3]  # Default: score-ranked top 3

    if diversified and not dry_run and not _check_claude_called_today(db_path):
        try:
            from llm.bedrock_client import BedrockClient
            from intraday.v3.ranker_claude import rank_top_3

            bedrock_region = "us-east-1"
            bedrock_model = "us.anthropic.claude-sonnet-4-6"
            bedrock = BedrockClient(region=bedrock_region, model_id=bedrock_model)
            ranked = rank_top_3(diversified[:20], regime, bedrock)
            if ranked:
                top_3 = ranked
            _mark_claude_called(db_path)
        except Exception as exc:
            logger.warning("V3: Claude ranking failed (using score fallback): %s", exc)

    funnel.log_stage("claude_ranked", len(top_3))

    # ── Step 10: FALLBACK CHECK ──
    fallback_triggered = False
    if len(top_3) == 0 and now_ist.hour >= 10 and now_ist.minute >= 30:
        if not dry_run:
            try:
                from intraday.v3.fallback_v1 import trigger_v1_fallback
                from llm.bedrock_client import BedrockClient

                bedrock = BedrockClient(region="us-east-1", model_id="us.anthropic.claude-sonnet-4-6")
                fallback_picks = trigger_v1_fallback(diversified[:20], regime, bedrock, db_path)
                if fallback_picks:
                    top_3 = fallback_picks
                    fallback_triggered = True
            except Exception as exc:
                logger.warning("V3: Fallback failed: %s", exc)

    funnel.set_fallback_triggered(fallback_triggered)

    # ── Step 11: PLACE ORDERS (V3 atomic executor) ──
    from intraday.v3.executor import place_v3_orders
    exec_result = place_v3_orders(broker, top_3, dry_run=dry_run)
    orders_placed = exec_result["placed"]

    funnel.log_stage("orders_placed", orders_placed)

    # ── Step 12: WRITE FUNNEL JSON ──
    funnel.write_daily_json()
    logger.info("V3 cycle COMPLETE — regime=%s, signals=%d, placed=%d, fallback=%s",
                regime, len(signals), orders_placed, fallback_triggered)

    return {
        "halted": False,
        "regime": regime,
        "signals_found": len(signals),
        "diversified": len(diversified),
        "trades_placed": orders_placed,
        "fallback_triggered": fallback_triggered,
        "tripped_wires": [],
    }


# ── Helper functions ──

def _load_profile_config(profile: str) -> Optional[dict]:
    """Load profile YAML config."""
    path = ROOT / "config" / "profiles" / f"{profile}.yaml"
    if not path.exists():
        logger.error("Profile config not found: %s", path)
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as exc:
        logger.error("Failed to load profile %s: %s", profile, exc)
        return None


def _compute_nifty_change(ltp_data: dict, tradeable: dict) -> float:
    """Estimate Nifty change from bulk LTP data (mean of top 50 stocks)."""
    changes = []
    for sym, info in list(tradeable.items())[:50]:
        sec_id = info.get("security_id", "")
        quote = ltp_data.get(sec_id, {})
        ltp = quote.get("ltp", 0)
        prev = quote.get("prev_close", 0)
        if ltp > 0 and prev > 0:
            changes.append((ltp - prev) / prev * 100)
    return sum(changes) / len(changes) if changes else 0.0


def _compute_breadth(candidates: list) -> float:
    """Compute market breadth: % of stocks where LTP > prev_close."""
    total = 0
    up = 0
    for c in candidates:
        ltp = c.get("ltp", 0)
        prev = c.get("prev_close", 0)
        if ltp > 0 and prev > 0:
            total += 1
            if ltp > prev:
                up += 1
    return (up / total * 100) if total > 0 else 50.0


def _check_claude_called_today(db_path: str) -> bool:
    """Check if Claude ranker was already called today."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(CREATE_CLAUDE_TABLE)
        row = conn.execute("SELECT 1 FROM v3_claude_calls WHERE date = ?", (today,)).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _mark_claude_called(db_path: str):
    """Mark Claude as called today."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(CREATE_CLAUDE_TABLE)
        conn.execute("INSERT OR REPLACE INTO v3_claude_calls (date, called_at) VALUES (?, ?)",
                     (today, datetime.now(IST).isoformat()))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("Failed to mark Claude called: %s", exc)
