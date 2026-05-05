"""Groww Trading API client.

Fetches live holdings, positions, LTP, and OHLC data from Groww API.
Can also place/cancel orders (used by auto-trader in dry-run or live mode).

Reads credentials from config/groww_api.yaml.
API docs: https://groww.in/trade-api/docs/curl
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

BASE_URL = "https://api.groww.in/v1"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "groww_api.yaml")


@dataclass
class GrowwHolding:
    isin: str
    trading_symbol: str
    quantity: int
    average_price: float
    pledge_quantity: float = 0
    t1_quantity: float = 0
    demat_free_quantity: float = 0


@dataclass
class GrowwPosition:
    trading_symbol: str
    segment: str
    exchange: str
    isin: str
    quantity: int
    net_price: float
    realised_pnl: float = 0
    product: str = ""


@dataclass
class GrowwQuote:
    trading_symbol: str
    ltp: float
    open: float = 0
    high: float = 0
    low: float = 0
    close: float = 0
    volume: int = 0


class GrowwClient:
    """Client for Groww Trading API."""

    def __init__(self, config_path: str = CONFIG_PATH):
        self._config = self._load_config(config_path)
        self._api_key = self._config["groww"]["api_key"]
        self._api_secret = self._config["groww"]["api_secret"]
        self._access_token = None

    @staticmethod
    def _load_config(path: str) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Groww config not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    def _generate_checksum(self, timestamp: str) -> str:
        """Generate SHA256 checksum from secret + timestamp."""
        raw = self._api_secret + timestamp
        return hashlib.sha256(raw.encode()).hexdigest()

    def authenticate(self) -> str:
        """Get access token using API key + secret flow."""
        timestamp = str(int(time.time()))
        checksum = self._generate_checksum(timestamp)

        resp = requests.post(
            f"{BASE_URL}/token/api/access",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "key_type": "approval",
                "checksum": checksum,
                "timestamp": timestamp,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Groww may return token directly or wrapped in status/payload
        if isinstance(data, dict):
            if "token" in data:
                self._access_token = data["token"]
            elif data.get("status") == "SUCCESS":
                payload = data.get("payload", {})
                self._access_token = payload.get("token", "")
            else:
                raise RuntimeError(f"Groww auth failed: {data}")

        if not self._access_token:
            raise RuntimeError(f"Groww auth: no token in response")

        logger.info("Groww authenticated, expires: %s", data.get("expiry", "unknown"))
        return self._access_token

    def _headers(self) -> dict:
        if not self._access_token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-VERSION": "1.0",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        resp = requests.get(f"{BASE_URL}{path}", headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "FAILURE":
            raise RuntimeError(f"Groww API error: {data.get('error', data)}")
        return data

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(f"{BASE_URL}{path}", headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "FAILURE":
            raise RuntimeError(f"Groww API error: {data.get('error', data)}")
        return data

    # ── Portfolio ─────────────────────────────────────────────

    def get_holdings(self) -> list[GrowwHolding]:
        """Get all stock holdings from DEMAT account."""
        data = self._get("/holdings/user")
        holdings = []
        for h in data.get("payload", []):
            holdings.append(GrowwHolding(
                isin=h.get("isin", ""),
                trading_symbol=h.get("trading_symbol", ""),
                quantity=h.get("quantity", 0),
                average_price=h.get("average_price", 0),
                pledge_quantity=h.get("pledge_quantity", 0),
                t1_quantity=h.get("t1_quantity", 0),
                demat_free_quantity=h.get("demat_free_quantity", 0),
            ))
        return holdings

    def get_positions(self, segment: str = "CASH") -> list[GrowwPosition]:
        """Get current positions."""
        data = self._get("/positions/user", params={"segment": segment})
        positions = []
        for p in data.get("payload", []):
            positions.append(GrowwPosition(
                trading_symbol=p.get("trading_symbol", ""),
                segment=p.get("segment", ""),
                exchange=p.get("exchange", ""),
                isin=p.get("symbol_isin", ""),
                quantity=p.get("quantity", 0),
                net_price=p.get("net_price", 0),
                realised_pnl=p.get("realised_pnl", 0),
                product=p.get("product", ""),
            ))
        return positions

    # ── Live Data ─────────────────────────────────────────────

    def get_ltp(self, exchange: str, segment: str, trading_symbol: str) -> float:
        """Get last traded price for a symbol."""
        data = self._get("/live/ltp", params={
            "exchange": exchange,
            "segment": segment,
            "trading_symbol": trading_symbol,
        })
        return data.get("payload", {}).get("ltp", 0)

    def get_quote(self, exchange: str, segment: str, trading_symbol: str) -> GrowwQuote:
        """Get full quote with OHLC, volume, market depth."""
        data = self._get("/live/quote", params={
            "exchange": exchange,
            "segment": segment,
            "trading_symbol": trading_symbol,
        })
        p = data.get("payload", {})
        ohlc = p.get("ohlc", {})
        return GrowwQuote(
            trading_symbol=trading_symbol,
            ltp=p.get("ltp", 0),
            open=ohlc.get("open", 0),
            high=ohlc.get("high", 0),
            low=ohlc.get("low", 0),
            close=ohlc.get("close", 0),
            volume=p.get("volume", 0),
        )

    def get_ohlc(self, exchange: str, segment: str, trading_symbol: str) -> dict:
        """Get OHLC data for a symbol."""
        data = self._get("/live/ohlc", params={
            "exchange": exchange,
            "segment": segment,
            "trading_symbol": trading_symbol,
        })
        return data.get("payload", {}).get("ohlc", {})

    # ── Orders ────────────────────────────────────────────────

    def place_order(
        self,
        trading_symbol: str,
        exchange: str = "NSE",
        segment: str = "CASH",
        transaction_type: str = "BUY",
        order_type: str = "LIMIT",
        product: str = "INTRADAY",
        quantity: int = 1,
        price: float = 0,
        trigger_price: float = 0,
        validity: str = "DAY",
    ) -> dict:
        """Place an order. Returns order response with order_id."""
        body = {
            "trading_symbol": trading_symbol,
            "exchange": exchange,
            "segment": segment,
            "transaction_type": transaction_type,
            "order_type": order_type,
            "product": product,
            "quantity": quantity,
            "price": price,
            "trigger_price": trigger_price,
            "validity": validity,
        }
        data = self._post("/order/create", body)
        return data.get("payload", {})

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an open order."""
        data = self._post("/order/cancel", {"order_id": order_id})
        return data.get("payload", {})

    def get_orders(self) -> list[dict]:
        """Get all orders for today."""
        data = self._get("/order/list")
        return data.get("payload", [])
