"""Order executor for the intraday auto-trader.

Places LIMIT buy + SL sell orders for each trade via the BrokerClient ABC.
Supports dry-run mode (simulated fills) and live mode.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from intraday.broker_base import BrokerClient
from intraday.models import IntraConfig, PositionState, TradeSetup

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN = (9, 15)  # 9:15 AM IST


class Order_Executor:
    """Places and manages intraday orders through the BrokerClient ABC."""

    def __init__(
        self,
        broker: BrokerClient,
        config: IntraConfig,
        db: Any = None,
        dry_run: bool = True,
    ) -> None:
        self.broker = broker
        self.config = config
        self.db = db
        self.dry_run = dry_run
        self._placed_trades: list[dict] = []

    def wait_for_entry_time(self, force: bool = False) -> None:
        """Wait until entry_delay_minutes after market open (9:15 AM IST).

        In ``--force`` mode this is skipped.
        """
        if force:
            logger.info("--force: skipping entry delay")
            return

        now = datetime.now(IST)
        market_open = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
        entry_time = market_open + timedelta(minutes=self.config.entry_delay_minutes)

        if now < entry_time:
            wait_secs = (entry_time - now).total_seconds()
            logger.info(
                "Waiting %.0f seconds until entry time %s IST…",
                wait_secs, entry_time.strftime("%H:%M"),
            )
            time.sleep(wait_secs)

    def execute_trades(
        self,
        trades: list[TradeSetup],
        risk_manager: Any = None,
        force: bool = False,
    ) -> list[dict]:
        """Place orders for all sized trades.

        Returns list of placed trade records (dicts with DB ids and order info).
        """
        self.wait_for_entry_time(force=force)

        placed: list[dict] = []
        mode = "DRY_RUN" if self.dry_run else "LIVE"

        for trade in trades:
            if risk_manager and not risk_manager.can_place_new_order():
                logger.error("Loss cap reached — stopping order placement")
                break

            try:
                record = self._place_single_trade(trade, mode)
                if record:
                    placed.append(record)
                    if risk_manager:
                        risk_manager.record_trade_placed(trade)
            except Exception as exc:
                logger.error("Failed to place order for %s: %s — skipping", trade.nse_symbol, exc)
                self._audit("ORDER_ERROR", {"symbol": trade.nse_symbol, "error": str(exc)})
                continue

        self._placed_trades = placed
        logger.info("Placed %d / %d orders (%s mode)", len(placed), len(trades), mode)
        return placed

    def _place_single_trade(self, trade: TradeSetup, mode: str) -> dict | None:
        """Place a LIMIT buy + SL sell for one trade."""
        # --- Place BUY order ---
        buy_result = self.broker.place_order(
            symbol=trade.tradingsymbol,
            exchange="NSE",
            transaction_type="BUY",
            order_type="LIMIT",
            product_type="INTRADAY",
            quantity=trade.quantity,
            price=trade.entry_price,
        )

        buy_order_id = buy_result.get("broker_order_id", "")
        if not buy_order_id:
            logger.error("No order ID returned for BUY %s", trade.nse_symbol)
            return None

        # --- Place SL sell order ---
        sl_result = self.broker.place_order(
            symbol=trade.tradingsymbol,
            exchange="NSE",
            transaction_type="SELL",
            order_type="SL",
            product_type="INTRADAY",
            quantity=trade.quantity,
            price=trade.stop_loss_price,
            trigger_price=trade.stop_loss_price,
        )
        sl_order_id = sl_result.get("broker_order_id", "")

        # --- Store in DB ---
        trade_id = None
        if self.db:
            trade_id = self.db.insert_intraday_trade(
                symbol=trade.stock_name,
                tradingsymbol=trade.tradingsymbol,
                action="BUY",
                order_type="LIMIT",
                quantity=trade.quantity,
                price=trade.entry_price,
                trigger_price=trade.stop_loss_price,
                broker_order_id=buy_order_id,
                broker_name=self.config.broker,
                status=PositionState.PENDING.value,
                entry_price=trade.entry_price,
                target_price=trade.target_price,
                stop_loss_price=trade.stop_loss_price,
                confidence_score=trade.confidence_score,
                strategy_type=trade.strategy_type,
                rationale=trade.rationale,
                mode=mode,
            )

        record = {
            "trade_id": trade_id,
            "symbol": trade.stock_name,
            "tradingsymbol": trade.tradingsymbol,
            "nse_symbol": trade.nse_symbol,
            "entry_price": trade.entry_price,
            "target_price": trade.target_price,
            "stop_loss_price": trade.stop_loss_price,
            "quantity": trade.quantity,
            "buy_order_id": buy_order_id,
            "sl_order_id": sl_order_id,
            "confidence_score": trade.confidence_score,
            "strategy_type": trade.strategy_type,
            "rationale": trade.rationale,
            "status": PositionState.PENDING.value,
            "pnl": 0.0,
            "current_price": trade.entry_price,
            "mode": mode,
        }

        self._audit("ORDER_PLACED", {
            "symbol": trade.nse_symbol,
            "buy_order_id": buy_order_id,
            "sl_order_id": sl_order_id,
            "qty": trade.quantity,
            "entry": trade.entry_price,
            "target": trade.target_price,
            "sl": trade.stop_loss_price,
        }, trade_id=trade_id)

        logger.info(
            "📋 Placed %s: BUY %d × ₹%.2f | Target ₹%.2f | SL ₹%.2f | %s",
            trade.nse_symbol, trade.quantity, trade.entry_price,
            trade.target_price, trade.stop_loss_price,
            "🧪 DRY-RUN" if mode == "DRY_RUN" else "🔴 LIVE",
        )
        return record

    @property
    def placed_trades(self) -> list[dict]:
        return self._placed_trades

    def _audit(self, event_type: str, details: dict, trade_id: int | None = None) -> None:
        if self.db:
            try:
                self.db.insert_audit_log(event_type, json.dumps(details, default=str), trade_id)
            except Exception:
                pass
