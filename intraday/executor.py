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

    def _wait_for_fill(self, order_id: str, expected_qty: int, timeout: int = 10) -> int:
        """
        Poll order status until filled, rejected, or timeout.
        Returns: filled quantity (0 if not filled at all).
        """
        if not hasattr(self.broker, "get_order_list"):
            # DryRun broker has no get_order_list — assume instant fill
            return expected_qty

        start = time.time()
        last_filled = 0
        while time.time() - start < timeout:
            try:
                orders = self.broker.get_order_list()
                for o in orders:
                    if str(o.get("orderId", "")) == str(order_id):
                        status = str(o.get("orderStatus", "")).upper()
                        filled = int(o.get("filledQty", 0) or 0)
                        last_filled = filled

                        if status == "TRADED" and filled >= expected_qty:
                            return filled
                        if status in ("REJECTED", "CANCELLED"):
                            return filled  # Could be 0 or partial
                        break  # Still pending — keep polling
            except Exception as e:
                logger.warning("wait_for_fill poll failed for %s: %s", order_id, e)
            time.sleep(2)

        # Timed out — return whatever filled so far
        return last_filled

    def _place_single_trade(self, trade: TradeSetup, mode: str) -> dict | None:
        """Place a LIMIT buy, wait for fill, then place SL for actual filled qty."""
        # --- Determine direction ---
        # LONG: BUY first, SELL stop-loss (when price drops below SL)
        # SHORT: SELL first, BUY stop-loss (when price rises above SL to cover short)
        entry_side = (trade.transaction_type or "BUY").upper()
        if entry_side not in ("BUY", "SELL"):
            logger.error(
                "Invalid transaction_type '%s' for %s — defaulting to BUY",
                trade.transaction_type, trade.nse_symbol,
            )
            entry_side = "BUY"
        sl_side = "SELL" if entry_side == "BUY" else "BUY"

        # --- Place ENTRY order (BUY for long, SELL for short) ---
        # Buffer: +0.3% for BUY (willing to pay slightly more for fill)
        #         -0.3% for SELL (willing to accept slightly less for fill)
        # Tick-aligned to NSE ₹0.05 tick size
        if entry_side == "BUY":
            buffered_price = round(trade.entry_price * 1.003 * 20) / 20
        else:
            buffered_price = round(trade.entry_price * 0.997 * 20) / 20
        buy_result = self.broker.place_order(
            symbol=trade.tradingsymbol,
            exchange="NSE",
            transaction_type=entry_side,
            order_type="LIMIT",
            product_type="INTRADAY",
            quantity=trade.quantity,
            price=buffered_price,
        )

        buy_order_id = buy_result.get("broker_order_id", "")
        if not buy_order_id:
            logger.error("No order ID returned for %s %s", entry_side, trade.nse_symbol)
            return None

        # --- Wait for ENTRY to fill (10s timeout, 2s polling) ---
        filled_qty = self._wait_for_fill(buy_order_id, trade.quantity, timeout=10)

        if filled_qty == 0:
            # Entry did not fill — cancel LIMIT order
            try:
                self.broker.cancel_order(buy_order_id)
            except Exception as e:
                logger.warning("cancel_order failed for %s: %s", buy_order_id, e)

            # MARKET fallback for high-confidence picks (conf >= 8)
            if trade.confidence_score >= 8:
                logger.info("Retrying %s with MARKET order (conf %d)", trade.nse_symbol, trade.confidence_score)
                market_result = self.broker.place_order(
                    symbol=trade.tradingsymbol,
                    exchange="NSE",
                    transaction_type=entry_side,
                    order_type="MARKET",
                    product_type="INTRADAY",
                    quantity=trade.quantity,
                    price=0,
                )
                buy_order_id = market_result.get("broker_order_id", "")
                if buy_order_id:
                    filled_qty = self._wait_for_fill(buy_order_id, trade.quantity, timeout=5)
                    if filled_qty > 0:
                        logger.info("MARKET retry filled %d shares for %s", filled_qty, trade.nse_symbol)

            if filled_qty == 0:
                logger.warning(
                    "%s %s (order %s) did not fill — all attempts exhausted, no SL placed",
                    entry_side, trade.nse_symbol, buy_order_id,
                )
                return None

        if filled_qty < trade.quantity:
            # Partial fill — cancel rest, place SL only for filled qty
            try:
                self.broker.cancel_order(buy_order_id)
            except Exception as e:
                logger.warning("cancel_order failed for partial %s: %s", buy_order_id, e)
            logger.warning(
                "%s %s partial fill: %d/%d — placing SL for %d, remainder cancelled",
                entry_side, trade.nse_symbol, filled_qty, trade.quantity, filled_qty,
            )

        # --- Place SL order in OPPOSITE direction ---
        # LONG SL: SELL with limit price slightly BELOW trigger (SL when price drops)
        # SHORT SL: BUY with limit price slightly ABOVE trigger (SL when price rises)
        if sl_side == "SELL":
            sl_limit_price = round(trade.stop_loss_price - 0.50, 2)
        else:
            sl_limit_price = round(trade.stop_loss_price + 0.50, 2)

        # NSE tick size = 0.05. Dhan rejects non-tick prices (omsErrorCode 16283).
        sl_limit_price = round(round(sl_limit_price / 0.05) * 0.05, 2)
        sl_trigger_price = round(round(trade.stop_loss_price / 0.05) * 0.05, 2)

        sl_result = self.broker.place_order(
            symbol=trade.tradingsymbol,
            exchange="NSE",
            transaction_type=sl_side,
            order_type="SL",
            product_type="INTRADAY",
            quantity=filled_qty,
            price=sl_limit_price,
            trigger_price=sl_trigger_price,
        )
        sl_order_id = sl_result.get("broker_order_id", "")

        # --- Store in DB ---
        trade_id = None
        if self.db:
            trade_id = self.db.insert_intraday_trade(
                symbol=trade.stock_name,
                tradingsymbol=trade.tradingsymbol,
                action=entry_side,
                order_type="LIMIT",
                quantity=filled_qty,
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
