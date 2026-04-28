"""Unit tests for fno/symbols.py — Symbol_Builder.

Tests symbol construction for Dhan and Zerodha, futures symbols,
round-trip parsing, and input validation.
"""

from datetime import date

import pytest

from fno.symbols import Symbol_Builder


@pytest.fixture
def sb():
    return Symbol_Builder()


# ── Dhan option symbols ──────────────────────────────────────────────────


class TestBuildDhan:
    """Tests for build_dhan."""

    def test_nifty_call(self):
        sym = Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), 24500, "CE")
        assert sym == "NIFTY25JUL24500CE"

    def test_nifty_put(self):
        sym = Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), 24500, "PE")
        assert sym == "NIFTY25JUL24500PE"

    def test_banknifty(self):
        sym = Symbol_Builder.build_dhan("BANKNIFTY", date(2025, 12, 18), 52000, "CE")
        assert sym == "BANKNIFTY25DEC52000CE"

    def test_finnifty(self):
        sym = Symbol_Builder.build_dhan("FINNIFTY", date(2026, 1, 15), 23000, "PE")
        assert sym == "FINNIFTY26JAN23000PE"

    def test_fractional_strike(self):
        sym = Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), 24550.5, "CE")
        assert sym == "NIFTY25JUL24550.5CE"

    def test_case_insensitive_index(self):
        sym = Symbol_Builder.build_dhan("nifty", date(2025, 7, 25), 24500, "CE")
        assert sym == "NIFTY25JUL24500CE"

    def test_case_insensitive_option_type(self):
        sym = Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), 24500, "ce")
        assert sym == "NIFTY25JUL24500CE"


# ── Zerodha option symbols ───────────────────────────────────────────────


class TestBuildZerodha:
    """Tests for build_zerodha."""

    def test_nifty_call_july(self):
        sym = Symbol_Builder.build_zerodha("NIFTY", date(2025, 7, 25), 24500, "CE")
        assert sym == "NIFTY2572524500CE"

    def test_nifty_put_july(self):
        sym = Symbol_Builder.build_zerodha("NIFTY", date(2025, 7, 25), 24500, "PE")
        assert sym == "NIFTY2572524500PE"

    def test_banknifty_october(self):
        """October uses 'O' month code."""
        sym = Symbol_Builder.build_zerodha("BANKNIFTY", date(2025, 10, 15), 52000, "CE")
        assert sym == "BANKNIFTY25O1552000CE"

    def test_november_code(self):
        """November uses 'N' month code."""
        sym = Symbol_Builder.build_zerodha("NIFTY", date(2025, 11, 20), 24500, "CE")
        assert sym == "NIFTY25N2024500CE"

    def test_december_code(self):
        """December uses 'D' month code."""
        sym = Symbol_Builder.build_zerodha("NIFTY", date(2025, 12, 25), 24500, "PE")
        assert sym == "NIFTY25D2524500PE"

    def test_single_digit_day_padded(self):
        """Day < 10 should be zero-padded."""
        sym = Symbol_Builder.build_zerodha("NIFTY", date(2025, 3, 5), 24500, "CE")
        assert sym == "NIFTY2530524500CE"


# ── Futures symbols ──────────────────────────────────────────────────────


class TestBuildFutures:
    """Tests for build_futures_dhan and build_futures_zerodha."""

    def test_dhan_futures(self):
        sym = Symbol_Builder.build_futures_dhan("NIFTY", date(2025, 7, 25))
        assert sym == "NIFTY25JULFUT"

    def test_zerodha_futures(self):
        sym = Symbol_Builder.build_futures_zerodha("NIFTY", date(2025, 7, 25))
        assert sym == "NIFTY25725FUT"

    def test_banknifty_dhan_futures(self):
        sym = Symbol_Builder.build_futures_dhan("BANKNIFTY", date(2025, 12, 18))
        assert sym == "BANKNIFTY25DECFUT"

    def test_banknifty_zerodha_futures(self):
        sym = Symbol_Builder.build_futures_zerodha("BANKNIFTY", date(2025, 12, 18))
        assert sym == "BANKNIFTY25D18FUT"


# ── Round-trip parsing ───────────────────────────────────────────────────


class TestParseSymbol:
    """Tests for parse_symbol round-trip."""

    def test_zerodha_option_round_trip(self):
        """Build → parse → verify for Zerodha option."""
        expiry = date(2025, 7, 25)
        sym = Symbol_Builder.build_zerodha("NIFTY", expiry, 24500, "CE")
        parsed = Symbol_Builder.parse_symbol(sym, "zerodha")
        assert parsed["index"] == "NIFTY"
        assert parsed["expiry"] == expiry
        assert parsed["strike"] == 24500.0
        assert parsed["option_type"] == "CE"

    def test_zerodha_put_round_trip(self):
        expiry = date(2025, 10, 15)
        sym = Symbol_Builder.build_zerodha("BANKNIFTY", expiry, 52000, "PE")
        parsed = Symbol_Builder.parse_symbol(sym, "zerodha")
        assert parsed["index"] == "BANKNIFTY"
        assert parsed["expiry"] == expiry
        assert parsed["strike"] == 52000.0
        assert parsed["option_type"] == "PE"

    def test_zerodha_futures_round_trip(self):
        expiry = date(2025, 7, 25)
        sym = Symbol_Builder.build_futures_zerodha("NIFTY", expiry)
        parsed = Symbol_Builder.parse_symbol(sym, "zerodha")
        assert parsed["index"] == "NIFTY"
        assert parsed["expiry"] == expiry
        assert parsed["strike"] == 0.0
        assert parsed["option_type"] == "FUT"

    def test_dhan_option_parse(self):
        """Dhan parse recovers index, month, strike, option_type.

        Note: Dhan format doesn't include the day, so expiry day
        defaults to last day of month.
        """
        sym = "NIFTY25JUL24500CE"
        parsed = Symbol_Builder.parse_symbol(sym, "dhan")
        assert parsed["index"] == "NIFTY"
        assert parsed["expiry"].year == 2025
        assert parsed["expiry"].month == 7
        assert parsed["strike"] == 24500.0
        assert parsed["option_type"] == "CE"

    def test_dhan_futures_parse(self):
        sym = "BANKNIFTY25DECFUT"
        parsed = Symbol_Builder.parse_symbol(sym, "dhan")
        assert parsed["index"] == "BANKNIFTY"
        assert parsed["expiry"].year == 2025
        assert parsed["expiry"].month == 12
        assert parsed["strike"] == 0.0
        assert parsed["option_type"] == "FUT"

    def test_finnifty_zerodha_round_trip(self):
        expiry = date(2026, 1, 8)
        sym = Symbol_Builder.build_zerodha("FINNIFTY", expiry, 23000, "PE")
        parsed = Symbol_Builder.parse_symbol(sym, "zerodha")
        assert parsed["index"] == "FINNIFTY"
        assert parsed["expiry"] == expiry
        assert parsed["strike"] == 23000.0
        assert parsed["option_type"] == "PE"


# ── Input validation ─────────────────────────────────────────────────────


class TestValidation:
    """Tests for input validation — ValueError on invalid inputs."""

    def test_invalid_index(self):
        with pytest.raises(ValueError, match="Invalid index"):
            Symbol_Builder.build_dhan("SENSEX", date(2025, 7, 25), 24500, "CE")

    def test_invalid_index_zerodha(self):
        with pytest.raises(ValueError, match="Invalid index"):
            Symbol_Builder.build_zerodha("MIDCAP", date(2025, 7, 25), 24500, "CE")

    def test_negative_strike(self):
        with pytest.raises(ValueError, match="Strike must be positive"):
            Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), -100, "CE")

    def test_zero_strike(self):
        with pytest.raises(ValueError, match="Strike must be positive"):
            Symbol_Builder.build_zerodha("NIFTY", date(2025, 7, 25), 0, "CE")

    def test_invalid_option_type(self):
        with pytest.raises(ValueError, match="Invalid option_type"):
            Symbol_Builder.build_dhan("NIFTY", date(2025, 7, 25), 24500, "XX")

    def test_invalid_option_type_zerodha(self):
        with pytest.raises(ValueError, match="Invalid option_type"):
            Symbol_Builder.build_zerodha("NIFTY", date(2025, 7, 25), 24500, "FUT")

    def test_invalid_broker_parse(self):
        with pytest.raises(ValueError, match="Unsupported broker"):
            Symbol_Builder.parse_symbol("NIFTY25JUL24500CE", "angel")

    def test_unparseable_dhan_symbol(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            Symbol_Builder.parse_symbol("GARBAGE123", "dhan")

    def test_unparseable_zerodha_symbol(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            Symbol_Builder.parse_symbol("GARBAGE123", "zerodha")

    def test_invalid_index_futures(self):
        with pytest.raises(ValueError, match="Invalid index"):
            Symbol_Builder.build_futures_dhan("SENSEX", date(2025, 7, 25))
