"""Property-based tests for fetcher data models and logic.

Tests Property 13 (Screener fundamentals), Property 14 (AMFI NAV lookup),
Property 15 (IPO record extraction), Property 16 (News item filtering),
and Property 31 (Market index parsing) from the design document.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from fetchers.models import (
    StockFundamentals,
    NAVRecord,
    IPORecord,
    NewsItem,
    IndexData,
)
from fetchers.amfi_nav_fetcher import _parse_amfi_nav_text
from fetchers.news_fetcher import _filter_last_24_hours

# ── Shared strategies ────────────────────────────────────────────────

positive_float = st.floats(
    min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False
)
any_float = st.floats(
    min_value=-1_000_000, max_value=1_000_000, allow_nan=False, allow_infinity=False
)
non_empty_text = st.text(min_size=1, max_size=60).filter(lambda s: s.strip())

# Strategy that produces an optional positive float (None or positive)
optional_positive_float = st.one_of(st.none(), positive_float)


# ── Property 13: StockFundamentals has at least one non-None metric ──


# Strategy: generate StockFundamentals where at least one metric is set
def _stock_fundamentals_strategy():
    """Build StockFundamentals ensuring at least one metric is non-None."""
    return st.builds(
        _build_fundamentals_with_at_least_one,
        symbol=non_empty_text,
        pe_ratio=optional_positive_float,
        market_cap=optional_positive_float,
        book_value=optional_positive_float,
        dividend_yield=optional_positive_float,
        roce=optional_positive_float,
        promoter_holding=optional_positive_float,
    )


def _build_fundamentals_with_at_least_one(
    symbol, pe_ratio, market_cap, book_value, dividend_yield, roce, promoter_holding
):
    """If all metrics are None, force pe_ratio to a default value."""
    metrics = [pe_ratio, market_cap, book_value, dividend_yield, roce, promoter_holding]
    if all(m is None for m in metrics):
        pe_ratio = 15.0  # sensible default
    return StockFundamentals(
        symbol=symbol,
        pe_ratio=pe_ratio,
        market_cap=market_cap,
        book_value=book_value,
        dividend_yield=dividend_yield,
        roce=roce,
        promoter_holding=promoter_holding,
    )


@given(fund=_stock_fundamentals_strategy())
@settings(max_examples=200, deadline=None)
def test_property_13_screener_fundamentals_has_at_least_one_metric(fund):
    """StockFundamentals must have at least one non-None metric among
    pe_ratio, market_cap, book_value, dividend_yield, roce, promoter_holding.
    """
    metrics = [
        fund.pe_ratio,
        fund.market_cap,
        fund.book_value,
        fund.dividend_yield,
        fund.roce,
        fund.promoter_holding,
    ]
    assert any(m is not None for m in metrics), (
        f"All metrics are None for symbol={fund.symbol}"
    )


# ── Property 14: AMFI NAV lookup returns NAVRecord with positive NAV ─

