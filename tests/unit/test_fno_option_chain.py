"""Unit tests for fno/option_chain.py — Option Chain Fetcher.

Tests ATM strike identification, PCR computation, Max Pain computation,
snapshot buffer management, bid-ask spread, highest OI strikes, demo
chain generation, and retry logic.
"""

from __future__ import annotations

import pytest

from fno.models import OptionChainSnapshot, OptionStrike
from fno.option_chain import (
    OptionChainFetcher,
    compute_bid_ask_spread,
    compute_max_pain,
    compute_pcr,
    generate_demo_chain,
    highest_oi_strike,
    identify_atm_strike,
)


# ── ATM Strike Identification ────────────────────────────────────────


class TestIdentifyATMStrike:
    def test_exact_match(self):
        assert identify_atm_strike(24500.0, [24400, 24450, 24500, 24550, 24600]) == 24500

    def test_closest_above(self):
        assert identify_atm_strike(24520.0, [24400, 24500, 24600]) == 24500

    def test_closest_below(self):
        assert identify_atm_strike(24580.0, [24400, 24500, 24600]) == 24600

    def test_tie_picks_lower(self):
        # 24525 is equidistant from 24500 and 24550 → pick 24500
        assert identify_atm_strike(24525.0, [24500, 24550]) == 24500

    def test_single_strike(self):
        assert identify_atm_strike(24500.0, [24600]) == 24600

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            identify_atm_strike(24500.0, [])


# ── PCR Computation ──────────────────────────────────────────────────


def _make_strike(strike: float, opt_type: str, oi: int) -> OptionStrike:
    return OptionStrike(
        strike_price=strike, expiry_date="2026-07-17", option_type=opt_type,
        ltp=100.0, bid_price=99.0, ask_price=101.0,
        open_interest=oi, oi_change=0, volume=1000, iv=15.0,
    )


class TestComputePCR:
    def test_balanced(self):
        strikes = [
            _make_strike(24500, "CE", 1_000_000),
            _make_strike(24500, "PE", 1_000_000),
        ]
        assert compute_pcr(strikes) == pytest.approx(1.0)

    def test_bullish_pcr(self):
        strikes = [
            _make_strike(24500, "CE", 500_000),
            _make_strike(24500, "PE", 1_000_000),
        ]
        assert compute_pcr(strikes) == pytest.approx(2.0)

    def test_zero_call_oi(self):
        strikes = [
            _make_strike(24500, "CE", 0),
            _make_strike(24500, "PE", 1_000_000),
        ]
        assert compute_pcr(strikes) == float("inf")

    def test_multiple_strikes(self):
        strikes = [
            _make_strike(24400, "CE", 200_000),
            _make_strike(24500, "CE", 300_000),
            _make_strike(24400, "PE", 400_000),
            _make_strike(24500, "PE", 600_000),
        ]
        # Total CE OI = 500K, Total PE OI = 1M → PCR = 2.0
        assert compute_pcr(strikes) == pytest.approx(2.0)


# ── Max Pain Computation ─────────────────────────────────────────────


class TestComputeMaxPain:
    def test_simple_case(self):
        """Max pain should be the strike minimizing total pain."""
        strikes = [
            _make_strike(24400, "CE", 100_000),
            _make_strike(24400, "PE", 500_000),
            _make_strike(24500, "CE", 300_000),
            _make_strike(24500, "PE", 300_000),
            _make_strike(24600, "CE", 500_000),
            _make_strike(24600, "PE", 100_000),
        ]
        mp = compute_max_pain(strikes)
        assert mp in (24400, 24500, 24600)

    def test_single_strike(self):
        strikes = [
            _make_strike(24500, "CE", 100_000),
            _make_strike(24500, "PE", 100_000),
        ]
        assert compute_max_pain(strikes) == 24500

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No strikes"):
            compute_max_pain([])

    def test_max_pain_is_in_chain(self):
        """Max pain must be one of the strikes in the chain."""
        strikes = [
            _make_strike(s, t, oi)
            for s in [24300, 24400, 24500, 24600, 24700]
            for t, oi in [("CE", 200_000), ("PE", 200_000)]
        ]
        mp = compute_max_pain(strikes)
        assert mp in [24300, 24400, 24500, 24600, 24700]


# ── Bid-Ask Spread ───────────────────────────────────────────────────


class TestBidAskSpread:
    def test_positive_spread(self):
        s = _make_strike(24500, "CE", 100_000)
        s.bid_price = 99.0
        s.ask_price = 101.0
        assert compute_bid_ask_spread(s) == pytest.approx(2.0)

    def test_zero_spread(self):
        s = _make_strike(24500, "CE", 100_000)
        s.bid_price = 100.0
        s.ask_price = 100.0
        assert compute_bid_ask_spread(s) == pytest.approx(0.0)


# ── Highest OI Strike ────────────────────────────────────────────────


class TestHighestOIStrike:
    def test_call_highest(self):
        strikes = [
            _make_strike(24400, "CE", 100_000),
            _make_strike(24500, "CE", 500_000),
            _make_strike(24600, "CE", 200_000),
        ]
        assert highest_oi_strike(strikes, "CE") == 24500

    def test_put_highest(self):
        strikes = [
            _make_strike(24400, "PE", 300_000),
            _make_strike(24500, "PE", 100_000),
        ]
        assert highest_oi_strike(strikes, "PE") == 24400

    def test_no_matching_type(self):
        strikes = [_make_strike(24500, "CE", 100_000)]
        assert highest_oi_strike(strikes, "PE") == 0.0


# ── Snapshot Buffer ──────────────────────────────────────────────────


class TestSnapshotBuffer:
    def test_buffer_max_6(self):
        fetcher = OptionChainFetcher()
        for i in range(10):
            fetcher._add_to_buffer("NIFTY", _dummy_snapshot(f"snap_{i}"))
        buf = fetcher.get_snapshot_buffer("NIFTY")
        assert len(buf) == 6

    def test_buffer_order(self):
        fetcher = OptionChainFetcher()
        for i in range(8):
            fetcher._add_to_buffer("NIFTY", _dummy_snapshot(f"snap_{i}"))
        buf = fetcher.get_snapshot_buffer("NIFTY")
        # Should have snapshots 2-7 (oldest first)
        assert buf[0].timestamp == "snap_2"
        assert buf[-1].timestamp == "snap_7"

    def test_buffer_per_index(self):
        fetcher = OptionChainFetcher()
        fetcher._add_to_buffer("NIFTY", _dummy_snapshot("n1"))
        fetcher._add_to_buffer("BANKNIFTY", _dummy_snapshot("b1"))
        assert len(fetcher.get_snapshot_buffer("NIFTY")) == 1
        assert len(fetcher.get_snapshot_buffer("BANKNIFTY")) == 1

    def test_empty_buffer(self):
        fetcher = OptionChainFetcher()
        assert fetcher.get_snapshot_buffer("NIFTY") == []


# ── Demo Chain Generation ────────────────────────────────────────────


class TestGenerateDemoChain:
    def test_returns_valid_snapshot(self):
        chain = generate_demo_chain("NIFTY", 24500.0)
        assert chain.index == "NIFTY"
        assert chain.spot_price == 24500.0
        assert chain.lot_size == 25
        assert len(chain.strikes) > 0
        assert chain.atm_strike > 0
        assert chain.pcr > 0
        assert chain.max_pain > 0

    def test_strikes_have_both_types(self):
        chain = generate_demo_chain("BANKNIFTY", 52000.0)
        ce_strikes = [s for s in chain.strikes if s.option_type == "CE"]
        pe_strikes = [s for s in chain.strikes if s.option_type == "PE"]
        assert len(ce_strikes) > 0
        assert len(pe_strikes) > 0

    def test_bid_ask_spread_populated(self):
        chain = generate_demo_chain("NIFTY", 24500.0)
        for s in chain.strikes:
            assert s.bid_ask_spread >= 0

    def test_fetcher_demo_mode(self):
        fetcher = OptionChainFetcher()
        chains = fetcher.fetch_option_chain("NIFTY", demo=True, spot_price=24500.0)
        assert len(chains) == 2  # Current + next expiry
        assert chains[0].index == "NIFTY"
        assert chains[1].index == "NIFTY"

    def test_invalid_index_raises(self):
        fetcher = OptionChainFetcher()
        with pytest.raises(ValueError, match="Invalid index"):
            fetcher.fetch_option_chain("INVALID")


# ── Retry Logic ──────────────────────────────────────────────────────


class TestRetryLogic:
    def test_retry_on_failure_raises_after_two_attempts(self):
        """Live fetch should raise RuntimeError after 2 failures."""

        class FailingBroker:
            def get_option_chain(self, index):
                raise ConnectionError("API down")

        fetcher = OptionChainFetcher()
        # Monkey-patch sleep to avoid 30s wait in tests
        import fno.option_chain as oc_mod
        original_sleep = oc_mod.time.sleep
        oc_mod.time.sleep = lambda _: None
        try:
            with pytest.raises(RuntimeError, match="after retry"):
                fetcher.fetch_option_chain("NIFTY", broker_client=FailingBroker(), demo=False)
        finally:
            oc_mod.time.sleep = original_sleep


# ── Helpers ──────────────────────────────────────────────────────────


def _dummy_snapshot(ts: str = "2026-07-15T10:00:00+05:30") -> OptionChainSnapshot:
    return OptionChainSnapshot(
        index="NIFTY", spot_price=24500.0, timestamp=ts,
        expiry_date="2026-07-17", lot_size=25, strikes=[],
        atm_strike=24500.0, pcr=1.0, max_pain=24500.0,
        highest_call_oi_strike=24600.0, highest_put_oi_strike=24400.0,
    )
