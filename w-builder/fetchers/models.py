"""Data models for market data fetchers.

Defines dataclasses for NSE Bhavcopy records, FII/DII flows, bulk/block deals,
stock fundamentals, AMFI NAV records, IPO records, news items, and market indices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BhavcopyRecord:
    """A single record from the NSE Bhavcopy CSV."""

    isin: str
    symbol: str
    close_price: float
    date: str


@dataclass
class FIIDIIFlow:
    """Daily FII and DII buy/sell activity from NSE."""

    date: str
    fii_buy: float
    fii_sell: float
    fii_net: float
    dii_buy: float
    dii_sell: float
    dii_net: float


@dataclass
class DealRecord:
    """A bulk or block deal record from NSE."""

    deal_type: str  # "bulk" or "block"
    security_name: str
    isin: str
    client_name: str
    quantity: int
    price: float


@dataclass
class StockFundamentals:
    """Comprehensive fundamental metrics for a stock from Screener.in."""

    symbol: str
    # Valuation
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None  # in Cr
    book_value: float | None = None
    dividend_yield: float | None = None
    ev_to_ebitda: float | None = None
    peg_ratio: float | None = None
    # Profitability
    roce: float | None = None
    roe: float | None = None
    operating_margin: float | None = None
    net_profit_margin: float | None = None
    # Growth
    sales_growth_3y: float | None = None
    sales_growth_5y: float | None = None
    profit_growth_3y: float | None = None
    profit_growth_5y: float | None = None
    eps: float | None = None
    # Financial Health
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    # Ownership
    promoter_holding: float | None = None
    promoter_pledge: float | None = None
    fii_holding: float | None = None
    dii_holding: float | None = None
    # Technical / Price
    high_52w: float | None = None
    low_52w: float | None = None
    high_all_time: float | None = None
    current_price: float | None = None
    industry_pe: float | None = None
    # Derived
    pct_from_52w_high: float | None = None
    pct_from_ath: float | None = None


@dataclass
class NAVRecord:
    """Net Asset Value record for a mutual fund scheme from AMFI."""

    scheme_code: str
    scheme_name: str
    nav: float
    date: str


@dataclass
class IPORecord:
    """IPO grey market premium data from Chittorgarh."""

    name: str
    price_band: str
    gmp: float
    estimated_listing_price: float
    subscription_status: str


@dataclass
class NewsItem:
    """A market news article from RSS feeds."""

    headline: str
    pub_date: datetime
    source: str
    summary: str


@dataclass
class IndexData:
    """Market index data point (e.g. Nifty 50, Sensex)."""

    name: str
    last_price: float
    change: float
    change_percent: float
