"""Broker abstraction layer for the intraday auto-trader.

Defines the BrokerClient abstract base class and a factory function
to instantiate the correct broker implementation based on config.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BrokerClient(ABC):
    """Abstract broker interface.

    All trading components (Order_Executor, Position_Monitor, Risk_Manager)
    interact exclusively with this interface — never with broker-specific
    implementations directly.
    """

    @abstractmethod
    def authenticate(self) -> bool:
        """Perform broker authentication / OAuth login.

        Returns:
            True on success, False on failure.
        """
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        product_type: str,
        quantity: int,
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> dict:
        """Place an order with the broker.

        Args:
            symbol: Trading symbol (e.g. ``"RELIANCE"``).
            exchange: Exchange segment (e.g. ``"NSE"``).
            transaction_type: ``"BUY"`` or ``"SELL"``.
            order_type: ``"LIMIT"``, ``"MARKET"``, or ``"SL"``.
            product_type: ``"INTRADAY"`` (normalised).
            quantity: Number of shares.
            price: Limit price (0 for market orders).
            trigger_price: Stop-loss trigger price (0 when not applicable).

        Returns:
            Dict with at least ``{"broker_order_id": str, "status": str}``.
        """
        ...

    @abstractmethod
    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> dict:
        """Modify an existing order.

        Only the provided (non-None) fields are updated.

        Returns:
            Dict with at least ``{"broker_order_id": str, "status": str}``.
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order.

        Returns:
            Dict with at least ``{"broker_order_id": str, "status": str}``.
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Fetch current positions from the broker.

        Returns:
            Normalised list of dicts, each containing::

                {
                    "symbol": str,
                    "tradingsymbol": str,
                    "quantity": int,
                    "buy_avg": float,
                    "sell_avg": float,
                    "pnl": float,
                    "product_type": str,
                }
        """
        ...

    @abstractmethod
    def get_margins(self) -> dict:
        """Fetch account margin / fund information.

        Returns:
            Dict with at least::

                {"available_cash": float, "used_margin": float}
        """
        ...

    # ── F&O abstract methods ─────────────────────────────────────────

    @abstractmethod
    def place_fno_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        product_type: str,
        quantity: int,
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> dict:
        """Place an F&O order with the broker.

        Args:
            tradingsymbol: Broker-specific F&O trading symbol.
            exchange: Exchange segment (``"NFO"`` for Zerodha, ``"NSE_FNO"`` for Dhan).
            transaction_type: ``"BUY"`` or ``"SELL"``.
            order_type: ``"LIMIT"``, ``"MARKET"``, or ``"SL"``.
            product_type: ``"NRML"`` or ``"MIS"``.
            quantity: Number of units (lots × lot_size).
            price: Limit price (0 for market orders).
            trigger_price: Stop-loss trigger price (0 when not applicable).

        Returns:
            Dict with at least ``{"broker_order_id": str, "status": str}``.
        """
        ...

    @abstractmethod
    def get_fno_positions(self) -> list[dict]:
        """Fetch current F&O positions from the broker.

        Returns:
            Normalised list of dicts, each containing::

                {
                    "tradingsymbol": str,
                    "index_name": str,
                    "option_type": str,
                    "strike_price": float,
                    "expiry_date": str,
                    "quantity": int,
                    "buy_avg": float,
                    "sell_avg": float,
                    "pnl": float,
                    "product_type": str,
                }
        """
        ...

    @abstractmethod
    def get_fno_margins(self) -> dict:
        """Fetch F&O-specific margin information.

        Returns:
            Dict with at least::

                {
                    "available_margin": float,
                    "used_margin": float,
                    "span_margin": float,
                    "exposure_margin": float,
                }
        """
        ...


def broker_factory(broker_name: str, config: dict) -> BrokerClient:
    """Instantiate the correct BrokerClient implementation.

    Args:
        broker_name: ``"dhan"`` or ``"zerodha"``.
        config: The broker-specific config section from *config.yaml*.

    Returns:
        A concrete ``BrokerClient`` instance.

    Raises:
        ValueError: If *broker_name* is not a supported broker.
    """
    name = broker_name.strip().lower()

    if name == "dhan":
        from intraday.dhan_broker import DhanBrokerClient

        logger.info("Instantiating DhanBrokerClient")
        return DhanBrokerClient(
            client_id=config.get("client_id", ""),
            api_key=config.get("api_key", ""),
            api_secret=config.get("api_secret", ""),
            access_token=config.get("access_token"),
        )

    if name == "zerodha":
        from intraday.zerodha_broker import ZerodhaBrokerClient

        logger.info("Instantiating ZerodhaBrokerClient")
        return ZerodhaBrokerClient(
            api_key=config.get("api_key", ""),
            api_secret=config.get("api_secret", ""),
            user_id=config.get("user_id", ""),
            access_token=config.get("access_token"),
        )

    supported = ["dhan", "zerodha"]
    raise ValueError(
        f"Unsupported broker '{broker_name}'. Supported brokers: {supported}"
    )
