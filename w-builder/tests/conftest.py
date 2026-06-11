"""Shared pytest fixtures and Hypothesis strategies for Wealth Builder Pro tests.

Provides custom strategies for generating valid dataclass instances,
ISIN strings, and shared fixtures for mocked AWS clients, temp files,
and in-memory SQLite databases.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import strategies as st

from parsers.models import StockHolding, MFHolding, TradeRecord, ScripSummary
from llm.models import StockVerdict, MFRecommendation, MarketOpportunity, IntradaySetup
from fetchers.models import (
    BhavcopyRecord, FIIDIIFlow, DealRecord, StockFundamentals,
    NAVRecord, IPORecord, NewsItem, IndexData,
)

IST = timezone(timedelta(hours=5, minutes=30))

# ── ISIN Strategies ──────────────────────────────────────────────────

_ISIN_SUFFIX = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=9, max_size=9,
)

ine_isin_strategy = st.builds(lambda s: "INE" + s, _ISIN_SUFFIX)
inf_isin_strategy = st.builds(lambda s: "INF" + s, _ISIN_SUFFIX)
isin_strategy = st.one_of(ine_isin_strategy, inf_isin_strategy)

# ── Positive float strategies ────────────────────────────────────────

positive_float = st.floats(min_value=0.01, max_value=1_000_000, allow_nan=False, allow_infinity=False)
any_float = st.floats(min_value=-1_000_000, max_value=1_000_000, allow_nan=False, allow_infinity=False)
positive_int = st.integers(min_value=1, max_value=1_000_000)

# ── Datetime strategy ────────────────────────────────────────────────

reasonable_datetime = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)

# ── StockHolding Strategy ────────────────────────────────────────────

stock_holding_strategy = st.builds(
    StockHolding,
    name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    isin=isin_strategy,
    quantity=positive_int,
    avg_buy_price=positive_float,
    buy_value=positive_float,
    groww_closing_price=positive_float,
    groww_closing_value=positive_float,
    unrealised_pnl=any_float,
    holding_type=st.sampled_from(["stock", "etf", "invit"]),
    pnl_percent=any_float,
    live_price=st.one_of(st.none(), positive_float),
    live_value=st.one_of(st.none(), positive_float),
    nse_symbol=st.one_of(st.none(), st.text(min_size=1, max_size=20).filter(lambda s: s.strip())),
)

# ── MFHolding Strategy ───────────────────────────────────────────────

mf_holding_strategy = st.builds(
    MFHolding,
    scheme_name=st.text(min_size=1, max_size=80).filter(lambda s: s.strip()),
    amc=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    category=st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
    sub_category=st.text(min_size=1, max_size=30).filter(lambda s: s.strip()),
    folio_no=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    source=st.sampled_from(["SIP", "Lumpsum", "STP"]),
    units=positive_float,
    invested_value=positive_float,
    current_value=positive_float,
    returns_absolute=any_float,
    xirr=any_float,
    returns_percent=any_float,
    current_nav=st.one_of(st.none(), positive_float),
    scheme_code=st.one_of(st.none(), st.text(min_size=1, max_size=10).filter(lambda s: s.strip())),
)

# ── TradeRecord Strategy ─────────────────────────────────────────────

trade_record_strategy = st.builds(
    TradeRecord,
    isin=isin_strategy,
    symbol=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    trade_type=st.sampled_from(["buy", "sell"]),
    trade_date=reasonable_datetime,
    quantity=positive_int,
    price=positive_float,
)

# ── ScripSummary Strategy ────────────────────────────────────────────

scrip_summary_strategy = st.builds(
    ScripSummary,
    isin=isin_strategy,
    symbol=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    buy_date=reasonable_datetime,
    buy_quantity=positive_int,
    buy_avg_price=positive_float,
    sell_quantity=positive_int,
    sell_avg_price=positive_float,
    realised_pnl=any_float,
    holding_period_days=st.integers(min_value=0, max_value=5000),
    tax_classification=st.sampled_from(["short_term", "long_term"]),
)

# ── Pytest Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def in_memory_db():
    """Provide an in-memory SQLite connection for testing."""
    from database.db_manager import DBManager
    db = DBManager(":memory:")
    yield db
    db.close()


@pytest.fixture
def mock_boto3_ses():
    """Provide a mocked boto3 SES client."""
    with patch("boto3.client") as mock_client:
        ses = MagicMock()
        mock_client.return_value = ses
        yield ses


@pytest.fixture
def mock_boto3_s3():
    """Provide a mocked boto3 S3 client."""
    with patch("boto3.client") as mock_client:
        s3 = MagicMock()
        mock_client.return_value = s3
        yield s3


@pytest.fixture
def mock_bedrock_client():
    """Provide a mocked BedrockClient."""
    client = MagicMock()
    client.invoke.return_value = {}
    return client


@pytest.fixture
def sample_stock_holdings():
    """Provide a list of sample StockHolding instances."""
    return [
        StockHolding(
            name="Reliance Industries", isin="INE002A01018", quantity=10,
            avg_buy_price=2400.0, buy_value=24000.0, groww_closing_price=2500.0,
            groww_closing_value=25000.0, unrealised_pnl=1000.0,
            holding_type="stock", pnl_percent=4.17,
        ),
        StockHolding(
            name="HDFC Bank", isin="INE040A01034", quantity=20,
            avg_buy_price=1600.0, buy_value=32000.0, groww_closing_price=1550.0,
            groww_closing_value=31000.0, unrealised_pnl=-1000.0,
            holding_type="stock", pnl_percent=-3.13,
        ),
    ]

@pytest.fixture
def sample_mf_holdings():
    """Provide a list of sample MFHolding instances."""
    return [
        MFHolding(
            scheme_name="Axis Bluechip Fund", amc="Axis", category="Equity",
            sub_category="Large Cap", folio_no="1234567890", source="SIP",
            units=100.5, invested_value=50000.0, current_value=55000.0,
            returns_absolute=5000.0, xirr=12.5, returns_percent=10.0,
        ),
    ]


@pytest.fixture
def sample_verdicts():
    """Provide a list of sample StockVerdict instances."""
    return [
        StockVerdict(
            name="Reliance Industries", isin="INE002A01018",
            verdict="buy", target_price=2800.0, stop_loss=2300.0,
            rationale="Strong fundamentals", tax_harvest_flag=False,
        ),
        StockVerdict(
            name="HDFC Bank", isin="INE040A01034",
            verdict="hold", target_price=1800.0, stop_loss=1450.0,
            rationale="Consolidation phase", tax_harvest_flag=True,
        ),
    ]


@pytest.fixture
def sample_mf_recommendations():
    """Provide a list of sample MFRecommendation instances."""
    return [
        MFRecommendation(
            scheme_name="Axis Bluechip Fund", recommendation="continue",
            alternative_scheme=None, rationale="Consistent performer",
        ),
    ]


@pytest.fixture
def tmp_xlsx(tmp_path):
    """Provide a temporary directory for XLSX test files."""
    return tmp_path
