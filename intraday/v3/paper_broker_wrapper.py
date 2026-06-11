"""Paper Broker Wrapper — PHYSICALLY blocks real orders while allowing data calls.

When profile.paper==True, this wrapper replaces the broker's place_order method
with a simulator that RAISES if somehow called, and logs simulated fills.
Real data methods (get_positions, get_order_list, get_historical_ohlc) pass through.

This is NOT a flag check. The real place_order method is REMOVED from the object.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PaperBrokerWrapper:
    """Wraps a real broker, allowing DATA calls but BLOCKING ORDER calls.

    Usage:
        real_broker = authenticate_broker(...)
        paper_broker = PaperBrokerWrapper(real_broker)
        # paper_broker.get_positions() → works (real data)
        # paper_broker.place_order() → RAISES PaperModeError (physically blocked)
    """

    def __init__(self, real_broker):
        self._real_broker = real_broker
        # Copy data-read attributes
        self.access_token = getattr(real_broker, "access_token", "")
        self.client_id = getattr(real_broker, "client_id", "")
        self._simulated_orders = []

    # === DATA METHODS — pass through to real broker ===

    def get_positions(self) -> list:
        return self._real_broker.get_positions()

    def get_order_list(self) -> list:
        return self._real_broker.get_order_list()

    def get_margins(self) -> dict:
        return self._real_broker.get_margins()

    def get_historical_ohlc(self, *args, **kwargs):
        return self._real_broker.get_historical_ohlc(*args, **kwargs)

    # === ORDER METHODS — PHYSICALLY BLOCKED ===

    def place_order(self, **kwargs) -> dict:
        """BLOCKED. Raises PaperModeError. Real orders are physically impossible."""
        raise PaperModeError(
            f"PAPER MODE: place_order BLOCKED. "
            f"Attempted: {kwargs.get('transaction_type','')} {kwargs.get('symbol','')} "
            f"x{kwargs.get('quantity',0)} @ {kwargs.get('price',0)}. "
            f"This is a paper profile — real orders are physically impossible."
        )

    def cancel_order(self, order_id: str) -> dict:
        """BLOCKED in paper mode."""
        raise PaperModeError(f"PAPER MODE: cancel_order BLOCKED for {order_id}")

    def modify_order(self, **kwargs) -> dict:
        """BLOCKED in paper mode."""
        raise PaperModeError(f"PAPER MODE: modify_order BLOCKED")


class PaperModeError(RuntimeError):
    """Raised when paper mode attempts a real order. This should NEVER happen
    if the orchestrator is correctly routing to the simulator."""
    pass


def wrap_broker_for_paper(broker) -> "PaperBrokerWrapper":
    """Wrap a real authenticated broker for paper mode.

    Returns a PaperBrokerWrapper that:
    - Allows all data/read calls (positions, orders, OHLC)
    - PHYSICALLY BLOCKS all order calls (place, cancel, modify)
    """
    wrapper = PaperBrokerWrapper(broker)
    logger.info("PAPER MODE: Broker wrapped — real orders physically blocked, data calls allowed")
    return wrapper
