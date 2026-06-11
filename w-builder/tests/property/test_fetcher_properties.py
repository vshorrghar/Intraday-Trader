"""Property-based tests for market data fetcher parsing logic.

Tests Property 10 (Bhavcopy CSV parsing), Property 11 (FII/DII response parsing),
and Property 12 (Deal record parsing) from the design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from fetchers.models import BhavcopyRecord, FIIDIIFlow, DealRecord
from fetchers.nse_bhavcopy import _parse_bhavcopy_csv
from fetchers.nse_fii_dii import _parse_fii_dii_response
from fetchers.nse_bulk_deals import _parse_deals
from tests.conftest import isin_strategy, positive_float, positive_int


# ── Strategies ───────────────────────────────────────────────────────

_symbol = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    min_size=2,
    max_size=10,
)

_non_empty_text = st.text(min_size=1, max_size=40).filter(lambda s: s.strip())


# ── Property 10: Bhavcopy CSV parsing ────────────────────────────────


def _build_bhavcopy_csv(rows: list[tuple[str, str, float]]) -> str:
    """Build a valid Bhavcopy CSV string from (ISIN, SYMBOL, CLOSE_PRICE) rows."""
    lines = ["ISIN_CODE, SYMBOL, CLOSE_PRICE"]
    for isin, symbol, price in rows:
        lines.append(f"{isin}, {symbol}, {price:.2f}")
    return "\n".join(lines)


_bhavcopy_row = st.tuples(isin_strategy, _symbol, positive_float)


@given(rows=st.lists(_bhavcopy_row, min_size=1, max_size=20))
@settings(max_examples=100, deadline=None)
def test_property_10_bhavcopy_csv_parsing(rows):
    """For any valid CSV with ISIN and closing price columns, parsing
    produces a dict keyed by ISIN with positive float closing prices.
    """
    csv_text = _build_bhavcopy_csv(rows)
    result = _parse_bhavcopy_csv(csv_text, "2025-01-01")

    # Result is a dict keyed by ISIN
    assert isinstance(result, dict)

    # Every key is a valid ISIN string from our input
    input_isins = {isin for isin, _, _ in rows}
    assert set(result.keys()).issubset(input_isins)

    # Every value is a BhavcopyRecord with a positive close_price
    for isin, record in result.items():
        assert isinstance(record, BhavcopyRecord)
        assert record.isin == isin
        assert isinstance(record.close_price, float)
        assert record.close_price > 0


# ── Property 11: FII/DII response parsing ───────────────────────────

_fii_dii_entry = st.fixed_dictionaries(
    {
        "category": st.sampled_from(["FII/FPI *", "DII *"]),
        "buyValue": positive_float.map(lambda v: f"{v:.2f}"),
        "sellValue": positive_float.map(lambda v: f"{v:.2f}"),
    }
)


def _build_fii_dii_data(
    fii_buy: float, fii_sell: float, dii_buy: float, dii_sell: float
) -> list[dict]:
    """Build a valid FII/DII API response list."""
    return [
        {
            "category": "FII/FPI *",
            "buyValue": f"{fii_buy:.2f}",
            "sellValue": f"{fii_sell:.2f}",
        },
        {
            "category": "DII *",
            "buyValue": f"{dii_buy:.2f}",
            "sellValue": f"{dii_sell:.2f}",
        },
    ]


@given(
    fii_buy=positive_float,
    fii_sell=positive_float,
    dii_buy=positive_float,
    dii_sell=positive_float,
)
@settings(max_examples=100, deadline=None)
def test_property_11_fii_dii_response_parsing(fii_buy, fii_sell, dii_buy, dii_sell):
    """For any valid FII/DII data with buy/sell values,
    fii_net == fii_buy - fii_sell and dii_net == dii_buy - dii_sell.
    """
    data = _build_fii_dii_data(fii_buy, fii_sell, dii_buy, dii_sell)
    flow = _parse_fii_dii_response(data)

    assert isinstance(flow, FIIDIIFlow)

    # Net values must equal buy minus sell (within float tolerance)
    assert abs(flow.fii_net - (flow.fii_buy - flow.fii_sell)) < 1e-6
    assert abs(flow.dii_net - (flow.dii_buy - flow.dii_sell)) < 1e-6

    # Buy/sell values must be positive
    assert flow.fii_buy > 0
    assert flow.fii_sell > 0
    assert flow.dii_buy > 0
    assert flow.dii_sell > 0


# ── Property 12: Deal record parsing ────────────────────────────────

_deal_entry = st.fixed_dictionaries(
    {
        "securityName": _non_empty_text,
        "isin": isin_strategy,
        "clientName": _non_empty_text,
        "quantity": positive_int,
        "price": positive_float,
    }
)


@given(
    entries=st.lists(_deal_entry, min_size=1, max_size=20),
    deal_type=st.sampled_from(["bulk", "block"]),
)
@settings(max_examples=100, deadline=None)
def test_property_12_deal_record_parsing(entries, deal_type):
    """For any valid deal data, DealRecord has deal_type in {"bulk","block"},
    non-empty security_name/isin/client_name, positive quantity and price.
    """
    records = _parse_deals(entries, deal_type)

    assert isinstance(records, list)
    assert len(records) == len(entries)

    for record in records:
        assert isinstance(record, DealRecord)
        assert record.deal_type in {"bulk", "block"}
        assert len(record.security_name) > 0
        assert len(record.isin) > 0
        assert len(record.client_name) > 0
        assert record.quantity > 0
        assert record.price > 0
