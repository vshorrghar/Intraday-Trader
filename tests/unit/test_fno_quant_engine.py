"""Unit tests for fno/quant_engine.py — Quant Edge Engine.

Tests all 6 quantitative signals: IV Percentile, OI Velocity, IV Skew,
GEX, VRP, and Confluence Score, plus adaptive weighting and the
compute_all_signals orchestrator.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from fno.config import FnO_Config
from fno.greeks import FnO_Greeks_Calculator
from fno.models import OptionChainSnapshot, OptionStrike, QuantSignals
from fno.quant_engine import (
    DEFAULT_WEIGHTS,
    OI_VELOCITY_THRESHOLD,
    Quant_Edge_Engine,
    _vrp_signal,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """In-memory DB mock with configurable return values."""
    from database.db_manager import DBManager
    db = DBManager(":memory:")
    return db


@pytest.fixture
def config():
    return FnO_Config()


@pytest.fixture
def greeks_calc():
    return FnO_Greeks_Calculator()


@pytest.fixture
def engine(mock_db, config):
    return Quant_Edge_Engine(mock_db, config)


def _make_strike(strike: float, opt_type: str, oi: int, iv: float = 15.0, ltp: float = 100.0) -> OptionStrike:
    return OptionStrike(
        strike_price=strike, expiry_date="2026-07-24", option_type=opt_type,
        ltp=ltp, bid_price=ltp * 0.99, ask_price=ltp * 1.01,
        open_interest=oi, oi_change=0, volume=5000, iv=iv,
    )


def _make_chain(
    spot: float = 24500.0,
    strikes: list[OptionStrike] | None = None,
    index: str = "NIFTY",
) -> OptionChainSnapshot:
    if strikes is None:
        strikes = [
            _make_strike(24300, "CE", 200_000, iv=16.0, ltp=220.0),
            _make_strike(24300, "PE", 400_000, iv=17.0, ltp=30.0),
            _make_strike(24400, "CE", 300_000, iv=15.5, ltp=140.0),
            _make_strike(24400, "PE", 350_000, iv=16.5, ltp=55.0),
            _make_strike(24500, "CE", 500_000, iv=15.0, ltp=80.0),
            _make_strike(24500, "PE", 500_000, iv=15.0, ltp=80.0),
            _make_strike(24600, "CE", 350_000, iv=15.5, ltp=40.0),
            _make_strike(24600, "PE", 300_000, iv=16.5, ltp=150.0),
            _make_strike(24700, "CE", 400_000, iv=16.0, ltp=20.0),
            _make_strike(24700, "PE", 200_000, iv=17.0, ltp=230.0),
        ]
    now = datetime.now(IST)
    return OptionChainSnapshot(
        index=index, spot_price=spot,
        timestamp=now.isoformat(),
        expiry_date=(now + timedelta(days=7)).strftime("%Y-%m-%d"),
        lot_size=25, strikes=strikes, atm_strike=24500.0,
        pcr=1.0, max_pain=24500.0,
        highest_call_oi_strike=24500.0, highest_put_oi_strike=24300.0,
    )


# ── 1. IV Percentile ────────────────────────────────────────────────


class TestIVPercentile:
    def test_no_history_returns_neutral(self, engine):
        assert engine.compute_iv_percentile("NIFTY", 15.0) == 50.0

    def test_all_below(self, engine, mock_db):
        # Insert 10 days of IV all below current
        for i in range(10):
            mock_db.insert_fno_iv_history(
                f"2026-07-{i+1:02d}", "NIFTY", 10.0 + i * 0.1, 24000.0,
            )
        # Current IV = 20.0 → all 10 are below → IVP = 100
        assert engine.compute_iv_percentile("NIFTY", 20.0) == 100.0

    def test_all_above(self, engine, mock_db):
        for i in range(10):
            mock_db.insert_fno_iv_history(
                f"2026-07-{i+1:02d}", "NIFTY", 20.0 + i * 0.1, 24000.0,
            )
        # Current IV = 5.0 → none below → IVP = 0
        assert engine.compute_iv_percentile("NIFTY", 5.0) == 0.0

    def test_half_below(self, engine, mock_db):
        for i in range(10):
            mock_db.insert_fno_iv_history(
                f"2026-07-{i+1:02d}", "NIFTY", 10.0 + i, 24000.0,
            )
        # IVs: 10,11,12,13,14,15,16,17,18,19. Current=15 → 5 below → 50%
        assert engine.compute_iv_percentile("NIFTY", 15.0) == 50.0

    def test_ivp_bounded(self, engine, mock_db):
        for i in range(5):
            mock_db.insert_fno_iv_history(
                f"2026-07-{i+1:02d}", "NIFTY", 15.0, 24000.0,
            )
        ivp = engine.compute_iv_percentile("NIFTY", 15.0)
        assert 0.0 <= ivp <= 100.0


class TestIVPSignal:
    def test_sell_premium(self):
        assert Quant_Edge_Engine.ivp_signal(80.0) == "SELL_PREMIUM"

    def test_buy_premium(self):
        assert Quant_Edge_Engine.ivp_signal(20.0) == "BUY_PREMIUM"

    def test_use_spreads(self):
        assert Quant_Edge_Engine.ivp_signal(50.0) == "USE_SPREADS"


# ── 2. OI Velocity ──────────────────────────────────────────────────


class TestOIVelocity:
    def test_insufficient_snapshots(self, engine):
        support, resistance = engine.compute_oi_velocity([])
        assert support == []
        assert resistance == []

    def test_single_snapshot(self, engine):
        support, resistance = engine.compute_oi_velocity([_make_chain()])
        assert support == []
        assert resistance == []

    def test_detects_institutional_support(self, engine):
        """Put OI increase > 500K should flag as support."""
        old_strikes = [
            _make_strike(24400, "PE", 100_000),
            _make_strike(24400, "CE", 100_000),
        ]
        new_strikes = [
            _make_strike(24400, "PE", 700_000),  # +600K
            _make_strike(24400, "CE", 100_000),
        ]
        old_chain = _make_chain(strikes=old_strikes)
        new_chain = _make_chain(strikes=new_strikes)
        support, resistance = engine.compute_oi_velocity([old_chain, new_chain])
        assert len(support) == 1
        assert support[0]["strike"] == 24400
        assert support[0]["oi_change_30m"] == 600_000
        assert resistance == []

    def test_detects_institutional_resistance(self, engine):
        """Call OI increase > 500K should flag as resistance."""
        old_strikes = [
            _make_strike(24600, "CE", 100_000),
            _make_strike(24600, "PE", 100_000),
        ]
        new_strikes = [
            _make_strike(24600, "CE", 800_000),  # +700K
            _make_strike(24600, "PE", 100_000),
        ]
        old_chain = _make_chain(strikes=old_strikes)
        new_chain = _make_chain(strikes=new_strikes)
        support, resistance = engine.compute_oi_velocity([old_chain, new_chain])
        assert resistance[0]["strike"] == 24600
        assert support == []

    def test_below_threshold_not_flagged(self, engine):
        old_strikes = [_make_strike(24500, "PE", 100_000)]
        new_strikes = [_make_strike(24500, "PE", 400_000)]  # +300K < 500K
        support, _ = engine.compute_oi_velocity(
            [_make_chain(strikes=old_strikes), _make_chain(strikes=new_strikes)]
        )
        assert support == []


# ── 3. IV Skew ───────────────────────────────────────────────────────


class TestIVSkew:
    def test_returns_float_and_signal(self, engine, greeks_calc):
        chain = _make_chain()
        skew, signal = engine.compute_iv_skew(chain, greeks_calc)
        assert isinstance(skew, float)
        assert signal in ("BEARISH", "BULLISH", "NEUTRAL")

    def test_empty_chain_returns_neutral(self, engine, greeks_calc):
        chain = _make_chain(strikes=[])
        skew, signal = engine.compute_iv_skew(chain, greeks_calc)
        assert skew == 0.0
        assert signal == "NEUTRAL"


# ── 4. GEX ───────────────────────────────────────────────────────────


class TestGEX:
    def test_returns_gex_map(self, engine, greeks_calc):
        chain = _make_chain()
        gex_map, gravity, regime = engine.compute_gex(chain, greeks_calc)
        assert isinstance(gex_map, list)
        assert isinstance(gravity, (int, float))
        assert regime in ("PINNED", "TRENDING")

    def test_gex_map_has_strikes(self, engine, greeks_calc):
        chain = _make_chain()
        gex_map, _, _ = engine.compute_gex(chain, greeks_calc)
        assert len(gex_map) > 0
        for item in gex_map:
            assert "strike" in item
            assert "net_gex" in item

    def test_empty_chain(self, engine, greeks_calc):
        chain = _make_chain(strikes=[])
        gex_map, gravity, regime = engine.compute_gex(chain, greeks_calc)
        assert gex_map == []
        assert regime == "PINNED"  # Total GEX = 0 → PINNED


# ── 5. VRP ───────────────────────────────────────────────────────────


class TestVRP:
    def test_insufficient_history(self, engine):
        vrp, signal = engine.compute_vrp("NIFTY", 15.0)
        assert vrp == 2.0  # Fallback when insufficient history
        assert signal == "MODERATE_SELL"  # New fallback signal

    def test_with_sufficient_history(self, engine, mock_db):
        # Insert 25 days of spot history with known log returns
        base_price = 24000.0
        for i in range(25):
            price = base_price * (1 + 0.001 * i)
            log_ret = math.log(price / (base_price * (1 + 0.001 * max(0, i - 1)))) if i > 0 else 0.0
            mock_db.insert_fno_spot_history(
                f"2026-07-{i+1:02d}", "NIFTY", price, log_ret,
            )
        vrp, signal = engine.compute_vrp("NIFTY", 15.0)
        assert isinstance(vrp, float)
        assert signal in ("STRONG_SELL", "MODERATE_SELL", "WEAK_EDGE", "BUY_PREMIUM")


class TestVRPSignal:
    def test_strong_sell(self):
        assert _vrp_signal(6.0) == "STRONG_SELL"

    def test_moderate_sell(self):
        assert _vrp_signal(3.0) == "MODERATE_SELL"

    def test_weak_edge(self):
        assert _vrp_signal(1.0) == "WEAK_EDGE"

    def test_buy_premium(self):
        assert _vrp_signal(-2.0) == "BUY_PREMIUM"

    def test_boundary_2(self):
        assert _vrp_signal(2.0) == "MODERATE_SELL"

    def test_boundary_5(self):
        assert _vrp_signal(5.0) == "MODERATE_SELL"

    def test_boundary_above_5(self):
        assert _vrp_signal(5.01) == "STRONG_SELL"


# ── 6. Confluence Score ──────────────────────────────────────────────


class TestConfluenceScore:
    def test_score_bounded(self, engine):
        score, breakdown = engine.compute_confluence_score(
            ivp=50.0, oi_support=[], oi_resistance=[],
            iv_skew=0.0, gex_regime="PINNED", vrp=3.0,
            pcr=1.0, max_pain=24500.0, spot=24500.0,
            strategy_type="IRON_CONDOR",
        )
        assert 0.0 <= score <= 100.0

    def test_breakdown_keys(self, engine):
        _, breakdown = engine.compute_confluence_score(
            ivp=80.0, oi_support=[{"strike": 24400}], oi_resistance=[],
            iv_skew=2.0, gex_regime="PINNED", vrp=6.0,
            pcr=1.1, max_pain=24500.0, spot=24500.0,
            strategy_type="SHORT_STRANGLE",
        )
        assert set(breakdown.keys()) == {"ivp", "oi", "skew", "gex", "vrp", "pcr_mp"}

    def test_high_ivp_selling_scores_well(self, engine):
        score, _ = engine.compute_confluence_score(
            ivp=90.0, oi_support=[{"strike": 24400}], oi_resistance=[{"strike": 24600}],
            iv_skew=1.0, gex_regime="PINNED", vrp=6.0,
            pcr=1.1, max_pain=24500.0, spot=24500.0,
            strategy_type="IRON_CONDOR",
        )
        assert score >= 50.0  # Should be a decent score

    def test_zero_inputs(self, engine):
        score, breakdown = engine.compute_confluence_score(
            ivp=0.0, oi_support=[], oi_resistance=[],
            iv_skew=0.0, gex_regime="PINNED", vrp=0.0,
            pcr=1.0, max_pain=24500.0, spot=24500.0,
            strategy_type="IRON_CONDOR",
        )
        assert score >= 0.0
        assert all(v >= 0 for v in breakdown.values())


# ── 7. Adaptive Weights ─────────────────────────────────────────────


class TestAdaptiveWeights:
    def test_default_weights_with_no_history(self, engine):
        weights = engine.get_adaptive_weights("IRON_CONDOR")
        assert weights == DEFAULT_WEIGHTS

    def test_returns_dict_with_correct_keys(self, engine):
        weights = engine.get_adaptive_weights("SHORT_STRANGLE")
        assert set(weights.keys()) == set(DEFAULT_WEIGHTS.keys())


# ── 8. compute_all_signals Orchestrator ──────────────────────────────


class TestComputeAllSignals:
    def test_returns_quant_signals(self, engine, greeks_calc):
        chain = _make_chain()
        signals = engine.compute_all_signals(chain, greeks_calc)
        assert isinstance(signals, QuantSignals)
        assert 0.0 <= signals.iv_percentile <= 100.0
        assert signals.iv_percentile_signal in ("SELL_PREMIUM", "BUY_PREMIUM", "USE_SPREADS")
        assert signals.gex_regime in ("PINNED", "TRENDING")
        assert signals.vrp_signal in ("STRONG_SELL", "MODERATE_SELL", "WEAK_EDGE", "BUY_PREMIUM")
        assert 0.0 <= signals.confluence_score <= 100.0

    def test_with_snapshots(self, engine, greeks_calc):
        chain = _make_chain()
        signals = engine.compute_all_signals(chain, greeks_calc, snapshots=[chain, chain])
        assert isinstance(signals, QuantSignals)
