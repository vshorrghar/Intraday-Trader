"""V3 Executor — atomic entry+SL with safety guarantees.

Fixes from old executor:
- BUG A (DH-906): Poll fill status instead of blind cancel-replace
- BUG B (Naked position): Emergency market exit if SL placement fails

Rule: NEVER hold a position without a stop-loss order protecting it.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
ENTRY_POLL_INTERVAL_SEC = 2
ENTRY_POLL_MAX_ATTEMPTS = 5  # 5 × 2s = 10s max wait
MARKET_RETRY_CONFIDENCE = 8  # Only retry with MARKET if confidence >= 8
NSE_TICK_SIZE = 0.05


def _tick_align(price: float) -> float:
    """Round price to NSE tick size (₹0.05)."""
    return round(round(price / NSE_TICK_SIZE) * NSE_TICK_SIZE, 2)


def place_v3_orders(broker, trade_setups: list, dry_run: bool = False) -> dict:
    """Place orders with atomic entry+SL guarantee.

    For each trade:
    1. Place ENTRY (LIMIT with buffer)
    2. POLL fill status (no blind cancel-replace)
    3. If filled → place SL
    4. If SL fails → EMERGENCY MARKET EXIT (no naked positions)

    Args:
        broker: Authenticated DhanBrokerClient (or None if dry_run)
        trade_setups: List of dicts with symbol, entry_price, stop_loss, target, qty, direction
        dry_run: If True, log intent only

    Returns:
        {"placed": N, "failed": N, "naked_exits": N, "details": [...]}
    """
    result = {"placed": 0, "failed": 0, "naked_exits": 0, "details": []}

    for setup in trade_setups:
        symbol = setup.get("symbol", "?")
        direction = setup.get("direction", "LONG")
        entry_price = setup.get("entry_price", 0)
        stop_loss = setup.get("stop_loss", 0)
        target = setup.get("target", 0)
        qty = setup.get("qty", 0)

        if dry_run:
            logger.info("[DRY] Would place: %s %s × %d @ ₹%.2f (SL=₹%.2f, T=₹%.2f)",
                        direction, symbol, qty, entry_price, stop_loss, target)
            result["placed"] += 1
            result["details"].append({"symbol": symbol, "status": "DRY_RUN"})
            continue

        if not broker or qty <= 0 or entry_price <= 0:
            logger.warning("V3 Executor: invalid setup for %s — skipping", symbol)
            result["failed"] += 1
            continue

        # Execute atomic sequence
        trade_result = _execute_atomic_trade(broker, symbol, direction, entry_price,
                                             stop_loss, target, qty,
                                             confidence=setup.get("confidence", 7))
        if trade_result["status"] == "PLACED":
            result["placed"] += 1
        elif trade_result["status"] == "NAKED_EXIT":
            result["naked_exits"] += 1
            result["failed"] += 1
        else:
            result["failed"] += 1

        result["details"].append(trade_result)

    logger.info("V3 Executor: placed=%d, failed=%d, naked_exits=%d",
                result["placed"], result["failed"], result["naked_exits"])
    return result


def _execute_atomic_trade(broker, symbol: str, direction: str, entry_price: float,
                          stop_loss: float, target: float, qty: int,
                          confidence: int = 7) -> dict:
    """Execute one trade with atomic entry→confirm→SL sequence.

    Returns dict with status: PLACED | UNFILLED | SL_FAILED | NAKED_EXIT
    """
    entry_side = "BUY" if direction == "LONG" else "SELL"
    sl_side = "SELL" if entry_side == "BUY" else "BUY"

    # Step 1: Place ENTRY order (LIMIT with 0.3% buffer)
    if entry_side == "BUY":
        buffered_price = _tick_align(entry_price * 1.003)
    else:
        buffered_price = _tick_align(entry_price * 0.997)

    logger.info("V3: Placing %s %s × %d @ ₹%.2f (buffered from ₹%.2f)",
                entry_side, symbol, qty, buffered_price, entry_price)

    try:
        entry_result = broker.place_order(
            symbol=symbol,
            exchange="NSE",
            transaction_type=entry_side,
            order_type="LIMIT",
            product_type="INTRADAY",
            quantity=qty,
            price=buffered_price,
        )
    except Exception as exc:
        logger.error("V3: Entry order failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "status": "ENTRY_FAILED", "error": str(exc)}

    entry_order_id = entry_result.get("broker_order_id", "")
    if not entry_order_id:
        logger.error("V3: No order ID returned for %s", symbol)
        return {"symbol": symbol, "status": "NO_ORDER_ID"}

    # Step 2: POLL fill status (FIX for DH-906 — no blind cancel-replace)
    filled_qty = _poll_fill_status(broker, entry_order_id, qty)

    if filled_qty == 0:
        # Not filled — try MARKET fallback for high confidence
        if confidence >= MARKET_RETRY_CONFIDENCE:
            logger.info("V3: LIMIT unfilled for %s, retrying MARKET (conf=%d)", symbol, confidence)
            # Cancel the unfilled LIMIT first (single clean cancel)
            _safe_cancel(broker, entry_order_id, symbol)
            time.sleep(0.5)

            try:
                market_result = broker.place_order(
                    symbol=symbol, exchange="NSE", transaction_type=entry_side,
                    order_type="MARKET", product_type="INTRADAY",
                    quantity=qty, price=0,
                )
                market_order_id = market_result.get("broker_order_id", "")
                if market_order_id:
                    filled_qty = _poll_fill_status(broker, market_order_id, qty)
                    if filled_qty > 0:
                        entry_order_id = market_order_id
            except Exception as exc:
                logger.error("V3: MARKET retry failed for %s: %s", symbol, exc)
        else:
            # Low confidence — just cancel and move on
            _safe_cancel(broker, entry_order_id, symbol)

        if filled_qty == 0:
            logger.info("V3: %s did not fill — no position taken", symbol)
            return {"symbol": symbol, "status": "UNFILLED", "order_id": entry_order_id}

    logger.info("V3: %s filled %d shares", symbol, filled_qty)

    # Step 3: Place SL order (ONLY after entry confirmed filled)
    sl_trigger = _tick_align(stop_loss)
    if sl_side == "SELL":
        sl_limit = _tick_align(stop_loss - 0.50)
    else:
        sl_limit = _tick_align(stop_loss + 0.50)

    try:
        sl_result = broker.place_order(
            symbol=symbol, exchange="NSE", transaction_type=sl_side,
            order_type="SL", product_type="INTRADAY",
            quantity=filled_qty, price=sl_limit, trigger_price=sl_trigger,
        )
        sl_order_id = sl_result.get("broker_order_id", "")
    except Exception as exc:
        logger.error("V3: SL placement FAILED for %s: %s", symbol, exc)
        sl_order_id = ""

    # Step 4: If SL failed → EMERGENCY MARKET EXIT (never hold naked)
    if not sl_order_id:
        logger.critical("V3: SL_FAILED for %s — EMERGENCY MARKET EXIT", symbol)
        try:
            exit_result = broker.place_order(
                symbol=symbol, exchange="NSE", transaction_type=sl_side,
                order_type="MARKET", product_type="INTRADAY",
                quantity=filled_qty, price=0,
            )
            logger.warning("V3: Emergency exit placed for %s: %s",
                           symbol, exit_result.get("broker_order_id", "?"))
        except Exception as exc:
            logger.critical("V3: EMERGENCY EXIT ALSO FAILED for %s: %s — MANUAL INTERVENTION NEEDED", symbol, exc)

        return {"symbol": symbol, "status": "NAKED_EXIT", "entry_order_id": entry_order_id,
                "filled_qty": filled_qty, "reason": "SL placement failed"}

    # Success — both entry and SL placed
    logger.info("V3: ✅ %s %s × %d @ ₹%.2f | SL ₹%.2f | Target ₹%.2f",
                entry_side, symbol, filled_qty, entry_price, stop_loss, target)

    return {
        "symbol": symbol, "status": "PLACED",
        "entry_order_id": entry_order_id, "sl_order_id": sl_order_id,
        "filled_qty": filled_qty, "entry_price": entry_price,
        "stop_loss": stop_loss, "target": target,
    }


def _poll_fill_status(broker, order_id: str, expected_qty: int) -> int:
    """Poll order status until filled or timeout. Returns filled quantity.

    FIX for DH-906: We POLL, never cancel-and-replace blindly.
    """
    for attempt in range(ENTRY_POLL_MAX_ATTEMPTS):
        time.sleep(ENTRY_POLL_INTERVAL_SEC)
        try:
            order_list = broker.get_order_list()
            if not order_list:
                continue
            for order in order_list:
                if str(order.get("orderId", "")) == str(order_id):
                    status = order.get("orderStatus", "").upper()
                    filled = int(order.get("filledQty", 0) or order.get("tradedQuantity", 0) or 0)
                    if status == "TRADED" or filled >= expected_qty:
                        return filled
                    if status in ("CANCELLED", "REJECTED", "EXPIRED"):
                        return 0
                    break
        except Exception as exc:
            logger.warning("V3: Poll attempt %d failed: %s", attempt + 1, exc)

    return 0


def _safe_cancel(broker, order_id: str, symbol: str):
    """Cancel an order safely — catch DH-906 if already gone."""
    try:
        broker.cancel_order(order_id)
        logger.info("V3: Cancelled unfilled order %s for %s", order_id, symbol)
    except Exception as exc:
        # DH-906 or already cancelled — that's fine
        logger.info("V3: Cancel for %s returned: %s (order may already be gone)", symbol, exc)
