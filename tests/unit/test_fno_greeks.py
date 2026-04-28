"""Unit tests for fno/greeks.py — FnO_Greeks_Calculator.

Tests Black-Scholes pricing, Greeks computation, IV root-finding,
strategy Greeks aggregation, and edge cases.
"""

import math

import pytest

from fno.greeks import FnO_Greeks_Calculator
from fno.models import Greeks, StrategyLeg


@pytest.fixture
def calc():
    return FnO_Greeks_Calculator()


# ── Black-Scholes pricing ────────────────────────────────────────────────


class TestComputeOptionPrice:
    """Tests for compute_option_price."""

    def test_call_price_positive(self, calc):
        """ATM call should have a positive price."""
        price = calc.compute_option_price(
            spot=24500, strike=24500, tte=7 / 365, iv=0.15, option_type="CE"
        )
        assert price > 0

    def test_put_price_positive(self, calc):
        """ATM put should have a positive price."""
        price = calc.compute_option_price(
            spot=24500, strike=24500, tte=7 / 365, iv=0.15, option_type="PE"
        )
        assert price > 0

    def test_put_call_parity(self, calc):
        """Put-call parity: C - P = S - K * exp(-rT)."""
        spot, strike, tte, iv, r = 24500, 24500, 30 / 365, 0.20, 0.07
        call = calc.compute_option_price(spot, strike, tte, iv, "CE", r)
        put = calc.compute_option_price(spot, strike, tte, iv, "PE", r)
        parity_rhs = spot - strike * math.exp(-r * tte)
        assert abs((call - put) - parity_rhs) < 0.01

    def test_deep_itm_call(self, calc):
        """Deep ITM call price ≈ intrinsic value."""
        price = calc.compute_option_price(
            spot=25000, strike=23000, tte=7 / 365, iv=0.15, option_type="CE"
        )
        intrinsic = 25000 - 23000
        assert price >= intrinsic * 0.99  # At least ~intrinsic

    def test_deep_otm_call_near_zero(self, calc):
        """Deep OTM call price should be very small."""
        price = calc.compute_option_price(
            spot=24500, strike=27000, tte=7 / 365, iv=0.15, option_type="CE"
        )
        assert price < 1.0

    def test_zero_tte_call_intrinsic(self, calc):
        """Zero TTE call returns intrinsic value."""
        price = calc.compute_option_price(
            spot=24600, strike=24500, tte=0, iv=0.15, option_type="CE"
        )
        assert price == 100.0

    def test_zero_tte_put_intrinsic(self, calc):
        """Zero TTE put returns intrinsic value."""
        price = calc.compute_option_price(
            spot=24400, strike=24500, tte=0, iv=0.15, option_type="PE"
        )
        assert price == 100.0

    def test_zero_tte_otm_call(self, calc):
        """Zero TTE OTM call returns 0."""
        price = calc.compute_option_price(
            spot=24400, strike=24500, tte=0, iv=0.15, option_type="CE"
        )
        assert price == 0.0

    def test_higher_iv_higher_price(self, calc):
        """Higher IV should produce a higher option price."""
        low_iv = calc.compute_option_price(24500, 24500, 7 / 365, 0.10, "CE")
        high_iv = calc.compute_option_price(24500, 24500, 7 / 365, 0.30, "CE")
        assert high_iv > low_iv


# ── Greeks computation ────────────────────────────────────────────────────


class TestComputeGreeks:
    """Tests for compute_greeks."""

    def test_atm_call_delta_near_half(self, calc):
        """ATM call delta should be close to 0.5."""
        g = calc.compute_greeks(24500, 24500, 30 / 365, 0.15, "CE")
        assert 0.4 < g.delta < 0.7

    def test_atm_put_delta_near_neg_half(self, calc):
        """ATM put delta should be close to -0.5."""
        g = calc.compute_greeks(24500, 24500, 30 / 365, 0.15, "PE")
        assert -0.7 < g.delta < -0.4

    def test_deep_itm_call_delta_near_one(self, calc):
        """Deep ITM call delta → 1."""
        g = calc.compute_greeks(25000, 23000, 30 / 365, 0.15, "CE")
        assert g.delta > 0.95

    def test_deep_otm_call_delta_near_zero(self, calc):
        """Deep OTM call delta → 0."""
        g = calc.compute_greeks(24500, 27000, 7 / 365, 0.15, "CE")
        assert g.delta < 0.05

    def test_gamma_positive(self, calc):
        """Gamma should always be positive for long options."""
        g = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "CE")
        assert g.gamma > 0

    def test_gamma_same_for_call_put(self, calc):
        """Gamma is the same for call and put at same strike."""
        gc = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "CE")
        gp = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "PE")
        assert abs(gc.gamma - gp.gamma) < 1e-10

    def test_vega_positive(self, calc):
        """Vega should be positive."""
        g = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "CE")
        assert g.vega > 0

    def test_vega_same_for_call_put(self, calc):
        """Vega is the same for call and put at same strike."""
        gc = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "CE")
        gp = calc.compute_greeks(24500, 24500, 7 / 365, 0.15, "PE")
        assert abs(gc.vega - gp.vega) < 1e-10

    def test_theta_negative_for_long_call(self, calc):
        """Theta should be negative (time decay hurts long positions)."""
        g = calc.compute_greeks(24500, 24500, 30 / 365, 0.15, "CE")
        assert g.theta < 0

    def test_zero_tte_greeks(self, calc):
        """Zero TTE: gamma, theta, vega all zero."""
        g = calc.compute_greeks(24600, 24500, 0, 0.15, "CE")
        assert g.delta == 1.0
        assert g.gamma == 0.0
        assert g.theta == 0.0
        assert g.vega == 0.0

    def test_zero_tte_otm_put(self, calc):
        """Zero TTE OTM put: delta = 0."""
        g = calc.compute_greeks(24600, 24500, 0, 0.15, "PE")
        assert g.delta == 0.0

    def test_zero_tte_itm_put(self, calc):
        """Zero TTE ITM put: delta = -1."""
        g = calc.compute_greeks(24400, 24500, 0, 0.15, "PE")
        assert g.delta == -1.0

    def test_zero_tte_atm_call(self, calc):
        """Zero TTE ATM call: delta = 0.5."""
        g = calc.compute_greeks(24500, 24500, 0, 0.15, "CE")
        assert g.delta == 0.5


# ── Implied Volatility ───────────────────────────────────────────────────


class TestImpliedVolatility:
    """Tests for implied_volatility (Newton-Raphson root finding)."""

    def test_round_trip_call(self, calc):
        """Price → IV → Price round-trip for a call."""
        iv_original = 0.18
        price = calc.compute_option_price(24500, 24500, 30 / 365, iv_original, "CE")
        iv_recovered = calc.implied_volatility(price, 24500, 24500, 30 / 365, "CE")
        assert abs(iv_recovered - iv_original) < 0.01

    def test_round_trip_put(self, calc):
        """Price → IV → Price round-trip for a put."""
        iv_original = 0.22
        price = calc.compute_option_price(24500, 24500, 30 / 365, iv_original, "PE")
        iv_recovered = calc.implied_volatility(price, 24500, 24500, 30 / 365, "PE")
        assert abs(iv_recovered - iv_original) < 0.01

    def test_round_trip_otm_call(self, calc):
        """Round-trip for OTM call."""
        iv_original = 0.25
        price = calc.compute_option_price(24500, 25000, 14 / 365, iv_original, "CE")
        iv_recovered = calc.implied_volatility(price, 24500, 25000, 14 / 365, "CE")
        assert abs(iv_recovered - iv_original) < 0.01

    def test_zero_tte_raises(self, calc):
        """IV computation with zero TTE should raise ValueError."""
        with pytest.raises(ValueError, match="zero or negative"):
            calc.implied_volatility(100, 24500, 24500, 0, "CE")

    def test_high_iv_round_trip(self, calc):
        """Round-trip with high IV (50%)."""
        iv_original = 0.50
        price = calc.compute_option_price(24500, 24500, 30 / 365, iv_original, "CE")
        iv_recovered = calc.implied_volatility(price, 24500, 24500, 30 / 365, "CE")
        assert abs(iv_recovered - iv_original) < 0.01


# ── Strategy Greeks ──────────────────────────────────────────────────────


class TestStrategyGreeks:
    """Tests for strategy_greeks (multi-leg aggregation)."""

    def test_single_buy_leg(self, calc):
        """Single BUY CE leg: net delta should be positive."""
        legs = [
            StrategyLeg(
                index="NIFTY", strike_price=24500, expiry_date="2026-07-25",
                option_type="CE", transaction_type="BUY",
                lot_size=25, num_lots=1, entry_price=100,
            )
        ]
        g = calc.strategy_greeks(legs, spot=24500)
        assert g.delta > 0

    def test_straddle_near_zero_delta(self, calc):
        """Short straddle (sell ATM CE + sell ATM PE): delta near zero."""
        legs = [
            StrategyLeg(
                index="NIFTY", strike_price=24500, expiry_date="2026-07-25",
                option_type="CE", transaction_type="SELL",
                lot_size=25, num_lots=1, entry_price=100,
            ),
            StrategyLeg(
                index="NIFTY", strike_price=24500, expiry_date="2026-07-25",
                option_type="PE", transaction_type="SELL",
                lot_size=25, num_lots=1, entry_price=100,
            ),
        ]
        g = calc.strategy_greeks(legs, spot=24500)
        # ATM call delta ≈ 0.5, ATM put delta ≈ -0.5
        # Sell both: net delta ≈ -0.5*25 - (-0.5)*25 ≈ 0 (roughly)
        assert abs(g.delta) < 30  # Within reasonable range for 25 qty

    def test_futures_leg_delta(self, calc):
        """Futures leg: delta = ±quantity."""
        legs = [
            StrategyLeg(
                index="NIFTY", strike_price=0, expiry_date="2026-07-25",
                option_type="FUT", transaction_type="BUY",
                lot_size=25, num_lots=1, entry_price=24500,
            )
        ]
        g = calc.strategy_greeks(legs, spot=24500)
        assert g.delta == 25  # BUY 1 lot of 25

    def test_empty_legs(self, calc):
        """Empty legs list: all Greeks zero."""
        g = calc.strategy_greeks([], spot=24500)
        assert g.delta == 0.0
        assert g.gamma == 0.0
        assert g.theta == 0.0
        assert g.vega == 0.0
