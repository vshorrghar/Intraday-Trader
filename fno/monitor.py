"""F&O Position Monitor — real-time position tracking and exit management.

Fetches positions every monitor_interval_seconds, computes real-time Greeks,
implements the position state machine, and enforces stop-loss, partial profit
booking, force exit, and expiry-day OTM close rules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from fno.models import FnOPositionState, Greeks

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
        """Run one monitoring cycle.

        Fetches positions, computes Greeks, checks exit conditions,
        and updates DB.

        Returns
        -------
        dict
            Summary of actions taken: {"checked": int, "exits": int, "warnings": list}
        """
        now = current_time or datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        # Fetch open strategies from DB
        strategies = self.db.get_fno_strategies_for_date(today)
        open_strategies = [
            s for s in strategies
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED", "PENDING")
        ]

        if not open_strategies:
            return {"checked": 0, "exits": 0, "warnings": []}

        # Fetch current positions
        positions = self._fetch_positions()

        # Aggregate Greeks
        net_greeks = Greeks(delta=0, gamma=0, theta=0, vega=0)
        warnings: list[str] = []
        exits = 0

        for strat in open_strategies:
            strategy_id = strat["id"]
            status = strat["status"]

            # Get trades for this strategy
            trades = self._get_strategy_trades(today, strategy_id)

            # Compute current premium and P&L
            current_premium = self._compute_current_premium(strat, positions)
            entry_premium = float(strat.get("net_premium", 0))

            # Check state transitions
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

            # Update Greeks for open positions
            strat_greeks = self._compute_strategy_greeks(strat)
            net_greeks = Greeks(
                delta=net_greeks.delta + strat_greeks.delta,
                gamma=net_greeks.gamma + strat_greeks.gamma,
                theta=net_greeks.theta + strat_greeks.theta,
                vega=net_greeks.vega + strat_greeks.vega,
            )

        # Check Greeks exposure warnings
        if abs(net_greeks.delta) > self.config.max_delta_exposure:
            msg = f"Delta exposure {net_greeks.delta:.1f} exceeds limit {self.config.max_delta_exposure}"
            logger.warning(msg)
            warnings.append(msg)

        if abs(net_greeks.vega) > self.config.max_vega_exposure:
            msg = f"Vega exposure {net_greeks.vega:.1f} exceeds limit {self.config.max_vega_exposure}"
            logger.warning(msg)
            warnings.append(msg)

        # Log Greeks snapshot
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

        return {
            "checked": len(open_strategies),
            "exits": exits,
            "warnings": warnings,
        }

    def force_exit_all(self, current_time: datetime | None = None) -> int:
        """Force exit all open positions (at force_exit_time or on demand).

        Returns the number of strategies force-exited.
        """
        now = current_time or datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        strategies = self.db.get_fno_strategies_for_date(today)
        open_strategies = [
            s for s in strategies
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED")
        ]

        count = 0
        for strat in open_strategies:
            self._execute_exit(strat["id"], "FORCE_EXITED", 0, now)
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
            # Stop loss: premium moves 1.5x against collected
            sl_threshold = entry_premium * (1 + self.config.trailing_sl_trigger_pct / 100)
            if current_premium > sl_threshold:
                return "STOPPED_OUT"

        # 3. Partial profit booking
        if status == "OPEN" and max_profit > 0:
            # For selling strategies: profit = entry_premium - current_premium
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

        # 5. Expiry-day close — only after 3:30 PM on expiry day
        try:
            expiry_str = strat.get("trade_date", "")
            legs_json = json.loads(strat.get("legs_json", "[]"))
            if legs_json:
                expiry_date = legs_json[0].get("expiry_date", expiry_str)
                expiry_dt = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                if now.date() == expiry_dt and now.hour >= 15 and now.minute >= 30:
                    return "EXPIRED"
                # Past expiry date entirely
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
        """Compute current combined premium for a strategy.

        In paper mode, simulates premium movement using:
        - Theta decay: premium decays proportionally to time elapsed
        - Delta impact: spot movement affects premium via net delta
        - Random noise: small jitter for realism

        For live mode, would use actual position LTPs from broker.
        """
        entry_premium = abs(float(strat.get("net_premium", 0)))

        if not self.paper_engine:
            # Live mode: try to get from positions
            # TODO: implement live premium lookup
            return entry_premium

        # Paper mode: simulate premium decay
        import random

        # Get strategy metadata
        net_theta = float(strat.get("net_theta", 0))
        net_delta = float(strat.get("net_delta", 0))
        entry_time_str = strat.get("entry_time", "")

        # Calculate time elapsed since entry (in days)
        try:
            entry_time = datetime.fromisoformat(entry_time_str)
            now = datetime.now(IST)
            hours_elapsed = (now - entry_time).total_seconds() / 3600.0
            days_elapsed = hours_elapsed / 6.25  # 6.25 trading hours per day
        except Exception:
            days_elapsed = 0.1  # default small decay

        # Theta decay: for selling strategies, premium decreases over time
        # net_theta is daily theta (positive = earning theta per day for sellers)
        # Premium change from theta = -theta * days (premium goes down)
        theta_impact = abs(net_theta) * days_elapsed * 0.15  # Scale factor for realism

        # Delta impact: simulate small spot movement (random walk)
        # For iron condors near ATM, delta is small, so impact is minimal
        spot_noise = random.gauss(0, 0.3)  # Small random spot movement %
        delta_impact = abs(net_delta) * spot_noise * entry_premium * 0.01

        # Compute new premium (for selling strategies, premium should decay)
        strategy_type = strat.get("strategy_type", "").upper()
        is_selling = strategy_type in (
            "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
            "NAKED_CE", "NAKED_PE",
        )

        if is_selling:
            # For sold strategies: premium decays (good for seller)
            # current_premium < entry_premium = profit
            new_premium = entry_premium - theta_impact + delta_impact
            # Add small random noise (±2%)
            noise = random.uniform(-0.02, 0.02) * entry_premium
            new_premium += noise
            # Clamp: can't go below 0.05 or above 2x entry (catastrophic move)
            new_premium = max(0.05, min(new_premium, entry_premium * 2.0))
        else:
            # For bought strategies: premium decays (bad for buyer)
            new_premium = entry_premium - theta_impact + delta_impact
            noise = random.uniform(-0.02, 0.02) * entry_premium
            new_premium += noise
            new_premium = max(0.0, new_premium)

        return round(new_premium, 2)

    def _compute_strategy_greeks(self, strat: dict) -> Greeks:
        """Compute current Greeks for a strategy."""
        # Simplified: use stored Greeks
        return Greeks(
            delta=float(strat.get("net_delta", 0)),
            gamma=float(strat.get("net_gamma", 0)),
            theta=float(strat.get("net_theta", 0)),
            vega=float(strat.get("net_vega", 0)),
        )

    def _execute_exit(
        self, strategy_id: int, new_status: str, current_premium: float, now: datetime,
    ) -> None:
        """Execute an exit by updating the strategy status in DB with P&L."""
        # Compute realized P&L
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
            strategy_type = strat.get("strategy_type", "").upper()
            is_selling = strategy_type in (
                "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
                "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
                "NAKED_CE", "NAKED_PE",
            )
            if is_selling:
                # Seller profit = entry_premium - current_premium
                realized_pnl = entry_premium - current_premium
            else:
                # Buyer profit = current_premium - entry_premium
                realized_pnl = current_premium - entry_premium

            # Multiply by lot size (approximate from legs)
            try:
                legs = json.loads(strat.get("legs_json", "[]"))
                if legs:
                    num_lots = legs[0].get("num_lots", 1)
                    # Approximate lot multiplier
                    realized_pnl *= num_lots
            except Exception:
                pass

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

    @staticmethod
    def _is_valid_transition(current: str, target: str) -> bool:
        """Check if a state transition is valid."""
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed
