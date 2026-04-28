"""Dhan broker API fetcher.

Fetches live holdings, positions, and market quotes from Dhan's REST API.
Replaces the need for manual XLSX downloads from Groww.

API docs: https://dhanhq.co/docs/v2/
Base URL: https://api.dhan.co/v2
Auth: access-token header (JWT)
"""
from __future__ import annotations
import logging
import yaml
import requests
from dataclasses import dataclass

logger = logging.getLogger(__name__)
BASE_URL = "https://api.dhan.co/v2"


@dataclass
class DhanHolding:
    trading_symbol: str
    security_id: str
    isin: str
    exchange: str
    total_qty: int
    dp_qty: int
    t1_qty: int
    available_qty: int
    avg_cost_price: float


@dataclass
class DhanPosition:
    trading_symbol: str
    security_id: str
    exchange_segment: str
    position_type: str
    product_type: str
    buy_avg: float
    buy_qty: int
    sell_avg: float
    sell_qty: int
    net_qty: int
    realized_profit: float
    unrealized_profit: float


class DhanClient:
    """Client for Dhan REST API v2."""

    def __init__(self, access_token: str, client_id: str):
        self.access_token = access_token
        self.client_id = client_id
        self.headers = {
            "Content-Type": "application/json",
            "access-token": access_token,
        }

    def get_holdings(self) -> list[DhanHolding]:
        """Fetch all holdings from demat account."""
        try:
            resp = requests.get(f"{BASE_URL}/holdings", headers=self.headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            holdings = []
            for h in data:
                holdings.append(DhanHolding(
                    trading_symbol=h.get("tradingSymbol", ""),
                    security_id=str(h.get("securityId", "")),
                    isin=h.get("isin", ""),
                    exchange=h.get("exchange", ""),
                    total_qty=h.get("totalQty", 0),
                    dp_qty=h.get("dpQty", 0),
                    t1_qty=h.get("t1Qty", 0),
                    available_qty=h.get("availableQty", 0),
                    avg_cost_price=h.get("avgCostPrice", 0.0),
                ))
            logger.info("Dhan: fetched %d holdings", len(holdings))
            return holdings
        except Exception as e:
            logger.error("Dhan holdings fetch failed: %s", e)
            return []

    def get_positions(self) -> list[DhanPosition]:
        """Fetch all open positions."""
        try:
            resp = requests.get(f"{BASE_URL}/positions", headers=self.headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            positions = []
            for p in data:
                positions.append(DhanPosition(
                    trading_symbol=p.get("tradingSymbol", ""),
                    security_id=str(p.get("securityId", "")),
                    exchange_segment=p.get("exchangeSegment", ""),
                    position_type=p.get("positionType", ""),
                    product_type=p.get("productType", ""),
                    buy_avg=p.get("buyAvg", 0.0),
                    buy_qty=p.get("buyQty", 0),
                    sell_avg=p.get("sellAvg", 0.0),
                    sell_qty=p.get("sellQty", 0),
                    net_qty=p.get("netQty", 0),
                    realized_profit=p.get("realizedProfit", 0.0),
                    unrealized_profit=p.get("unrealizedProfit", 0.0),
                ))
            logger.info("Dhan: fetched %d positions", len(positions))
            return positions
        except Exception as e:
            logger.error("Dhan positions fetch failed: %s", e)
            return []

    def get_fund_limits(self) -> dict:
        """Fetch available funds/margins."""
        try:
            resp = requests.get(f"{BASE_URL}/fundlimit", headers=self.headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Dhan fund limits fetch failed: %s", e)
            return {}


def load_dhan_client(config_path: str = "config/config.yaml") -> DhanClient | None:
    """Load Dhan client from config file."""
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        dhan_cfg = cfg.get("dhan", {})
        token = dhan_cfg.get("access_token", "")
        client_id = dhan_cfg.get("client_id", "")
        if not token or token == "YOUR_DHAN_TOKEN_HERE":
            logger.warning("Dhan token not configured in %s", config_path)
            return None
        return DhanClient(token, client_id)
    except Exception as e:
        logger.error("Failed to load Dhan config: %s", e)
        return None
