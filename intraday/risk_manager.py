"""Risk manager for the intraday auto-trader.

Handles position sizing, VIX-based volatility checks, daily capital
tracking, and loss cap enforcement.  All monetary values are in INR.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from intraday.models import IntraConfig, TradeSetup

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class Risk_Manager:
    """Enforces risk rules: sizing, VIX checks, capital & loss caps."""

    def __init__(self, config: IntraConfig, db: Any = None) -> None:
        self.config = config
        self.db = db
        self._capital_used_today: float = 0.0
        self._realized_loss_today: float = 0.0
        self._trades_placed_today: int = 0

        # Restore from DB if available
        if db is not None:
            self._restore_daily_state()

    # ------------------------------------------------------------------
    # VIX checks
    # ------------------------------------------------------------------

    def check_vix(self, vix_value: float) -> dict:
        """Evaluate VIX against thresholds.

        Returns
        -------
        dict
            ``{"action": "SKIP"|"REDUCE"|"NORMAL",
               "effective_max_trades": int,
               "reason": str}``
        """
        threshold = self.config.vix_threshold
        if threshold <= 0:
            return {"action": "NORMAL", "effective_max_trades": self.config.max_trades_per_day, "reason": ""}

        if vix_value > 1.5 * threshold:
            reason = f"VIX {vix_value:.2f} > 1.5× threshold ({1.5 * threshold:.1f}) — skipping session"
            logger.warning(reason)
            return {"action": "SKIP", "effective_max_trades": 0, "reason": reason}

        if vix_value > threshold:
            halved = self.config.max_trades_per_day // 2
            reason = f"VIX {vix_value:.2f} > threshold ({threshold:.1f}) — reducing max trades to {halved}"
            logger.warning(reason)
            return {"action": "REDUCE", "effective_max_trades": halved, "reason": reason}

        return {
            "action": "NORMAL",
            "effective_max_trades": self.config.max_trades_per_day,
            "reason": f"VIX {vix_value:.2f} within normal range",
        }

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def size_trades(
        self,
        trades: list[TradeSetup],
        available_margin: float | None = None,
    ) -> list[TradeSetup]:
        """Calculate position sizes for a list of trades.

        Sizing logic:
        1. Base qty = floor(per_trade_max_capital / entry_price)
        2. Confidence weighting: higher confidence → proportionally larger
        3. Total capital across all trades ≤ daily_capital_limit
        4. Total capital across all trades ≤ available_margin (if provided)
        """
        if not trades:
            return trades

        margin = available_margin if available_margin is not None else self.config.daily_capital_limit
        remaining_capital = min(
            self.config.daily_capital_limit - self._capital_used_today,
            margin,
        )

        if remaining_capital <= 0:
            logger.error("No remaining capital (used ₹%.2f today) — refusing all trades", self._capital_used_today)
            return []

        # --- Confidence-weighted allocation ---
        total_confidence = sum(t.confidence_score for t in trades)
        if total_confidence <= 0:
            total_confidence = len(trades)

        sized: list[TradeSetup] = []
        capital_allocated = 0.0

        for trade in trades:
            if trade.entry_price <= 0:
                continue

            # Base size from per-trade cap
            base_qty = math.floor(self.config.per_trade_max_capital / trade.entry_price)

            # Confidence weight: scale allocation proportionally
            weight = trade.confidence_score / total_confidence
            weighted_capital = remaining_capital * weight
            weighted_qty = math.floor(weighted_capital / trade.entry_price)

            # Take the smaller of base and weighted
            qty = min(base_qty, weighted_qty)

            # Ensure we don't exceed remaining capital
            trade_capital = qty * trade.entry_price
            if capital_allocated + trade_capital > remaining_capital:
                qty = math.floor((remaining_capital - capital_allocated) / trade.entry_price)

            if qty <= 0:
                logger.warning("Cannot size %s — insufficient capital", trade.nse_symbol)
                continue

            trade.quantity = qty
            trade_capital = qty * trade.entry_price
            capital_allocated += trade_capital

            risk = trade.entry_price - trade.stop_loss_price
            rr = (trade.target_price - trade.entry_price) / risk if risk > 0 else 0
            trade.risk_reward_ratio = round(rr, 2)

            sized.append(trade)
            logger.info(
                "Sized %s: %d shares × ₹%.2f = ₹%.0f (conf %d, R:R %.1f)",
                trade.nse_symbol, qty, trade.entry_price, trade_capital,
                trade.confidence_score, trade.risk_reward_ratio,
            )

        logger.info("Total capital allocated: ₹%.0f / ₹%.0f remaining", capital_allocated, remaining_capital)
        return sized

    # ------------------------------------------------------------------
    # Capital tracking
    # ------------------------------------------------------------------

    def record_trade_placed(self, trade: TradeSetup) -> None:
        """Record that a trade has been placed (updates capital used)."""
        cost = trade.quantity * trade.entry_price
        self._capital_used_today += cost
        self._trades_placed_today += 1

    def record_trade_closed(self, pnl: float) -> None:
        """Record a closed trade's P&L for loss cap tracking."""
        if pnl < 0:
            self._realized_loss_today += abs(pnl)

    def can_place_new_order(self) -> bool:
        """Check if new orders are allowed (loss cap not breached)."""
        if self._realized_loss_today >= self.config.daily_loss_limit:
            logger.error(
                "Daily loss cap BREACHED: ₹%.2f realized loss ≥ ₹%.2f cap — refusing new orders",
                self._realized_loss_today, self.config.daily_loss_limit,
            )
            return False
        return True

    def check_loss_warning(self, unrealized_loss: float = 0.0) -> dict:
        """Check proximity to daily loss cap.

        Returns dict with ``breach``, ``warning``, and ``pct`` keys.
        """
        total_loss = self._realized_loss_today + abs(unrealized_loss)
        cap = self.config.daily_loss_limit
        pct = (total_loss / cap * 100) if cap > 0 else 0

        breach = self._realized_loss_today >= cap
        warning = total_loss >= 0.8 * cap

        if breach:
            logger.error("LOSS CAP BREACHED: ₹%.2f / ₹%.2f (%.1f%%)", total_loss, cap, pct)
        elif warning:
            logger.warning("Loss cap WARNING: ₹%.2f / ₹%.2f (%.1f%%)", total_loss, cap, pct)

        return {
            "breach": breach,
            "warning": warning,
            "realized_loss": self._realized_loss_today,
            "total_loss": total_loss,
            "cap": cap,
            "pct": round(pct, 1),
        }

    @property
    def capital_used_today(self) -> float:
        return self._capital_used_today

    @property
    def realized_loss_today(self) -> float:
        return self._realized_loss_today

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    def _restore_daily_state(self) -> None:
        """Restore today's capital/loss/trade state from DB."""
        if self.db is None:
            return
        try:
            today = datetime.now(IST).strftime("%Y-%m-%d")

            # Restore realized loss
            loss = self.db.get_daily_realized_loss(today)
            self._realized_loss_today = loss or 0.0

            # Restore trades placed and capital used from today's trade records
            trades = self.db.get_trades_for_date(today)
            buy_trades = [t for t in trades if t.get("action", "").upper() == "BUY"]
            self._trades_placed_today = len(buy_trades)
            self._capital_used_today = sum(
                float(t.get("price", 0)) * int(t.get("quantity", 0))
                for t in buy_trades
            )

            logger.info(
                "Restored daily state: trades=%d, capital_used=₹%.2f, realized_loss=₹%.2f",
                self._trades_placed_today,
                self._capital_used_today,
                self._realized_loss_today,
            )
        except Exception:
            logger.debug("Could not restore daily state from DB", exc_info=True)

    def persist_daily_state(self) -> None:
        """Save current daily state to DB."""
        if self.db is None:
            return
        try:
            today = datetime.now(IST).strftime("%Y-%m-%d")
            self.db.upsert_daily_summary(
                trade_date=today,
                total_pnl=0,
                total_realized_loss=self._realized_loss_today,
                total_trades=self._trades_placed_today,
                winning_trades=0,
                losing_trades=0,
                max_drawdown=0,
                broker_name=self.config.broker,
                mode="DRY_RUN",
            )
        except Exception:
            logger.error("Failed to persist daily state", exc_info=True)
