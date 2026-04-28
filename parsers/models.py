"""Data models for Groww broker XLSX parsers.

Defines dataclasses for stock holdings, mutual fund holdings, trade records,
and scrip summaries. All models include to_dict/from_dict methods for JSON
serialization with ISO 8601 datetime handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class StockHolding:
    """A single stock/ETF/InvIT holding from Groww Stocks Holdings XLSX."""

    name: str
    isin: str
    quantity: int
    avg_buy_price: float
    buy_value: float
    groww_closing_price: float
    groww_closing_value: float
    unrealised_pnl: float
    holding_type: str  # "stock", "etf", "invit"
    pnl_percent: float
    live_price: float | None = None
    live_value: float | None = None
    nse_symbol: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "isin": self.isin,
            "quantity": self.quantity,
            "avg_buy_price": self.avg_buy_price,
            "buy_value": self.buy_value,
            "groww_closing_price": self.groww_closing_price,
            "groww_closing_value": self.groww_closing_value,
            "unrealised_pnl": self.unrealised_pnl,
            "holding_type": self.holding_type,
            "pnl_percent": self.pnl_percent,
            "live_price": self.live_price,
            "live_value": self.live_value,
            "nse_symbol": self.nse_symbol,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StockHolding:
        """Deserialize from a dictionary."""
        return cls(
            name=data["name"],
            isin=data["isin"],
            quantity=int(data["quantity"]),
            avg_buy_price=float(data["avg_buy_price"]),
            buy_value=float(data["buy_value"]),
            groww_closing_price=float(data["groww_closing_price"]),
            groww_closing_value=float(data["groww_closing_value"]),
            unrealised_pnl=float(data["unrealised_pnl"]),
            holding_type=data["holding_type"],
            pnl_percent=float(data["pnl_percent"]),
            live_price=float(data["live_price"]) if data.get("live_price") is not None else None,
            live_value=float(data["live_value"]) if data.get("live_value") is not None else None,
            nse_symbol=data.get("nse_symbol"),
        )


@dataclass
class MFHolding:
    """A single mutual fund scheme holding from Groww Mutual Funds XLSX."""

    scheme_name: str
    amc: str
    category: str
    sub_category: str
    folio_no: str
    source: str
    units: float
    invested_value: float
    current_value: float
    returns_absolute: float
    xirr: float
    returns_percent: float
    current_nav: float | None = None
    scheme_code: str | None = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "scheme_name": self.scheme_name,
            "amc": self.amc,
            "category": self.category,
            "sub_category": self.sub_category,
            "folio_no": self.folio_no,
            "source": self.source,
            "units": self.units,
            "invested_value": self.invested_value,
            "current_value": self.current_value,
            "returns_absolute": self.returns_absolute,
            "xirr": self.xirr,
            "returns_percent": self.returns_percent,
            "current_nav": self.current_nav,
            "scheme_code": self.scheme_code,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MFHolding:
        """Deserialize from a dictionary."""
        return cls(
            scheme_name=data["scheme_name"],
            amc=data["amc"],
            category=data["category"],
            sub_category=data["sub_category"],
            folio_no=data["folio_no"],
            source=data["source"],
            units=float(data["units"]),
            invested_value=float(data["invested_value"]),
            current_value=float(data["current_value"]),
            returns_absolute=float(data["returns_absolute"]),
            xirr=float(data["xirr"]),
            returns_percent=float(data["returns_percent"]),
            current_nav=float(data["current_nav"]) if data.get("current_nav") is not None else None,
            scheme_code=data.get("scheme_code"),
        )


@dataclass
class TradeRecord:
    """A single trade from Groww P&L Report trade-level sheet."""

    isin: str
    symbol: str
    trade_type: str  # "buy" or "sell"
    trade_date: datetime
    quantity: int
    price: float

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary. Datetime as ISO 8601."""
        return {
            "isin": self.isin,
            "symbol": self.symbol,
            "trade_type": self.trade_type,
            "trade_date": self.trade_date.isoformat(),
            "quantity": self.quantity,
            "price": self.price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TradeRecord:
        """Deserialize from a dictionary. Parses ISO 8601 datetime strings."""
        return cls(
            isin=data["isin"],
            symbol=data["symbol"],
            trade_type=data["trade_type"],
            trade_date=datetime.fromisoformat(data["trade_date"]),
            quantity=int(data["quantity"]),
            price=float(data["price"]),
        )


@dataclass
class ScripSummary:
    """Aggregated scrip-level summary from Groww P&L Report."""

    isin: str
    symbol: str
    buy_date: datetime
    buy_quantity: int
    buy_avg_price: float
    sell_quantity: int
    sell_avg_price: float
    realised_pnl: float
    holding_period_days: int
    tax_classification: str  # "short_term" or "long_term"

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary. Datetime as ISO 8601."""
        return {
            "isin": self.isin,
            "symbol": self.symbol,
            "buy_date": self.buy_date.isoformat(),
            "buy_quantity": self.buy_quantity,
            "buy_avg_price": self.buy_avg_price,
            "sell_quantity": self.sell_quantity,
            "sell_avg_price": self.sell_avg_price,
            "realised_pnl": self.realised_pnl,
            "holding_period_days": self.holding_period_days,
            "tax_classification": self.tax_classification,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScripSummary:
        """Deserialize from a dictionary. Parses ISO 8601 datetime strings."""
        return cls(
            isin=data["isin"],
            symbol=data["symbol"],
            buy_date=datetime.fromisoformat(data["buy_date"]),
            buy_quantity=int(data["buy_quantity"]),
            buy_avg_price=float(data["buy_avg_price"]),
            sell_quantity=int(data["sell_quantity"]),
            sell_avg_price=float(data["sell_avg_price"]),
            realised_pnl=float(data["realised_pnl"]),
            holding_period_days=int(data["holding_period_days"]),
            tax_classification=data["tax_classification"],
        )
