"""F&O Risk Manager — margin, position limits, loss caps, VIX control.

Enforces SPAN + exposure margin estimation, max_positions, max_lots_per_trade,
daily_loss_limit, VIX-based session control, and naked selling margin checks.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.models import FnOStrategySetup
    from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class FnO_Risk_Manager:
    """Enforces all F&O risk management rules."""

    def __init__(
        self,
        config: FnO_Config,
        db: DBManager,
        broker: BrokerClient | None = None,
        paper_engine: Any = None,
    ) -> None:
        self.config = config
        self.db = db
        self.broker = broker
        self.paper_engine = paper_engine
        self._daily_realized_loss: float = 0.0
        self._loss_cap_breached: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_strategy(
        self,
        strategy: FnOStrategySetup,
        vix: float | None = None,
        current_time: datetime | None = None,
    ) -> tuple[bool, str]:
        """Validate a strategy against all risk rules.

        Returns
        -------
        tuple[bool, str]
            (approved, reason) — True if approved, False with rejection reason.
        """
        now = current_time or datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        # 1. VIX-based session control
        if vix is not None:
            vix_result = self.check_vix_session(vix)
            if vix_result == "SKIP":
                return False, f"VIX {vix:.1f} > 1.5x threshold {self.config.vix_threshold} — session skipped"

        # 2. Daily loss cap
        self._load_daily_loss(today)
        if self._loss_cap_breached:
            return False, f"Daily loss cap ₹{self.config.daily_loss_limit} breached — no new orders"

        # 3. Check 80% warning
        unrealized = self._get_unrealized_loss(today)
        total_exposure = self._daily_realized_loss + unrealized
        if total_exposure >= 0.8 * self.config.daily_loss_limit:
            logger.warning(
                "⚠️ 80%% of daily loss cap reached: realized ₹%.0f + unrealized ₹%.0f = ₹%.0f / ₹%.0f",
                self._daily_realized_loss, unrealized, total_exposure,
                self.config.daily_loss_limit,
            )

        # 4. Position limits
        effective_max = self._effective_max_positions(vix)
        open_count = self._count_open_positions(today)
        if open_count >= effective_max:
            return False, f"Max positions reached: {open_count}/{effective_max}"

        # 5. Lot limits
        for leg in strategy.legs:
            if leg.num_lots > self.config.max_lots_per_trade:
                return False, f"Leg has {leg.num_lots} lots > max {self.config.max_lots_per_trade}"

        # 6. Margin check
        estimated_margin = self._estimate_margin(strategy)
        available = self._get_available_margin()
        if estimated_margin > available:
            return False, f"Margin ₹{estimated_margin:.0f} > available ₹{available:.0f}"

        # 7. Naked selling 2-sigma check
        if strategy.strategy_type in (
            "SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
            "NAKED_CE", "NAKED_PE",
        ):
            sigma2_margin = self._compute_2sigma_margin(strategy)
            if sigma2_margin > available:
                return False, (
                    f"Naked selling rejected — 2σ margin ₹{sigma2_margin:.0f} "
                    f"> available ₹{available:.0f}"
                )

        return True, "Approved"

    def check_vix_session(self, vix: float) -> str:
        """Check VIX-based session control.

        Returns
        -------
        str
            "SKIP" if VIX > 1.5x threshold (skip session entirely),
            "HALVE" if VIX > threshold (halve max_positions),
            "NORMAL" otherwise.
        """
        if vix > 1.5 * self.config.vix_threshold:
            logger.warning(
                "VIX %.1f > 1.5x threshold %.1f — SKIPPING session",
                vix, self.config.vix_threshold,
            )
            return "SKIP"
        if vix > self.config.vix_threshold:
            logger.warning(
                "VIX %.1f > threshold %.1f — halving max_positions",
                vix, self.config.vix_threshold,
            )
            return "HALVE"
        return "NORMAL"

    def on_loss_cap_breach(self) -> None:
        """Handle daily loss cap breach: cancel all pending, close all open."""
        self._loss_cap_breached = True
        logger.error("🚨 DAILY LOSS CAP BREACHED — closing all positions")

        now = datetime.now(IST)
        today = now.strftime("%Y-%m-%d")

        strategies = self.db.get_fno_strategies_for_date(today)
        for strat in strategies:
            status = strat.get("status", "")
            if status in ("OPEN", "PARTIAL_BOOKED", "PENDING"):
                self.db.update_fno_strategy(
                    strat["id"],
                    status="FORCE_EXITED",
                    exit_time=now.isoformat(),
                )

        self.db.insert_audit_log(
            "FNO_ERROR",
            json.dumps({
                "event": "DAILY_LOSS_CAP_BREACH",
                "realized_loss": self._daily_realized_loss,
                "limit": self.config.daily_loss_limit,
            }),
        )

    def update_realized_loss(self, pnl: float) -> None:
        """Update cumulative realized loss after a strategy closes."""
        if pnl < 0:
            self._daily_realized_loss += abs(pnl)

        if self._daily_realized_loss >= self.config.daily_loss_limit:
            self.on_loss_cap_breach()

    def persist_daily_loss(self) -> None:
        """Persist daily loss tracking state in DB for restart resilience."""
        today = datetime.now(IST).strftime("%Y-%m-%d")
        self.db.upsert_fno_daily_summary(
            today,
            total_realized_loss=self._daily_realized_loss,
        )

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _load_daily_loss(self, date_str: str) -> None:
        """Load daily realized loss from DB."""
        self._daily_realized_loss = self.db.get_fno_daily_realized_loss(date_str)
        if self._daily_realized_loss >= self.config.daily_loss_limit:
            self._loss_cap_breached = True

    def _get_unrealized_loss(self, date_str: str) -> float:
        """Get total unrealized loss from open positions."""
        strategies = self.db.get_fno_strategies_for_date(date_str)
        unrealized = 0.0
        for s in strategies:
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED"):
                # Use max_loss as worst-case unrealized
                unrealized += abs(float(s.get("max_loss", 0))) * 0.3  # 30% of max as estimate
        return unrealized

    def _effective_max_positions(self, vix: float | None) -> int:
        """Get effective max positions (halved if VIX > threshold)."""
        if vix is not None and vix > self.config.vix_threshold:
            return max(1, self.config.max_positions // 2)
        return self.config.max_positions

    def _count_open_positions(self, date_str: str) -> int:
        """Count open strategy positions for today."""
        strategies = self.db.get_fno_strategies_for_date(date_str)
        return sum(
            1 for s in strategies
            if s.get("status") in ("OPEN", "PARTIAL_BOOKED", "PENDING")
        )

    def _get_available_margin(self) -> float:
        """Get available margin from broker or paper engine."""
        if self.paper_engine:
            return self.paper_engine.available_margin
        if self.broker:
            try:
                margins = self.broker.get_fno_margins()
                return float(margins.get("available_margin", 0))
            except Exception:
                pass
        return self.config.daily_capital_limit

    @staticmethod
    def _estimate_margin(strategy: FnOStrategySetup) -> float:
        """Estimate SPAN + exposure margin for a strategy."""
        stype = strategy.strategy_type.upper()

        if stype in ("IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            return abs(strategy.max_loss) * 1.2

        if stype in ("SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
                      "NAKED_CE", "NAKED_PE"):
            return abs(strategy.max_loss) * 2.0

        return abs(strategy.net_premium)

    @staticmethod
    def _compute_2sigma_margin(strategy: FnOStrategySetup) -> float:
        """Compute margin needed to cover a 2-standard-deviation move.

        For naked selling, estimates the margin as:
        2σ move × lot_size × num_lots × 1.5 (safety factor)
        """
        if not strategy.legs:
            return 0.0

        # Use the first leg's lot_size and num_lots
        leg = strategy.legs[0]
        # Estimate 2σ daily move as ~3% of strike price
        avg_strike = sum(l.strike_price for l in strategy.legs) / len(strategy.legs)
        two_sigma_move = avg_strike * 0.03  # ~3% for 2σ daily
        margin = two_sigma_move * leg.lot_size * leg.num_lots * 1.5
        return margin
