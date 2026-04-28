"""Property-based tests for data model JSON round-trips.

**Validates: Requirements 1.8, 2.6, 3.6**

Tests Property 1 (StockHolding JSON round-trip), Property 2 (MFHolding JSON round-trip),
and Property 3 (P&L data JSON round-trip) from the design document.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from parsers.models import StockHolding, MFHolding, TradeRecord, ScripSummary
from tests.conftest import (
    stock_holding_strategy,
    mf_holding_strategy,
    trade_record_strategy,
    scrip_summary_strategy,
)


# ── Property 1: StockHolding JSON round-trip ─────────────────────────
# **Validates: Requirements 1.8**


@given(holdings=st.lists(stock_holding_strategy, min_size=0, max_size=10))
@settings(max_examples=100, deadline=None)
def test_property_1_stock_holding_json_round_trip(holdings):
    """For any valid list of StockHolding objects, serializing to JSON
    and then deserializing back should produce an equivalent list with
    all fields preserved.

    **Validates: Requirements 1.8**
    """
    serialized = [h.to_dict() for h in holdings]
    deserialized = [StockHolding.from_dict(d) for d in serialized]

    assert len(deserialized) == len(holdings)
    for original, restored in zip(holdings, deserialized):
        assert restored.name == original.name
        assert restored.isin == original.isin
        assert restored.quantity == original.quantity
        assert restored.avg_buy_price == original.avg_buy_price
        assert restored.buy_value == original.buy_value
        assert restored.groww_closing_price == original.groww_closing_price
        assert restored.groww_closing_value == original.groww_closing_value
        assert restored.unrealised_pnl == original.unrealised_pnl
        assert restored.holding_type == original.holding_type
        assert restored.pnl_percent == original.pnl_percent
        assert restored.live_price == original.live_price
        assert restored.live_value == original.live_value
        assert restored.nse_symbol == original.nse_symbol


# ── Property 2: MFHolding JSON round-trip ────────────────────────────
# **Validates: Requirements 2.6**


@given(holdings=st.lists(mf_holding_strategy, min_size=0, max_size=10))
@settings(max_examples=100, deadline=None)
def test_property_2_mf_holding_json_round_trip(holdings):
    """For any valid list of MFHolding objects, serializing to JSON
    and then deserializing back should produce an equivalent list with
    all fields preserved.

    **Validates: Requirements 2.6**
    """
    serialized = [h.to_dict() for h in holdings]
    deserialized = [MFHolding.from_dict(d) for d in serialized]

    assert len(deserialized) == len(holdings)
    for original, restored in zip(holdings, deserialized):
        assert restored.scheme_name == original.scheme_name
        assert restored.amc == original.amc
        assert restored.category == original.category
        assert restored.sub_category == original.sub_category
        assert restored.folio_no == original.folio_no
        assert restored.source == original.source
        assert restored.units == original.units
        assert restored.invested_value == original.invested_value
        assert restored.current_value == original.current_value
        assert restored.returns_absolute == original.returns_absolute
        assert restored.xirr == original.xirr
        assert restored.returns_percent == original.returns_percent
        assert restored.current_nav == original.current_nav
        assert restored.scheme_code == original.scheme_code


# ── Property 3: P&L data JSON round-trip ─────────────────────────────
# **Validates: Requirements 3.6**


@given(trades=st.lists(trade_record_strategy, min_size=0, max_size=10))
@settings(max_examples=100, deadline=None)
def test_property_3a_trade_record_json_round_trip(trades):
    """For any valid list of TradeRecord objects, serializing to JSON
    and then deserializing back should produce equivalent objects with
    all fields preserved.

    **Validates: Requirements 3.6**
    """
    serialized = [t.to_dict() for t in trades]
    deserialized = [TradeRecord.from_dict(d) for d in serialized]

    assert len(deserialized) == len(trades)
    for original, restored in zip(trades, deserialized):
        assert restored.isin == original.isin
        assert restored.symbol == original.symbol
        assert restored.trade_type == original.trade_type
        assert restored.trade_date == original.trade_date
        assert restored.quantity == original.quantity
        assert restored.price == original.price


@given(summaries=st.lists(scrip_summary_strategy, min_size=0, max_size=10))
@settings(max_examples=100, deadline=None)
def test_property_3b_scrip_summary_json_round_trip(summaries):
    """For any valid list of ScripSummary objects, serializing to JSON
    and then deserializing back should produce equivalent objects with
    all fields preserved.

    **Validates: Requirements 3.6**
    """
    serialized = [s.to_dict() for s in summaries]
    deserialized = [ScripSummary.from_dict(d) for d in serialized]

    assert len(deserialized) == len(summaries)
    for original, restored in zip(summaries, deserialized):
        assert restored.isin == original.isin
        assert restored.symbol == original.symbol
        assert restored.buy_date == original.buy_date
        assert restored.buy_quantity == original.buy_quantity
        assert restored.buy_avg_price == original.buy_avg_price
        assert restored.sell_quantity == original.sell_quantity
        assert restored.sell_avg_price == original.sell_avg_price
        assert restored.realised_pnl == original.realised_pnl
        assert restored.holding_period_days == original.holding_period_days
        assert restored.tax_classification == original.tax_classification
