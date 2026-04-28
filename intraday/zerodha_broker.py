"""Zerodha Kite Connect broker implementation for the intraday auto-trader.

Maps the ``BrokerClient`` abstract interface to the ``kiteconnect`` Python SDK.
The SDK is imported conditionally so the module can be loaded even when
``kiteconnect`` is not installed (e.g. when using Dhan).
"""

import logging
from typing import Any, Optional

from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

# Conditional import — kiteconnect may not be installed.
try:
    from kiteconnect import KiteConnect  # type: ignore[import-untyped]

    _KITE_AVAILABLE = True
except ImportError:
    KiteConnect = None  # type: ignore[assignment,misc]
    _KITE_AVAILABLE = False
    logger.debug("kiteconnect SDK not installed — ZerodhaBrokerClient unavailable")


class ZerodhaBrokerClient(BrokerClient):
    """Concrete ``BrokerClient`` backed by the Zerodha Kite Connect SDK.

    Args:
        api_key: Kite Connect API key.
        api_secret: Kite Connect API secret.
        user_id: Zerodha user / client ID.
        access_token: Pre-existing access token (optional).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        user_id: str,
        access_token: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.user_id = user_id
        self.access_token = access_token or ""

        self.kite: Any = None
        if _KITE_AVAILABLE:
            self.kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self.kite.set_access_token(self.access_token)
        else:
            logger.warning(
                "kiteconnect SDK not installed — broker operations will fail"
            )

    # ------------------------------------------------------------------
    # BrokerClient interface
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate with Zerodha Kite Connect.

        For now this initialises ``KiteConnect`` with the api_key and sets
        the access_token if available.  The full login-URL → request_token
        → generate_session flow will be wired in the ``auth_server`` task.
        """
        if not _KITE_AVAILABLE:
            logger.error("Cannot authenticate — kiteconnect SDK not installed")
            return False

        if self.kite is None:
            self.kite = KiteConnect(api_key=self.api_key)

        if self.access_token:
            self.kite.set_access_token(self.access_token)
            logger.info("Zerodha: using pre-configured access token")
            return True

        logger.warning(
            "Zerodha: no access_token provided — full auth not yet implemented"
        )
        return False

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
        """Place an intraday order via Kite Connect SDK.

        Uses ``kite.place_order(variety="regular", exchange="NSE",
        product="MIS", ...)``.
        """
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"broker_order_id": "", "status": "error", "error": "SDK not available"}

        # Map generic product type to Kite's MIS for intraday
        kite_product = "MIS" if product_type.upper() == "INTRADAY" else product_type

        kite_exchange = exchange.upper()
        if kite_exchange in ("NSE", "NSE_EQ"):
            kite_exchange = "NSE"

        logger.info(
            "Zerodha place_order: %s %s x%d @ %.2f",
            transaction_type, symbol, quantity, price,
        )

        try:
            order_params: dict[str, Any] = {
                "variety": "regular",
                "exchange": kite_exchange,
                "tradingsymbol": symbol,
                "transaction_type": transaction_type.upper(),
                "order_type": order_type.upper(),
                "product": kite_product,
                "quantity": quantity,
            }
            if price and order_type.upper() in ("LIMIT", "SL"):
                order_params["price"] = price
            if trigger_price and order_type.upper() in ("SL", "SL-M"):
                order_params["trigger_price"] = trigger_price

            order_id = self.kite.place_order(**order_params)

            return {
                "broker_order_id": str(order_id),
                "status": "placed",
            }
        except Exception as exc:
            logger.error("Zerodha place_order failed: %s", exc)
            return {"broker_order_id": "", "status": "error", "error": str(exc)}

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> dict:
        """Modify an existing order via Kite Connect SDK."""
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"broker_order_id": str(order_id), "status": "error", "error": "SDK not available"}

        logger.info("Zerodha modify_order: %s", order_id)

        try:
            params: dict[str, Any] = {
                "variety": "regular",
                "order_id": order_id,
            }
            if quantity is not None:
                params["quantity"] = quantity
            if price is not None:
                params["price"] = price
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            if order_type is not None:
                params["order_type"] = order_type.upper()

            self.kite.modify_order(**params)

            return {
                "broker_order_id": str(order_id),
                "status": "modified",
            }
        except Exception as exc:
            logger.error("Zerodha modify_order failed: %s", exc)
            return {"broker_order_id": str(order_id), "status": "error", "error": str(exc)}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an order via Kite Connect SDK."""
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"broker_order_id": str(order_id), "status": "error", "error": "SDK not available"}

        logger.info("Zerodha cancel_order: %s", order_id)

        try:
            self.kite.cancel_order(variety="regular", order_id=order_id)

            return {
                "broker_order_id": str(order_id),
                "status": "cancelled",
            }
        except Exception as exc:
            logger.error("Zerodha cancel_order failed: %s", exc)
            return {"broker_order_id": str(order_id), "status": "error", "error": str(exc)}

    def get_positions(self) -> list[dict]:
        """Fetch positions via ``kite.positions()["net"]``.

        Normalises Kite fields to the common dict format::

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
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return []

        logger.info("Zerodha get_positions")

        try:
            positions_data = self.kite.positions()
            net_positions = positions_data.get("net", [])
        except Exception as exc:
            logger.error("Zerodha get_positions failed: %s", exc)
            return []

        normalised: list[dict] = []
        for pos in net_positions:
            pnl = float(pos.get("pnl", 0)) + float(pos.get("unrealised", 0))
            normalised.append(
                {
                    "symbol": str(pos.get("tradingsymbol", "")),
                    "tradingsymbol": str(pos.get("tradingsymbol", "")),
                    "quantity": int(pos.get("quantity", 0)),
                    "buy_avg": float(pos.get("average_price", pos.get("buy_price", 0))),
                    "sell_avg": float(pos.get("sell_price", 0)),
                    "pnl": pnl,
                    "product_type": str(pos.get("product", "MIS")),
                }
            )

        return normalised

    def get_margins(self) -> dict:
        """Fetch margins via ``kite.margins()``.

        Normalises to ``{"available_cash": float, "used_margin": float}``.
        """
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"available_cash": 0.0, "used_margin": 0.0}

        logger.info("Zerodha get_margins")

        try:
            margins = self.kite.margins()
            # Kite returns margins per segment; use equity segment
            equity = margins.get("equity", margins)

            available = float(
                equity.get("available", {}).get("cash", equity.get("net", 0))
            )
            used = float(
                equity.get("utilised", {}).get("debits", equity.get("utilised", 0))
            )

            return {"available_cash": available, "used_margin": used}
        except Exception as exc:
            logger.error("Zerodha get_margins failed: %s", exc)
            return {"available_cash": 0.0, "used_margin": 0.0}

    # ── F&O methods ──────────────────────────────────────────────────

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
        """Place an F&O order via Kite Connect SDK with ``exchange="NFO"``."""
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"broker_order_id": "", "status": "error", "error": "SDK not available"}

        logger.info(
            "Zerodha place_fno_order: %s %s x%d @ %.2f",
            transaction_type, tradingsymbol, quantity, price,
        )

        try:
            order_params: dict[str, Any] = {
                "variety": "regular",
                "exchange": "NFO",
                "tradingsymbol": tradingsymbol,
                "transaction_type": transaction_type.upper(),
                "order_type": order_type.upper(),
                "product": product_type.upper(),
                "quantity": quantity,
            }
            if price and order_type.upper() in ("LIMIT", "SL"):
                order_params["price"] = price
            if trigger_price and order_type.upper() in ("SL", "SL-M"):
                order_params["trigger_price"] = trigger_price

            order_id = self.kite.place_order(**order_params)

            return {
                "broker_order_id": str(order_id),
                "status": "placed",
            }
        except Exception as exc:
            logger.error("Zerodha place_fno_order failed: %s", exc)
            return {"broker_order_id": "", "status": "error", "error": str(exc)}

    def get_fno_positions(self) -> list[dict]:
        """Fetch F&O positions via ``kite.positions()["net"]`` filtered for NFO."""
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return []

        logger.info("Zerodha get_fno_positions")

        try:
            positions_data = self.kite.positions()
            net_positions = positions_data.get("net", [])
        except Exception as exc:
            logger.error("Zerodha get_fno_positions failed: %s", exc)
            return []

        normalised: list[dict] = []
        for pos in net_positions:
            exchange = str(pos.get("exchange", ""))
            if exchange != "NFO":
                continue

            pnl = float(pos.get("pnl", 0)) + float(pos.get("unrealised", 0))
            tradingsymbol = str(pos.get("tradingsymbol", ""))

            normalised.append({
                "tradingsymbol": tradingsymbol,
                "index_name": str(pos.get("instrument_token", tradingsymbol[:5])),
                "option_type": str(pos.get("option_type", "")),
                "strike_price": float(pos.get("strike", 0)),
                "expiry_date": str(pos.get("expiry", "")),
                "quantity": int(pos.get("quantity", 0)),
                "buy_avg": float(pos.get("average_price", pos.get("buy_price", 0))),
                "sell_avg": float(pos.get("sell_price", 0)),
                "pnl": pnl,
                "product_type": str(pos.get("product", "NRML")),
            })

        return normalised

    def get_fno_margins(self) -> dict:
        """Fetch F&O margins via ``kite.margins()`` commodity/equity segment."""
        if self.kite is None:
            logger.error("Zerodha: KiteConnect not initialised")
            return {"available_margin": 0.0, "used_margin": 0.0, "span_margin": 0.0, "exposure_margin": 0.0}

        logger.info("Zerodha get_fno_margins")

        try:
            margins = self.kite.margins()
            # Use equity segment for F&O margins on NSE
            equity = margins.get("equity", margins)

            available = float(
                equity.get("available", {}).get("cash", equity.get("net", 0))
            )
            used = float(
                equity.get("utilised", {}).get("debits", equity.get("utilised", 0))
            )
            span = float(
                equity.get("utilised", {}).get("span", 0)
            )
            exposure = float(
                equity.get("utilised", {}).get("exposure", 0)
            )

            return {
                "available_margin": available,
                "used_margin": used,
                "span_margin": span,
                "exposure_margin": exposure,
            }
        except Exception as exc:
            logger.error("Zerodha get_fno_margins failed: %s", exc)
            return {"available_margin": 0.0, "used_margin": 0.0, "span_margin": 0.0, "exposure_margin": 0.0}
