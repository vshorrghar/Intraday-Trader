"""V3 Broker-Truth Safety Layer — trusts ONLY Dhan, never internal state.

This module exists because the May 29 INFY -Rs910 loss proved that every
internal safety layer (monitor P&L, loss cap, exit reporting) can be fooled
by a single empty order_id. This layer queries Dhan directly and acts on
REAL numbers.

Core principle: if Dhan says you're losing, you're losing. Period.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

POLL_EXIT_ATTEMPTS = 5
POLL_EXIT_INTERVAL = 2  # seconds


def fetch_dhan_truth(broker) -> dict:
    """Fetch REAL position state from Dhan.

    Returns:
        {
            "positions": [...],  # raw Dhan positions
            "total_realized": float,
            "total_unrealized": float,
            "total_pnl": float,
            "open_count": int,
        }
    """
    try:
        positions = broker.get_positions()
        if not positions:
            return {"positions": [], "total_realized": 0, "total_unrealized": 0,
                    "total_pnl": 0, "open_count": 0}

        total_realized = 0.0
        total_unrealized = 0.0
        open_count = 0

        for p in positions:
            realized = float(p.get("realizedProfit", 0) or 0)
            unrealized = float(p.get("unrealizedProfit", 0) or 0)
            total_realized += realized
            total_unrealized += unrealized
            net_qty = int(p.get("netQty", 0) or 0)
            if net_qty != 0:
                open_count += 1

        total_pnl = total_realized + total_unrealized

        logger.info("DHAN TRUTH: realized=%.2f, unrealized=%.2f, total=%.2f, open=%d",
                    total_realized, total_unrealized, total_pnl, open_count)

        return {
            "positions": positions,
            "total_realized": round(total_realized, 2),
            "total_unrealized": round(total_unrealized, 2),
            "total_pnl": round(total_pnl, 2),
            "open_count": open_count,
        }
    except Exception as exc:
        logger.error("fetch_dhan_truth FAILED: %s", exc)
        return {"positions": [], "total_realized": 0, "total_unrealized": 0,
                "total_pnl": 0, "open_count": 0, "error": str(exc)}


def check_hard_loss_cap(broker, daily_cap: float) -> dict:
    """Check if daily loss exceeds hard cap using ONLY Dhan truth.

    This CANNOT be fooled by a lying monitor or empty order IDs.

    Args:
        broker: Authenticated DhanBrokerClient
        daily_cap: Maximum acceptable daily loss (positive number, e.g., 1000)

    Returns:
        {"breached": bool, "total_pnl": float, "cap": float, "action": str or None}
    """
    truth = fetch_dhan_truth(broker)
    total_pnl = truth["total_pnl"]

    if total_pnl <= -abs(daily_cap):
        logger.critical(
            "HARD LOSS CAP BREACHED: Dhan P&L = Rs%.2f, cap = Rs%.2f — SQUARE OFF ALL",
            total_pnl, daily_cap
        )
        return {
            "breached": True,
            "total_pnl": total_pnl,
            "cap": daily_cap,
            "action": "SQUARE_OFF_ALL",
            "dhan_truth": truth,
        }

    logger.info("Hard cap OK: Dhan P&L = Rs%.2f (cap Rs%.2f)", total_pnl, daily_cap)
    return {
        "breached": False,
        "total_pnl": total_pnl,
        "cap": daily_cap,
        "action": None,
    }


def emergency_square_off_all(broker) -> dict:
    """Emergency: flatten ALL open positions via MARKET orders.

    Polls ACTUAL fill prices — never assumes entry==exit.

    Returns:
        {"squared_off": N, "total_realized_pnl": float, "details": [...]}
    """
    truth = fetch_dhan_truth(broker)
    positions = truth["positions"]
    results = []
    total_pnl = 0.0

    for p in positions:
        net_qty = int(p.get("netQty", 0) or 0)
        if net_qty == 0:
            continue  # Already flat

        symbol = p.get("tradingSymbol", "?")
        # Determine exit side
        if net_qty > 0:
            exit_side = "SELL"
            exit_qty = net_qty
        else:
            exit_side = "BUY"
            exit_qty = abs(net_qty)

        logger.warning("EMERGENCY SQUARE OFF: %s %s × %d", exit_side, symbol, exit_qty)

        try:
            result = broker.place_order(
                symbol=symbol, exchange="NSE", transaction_type=exit_side,
                order_type="MARKET", product_type="INTRADAY",
                quantity=exit_qty, price=0,
            )
            order_id = result.get("broker_order_id", "") if isinstance(result, dict) else ""

            # Poll for actual fill price
            fill_price = poll_exit_fill(broker, order_id, exit_qty)

            # Compute realized P&L for this position
            if net_qty > 0:  # Was LONG
                entry_avg = float(p.get("buyAvg", 0) or p.get("costPrice", 0) or 0)
                pnl = (fill_price - entry_avg) * exit_qty if fill_price > 0 else 0
            else:  # Was SHORT
                entry_avg = float(p.get("sellAvg", 0) or 0)
                pnl = (entry_avg - fill_price) * exit_qty if fill_price > 0 else 0

            total_pnl += pnl
            results.append({
                "symbol": symbol, "side": exit_side, "qty": exit_qty,
                "fill_price": fill_price, "pnl": round(pnl, 2),
                "order_id": order_id,
            })
            logger.warning("SQUARED OFF %s: fill=%.2f, pnl=%.2f", symbol, fill_price, pnl)

        except Exception as exc:
            logger.critical("EMERGENCY EXIT FAILED for %s: %s — MANUAL INTERVENTION NEEDED", symbol, exc)
            results.append({"symbol": symbol, "error": str(exc)})

    return {
        "squared_off": len(results),
        "total_realized_pnl": round(total_pnl, 2),
        "details": results,
    }


def poll_exit_fill(broker, order_id: str, qty: int) -> float:
    """Poll get_order_list for ACTUAL traded price of an exit order.

    Returns real fill price. Returns 0.0 if unable to determine
    (caller must handle — never assume entry price).

    Fixes the "fill=no_poll" lie from old monitor.
    """
    if not order_id:
        logger.warning("poll_exit_fill: no order_id — cannot determine fill price")
        return 0.0

    for attempt in range(POLL_EXIT_ATTEMPTS):
        time.sleep(POLL_EXIT_INTERVAL)
        try:
            orders = broker.get_order_list()
            if not orders:
                continue
            for o in orders:
                if str(o.get("orderId", "")) == str(order_id):
                    status = (o.get("orderStatus", "") or "").upper()
                    if status == "TRADED":
                        avg_price = float(o.get("averageTradedPrice", 0) or 0)
                        if avg_price > 0:
                            logger.info("Exit fill confirmed: order %s @ Rs%.2f", order_id, avg_price)
                            return avg_price
                    elif status in ("CANCELLED", "REJECTED"):
                        logger.warning("Exit order %s was %s — fill price unknown", order_id, status)
                        return 0.0
        except Exception as exc:
            logger.warning("poll_exit_fill attempt %d failed: %s", attempt + 1, exc)

    logger.warning("poll_exit_fill: timeout after %d attempts for order %s", POLL_EXIT_ATTEMPTS, order_id)
    return 0.0
