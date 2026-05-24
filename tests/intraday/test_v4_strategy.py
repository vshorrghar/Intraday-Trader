"""
Tests for V4 strategy: ORB + VWAP + ATR + Market Direction.
Verifies that market direction filter correctly gates trades.
"""
import pytest


class TestV4MarketDirectionGate:
    def test_no_trades_on_flat_day(self):
        """V4 should return no signals on flat market days (±0.3%)."""
        pass  # skeleton — needs synthetic data

    def test_long_only_on_bull_day(self):
        """V4 on bull day returns only LONG signals."""
        pass  # skeleton

    def test_short_only_on_bear_day(self):
        """V4 on bear day returns only SHORT signals."""
        pass  # skeleton

    def test_v4_reduces_trades_vs_v2(self):
        """
        V4 should have fewer trades than V2 (market filter skips ~40% of days).
        This mirrors backtest finding: V2=203 trades vs V4=137 trades.
        """
        pass  # skeleton


class TestV4VWAPConfirmation:
    def test_breakout_below_vwap_skipped(self):
        """Price breaks ORB high but is below VWAP — V4 should not fire."""
        pass  # skeleton

    def test_breakout_above_vwap_fires(self):
        """Price breaks ORB high and is above VWAP — V4 should fire."""
        pass  # skeleton
