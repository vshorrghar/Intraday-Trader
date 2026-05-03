"""Swing trade executor — places and manages orders via broker."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from swing.models import SwingConfig, SwingSetup, SwingPosition

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


class SwingExecutor:
    """Executes swing trades via broker (or dry-run)."""

    def __init__(self, config: SwingConfig, broker=None, db=None, dry_run: bool = True):
        self.config = config
        self.broker = broker
        self.db = db
        self.dry_run = dry_run

    def execute_trades(self, setups: list[SwingSetup], available_capital: float) -> list[SwingPosition]:
        """Size and execute swing trades."""
        positions = []
        remaining = min(available_capital, self.config.daily_capital_limit)

        for setup in setups:
            if len(positions) >= self.config.max_open_positions:
                break

            # Position sizing
            max_capital = min(self.config.per_trade_max_capital, remaining)
            quantity = int(max_capital / setup.entry_price)

            if quantity <= 0:
                continue

            capital_used = quantity * setup.entry_price
            if capital_used > remaining:
                continue

            # Place order (or simulate)
            if self.dry_run:
                order_id = f"SWING-DRY-{len(positions)+1:04d}"
                logger.info(
                    "📋 Swing DRY-RUN: BUY %s × %d @ ₹%.2f | Target ₹%.2f | SL ₹%.2f | Hold ~%d days",
                    setup.nse_symbol, quantity, setup.entry_price,
                    setup.target_price, setup.stop_loss_price, setup.expected_hold_days,
                )
            else:
                # Live order via broker
                try:
                    order_id = self.broker.place_order(
                        symbol=setup.nse_symbol,
                        quantity=quantity,
                        price=setup.entry_price,
                        order_type="LIMIT",
                        transaction_type="BUY",
                        product_type="CNC",  # Cash & Carry (delivery)
                    )
                except Exception as exc:
                    logger.error("Failed to place swing order for %s: %s", setup.nse_symbol, exc)
                    continue

            pos = SwingPosition(
                nse_symbol=setup.nse_symbol,
                entry_price=setup.entry_price,
                entry_date=datetime.now(IST).strftime("%Y-%m-%d"),
                target_price=setup.target_price,
                stop_loss_price=setup.stop_loss_price,
                current_price=setup.entry_price,
                quantity=quantity,
                status="OPEN",
                strategy_type=setup.strategy_type,
                confidence_score=setup.confidence_score,
            )
            positions.append(pos)
            remaining -= capital_used

            # Save to DB
            if self.db:
                self.db.insert_swing_trade(pos)

        logger.info("Swing: placed %d positions, capital used ₹%.0f", len(positions), self.config.daily_capital_limit - remaining)
        return positions
