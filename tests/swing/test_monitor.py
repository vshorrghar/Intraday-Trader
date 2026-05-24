"""
Tests for swing/monitor.py
Covers: time stop logic, SL hit detection, target hit detection,
        smart time stop (never sells winners early).
"""
import pytest


class TestSmartTimeStop:
    def test_30_day_hard_limit_always_exits(self):
        """After 30 days, always exit regardless of P&L."""
        from swing.monitor import should_time_exit
        action, reason = should_time_exit(days_held=30, pnl_pct=50.0)
        assert action == "EXIT"
        assert reason == "30_DAY_HARD_LIMIT"

    def test_big_winner_held_longer_than_30_days_still_exits(self):
        """Even +100% winner must exit at hard limit."""
        from swing.monitor import should_time_exit
        action, _ = should_time_exit(days_held=35, pnl_pct=100.0)
        assert action == "EXIT"

    def test_profitable_trade_not_exited_early(self):
        """Trade at +5% after 14 days must HOLD."""
        from swing.monitor import should_time_exit
        action, _ = should_time_exit(days_held=14, pnl_pct=5.0)
        assert action == "HOLD"

    def test_losing_trade_exited_at_15_days(self):
        """Trade at -1% after 15 days must EXIT."""
        from swing.monitor import should_time_exit
        action, _ = should_time_exit(days_held=15, pnl_pct=-1.0)
        assert action == "EXIT"

    def test_flat_trade_exited_at_10_days(self):
        """Trade flat (0.5%) after 10 days must EXIT."""
        from swing.monitor import should_time_exit
        action, _ = should_time_exit(days_held=10, pnl_pct=0.5)
        assert action == "EXIT"

    def test_big_drawdown_exited_at_7_days(self):
        """Trade at -3% after 7 days must EXIT."""
        from swing.monitor import should_time_exit
        action, _ = should_time_exit(days_held=7, pnl_pct=-3.0)
        assert action == "EXIT"

    def test_new_trade_not_exited(self):
        """Trade at day 3 with any P&L must HOLD."""
        from swing.monitor import should_time_exit
        for pnl in [-5.0, 0.0, 10.0]:
            action, _ = should_time_exit(days_held=3, pnl_pct=pnl)
            assert action == "HOLD", f"Day 3 trade should HOLD, got EXIT at pnl={pnl}"


class TestNeedsReview:
    def test_big_winner_needs_review(self):
        """30+ days and 50%+ gain triggers review alert."""
        from swing.monitor import needs_review
        flag, reason = needs_review(days_held=31, pnl_pct=55.0)
        assert flag is True

    def test_normal_trade_no_review(self):
        """Normal trade does not need review."""
        from swing.monitor import needs_review
        flag, _ = needs_review(days_held=5, pnl_pct=3.0)
        assert flag is False
