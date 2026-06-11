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

        # Load NSE security ID mapping
        import json as _json
        import os as _os
        _map_path = _os.path.join(_os.path.dirname(__file__), '..', 'config', 'nse_security_ids.json')
        try:
            with open(_map_path) as _f:
                self._security_ids = _json.load(_f)
            logger.info("Loaded %d NSE security IDs", len(self._security_ids))
        except Exception:
            self._security_ids = {}
            logger.warning("Could not load nse_security_ids.json — securityId will use symbol name")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Return common request headers including the access token + client-id.

        Note: client-id is REQUIRED by Dhan optionchain endpoint per official docs.
        Other endpoints (orders, positions) accept it without harm.
        """
        return {
            "access-token": self.access_token,
            "client-id": self.client_id,
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

    def _get_security_id(self, symbol: str) -> str:
        """Return numeric Dhan security ID for NSE symbol."""
        return self._security_ids.get(symbol, symbol)

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
            "securityId": self._get_security_id(symbol),
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

    def get_order_list(self) -> list[dict]:
        """Fetch all orders for the day via GET ``/v2/orders``.

        Returns list of order dicts. Each dict has fields:
        - orderId: str
        - orderStatus: str (PENDING, TRADED, REJECTED, CANCELLED, etc.)
        - filledQty: int (quantity actually executed)
        - remainingQuantity: int (quantity not yet executed)
        - tradingSymbol, transactionType, price, etc.
        """
        logger.info("Dhan get_order_list")
        resp = self._session.get(
            f"{BASE_URL}/orders",
            headers=self._headers(),
        )
        data = self._handle_response(resp, "Dhan get_order_list")
        # Dhan returns either a list directly OR {"data": [...]}
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", []) or []
        return []

    def get_order_status(self, order_id: str) -> str:
        """Get status of a specific order. Returns status string or empty string on failure."""
        try:
            orders = self.get_order_list()
            for o in orders:
                if str(o.get("orderId", "")) == str(order_id):
                    return str(o.get("orderStatus", ""))
            return ""
        except Exception as e:
            logger.warning("get_order_status failed for %s: %s", order_id, e)
            return ""

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
            "securityId": self._get_security_id(tradingsymbol),
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

    def get_option_chain(self, index: str, expiry: str = "") -> dict:
        """Fetch live option chain from Dhan API per official v2 spec.

        Endpoint: POST /v2/optionchain
        Payload: {"UnderlyingScrip": , "UnderlyingSeg": "IDX_I", "Expiry": "YYYY-MM-DD"}
        Headers: access-token + client-id (both required)

        Parameters
        ----------
        index : str
            "NIFTY", "BANKNIFTY", or "FINNIFTY".
        expiry : str
            Expiry "YYYY-MM-DD". If empty, fetches expirylist and uses nearest.

        Returns
        -------
        dict with keys: index, spot_price, expiry_date, strikes (flat list).
        """
        # Per Dhan v2 docs: NIFTY=13, BANKNIFTY=25, FINNIFTY=27 (UnderlyingScrip ints, not 26000-series)
        SCRIP_IDS = {
            "NIFTY": 13,
            "BANKNIFTY": 25,
            "FINNIFTY": 27,
        }

        scrip_id = SCRIP_IDS.get(index.upper())
        if scrip_id is None:
            raise ValueError(f"Unknown index '{index}' for Dhan option chain")

        # Step 1: get nearest expiry if not provided
        if not expiry:
            try:
                exp_resp = self._session.post(
                    f"{BASE_URL}/optionchain/expirylist",
                    json={"UnderlyingScrip": scrip_id, "UnderlyingSeg": "IDX_I"},
                    headers=self._headers(),
                    timeout=10,
                )
                if exp_resp.status_code == 200:
                    exp_data = exp_resp.json()
                    expiries = exp_data.get("data", [])
                    if expiries:
                        expiry = expiries[0]
                        logger.info("Dhan expirylist: nearest=%s (total=%d)", expiry, len(expiries))
                else:
                    logger.warning("Dhan expirylist HTTP %s: %s", exp_resp.status_code, exp_resp.text[:200])
            except Exception as e:
                logger.warning("Dhan expirylist fetch failed: %s", e)

        if not expiry:
            logger.error("Dhan optionchain: no expiry available for %s", index)
            return {"index": index, "spot_price": 0.0, "expiry_date": "", "strikes": []}

        logger.info("Dhan get_option_chain: %s (scrip=%d, expiry=%s)", index, scrip_id, expiry)

        # Step 2: fetch the actual chain
        payload = {
            "UnderlyingScrip": scrip_id,
            "UnderlyingSeg": "IDX_I",
            "Expiry": expiry,
        }

        resp = self._session.post(
            f"{BASE_URL}/optionchain",
            json=payload,
            headers=self._headers(),
            timeout=15,
        )

        if resp.status_code != 200:
            logger.warning(
                "Dhan optionchain HTTP %s for %s: %s",
                resp.status_code, index, resp.text[:300]
            )
            return {"index": index, "spot_price": 0.0, "expiry_date": expiry, "strikes": []}

        try:
            data = resp.json()
        except ValueError:
            logger.error("Dhan optionchain: invalid JSON for %s", index)
            return {"index": index, "spot_price": 0.0, "expiry_date": expiry, "strikes": []}

        if not data or data.get("status") != "success":
            logger.warning("Dhan optionchain status=%s for %s", data.get("status"), index)
            return {"index": index, "spot_price": 0.0, "expiry_date": expiry, "strikes": []}

        return self._normalize_option_chain_v2(index, expiry, data)

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
    def _normalize_option_chain_v2(index: str, expiry: str, raw: dict) -> dict:
        """Parse Dhan v2 optionchain response into pnl_calculator's expected format.

        Dhan v2 returns:
          {"data": {"last_price": 25642.8,
                    "oc": {"25650.000000": {"ce": {...}, "pe": {...}}, ...}},
           "status": "success"}

        Returns:
          {"index": str, "spot_price": float, "expiry_date": str,
           "strikes": [{"strike_price": ..., "option_type": "CE"|"PE",
                        "ltp": ..., "bid_price": ..., "ask_price": ...,
                        "open_interest": ..., "volume": ..., "iv": ...}, ...]}
        """
        data = raw.get("data", {})
        spot = float(data.get("last_price", 0) or 0)
        oc = data.get("oc", {}) or {}

        strikes = []
        for strike_str, leg_pair in oc.items():
            try:
                strike_price = float(strike_str)
            except (TypeError, ValueError):
                continue

            for opt_type_lower in ("ce", "pe"):
                leg = leg_pair.get(opt_type_lower)
                if not leg:
                    continue
                strikes.append({
                    "strike_price": strike_price,
                    "option_type": opt_type_lower.upper(),
                    "expiry_date": expiry,
                    "ltp": float(leg.get("last_price", 0) or 0),
                    "bid_price": float(leg.get("top_bid_price", 0) or 0),
                    "ask_price": float(leg.get("top_ask_price", 0) or 0),
                    "open_interest": int(leg.get("oi", 0) or 0),
                    "oi_change": int((leg.get("oi", 0) or 0) - (leg.get("previous_oi", 0) or 0)),
                    "volume": int(leg.get("volume", 0) or 0),
                    "iv": float(leg.get("implied_volatility", 0) or 0),
                })

        return {
            "index": index,
            "spot_price": spot,
            "expiry_date": expiry,
            "strikes": strikes,
        }

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

    # ------------------------------------------------------------------
    # Historical OHLC (Data API — requires subscription)
    # ------------------------------------------------------------------

    def get_historical_ohlc(
        self,
        security_id: str,
        exchange_segment: str,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> dict | None:
        """Fetch historical OHLC candles from Dhan /v2/charts/intraday.

        Parameters
        ----------
        security_id : str
            Dhan security ID (e.g. "11536" for TCS).
        exchange_segment : str
            "NSE_EQ", "BSE_EQ", "NSE_FNO", etc.
        instrument : str
            "EQUITY", "FUTIDX", "OPTIDX", etc.
        interval : str
            Candle interval: "1", "5", "15", "25", "60".
        from_date : str
            Start date "YYYY-MM-DD".
        to_date : str
            End date "YYYY-MM-DD".

        Returns
        -------
        dict | None
            Dict with keys: open, high, low, close, volume, timestamp
            (each is a list). Returns None on failure.
        """
        url = f"{BASE_URL}/charts/intraday"
        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "interval": interval,
            "fromDate": from_date,
            "toDate": to_date,
        }
        try:
            resp = self._session.post(
                url, headers=self._headers(), json=payload, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "open" in data:
                    return data
                logger.warning("Dhan historical OHLC: unexpected response structure")
                return None
            else:
                logger.warning("Dhan historical OHLC HTTP %s for %s", resp.status_code, security_id)
                return None
        except Exception as e:
            logger.error("Dhan historical OHLC error for %s: %s", security_id, e)
            return None

    def get_daily_ohlc(
        self,
        security_id: str,
        exchange_segment: str = "NSE_EQ",
        instrument: str = "EQUITY",
        from_date: str = "",
        to_date: str = "",
    ) -> dict | None:
        """Fetch daily OHLC candles from Dhan /v2/charts/historical.

        Parameters
        ----------
        security_id : str
            Dhan security ID (e.g. "11536" for TCS).
        exchange_segment : str
            "NSE_EQ", "BSE_EQ", etc. Default "NSE_EQ".
        instrument : str
            "EQUITY", "FUTIDX", etc. Default "EQUITY".
        from_date : str
            Start date "YYYY-MM-DD".
        to_date : str
            End date "YYYY-MM-DD".

        Returns
        -------
        dict | None
            Dict with keys: open, high, low, close, volume, timestamp
            (each is a list). Returns None on failure.
        """
        url = f"{BASE_URL}/charts/historical"
        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "expiryCode": 0,
            "fromDate": from_date,
            "toDate": to_date,
        }
        try:
            resp = self._session.post(
                url, headers=self._headers(), json=payload, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "open" in data:
                    return data
                logger.warning("Dhan daily OHLC: unexpected response structure")
                return None
            else:
                logger.warning("Dhan daily OHLC HTTP %s for %s", resp.status_code, security_id)
                return None
        except Exception as e:
            logger.error("Dhan daily OHLC error for %s: %s", security_id, e)
            return None

