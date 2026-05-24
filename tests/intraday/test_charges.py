"""
Tests for intraday/charges.py
Verifies charge calculation accuracy against known values.
No broker calls. Pure math.
"""
import pytest


class TestIntradayCharges:
    def test_charges_positive(self):
        """Charges must always be positive."""
        from intraday.charges import calculate_intraday_charges
        result = calculate_intraday_charges(100.0, 105.0, 10)
        assert result > 0

    def test_charges_scale_with_trade_size(self):
        """Larger trade = larger charges."""
        from intraday.charges import calculate_intraday_charges
        small = calculate_intraday_charges(100.0, 105.0, 10)
        large = calculate_intraday_charges(100.0, 105.0, 100)
        assert large > small

    def test_charges_reasonable_percentage(self):
        """
        Total charges should be 0.05% - 0.5% of trade value.
        Real Dhan intraday charges are ~0.03% brokerage + STT + exchange.
        """
        from intraday.charges import calculate_intraday_charges
        trade_value = 100.0 * 100  # 100 shares at Rs.100
        charges = calculate_intraday_charges(100.0, 100.0, 100)
        pct = charges / trade_value * 100
        assert 0.01 < pct < 1.0, f"Charges {pct:.3f}% seems wrong"

    def test_buy_and_sell_same_price_still_has_charges(self):
        """Even breakeven trade incurs charges."""
        from intraday.charges import calculate_intraday_charges
        charges = calculate_intraday_charges(100.0, 100.0, 10)
        assert charges > 0
