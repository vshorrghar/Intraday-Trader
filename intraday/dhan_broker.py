"""Dhan broker implementation for the intraday auto-trader.

Maps the ``BrokerClient`` abstract interface to the Dhan REST API v2.

API reference:
    - Orders:    POST   https://api.dhan.co/v2/orders
    - Modify:    PUT    https://api.dhan.co/v2/orders/{orderId}
    - Cancel:    DELETE https://api.dhan.co/v2/orders/{orderId}
    - Positions: GET    https://api.dhan.co/v2/positions
    - Margins:   GET    https://api.dhan.co/v2/fundlimit
"""

import logging
from typing import Any, Optional

import requests

from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dhan.co/v2"


class DhanBrokerClient(BrokerClient):
    """Concrete ``BrokerClient`` backed by the Dhan REST API v2.

    Args:
        client_id: Dhan client / user ID.
        api_key: Dhan application key (``app_id``).
        api_secret: Dhan application secret.
        access_token: Pre-existing access token (optional).  When provided
            the client skips the full TOTP-based auth flow and uses this
            token directly.
    """

    def __init__(
        self,
        client_id: str,
        api_key: str,
        api_secret: str,
        access_token: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token or ""
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Return common request headers including the access token."""
        return {
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _handle_response(self, resp: requests.Response, context: str) -> dict[str, Any]:
        """Parse a Dhan API response and log errors."""
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        if resp.status_code not in (200, 201):
            logger.error(
                "%s failed — HTTP %s: %s", context, resp.status_code, data
            )
            return {"status": "error", "error": data, "broker_order_id": ""}

        return data

    # ------------------------------------------------------------------
    # BrokerClient interface
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate with Dhan.

        For now this simply stores the access_token from config and
        returns ``True``.  The full TOTP-based flow (generate-consent →
        browser login → consume-consent) will be wired in the
        ``auth_server`` task.
        """
        if self.access_token:
            logger.info("Dhan: using pre-configured access token")
            return True

        logger.warning(
            "Dhan: no access_token provided — full TOTP auth not yet implemented"
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
        """Place an intraday order via Dhan REST API.

        POST ``/v2/orders`` with ``productType="INTRADAY"`` and
        ``exchangeSegment="NSE_EQ"``.
        """
        # Map generic order types to Dhan-specific values
        dhan_order_type_map = {
            "LIMIT": "LIMIT",
            "MARKET": "MARKET",
            "SL": "STOP_LOSS",
            "SL-M": "STOP_LOSS_MARKET",
        }
        dhan_txn_map = {"BUY": "BUY", "SELL": "SELL"}

        payload = {
            "dhanClientId": self.client_id,
            "transactionType": dhan_txn_map.get(transaction_type, transaction_type),
            "exchangeSegment": "NSE_EQ",
            "productType": "INTRADAY",
            "orderType": dhan_order_type_map.get(order_type, order_type),
            "validity": "DAY",
            "securityId": symbol,
            "quantity": quantity,
            "price": price,
            "triggerPrice": trigger_price,
        }

        logger.info("Dhan place_order: %s %s x%d @ %.2f", transaction_type, symbol, quantity, price)

        resp = self._session.post(
            f"{BASE_URL}/orders",
            json=payload,
            headers=self._headers(),
        )
        data = self._handle_response(resp, "Dhan place_order")

        # Normalise broker_order_id
        order_id = data.get("orderId") or data.get("order_id") or ""
        data["broker_order_id"] = str(order_id)
        data.setdefault("status", "placed")
        return data

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> dict:
        """Modify an existing order via PUT ``/v2/orders/{orderId}``."""
        dhan_order_type_map = {
            "LIMIT": "LIMIT",
            "MARKET": "MARKET",
            "SL": "STOP_LOSS",
            "SL-M": "STOP_LOSS_MARKET",
        }

        payload: dict[str, Any] = {
            "dhanClientId": self.client_id,
            "orderId": order_id,
        }
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["triggerPrice"] = trigger_price
        if order_type is not None:
            payload["orderType"] = dhan_order_type_map.get(order_type, order_type)

        logger.info("Dhan modify_order: %s", order_id)

        resp = self._session.put(
            f"{BASE_URL}/orders/{order_id}",
            json=payload,
            headers=self._headers(),
        )
        data = self._handle_response(resp, "Dhan modify_order")
        data["broker_order_id"] = str(order_id)
        data.setdefault("status", "modified")
        return data

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an order via DELETE ``/v2/orders/{orderId}``."""
        logger.info("Dhan cancel_order: %s", order_id)

        resp = self._session.delete(
            f"{BASE_URL}/orders/{order_id}",
            headers=self._headers(),
        )
        data = self._handle_response(resp, "Dhan cancel_order")
        data["broker_order_id"] = str(order_id)
        data.setdefault("status", "cancelled")
        return data

    def get_positions(self) -> list[dict]:
        """Fetch positions via GET ``/v2/positions``.

        Normalises Dhan fields to the common dict format::

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
        logger.info("Dhan get_positions")

        resp = self._session.get(
            f"{BASE_URL}/positions",
            headers=self._headers(),
        )

        if resp.status_code != 200:
            logger.error("Dhan get_positions failed — HTTP %s", resp.status_code)
            return []

        try:
            raw_positions = resp.json()
        except ValueError:
            logger.error("Dhan get_positions: invalid JSON response")
            return []

        # Dhan may return a list directly or wrap it in a key
        if isinstance(raw_positions, dict):
            raw_positions = raw_positions.get("data", raw_positions.get("positions", []))

        normalised: list[dict] = []
        for pos in raw_positions:
            realised = float(pos.get("realizedProfit", 0))
            unrealised = float(pos.get("unrealizedProfit", 0))
            normalised.append(
                {
                    "symbol": str(pos.get("tradingSymbol", pos.get("securityId", ""))),
                    "tradingsymbol": str(pos.get("tradingSymbol", "")),
                    "quantity": int(pos.get("netQty", pos.get("quantity", 0))),
                    "buy_avg": float(pos.get("buyAvg", pos.get("buyAvgPrice", 0))),
                    "sell_avg": float(pos.get("sellAvg", pos.get("sellAvgPrice", 0))),
                    "pnl": realised + unrealised,
                    "product_type": str(pos.get("productType", "INTRADAY")),
                }
            )

        return normalised

    def get_margins(self) -> dict:
        """Fetch fund limits via GET ``/v2/fundlimit``.

        Normalises to ``{"available_cash": float, "used_margin": float}``.
        """
        logger.info("Dhan get_margins")

        resp = self._session.get(
            f"{BASE_URL}/fundlimit",
            headers=self._headers(),
        )

        if resp.status_code != 200:
            logger.error("Dhan get_margins failed — HTTP %s", resp.status_code)
            return {"available_cash": 0.0, "used_margin": 0.0}

        try:
            data = resp.json()
        except ValueError:
            logger.error("Dhan get_margins: invalid JSON response")
            return {"available_cash": 0.0, "used_margin": 0.0}

        # Dhan fundlimit response may have various field names
        available = float(
            data.get("availabelBalance", data.get("availableBalance", data.get("sodLimit", 0)))
        )
        used = float(
            data.get("utilizedAmount", data.get("blockedPayoutAmount", 0))
        )

        return {"available_cash": available, "used_margin": used}

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
        """Place an F&O order via Dhan REST API with ``exchangeSegment="NSE_FNO"``."""
        dhan_order_type_map = {
            "LIMIT": "LIMIT",
            "MARKET": "MARKET",
            "SL": "STOP_LOSS",
            "SL-M": "STOP_LOSS_MARKET",
        }
        dhan_txn_map = {"BUY": "BUY", "SELL": "SELL"}

        payload = {
            "dhanClientId": self.client_id,
            "transactionType": dhan_txn_map.get(transaction_type, transaction_type),
            "exchangeSegment": "NSE_FNO",
            "productType": product_type.upper(),
            "orderType": dhan_order_type_map.get(order_type, order_type),
            "validity": "DAY",
            "securityId": tradingsymbol,
            "quantity": quantity,
            "price": price,
            "triggerPrice": trigger_price,
        }

        logger.info(
            "Dhan place_fno_order: %s %s x%d @ %.2f",
            transaction_type, tradingsymbol, quantity, price,
        )

        resp = self._session.post(
            f"{BASE_URL}/orders",
            json=payload,
            headers=self._headers(),
        )
        data = self._handle_response(resp, "Dhan place_fno_order")

        order_id = data.get("orderId") or data.get("order_id") or ""
        data["broker_order_id"] = str(order_id)
        data.setdefault("status", "placed")
        return data

    def get_fno_positions(self) -> list[dict]:
        """Fetch F&O positions via GET ``/v2/positions`` filtered for NSE_FNO."""
        logger.info("Dhan get_fno_positions")

        resp = self._session.get(
            f"{BASE_URL}/positions",
            headers=self._headers(),
        )

        if resp.status_code != 200:
            logger.error("Dhan get_fno_positions failed — HTTP %s", resp.status_code)
            return []

        try:
            raw_positions = resp.json()
        except ValueError:
            logger.error("Dhan get_fno_positions: invalid JSON response")
            return []

        if isinstance(raw_positions, dict):
            raw_positions = raw_positions.get("data", raw_positions.get("positions", []))

        normalised: list[dict] = []
        for pos in raw_positions:
            segment = str(pos.get("exchangeSegment", ""))
            if segment not in ("NSE_FNO", "NFO"):
                continue

            realised = float(pos.get("realizedProfit", 0))
            unrealised = float(pos.get("unrealizedProfit", 0))
            normalised.append({
                "tradingsymbol": str(pos.get("tradingSymbol", "")),
                "index_name": str(pos.get("tradingSymbol", ""))[:5].rstrip("0123456789"),
                "option_type": str(pos.get("optionType", "")),
                "strike_price": float(pos.get("strikePrice", 0)),
                "expiry_date": str(pos.get("expiryDate", "")),
                "quantity": int(pos.get("netQty", pos.get("quantity", 0))),
                "buy_avg": float(pos.get("buyAvg", pos.get("buyAvgPrice", 0))),
                "sell_avg": float(pos.get("sellAvg", pos.get("sellAvgPrice", 0))),
                "pnl": realised + unrealised,
                "product_type": str(pos.get("productType", "NRML")),
            })

        return normalised

    def get_fno_margins(self) -> dict:
        """Fetch F&O margin info via GET ``/v2/fundlimit``."""
        logger.info("Dhan get_fno_margins")

        resp = self._session.get(
            f"{BASE_URL}/fundlimit",
            headers=self._headers(),
        )

        if resp.status_code != 200:
            logger.error("Dhan get_fno_margins failed — HTTP %s", resp.status_code)
            return {"available_margin": 0.0, "used_margin": 0.0, "span_margin": 0.0, "exposure_margin": 0.0}

        try:
            data = resp.json()
        except ValueError:
            logger.error("Dhan get_fno_margins: invalid JSON response")
            return {"available_margin": 0.0, "used_margin": 0.0, "span_margin": 0.0, "exposure_margin": 0.0}

        available = float(
            data.get("availabelBalance", data.get("availableBalance", data.get("sodLimit", 0)))
        )
        used = float(data.get("utilizedAmount", data.get("blockedPayoutAmount", 0)))
        span = float(data.get("spanMargin", 0))
        exposure = float(data.get("exposureMargin", 0))

        return {
            "available_margin": available,
            "used_margin": used,
            "span_margin": span,
            "exposure_margin": exposure,
        }

    # ------------------------------------------------------------------
    # Option Chain
    # ------------------------------------------------------------------

    def get_option_chain(self, index: str) -> dict:
        """Fetch live option chain from Dhan API.

        Uses Dhan's ``/v2/optionchain`` endpoint.  Returns raw JSON with
        strikes, OI, IV, LTP, bid/ask for all expiries.

        Parameters
        ----------
        index : str
            Index name — ``"NIFTY"``, ``"BANKNIFTY"``, or ``"FINNIFTY"``.

        Returns
        -------
        dict
            Raw option chain data from Dhan.
        """
        # Dhan security IDs for index options
        SECURITY_IDS = {
            "NIFTY": "26000",
            "BANKNIFTY": "26009",
            "FINNIFTY": "26037",
        }

        sec_id = SECURITY_IDS.get(index.upper())
        if not sec_id:
            raise ValueError(f"Unknown index '{index}' for Dhan option chain")

        logger.info("Dhan get_option_chain: %s (securityId=%s)", index, sec_id)

        # Dhan option chain endpoint
        payload = {
            "Data": {
                "Seg": "I",
                "Sid": sec_id,
                "Exp": 0,  # 0 = current expiry, 1 = next expiry
            }
        }

        resp = self._session.post(
            f"{BASE_URL}/optionchain",
            json=payload,
            headers=self._headers(),
        )

        if resp.status_code != 200:
            # Fallback: try the v2 marketfeed endpoint
            logger.warning(
                "Dhan optionchain returned HTTP %s — trying marketfeed fallback",
                resp.status_code,
            )
            return self._get_option_chain_via_marketfeed(index, sec_id)

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"Dhan option chain: invalid JSON for {index}")

        if not data or data.get("status") == "failure":
            raise RuntimeError(
                f"Dhan option chain failed for {index}: {data.get('remarks', 'unknown error')}"
            )

        # Normalize to standard format
        return self._normalize_option_chain(index, data)

    def _get_option_chain_via_marketfeed(self, index: str, sec_id: str) -> dict:
        """Fallback: fetch option chain via Dhan market feed API."""
        resp = self._session.get(
            f"{BASE_URL}/marketfeed/optionchain",
            params={"securityId": sec_id, "exchangeSegment": "NSE_FNO"},
            headers=self._headers(),
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Dhan option chain fallback failed for {index}: HTTP {resp.status_code}"
            )

        return resp.json()

    @staticmethod
    def _normalize_option_chain(index: str, raw: dict) -> dict:
        """Normalize Dhan option chain response to standard format.

        Returns dict with keys: index, spot_price, expiry_date, strikes.
        Each strike has: strike_price, option_type, ltp, bid, ask, oi, oi_change, volume, iv.
        """
        strikes = []
        spot_price = 0.0

        # Dhan returns data in various formats depending on API version
        chain_data = raw.get("data", raw.get("oc", raw))

        if isinstance(chain_data, list):
            for item in chain_data:
                spot_price = float(item.get("spot_price", item.get("underlyingValue", spot_price)))
                strike_price = float(item.get("strikePrice", item.get("strike_price", 0)))
                expiry = item.get("expiryDate", item.get("expiry_date", ""))

                for opt_type in ("CE", "PE"):
                    prefix = opt_type.lower() + "_"
                    alt_prefix = opt_type + "_"

                    ltp = float(item.get(f"{prefix}ltp", item.get(f"{alt_prefix}ltp", 0)))
                    oi = int(item.get(f"{prefix}oi", item.get(f"{alt_prefix}oi", 0)))
                    volume = int(item.get(f"{prefix}volume", item.get(f"{alt_prefix}volume", 0)))
                    iv = float(item.get(f"{prefix}iv", item.get(f"{alt_prefix}iv", 0)))
                    bid = float(item.get(f"{prefix}bid", item.get(f"{alt_prefix}bid", ltp * 0.98)))
                    ask = float(item.get(f"{prefix}ask", item.get(f"{alt_prefix}ask", ltp * 1.02)))
                    oi_change = int(item.get(f"{prefix}oi_change", item.get(f"{alt_prefix}oiChange", 0)))

                    if ltp > 0 or oi > 0:
                        strikes.append({
                            "strike_price": strike_price,
                            "option_type": opt_type,
                            "expiry_date": expiry,
                            "ltp": ltp,
                            "bid_price": bid,
                            "ask_price": ask,
                            "open_interest": oi,
                            "oi_change": oi_change,
                            "volume": volume,
                            "iv": iv,
                        })

        elif isinstance(chain_data, dict):
            spot_price = float(chain_data.get("spotPrice", chain_data.get("underlyingValue", 0)))
            for strike_key, strike_data in chain_data.items():
                if not isinstance(strike_data, dict):
                    continue
                try:
                    strike_price = float(strike_key)
                except (ValueError, TypeError):
                    continue

                for opt_type in ("CE", "PE"):
                    opt_data = strike_data.get(opt_type, {})
                    if not opt_data:
                        continue
                    strikes.append({
                        "strike_price": strike_price,
                        "option_type": opt_type,
                        "expiry_date": opt_data.get("expiryDate", ""),
                        "ltp": float(opt_data.get("ltp", 0)),
                        "bid_price": float(opt_data.get("bid", 0)),
                        "ask_price": float(opt_data.get("ask", 0)),
                        "open_interest": int(opt_data.get("oi", 0)),
                        "oi_change": int(opt_data.get("oiChange", 0)),
                        "volume": int(opt_data.get("volume", 0)),
                        "iv": float(opt_data.get("iv", 0)),
                    })

        return {
            "index": index,
            "spot_price": spot_price,
            "strikes": strikes,
        }
