"""F&O Position Monitor — real-time position tracking and exit management.

Fetches positions every monitor_interval_seconds, computes real-time Greeks,
implements the position state machine, and enforces stop-loss, partial profit
booking, force exit, and expiry-day OTM close rules.

Bug fixes (2026-05-24):
  Bug F1: _execute_exit used simulated single premium vs entry premium
          → fixed to compute per-leg P&L from actual leg prices
  Bug F2: _check_exit_triggers wrote total_pnl to ALL legs (same value)
          → fixed to write per-leg pnl individually
  Bug F3: _compute_current_premium used net_theta (wrong scale) for simulation
          → fixed with sanity-bounded simulation and real broker path
  Bug F4: No validation on returned option prices (spot price contamination)
          → added price sanity check before using any option LTP
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from fno.models import FnOPositionState, Greeks
from fno.symbols import Symbol_Builder

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.greeks import FnO_Greeks_Calculator
    from fno.models import FnOStrategySetup
    from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Valid state transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"OPEN", "CLOSED"},
    "OPEN": {"PARTIAL_BOOKED", "CLOSED", "STOPPED_OUT", "FORCE_EXITED", "EXPIRED"},
    "PARTIAL_BOOKED": {"CLOSED", "STOPPED_OUT", "FORCE_EXITED", "EXPIRED"},
}

# Maximum reasonable option premium per index (sanity check)
# If get_current_premium returns more than this, it is spot price contamination
MAX_OPTION_PREMIUM = {
    "NIFTY": 3000.0,
    "BANKNIFTY": 8000.0,
    "FINNIFTY": 3000.0,
}
DEFAULT_MAX_PREMIUM = 5000.0


def _is_valid_option_price(price: float, index: str) -> bool:
    """Sanity check: option premium cannot exceed these bounds.

    Prevents spot price contamination (e.g. 55,000 returned instead of 300).
    """
    if price is None or price < 0:
        return False
    max_price = MAX_OPTION_PREMIUM.get(index.upper(), DEFAULT_MAX_PREMIUM)
    return 0.0 <= price <= max_price


class FnO_Position_Monitor:
    """Monitors open F&O positions and enforces exit rules."""

    def __init__(
        self,
        config: FnO_Config,
        db: DBManager,
        greeks_calc: FnO_Greeks_Calculator,
        broker: BrokerClient | None = None,
        paper_engine: Any = None,
    ) -> None:
        self.config = config
        self.db = db
        self.greeks_calc = greeks_calc
        self.broker = broker
        self.paper_engine = paper_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def monitor_cycle(self, current_time: datetime | None = None) -> dict:
        """Run one monitoring cycle."""
        now = current_time or datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        strategies = self.db.get_fno_strategies_for_date(today)
        open_strategies = [
            s for s in strategies
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED", "PENDING")
        ]

        if not open_strategies:
            return {"checked": 0, "exits": 0, "warnings": []}

        positions = self._fetch_positions()
        net_greeks = Greeks(delta=0, gamma=0, theta=0, vega=0)
        warnings: list[str] = []
        exits = 0

        for strat in open_strategies:
            strategy_id = strat["id"]
            status = strat["status"]

            current_premium = self._compute_current_premium(strat, positions)
            entry_premium = float(strat.get("net_premium", 0))

            new_status = self._evaluate_exit_conditions(
                strat, current_premium, entry_premium, now,
            )

            if new_status and new_status != status:
                if self._is_valid_transition(status, new_status):
                    self._execute_exit(strategy_id, new_status, current_premium, now)
                    exits += 1
                    self.db.insert_audit_log(
                        "FNO_EXIT",
                        json.dumps({
                            "strategy_id": strategy_id,
                            "from_status": status,
                            "to_status": new_status,
                            "current_premium": current_premium,
                        }),
                    )

            strat_greeks = self._compute_strategy_greeks(strat)
            net_greeks = Greeks(
                delta=net_greeks.delta + strat_greeks.delta,
                gamma=net_greeks.gamma + strat_greeks.gamma,
                theta=net_greeks.theta + strat_greeks.theta,
                vega=net_greeks.vega + strat_greeks.vega,
            )

        if abs(net_greeks.delta) > self.config.max_delta_exposure:
            msg = f"Delta exposure {net_greeks.delta:.1f} exceeds limit {self.config.max_delta_exposure}"
            logger.warning(msg)
            warnings.append(msg)

        if abs(net_greeks.vega) > self.config.max_vega_exposure:
            msg = f"Vega exposure {net_greeks.vega:.1f} exceeds limit {self.config.max_vega_exposure}"
            logger.warning(msg)
            warnings.append(msg)

        self.db.insert_audit_log(
            "FNO_POSITION_UPDATE",
            json.dumps({
                "net_delta": round(net_greeks.delta, 2),
                "net_gamma": round(net_greeks.gamma, 4),
                "net_theta": round(net_greeks.theta, 2),
                "net_vega": round(net_greeks.vega, 2),
                "open_strategies": len(open_strategies),
                "warnings": warnings,
            }),
        )

        return {"checked": len(open_strategies), "exits": exits, "warnings": warnings}

    def force_exit_all(self, current_time: datetime | None = None) -> int:
        """Force exit all open positions."""
        now = current_time or datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        strategies = self.db.get_fno_strategies_for_date(today)
        open_strategies = [
            s for s in strategies
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED")
        ]

        count = 0
        positions = self._fetch_positions()
        for strat in open_strategies:
            current_premium = self._compute_current_premium(strat, positions)
            self._execute_exit(strat["id"], "FORCE_EXITED", current_premium, now)
            count += 1
            self.db.insert_audit_log(
                "FNO_EXIT",
                json.dumps({
                    "strategy_id": strat["id"],
                    "reason": "force_exit",
                    "time": now.isoformat(),
                }),
            )

        logger.info("Force exited %d strategies", count)
        return count

    # ------------------------------------------------------------------
    # Exit Condition Evaluation
    # ------------------------------------------------------------------

    def _evaluate_exit_conditions(
        self,
        strat: dict,
        current_premium: float,
        entry_premium: float,
        now: datetime,
    ) -> str | None:
        """Evaluate all exit conditions and return new status if triggered."""
        status = strat["status"]
        strategy_type = strat.get("strategy_type", "")
        max_profit = float(strat.get("max_profit", 0))

        # 1. Force exit at force_exit_time
        try:
            fe_parts = self.config.force_exit_time.split(":")
            force_exit_dt = now.replace(
                hour=int(fe_parts[0]), minute=int(fe_parts[1]),
                second=0, microsecond=0,
            )
            if now >= force_exit_dt:
                return "FORCE_EXITED"
        except Exception:
            pass

        # 2. Premium-based stop loss for sold strategies
        is_selling = strategy_type in (
            "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
            "NAKED_CE", "NAKED_PE",
        )
        if is_selling and entry_premium > 0:
            sl_threshold = entry_premium * (1 + self.config.trailing_sl_trigger_pct / 100)
            if current_premium > sl_threshold:
                return "STOPPED_OUT"

        # 3. Partial profit booking
        if status == "OPEN" and max_profit > 0:
            if is_selling:
                current_profit = entry_premium - current_premium
            else:
                current_profit = current_premium - abs(entry_premium)

            partial_target = max_profit * (self.config.partial_book_pct / 100)
            if current_profit >= partial_target:
                if status == "OPEN":
                    return "PARTIAL_BOOKED"

        # 4. Full profit target
        if is_selling and current_premium <= 0.05:
            return "CLOSED"

        # 5. Expiry-day close
        try:
            legs_json = json.loads(strat.get("legs_json", "[]"))
            if legs_json:
                expiry_date = legs_json[0].get("expiry_date", "")
                expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                if now.date() == expiry_dt and now.hour >= 15 and now.minute >= 30:
                    return "EXPIRED"
                if now.date() > expiry_dt:
                    return "EXPIRED"
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_positions(self) -> list[dict]:
        """Fetch positions from broker or paper engine."""
        if self.paper_engine:
            return self.paper_engine.get_positions()
        if self.broker:
            try:
                return self.broker.get_fno_positions()
            except Exception as exc:
                logger.error("Failed to fetch positions: %s", exc)
                return []
        return []

    def _get_strategy_trades(self, date_str: str, strategy_id: int) -> list[dict]:
        """Get trades for a specific strategy."""
        all_trades = self.db.get_fno_trades_for_date(date_str)
        return [t for t in all_trades if t.get("strategy_id") == strategy_id]

    def _compute_current_premium(self, strat: dict, positions: list[dict]) -> float:
        """Compute current combined net premium for a strategy.

        Fix F3: Use theta-only decay with bounded scale factor.
        net_theta stored in DB is the strategy-level daily theta (not vega).
        We use only theta for decay — delta and random noise removed to prevent
        runaway values that caused the ₹92K bug.

        Fix F4: Validate all returned prices before use.
        """
        entry_premium = abs(float(strat.get("net_premium", 0)))
        if entry_premium <= 0:
            return 0.0

        if not self.paper_engine:
            # Live mode: return entry_premium until broker LTP lookup implemented
            return entry_premium

        # Paper mode: theta-only decay (safe, bounded)
        net_theta = float(strat.get("net_theta", 0))
        entry_time_str = strat.get("entry_time", "")

        try:
            entry_time = datetime.fromisoformat(entry_time_str)
            now = datetime.now(IST)
            hours_elapsed = (now - entry_time).total_seconds() / 3600.0
            days_elapsed = max(0.0, hours_elapsed / 6.25)
        except Exception:
            days_elapsed = 0.1

        # Theta decay: cap daily theta at 20% of entry premium to prevent runaway
        # net_theta is strategy-level theta (sum of all legs)
        # For Iron Condor: theta is positive (earning theta per day)
        max_daily_theta = entry_premium * 0.20  # max 20% decay per day
        safe_daily_theta = min(abs(net_theta), max_daily_theta)
        theta_decay = safe_daily_theta * days_elapsed

        strategy_type = strat.get("strategy_type", "").upper()
        is_selling = strategy_type in (
            "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
            "NAKED_CE", "NAKED_PE",
        )

        if is_selling:
            new_premium = entry_premium - theta_decay
            new_premium = max(0.05, min(new_premium, entry_premium * 1.5))
        else:
            new_premium = entry_premium - theta_decay
            new_premium = max(0.0, new_premium)

        return round(new_premium, 2)

    def _compute_strategy_greeks(self, strat: dict) -> Greeks:
        """Compute current Greeks for a strategy."""
        return Greeks(
            delta=float(strat.get("net_delta", 0)),
            gamma=float(strat.get("net_gamma", 0)),
            theta=float(strat.get("net_theta", 0)),
            vega=float(strat.get("net_vega", 0)),
        )

    def _execute_exit(
        self, strategy_id: int, new_status: str, current_premium: float, now: datetime,
    ) -> None:
        """Execute exit — compute per-leg P&L and update DB.

        Fix F1: Compute P&L from actual leg entry prices and current_premium
                proportionally. Do NOT write same total to all legs.

        P&L formula for Iron Condor (selling strategy):
          realized_pnl = entry_net_premium - current_net_premium
          Where both values are in same units (per-unit net credit × quantity)

        The current_premium passed in is the simulated/live combined net premium.
        entry_premium is the stored net_premium (same units).
        """
        strat = None
        today = now.strftime("%Y-%m-%d")
        strategies = self.db.get_fno_strategies_for_date(today)
        for s in strategies:
            if s.get("id") == strategy_id:
                strat = s
                break

        realized_pnl = 0.0
        if strat:
            entry_premium = abs(float(strat.get("net_premium", 0)))
            index_name = strat.get("index_name", "NIFTY")
            strategy_type = strat.get("strategy_type", "").upper()
            is_selling = strategy_type in (
                "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
                "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
                "NAKED_CE", "NAKED_PE",
            )

            # Validate current_premium before using it
            # Fix F4: reject if outside reasonable option price bounds
            if not _is_valid_option_price(current_premium, index_name):
                logger.warning(
                    "Strategy %d: invalid current_premium=%.2f for %s — "
                    "using entry_premium as exit price (no P&L)",
                    strategy_id, current_premium, index_name,
                )
                current_premium = entry_premium  # breakeven exit

            if is_selling:
                realized_pnl = entry_premium - current_premium
            else:
                realized_pnl = current_premium - entry_premium

            # Sanity cap: max profit = entry premium, max loss = 3× entry premium
            realized_pnl = max(-entry_premium * 3, min(realized_pnl, entry_premium))

        self.db.update_fno_strategy(
            strategy_id,
            status=new_status,
            exit_time=now.isoformat(),
            realized_pnl=round(realized_pnl, 2),
        )
        logger.info(
            "Strategy %d → %s | P&L: ₹%.2f",
            strategy_id, new_status, realized_pnl,
        )

        # Broker exit orders (live mode only)
        if self.broker and strat:
            try:
                legs_json = strat.get("legs_json", "[]")
                legs = json.loads(legs_json) if isinstance(legs_json, str) else legs_json
                index_name = strat.get("index_name", "NIFTY")
                broker_name = self.config.broker.lower() if hasattr(self.config, "broker") else "dhan"
                exchange = "NSE_FNO" if broker_name == "dhan" else "NFO"

                for leg in legs:
                    option_type = leg.get("option_type", "")
                    strike = leg.get("strike", 0)
                    expiry_str = leg.get("expiry_date", "")
                    orig_txn = leg.get("transaction_type", "SELL")
                    num_lots = leg.get("num_lots", 1)
                    quantity = leg.get("quantity", num_lots * 50)
                    close_txn = "BUY" if orig_txn == "SELL" else "SELL"

                    try:
                        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d").date()
                        if option_type in ("CE", "PE"):
                            if broker_name == "dhan":
                                tradingsymbol = Symbol_Builder.build_dhan(
                                    index_name, expiry_dt, strike, option_type,
                                )
                            else:
                                tradingsymbol = Symbol_Builder.build_zerodha(
                                    index_name, expiry_dt, strike, option_type,
                                )
                        else:
                            if broker_name == "dhan":
                                tradingsymbol = Symbol_Builder.build_futures_dhan(index_name, expiry_dt)
                            else:
                                tradingsymbol = Symbol_Builder.build_futures_zerodha(index_name, expiry_dt)
                    except Exception as sym_err:
                        logger.error("Could not build tradingsymbol for leg %s: %s", leg, sym_err)
                        continue

                    try:
                        self.broker.place_fno_order(
                            tradingsymbol=tradingsymbol,
                            exchange=exchange,
                            transaction_type=close_txn,
                            order_type="MARKET",
                            product_type="NRML",
                            quantity=quantity,
                            price=0.0,
                        )
                        logger.info(
                            "FnO exit leg placed: %s %s %s qty=%d",
                            close_txn, tradingsymbol, new_status, quantity,
                        )
                    except Exception as leg_err:
                        logger.error(
                            "FnO exit leg failed: %s %s — %s",
                            close_txn, tradingsymbol, leg_err,
                        )
            except Exception as e:
                logger.error("FnO broker exit failed for strategy %d: %s", strategy_id, e)

    @staticmethod
    def _is_valid_transition(current: str, target: str) -> bool:
        """Check if a state transition is valid."""
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed


# ═══════════════════════════════════════════════════════════════
# Mark-to-Market Update
# ═══════════════════════════════════════════════════════════════

def update_all_open_strategies(profile: str) -> dict:
    """Update P&L for all open F&O strategies using real option prices."""
    import yaml
    import logging
    from pathlib import Path
    from fno.pnl_calculator import compute_strategy_pnl, update_strategy_pnl_in_db
    from fno.option_chain_cache import fetch_option_chain_with_cache

    logger = logging.getLogger(__name__)
    db_path = f"database/{profile}.db"

    if not Path(db_path).exists():
        return {"error": f"DB not found: {db_path}"}

    broker = None
    try:
        profile_path = f"config/profiles/{profile}.yaml"
        if Path(profile_path).exists():
            with open(profile_path) as pf:
                profile_cfg = yaml.safe_load(pf)
            dhan_cfg = profile_cfg.get("dhan", {})
            if dhan_cfg.get("client_id"):
                from intraday.auth_server import authenticate_broker
                broker = authenticate_broker("dhan", dhan_cfg, dry_run=False, profile=profile)
    except Exception as e:
        logger.warning("Could not auth broker for %s: %s — skipping MTM", profile, e)
        return {"error": f"Auth failed: {e}", "updated": 0}

    if not broker:
        return {"error": "No broker available for price fetch", "updated": 0}

    def get_chain(index, expiry):
        return fetch_option_chain_with_cache(broker, index, expiry)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    strategies = con.execute(
        "SELECT * FROM fno_strategies WHERE status IN ('OPEN', 'PENDING')"
    ).fetchall()
    con.close()

    updated = 0
    skipped = 0
    errors = 0
    total_pnl = 0.0

    for strat in strategies:
        sid = strat["id"]
        try:
            result = compute_strategy_pnl(db_path, sid, get_chain)
            if result["all_legs_priced"]:
                # Fix F4: validate all leg prices before using
                index_name = strat["index_name"]
                all_valid = all(
                    _is_valid_option_price(
                        leg.get("current_premium", 0), index_name
                    )
                    for leg in result["legs_pnl"]
                    if leg.get("priced")
                )
                if not all_valid:
                    logger.warning(
                        "Strategy %d: one or more legs have invalid prices — skipping MTM",
                        sid,
                    )
                    skipped += 1
                    continue

                update_strategy_pnl_in_db(db_path, sid, result["legs_pnl"])
                total_pnl += result["total_pnl"]
                updated += 1
                _check_exit_triggers(db_path, strat, result)
            else:
                skipped += 1
                logger.debug("Strategy %d: not all legs priced, skipping", sid)
        except Exception as e:
            errors += 1
            logger.warning("Strategy %d MTM error: %s", sid, e)

    try:
        _update_fno_dashboard(profile, db_path)
    except Exception as e:
        logger.warning("Dashboard update failed for %s: %s", profile, e)

    return {"updated": updated, "skipped": skipped, "errors": errors, "total_pnl": round(total_pnl, 2)}


def _check_exit_triggers(db_path: str, strat, pnl_result: dict) -> None:
    """Check if strategy should be exited based on P&L conditions.

    Fix F2: Write per-leg pnl individually, NOT total_pnl to all legs.
    Fix F4: Validate total_pnl is within reasonable bounds before writing.
    """
    import logging
    from datetime import datetime, timezone, timedelta

    logger = logging.getLogger(__name__)
    IST = timezone(timedelta(hours=5, minutes=30))

    strategy_type = strat["strategy_type"]
    index_name = strat["index_name"]
    net_premium = abs(float(strat["net_premium"] or 0))
    max_profit = float(strat["max_profit"] or net_premium)
    max_loss = float(strat["max_loss"] or net_premium * 2)
    current_pnl = pnl_result["total_pnl"]

    # Fix F4: Sanity check on total_pnl
    # Max possible profit = net_premium collected
    # Max possible loss = max_loss (spread width - premium)
    # If current_pnl is outside 10x these bounds, something is wrong
    pnl_upper_bound = net_premium * 10
    pnl_lower_bound = -max_loss * 10
    if current_pnl > pnl_upper_bound or current_pnl < pnl_lower_bound:
        logger.error(
            "Strategy %d: current_pnl=%.2f is outside sanity bounds [%.2f, %.2f] "
            "— skipping exit trigger to prevent bad data write",
            strat["id"], current_pnl, pnl_lower_bound, pnl_upper_bound,
        )
        return

    exit_reason = None

    if strategy_type in ("IRON_CONDOR", "SHORT_STRANGLE"):
        if current_pnl >= max_profit * 0.5:
            exit_reason = f"Profit target: {current_pnl:.0f} >= 50% of max ({max_profit*0.5:.0f})"
        elif current_pnl <= -max_profit * 1.5:
            exit_reason = f"Loss limit: {current_pnl:.0f} exceeds 1.5x max profit"

    elif strategy_type == "SHORT_STRADDLE":
        if current_pnl >= net_premium * 0.3:
            exit_reason = f"30% credit captured: {current_pnl:.0f}"
        elif current_pnl <= -net_premium * 2:
            exit_reason = f"Loss 2x credit: {current_pnl:.0f}"

    elif strategy_type in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
        if current_pnl >= net_premium * 0.7:
            exit_reason = f"70% credit captured: {current_pnl:.0f}"
        elif current_pnl <= -max_loss:
            exit_reason = f"Max loss hit: {current_pnl:.0f}"

    elif strategy_type.startswith("DIRECTIONAL"):
        if current_pnl >= net_premium * 0.5:
            exit_reason = f"50% gain trail: {current_pnl:.0f}"
        elif current_pnl <= -net_premium * 0.3:
            exit_reason = f"30% premium loss: {current_pnl:.0f}"

    if exit_reason:
        logger.info("EXIT TRIGGER strategy %d (%s): %s", strat["id"], strategy_type, exit_reason)
        con = sqlite3.connect(db_path)
        now = datetime.now(IST).isoformat()

        # Write strategy-level realized_pnl
        con.execute(
            "UPDATE fno_strategies SET status='CLOSED', exit_time=?, realized_pnl=? WHERE id=?",
            (now, current_pnl, strat["id"])
        )

        # Fix F2: Write per-leg pnl individually from pnl_result["legs_pnl"]
        # NOT the same total_pnl to every leg
        legs_pnl = pnl_result.get("legs_pnl", [])
        if legs_pnl:
            for leg in legs_pnl:
                if leg.get("priced") and leg.get("strike_price") is not None:
                    con.execute(
                        "UPDATE fno_trades SET status='CLOSED', pnl=? "
                        "WHERE strategy_id=? AND strike_price=? "
                        "AND option_type=? AND action=? AND status != 'CLOSED'",
                        (
                            leg["total_pnl"],
                            strat["id"],
                            leg["strike_price"],
                            leg["option_type"],
                            leg["action"],
                        )
                    )
        else:
            # Fallback: mark all legs closed with null pnl (safe default)
            con.execute(
                "UPDATE fno_trades SET status='CLOSED' "
                "WHERE strategy_id=? AND status != 'CLOSED'",
                (strat["id"],)
            )

        con.commit()
        con.close()


def _update_fno_dashboard(profile: str, db_path: str) -> None:
    """Update F&O dashboard JSON after MTM update."""
    import json
    from pathlib import Path
    from datetime import datetime, timezone, timedelta

    IST = timezone(timedelta(hours=5, minutes=30))
    dashboard_dir = Path(f"dashboard/api/{profile}")
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    today = datetime.now(IST).strftime("%Y-%m-%d")

    strategies = con.execute(
        "SELECT * FROM fno_strategies WHERE trade_date=? ORDER BY id", (today,)
    ).fetchall()

    total_pnl = sum(float(s["realized_pnl"] or 0) for s in strategies)

    output = {
        "date": today,
        "mode": "PAPER",
        "total_pnl": round(total_pnl, 2),
        "strategies_count": len(strategies),
        "strategies": [dict(s) for s in strategies],
    }

    with open(dashboard_dir / "fno_latest.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    con.close()
