"""
Swing executor — places CNC (delivery) BUY orders.
LONG ONLY for v0.1. No SL order at entry (monitor handles daily).

Bug 1 fix carried: reconcile via get_positions before MARKET retry.
Bug 3 fix carried: cancel hint detection.

# TODO Week 3: Slice large orders (TWAP) for stocks with low daily turnover
# TODO Week 3: Add VWAP-based entry timing (better fills)
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from swing.models import SwingTradeSetup, SwingPositionState, SwingConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


class SwingExecutor:
    """Execute swing CNC buy orders."""

    def __init__(self, config: SwingConfig, broker=None, db=None, dry_run: bool = True):
        self.config = config
        self.broker = broker
        self.db = db
        self.dry_run = dry_run
        self._placed_trades = []

    def _wait_for_fill(self, order_id: str, expected_qty: int, timeout: int = 10) -> int:
        """Poll order status until filled, rejected, or timeout."""
        if not hasattr(self.broker, "get_order_list"):
            return expected_qty  # DryRun

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
                            return filled
                        break
            except Exception as e:
                logger.warning("wait_for_fill poll failed for %s: %s", order_id, e)
            time.sleep(2)
        return last_filled

    def _place_single_trade(self, trade: SwingTradeSetup, mode: str) -> dict | None:
        """Place CNC BUY order. No SL at entry (monitor handles daily)."""
        # Tick-align entry price (NSE Rs.0.05)
        buffered_price = round(trade.entry_price * 1.003 * 20) / 20  # +0.3% buffer for fill

        buy_result = self.broker.place_order(
            symbol=trade.tradingsymbol,
            exchange="NSE",
            transaction_type="BUY",
            order_type="LIMIT",
            product_type="CNC",  # DELIVERY, not INTRADAY
            quantity=trade.quantity,
            price=buffered_price,
        )

        buy_order_id = buy_result.get("broker_order_id", "")
        if not buy_order_id:
            logger.error("No order ID returned for BUY %s", trade.nse_symbol)
            return None

        # Wait for fill
        filled_qty = self._wait_for_fill(buy_order_id, trade.quantity, timeout=10)

        # ─── Bug 1 fix: reconcile via positions before MARKET retry ───
        if filled_qty == 0:
            try:
                if hasattr(self.broker, "get_positions"):
                    positions = self.broker.get_positions()
                    for pos in positions:
                        pos_symbol = str(pos.get("tradingsymbol", "")).upper()
                        pos_qty = int(pos.get("quantity", 0))
                        if pos_symbol == trade.tradingsymbol.upper() and pos_qty != 0:
                            logger.warning(
                                "RECONCILE: %s shows %d qty in positions despite wait_for_fill=0. "
                                "LIMIT actually filled. Skipping MARKET retry.",
                                trade.tradingsymbol, pos_qty
                            )
                            filled_qty = abs(pos_qty)
                            break
            except Exception as e:
                logger.warning("Position reconcile failed for %s: %s", trade.nse_symbol, e)

        # If still 0, try cancel + MARKET retry
        if filled_qty == 0:
            try:
                cancel_result = self.broker.cancel_order(buy_order_id)
                cancel_str = str(cancel_result).lower()
                if "cancelled" in cancel_str or "traded" in cancel_str:
                    logger.warning(
                        "CANCEL HINT: %s cancel suggests already filled: %s",
                        trade.nse_symbol, cancel_result
                    )
                    try:
                        if hasattr(self.broker, "get_positions"):
                            positions = self.broker.get_positions()
                            for pos in positions:
                                if str(pos.get("tradingsymbol", "")).upper() == trade.tradingsymbol.upper():
                                    if int(pos.get("quantity", 0)) != 0:
                                        filled_qty = abs(int(pos.get("quantity", 0)))
                                        break
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("cancel_order exception for %s: %s", buy_order_id, e)

            # MARKET fallback for high-confidence picks
            if filled_qty == 0 and trade.confidence_score >= 8:
                logger.info("Retrying %s with MARKET order (conf %d)", trade.nse_symbol, trade.confidence_score)
                market_result = self.broker.place_order(
                    symbol=trade.tradingsymbol,
                    exchange="NSE",
                    transaction_type="BUY",
                    order_type="MARKET",
                    product_type="CNC",
                    quantity=trade.quantity,
                    price=0,
                )
                buy_order_id = market_result.get("broker_order_id", "")
                if buy_order_id:
                    filled_qty = self._wait_for_fill(buy_order_id, trade.quantity, timeout=5)
                    if filled_qty > 0:
                        logger.info("MARKET retry filled %d shares for %s", filled_qty, trade.nse_symbol)

            if filled_qty == 0:
                logger.warning("%s BUY did not fill — all attempts exhausted", trade.nse_symbol)
                return None

        # ─── Store in DB (NO SL order for swing — monitor handles daily) ───
        trade_id = None
        if self.db:
            try:
                trade_id = self.db.insert_swing_trade(
                    symbol=trade.stock_name,
                    tradingsymbol=trade.tradingsymbol,
                    nse_symbol=trade.nse_symbol,
                    action="BUY",
                    quantity=filled_qty,
                    entry_price=trade.entry_price,
                    target_price=trade.target_price,
                    stop_loss_price=trade.stop_loss_price,
                    status=SwingPositionState.OPEN.value,
                    confidence_score=trade.confidence_score,
                    strategy_type=trade.strategy_type,
                    rationale=trade.rationale,
                    thesis_invalidation=trade.thesis_invalidation,
                    sector=trade.sector,
                    holding_days_estimate=trade.holding_days_estimate,
                    buy_order_id=buy_order_id,
                    mode=mode,
                )
            except Exception as e:
                logger.error("DB insert failed for %s: %s", trade.nse_symbol, e)

        record = {
            "trade_id": trade_id,
            "symbol": trade.stock_name,
            "tradingsymbol": trade.tradingsymbol,
            "nse_symbol": trade.nse_symbol,
            "entry_price": trade.entry_price,
            "target_price": trade.target_price,
            "stop_loss_price": trade.stop_loss_price,
            "quantity": filled_qty,
            "buy_order_id": buy_order_id,
            "confidence_score": trade.confidence_score,
            "strategy_type": trade.strategy_type,
            "status": SwingPositionState.OPEN.value,
            "mode": mode,
        }

        self._audit("SWING_ENTRY", {
            "symbol": trade.nse_symbol,
            "buy_order_id": buy_order_id,
            "qty": filled_qty,
            "entry": trade.entry_price,
            "target": trade.target_price,
            "sl": trade.stop_loss_price,
            "thesis": trade.thesis_invalidation,
        }, trade_id=trade_id)

        logger.info(
            "📋 SWING BUY: %s %d × Rs.%.2f | Target Rs.%.2f | SL Rs.%.2f | %s",
            trade.nse_symbol, filled_qty, trade.entry_price,
            trade.target_price, trade.stop_loss_price,
            "🧪 DRY-RUN" if mode == "DRY_RUN" else "🔴 LIVE",
        )
        return record

    def execute_trades(self, trades: list, risk_manager=None) -> list:
        """Place orders for all sized trades."""
        placed = []
        mode = "DRY_RUN" if self.dry_run else "LIVE"

        for trade in trades:
            if risk_manager:
                can_enter, reason = risk_manager.can_enter_trade(trade)
                if can_enter is False:
                    logger.warning("Risk gate blocked %s: %s", trade.nse_symbol, reason)
                    continue

            try:
                record = self._place_single_trade(trade, mode)
                if record:
                    placed.append(record)
            except Exception as exc:
                logger.error("Failed to place swing order for %s: %s", trade.nse_symbol, exc)
                self._audit("SWING_ORDER_ERROR", {"symbol": trade.nse_symbol, "error": str(exc)})
                continue

        self._placed_trades = placed
        logger.info("Placed %d / %d swing orders (%s mode)", len(placed), len(trades), mode)
        return placed

    @property
    def placed_trades(self) -> list:
        return self._placed_trades

    def _audit(self, event_type: str, details: dict, trade_id=None):
        if self.db:
            try:
                self.db.insert_swing_audit(event_type, json.dumps(details, default=str), trade_id)
            except Exception:
                pass
