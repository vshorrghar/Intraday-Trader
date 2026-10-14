"""V3 Intraday Monitor - the exit half of the strategy.

Loads OPEN intraday positions, checks each against target/SL on current LTP,
places the exit, writes the close with direction-aware P&L. Force-exits 15:15 IST.

Pricing uses a SEPARATE read-only data broker - in paper the execution broker
is a PaperWrapper that simulates fills (mirrors swing/monitor.py pattern).

Single writer: updates existing rows via update_intraday_trade. Never INSERTs
(orchestrator owns entries). No orphan SL (paper simulates fills; a real-money
port must cancel any resting SL before market exit).
"""
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("v3.monitor")
IST = timezone(timedelta(hours=5, minutes=30))
FORCE_EXIT_HHMM = (15, 15)
NONTERMINAL = {"OPEN", "PARTIAL_BOOKED", "PENDING"}

def _load_security_ids():
    try:
        p = Path("config/nse_security_ids.json")
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception as e:
        logger.warning("sec id map load failed: %s", e)
        return {}

def _ltp(price_broker, sec_id):
    from intraday.v3.dhan_data import fetch_bulk_ltp
    for attempt in range(2):
        q = (fetch_bulk_ltp(price_broker, [str(sec_id)]) or {}).get(str(sec_id), {})
        v = float(q.get("ltp", 0) or 0) or float(q.get("close", 0) or 0)
        if v > 0:
            return v
        if attempt == 0:
            time.sleep(1.5)
    return 0.0

def _charges(entry, exit_, qty):
    bv, sv = entry * qty, exit_ * qty
    return round(40.0 + sv * 0.00025 + (bv + sv) * 0.0000325 + 40.0 * 0.18, 2)

def run_v3_monitor(profile, dry_run=False):
    import yaml
    from database.db_manager import DBManager
    from intraday.v3.safety import poll_exit_fill
    from intraday.auth_server import authenticate_broker

    cfg = yaml.safe_load((Path("config/profiles") / f"{profile}.yaml").read_text())
    db_path = cfg.get("database", {}).get("path", f"database/{profile}.db")
    is_paper = cfg.get("profile", {}).get("paper", False)
    db = DBManager(db_path)

    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    force = (now.hour, now.minute) >= FORCE_EXIT_HHMM

    try:
        price_broker = authenticate_broker("dhan", cfg.get("dhan", {}),
                                           dry_run=False, profile=profile)
    except Exception as e:
        logger.error("price broker auth failed for %s: %s", profile, e)
        return {"error": "price_auth_failed", "detail": str(e)}

    exec_broker = price_broker
    if is_paper:
        from intraday.v3.paper_broker_wrapper import wrap_broker_for_paper
        exec_broker = wrap_broker_for_paper(price_broker)

    secmap = _load_security_ids()
    opens = [t for t in (db.get_trades_for_date(today) or [])
             if (t.get("status") or "").upper() in NONTERMINAL]
    logger.info("V3 monitor: %d open position(s), force_exit=%s", len(opens), force)

    result = {"checked": 0, "exits": 0, "force": force, "details": []}
    for t in opens:
        result["checked"] += 1
        sym = t.get("symbol", "")
        direction = "LONG" if (t.get("action", "BUY") in ("BUY", "LONG")) else "SHORT"
        entry = float(t.get("entry_price") or 0)
        target = float(t.get("target_price") or 0)
        sl = float(t.get("stop_loss_price") or 0)
        qty = int(t.get("quantity") or 0)
        sec_id = secmap.get(sym.upper())
        if not sec_id or entry <= 0 or qty <= 0:
            logger.warning("skip %s: missing sec_id/entry/qty", sym)
            continue

        ltp = _ltp(price_broker, sec_id)
        if ltp <= 0:
            logger.warning("no LTP for %s - skip this cycle", sym)
            continue

        reason = None
        if direction == "LONG":
            if target > 0 and ltp >= target:
                reason = "TARGET_HIT"
            elif sl > 0 and ltp <= sl:
                reason = "SL_HIT"
        else:
            if target > 0 and ltp <= target:
                reason = "TARGET_HIT"
            elif sl > 0 and ltp >= sl:
                reason = "SL_HIT"
        if not reason and force:
            reason = "FORCE_EXIT"
        if not reason:
            logger.info("HOLD %s: ltp=%.2f T=%.2f SL=%.2f", sym, ltp, target, sl)
            continue

        exit_side = "SELL" if direction == "LONG" else "BUY"
        if dry_run:
            logger.info("[DRY] would exit %s %s x%d @ %.2f (%s)", exit_side, sym, qty, ltp, reason)
            result["details"].append({"symbol": sym, "reason": reason, "ltp": ltp, "dry": True})
            continue

        try:
            r = exec_broker.place_order(symbol=sym, exchange="NSE",
                                        transaction_type=exit_side, order_type="MARKET",
                                        product_type="INTRADAY", quantity=qty, price=ltp)
            oid = r.get("broker_order_id", "") if isinstance(r, dict) else ""
        except Exception as e:
            logger.error("exit order FAILED %s: %s - leaving OPEN", sym, e)
            continue

        fill = ltp
        if not is_paper and oid:
            pf = poll_exit_fill(exec_broker, oid, qty)
            if pf > 0:
                fill = pf

        gross = (fill - entry) * qty if direction == "LONG" else (entry - fill) * qty
        net = round(gross - _charges(entry, fill, qty), 2)
        status = {"TARGET_HIT": "CLOSED", "SL_HIT": "STOPPED_OUT",
                  "FORCE_EXIT": "FORCE_EXITED"}[reason]
        db.update_intraday_trade(t["id"], status=status, exit_price=fill, pnl=net)
        result["exits"] += 1
        result["details"].append({"symbol": sym, "reason": reason, "exit": fill, "pnl": net})
        logger.info("EXIT %s %s @ %.2f | %s | P&L Rs.%.2f", sym, reason, fill, status, net)

    return result
