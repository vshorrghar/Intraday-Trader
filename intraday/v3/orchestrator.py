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
            broker = authenticate_broker("dhan", dhan_cfg, dry_run=False, profile=profile, allow_fresh_auth=False)
            logger.info("V3: Authenticated broker for %s", profile)
        except Exception as exc:
            logger.error("V3: Auth failed: %s", exc)
            funnel.log_stage("auth_failed", 0, drop_reasons={"auth_error": 1})
            funnel.write_daily_json()
            return {"error": "auth_failed", "detail": str(exc)}

    # ── Step 2.1: PAPER MODE WRAPPER (physical order block) ──
    if not dry_run and broker and cfg.get("profile", {}).get("paper", False):
        from intraday.v3.paper_broker_wrapper import wrap_broker_for_paper
        broker = wrap_broker_for_paper(broker)
        logger.info("V3: PAPER MODE — broker wrapped, real orders physically blocked")

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
    from intraday.v3.regime import detect_regime, TRENDING_UP, RANGING, TRENDING_DOWN

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

    # Build historical + nifty data for strategies (populated in live, empty in dry_run)
    historical_data = {}
    nifty_data = None
    universe_ids = {sym: info["security_id"] for sym, info in tradeable.items() if info.get("security_id")}

    if not dry_run and broker:
        # Rate-limit guard: fetch candles ONLY for top movers, not all 260+.
        def _abs_change(c):
            prev = c.get("prev_close", 0) or 0
            ltp = c.get("ltp", 0) or 0
            return abs((ltp - prev) / prev) if prev > 0 and ltp > 0 else 0.0
        movers = sorted(candidates_with_data, key=_abs_change, reverse=True)[:25]
        from_date = (now_ist - timedelta(days=6)).strftime("%Y-%m-%d")
        to_date = today
        fetched = 0
        import time as _time  # V3 throttle: respect Dhan charts rate limit

        def _fetch_ohlc(_sid, _seg, _inst):
            for _attempt in range(2):
                try:
                    _r = broker.get_historical_ohlc(
                        security_id=str(_sid), exchange_segment=_seg, instrument=_inst,
                        interval="5", from_date=from_date, to_date=to_date,
                    )
                    if _r and isinstance(_r, dict) and _r.get("timestamp"):
                        return _r
                except Exception as _e:
                    logger.warning("V3: candle fetch error %s: %s", _sid, _e)
                _time.sleep(1.0)  # backoff on empty/429
            return None

        for _c in movers:
            _sym = _c["symbol"]
            _sid = _c.get("security_id")
            if not _sid:
                continue
            _ohlc = _fetch_ohlc(_sid, "NSE_EQ", "EQUITY")
            if _ohlc:
                historical_data[_sym] = _ohlc
                fetched += 1
            _time.sleep(0.4)  # throttle between calls
        logger.info("V3: fetched candles for %d/%d movers", fetched, len(movers))

        _time.sleep(0.4)
        _nd = _fetch_ohlc("13", "IDX_I", "INDEX")
        if _nd:
            nifty_data = _nd
            logger.info("V3: Nifty candles fetched (%d)", len(_nd.get("open", [])))
        else:
            logger.warning("V3: Nifty candle fetch returned no data")

    if regime == TRENDING_UP:
        v6_signals = detect_v6_signals(historical_data, universe_ids, strategy_config, today, nifty_data=nifty_data)
        v4_signals = detect_v4_signals(historical_data, universe_ids, strategy_config, today, nifty_data=nifty_data)
        signals = v6_signals + v4_signals
        logger.info("V3: TRENDING_UP — V6=%d, V4=%d signals", len(v6_signals), len(v4_signals))
    elif regime == RANGING:
        vwap_signals = detect_vwap_mr_signals(historical_data, universe_ids, strategy_config, today, regime=RANGING)
        v4_signals = detect_v4_signals(historical_data, universe_ids, strategy_config, today, nifty_data=nifty_data)
        signals = vwap_signals + v4_signals
        logger.info("V3: RANGING — VWAP_MR=%d, V4=%d signals", len(vwap_signals), len(v4_signals))
    elif regime == TRENDING_DOWN:
        # LOOSENED 2026-10-08: TRENDING_DOWN now trades too (mirrors RANGING) —
        # was STAY_FLAT, leaving down days completely idle. V4 allows SHORT on BEAR.
        vwap_signals = detect_vwap_mr_signals(historical_data, universe_ids, strategy_config, today, regime=TRENDING_DOWN)
        v4_signals = detect_v4_signals(historical_data, universe_ids, strategy_config, today, nifty_data=nifty_data)
        signals = vwap_signals + v4_signals
        logger.info("V3: TRENDING_DOWN — VWAP_MR=%d, V4=%d signals", len(vwap_signals), len(v4_signals))
    else:
        logger.info("V3: STAY_FLAT — regime=%s, no strategies active", regime)
        funnel.log_stage("strategies_skipped", 0, drop_reasons={"regime_no_trade": 1})
        funnel.write_daily_json()
        return {"halted": False, "regime": regime, "reason": f"stay_flat_{regime}",
                "trades_placed": 0, "fallback_triggered": False}

    funnel.log_stage("strategy_signals", len(signals))

    # ── Step 7b: DUP-GUARD 2026-10-12 — never re-enter a symbol already OPEN today ──
    # (Found live: DMART+LENSKART entered twice in consecutive cycles, doubling exposure.)
    try:
        _conn_dup = sqlite3.connect(db_path)
        _open_syms = {row[0] for row in _conn_dup.execute(
            "SELECT DISTINCT symbol FROM intraday_trades WHERE trade_date=? AND status='OPEN'",
            (today,),
        ).fetchall()}
        _conn_dup.close()
    except Exception as _exc:
        logger.warning("V3: dup-guard DB check failed (%s) — proceeding without filter", _exc)
        _open_syms = set()
    if _open_syms:
        _before = len(signals)
        signals = [s for s in signals if s.get("symbol") not in _open_syms]
        if _before != len(signals):
            logger.info("V3: dup-guard dropped %d signal(s) already OPEN today: %s",
                        _before - len(signals), _open_syms & {s.get("symbol") for s in signals} or _open_syms)

    # ── Step 7c: DAILY CAPS 2026-10-14 — enforce max_trades_per_day + daily_capital_limit ──
    # (Bug 5 class: V3 had NO trade-count/capital enforcement. Real-money safety.)
    _intra = cfg.get("intraday", {})
    _max_trades = int(_intra.get("max_trades_per_day", 3))
    _daily_cap = float(_intra.get("daily_capital_limit", 0) or 0)
    try:
        _c = sqlite3.connect(db_path)
        _rows = _c.execute(
            "SELECT entry_price, quantity FROM intraday_trades "
            "WHERE trade_date=? AND status NOT IN ('REJECTED','CANCELLED','REJECTED_BAD_DATA','REJECTED_DUPLICATE','FAILED','ABANDONED')",
            (today,),
        ).fetchall()
        _c.close()
    except Exception as _exc:
        logger.error("V3: daily-cap DB read failed (%s) — HALTING for safety", _exc)
        funnel.write_daily_json()
        return {"halted": True, "reason": "cap_check_db_fail", "regime": regime, "trades_placed": 0}

    _trades_today = len(_rows)
    _deployed = sum((float(r[0] or 0) * int(r[1] or 0)) for r in _rows)
    _slots_left = max(0, _max_trades - _trades_today)
    _cap_left = (_daily_cap - _deployed) if _daily_cap > 0 else float("inf")
    logger.info("V3 caps: trades %d/%d, deployed Rs.%.0f/%.0f, slots_left=%d",
                _trades_today, _max_trades, _deployed, _daily_cap, _slots_left)
    if _slots_left <= 0:
        logger.info("V3: max_trades_per_day (%d) reached — no new entries", _max_trades)
        funnel.write_daily_json()
        return {"halted": False, "reason": "max_trades_reached", "regime": regime, "trades_placed": 0}
    if _cap_left <= 0:
        logger.info("V3: daily_capital_limit (Rs.%.0f) reached — no new entries", _daily_cap)
        funnel.write_daily_json()
        return {"halted": False, "reason": "capital_limit_reached", "regime": regime, "trades_placed": 0}

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
    _v3_db = None
    if not dry_run:
        try:
            from database.db_manager import DBManager
            _v3_db = DBManager(db_path)
        except Exception as _dbexc:
            logger.error("V3: could not open DB for trade recording: %s", _dbexc)
    _v3_mode = "PAPER" if cfg.get("profile", {}).get("paper", False) else "LIVE"
    # Enforce remaining-slot cap: never place more than slots_left this cycle
    if len(top_3) > _slots_left:
        logger.info("V3: capping entries %d -> %d (slots_left)", len(top_3), _slots_left)
        top_3 = top_3[:_slots_left]
    exec_result = place_v3_orders(broker, top_3, dry_run=dry_run,
                                  db=_v3_db, profile=profile, mode=_v3_mode)
    orders_placed = exec_result["placed"]

    funnel.log_stage("orders_placed", orders_placed)

    # ── Step 11b: RECORD PLACED TRADES TO DB (was MISSING — trades_placed logged
    #     but never persisted; dashboard/DB always showed 0 despite real signals) ──
    if orders_placed > 0:
        _now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            _conn = sqlite3.connect(db_path)
            for _d in exec_result.get("details", []):
                if _d.get("status") != "PLACED":
                    continue
                _sym = _d.get("symbol", "?")
                _setup = next((s for s in top_3 if s.get("symbol") == _sym), {})
                # KEY-FIX 2026-10-12: signal dicts use target_price/stop_loss_price/
                # confidence_score/strategy_type, NOT target/stop_loss/confidence/strategy.
                # Previous version silently wrote 0.0 for target+SL on every trade.
                _target = _setup.get("target_price", _d.get("target", 0))
                _sl = _setup.get("stop_loss_price", _d.get("stop_loss", 0))
                _conf = _setup.get("confidence_score", _setup.get("confidence", 0))
                _strat = _setup.get("strategy_type", _setup.get("strategy", regime))
                _conn.execute(
                    "INSERT INTO intraday_trades "
                    "(trade_date, timestamp, symbol, tradingsymbol, action, order_type, "
                    " product_type, quantity, price, broker_order_id, broker_name, status, "
                    " entry_price, target_price, stop_loss_price, confidence_score, "
                    " strategy_type, rationale, mode) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        today, _now_str, _sym, _sym,
                        _setup.get("direction", "LONG"), "LIMIT", "INTRADAY",
                        _d.get("filled_qty", 0), _d.get("entry_price", 0),
                        _d.get("entry_order_id", ""), "dhan", "OPEN",
                        _d.get("entry_price", 0), _target, _sl,
                        _conf, _strat,
                        _setup.get("rationale", ""), "PAPER" if cfg.get("profile", {}).get("paper") else "LIVE",
                    ),
                )
            _conn.commit()
            _conn.close()
            logger.info("V3: recorded %d PLACED trade(s) to DB", orders_placed)
        except Exception as _exc:
            logger.error("V3: FAILED to record trades to DB: %s", _exc)

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
