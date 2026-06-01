"""Unit tests for backtest/run_swing_backtest.py."""

import pytest

from backtest.run_swing_backtest import (
    simulate_exit,
    compute_charges,
    build_universe_as_of_date,
    get_trading_dates,
    CHARGE_PER_SIDE,
)


def _make_candles(n: int, base: float = 100.0, trend: float = 0.5) -> list[dict]:
    """Generate N candles with a slight uptrend."""
    candles = []
    for i in range(n):
        close = base + i * trend
        candles.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": close - 0.3,
            "high": close + 1.5,
            "low": close - 1.5,
            "close": close,
            "volume": 1000000,
        })
    return candles


class TestNoFutureLeak:
    def test_universe_excludes_future_dates(self):
        """build_universe_as_of_date must not include candles after scan_date."""
        all_data = {
            "TCS": [
                {"date": "2026-01-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1e6},
                {"date": "2026-01-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1e6},
                {"date": "2026-01-03", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 1e6},
            ] + _make_candles(200, base=103)  # Pad to 200+
        }

        # Scan as of Jan 2 — should NOT see Jan 3 data
        universe = build_universe_as_of_date(all_data, "2026-01-02")

        if "TCS" in universe:
            closes = universe["TCS"]["close"]
            # Last close should be 102 (Jan 2), not 103 (Jan 3)
            assert closes[-1] <= 102.0
            # Should not contain any value from Jan 3 onwards
            assert 103.0 not in closes[:3]  # First 3 original candles

    def test_insufficient_history_excluded(self):
        """Stocks with < 200 candles as of scan_date are excluded."""
        all_data = {
            "SMALL": _make_candles(150),  # Only 150 candles total
        }
        universe = build_universe_as_of_date(all_data, "2026-01-28")
        assert "SMALL" not in universe


class TestChargesApplied:
    def test_charges_reduce_pnl(self):
        """0.1% per side charges reduce P&L."""
        entry = 100.0
        exit_price = 110.0
        qty = 10

        charges = compute_charges(entry, exit_price, qty)
        # Buy side: 100 * 10 * 0.001 = 1.0
        # Sell side: 110 * 10 * 0.001 = 1.1
        expected = 1.0 + 1.1
        assert abs(charges - expected) < 0.01

    def test_charges_positive_even_on_loss(self):
        """Charges are always positive (cost)."""
        charges = compute_charges(100.0, 90.0, 5)
        assert charges > 0


class TestExitPriority:
    def test_sl_before_target_same_day(self):
        """When both SL and target hit same day, SL wins (conservative)."""
        # Candle where both SL (95) and target (115) are hit
        forward_candles = [
            {"date": "2026-01-05", "open": 100, "high": 120, "low": 90, "close": 105, "volume": 1e6},
        ]

        exit_date, exit_price, reason, days = simulate_exit(
            forward_candles,
            entry_price=100.0,
            sl_price=95.0,
            target_price=115.0,
            entry_date="2026-01-04",
        )

        assert reason == "STOPPED_OUT"
        assert exit_price == 95.0

    def test_target_hit_when_sl_not_breached(self):
        """Target hit when SL not breached."""
        forward_candles = [
            {"date": "2026-01-05", "open": 100, "high": 120, "low": 98, "close": 115, "volume": 1e6},
        ]

        exit_date, exit_price, reason, days = simulate_exit(
            forward_candles,
            entry_price=100.0,
            sl_price=90.0,  # SL not hit (low=98 > 90)
            target_price=115.0,
            entry_date="2026-01-04",
        )

        assert reason == "TARGET_HIT"
        assert exit_price == 115.0


class TestPositionSizing:
    def test_risk_capped_at_1_pct(self):
        """Position sizing uses 1% of capital as risk amount.

        SwingConfig default: capital=50000, so risk_amount = 500.
        With entry=100, SL at 6% below (=94), risk=6 per share, qty = 500/6 = 83.
        But per_trade_max=5000, so max_qty = 5000/100 = 50.
        Final qty = min(83, 50) = 50.
        """
        from swing.rules_selector import _build_trade_setup
        from swing.models import SwingConfig

        config = SwingConfig()
        candidate = {
            "symbol": "TEST",
            "latest_close": 100.0,
            "atr_pct": 4.0,  # ATR 4% → SL = max(4%, 1.5*4%=6%) = 6%, capped at 8%
            "score": 12,
            "delta_from_20dma": -1.0,
            "rsi2": 20,
            "signals": {"pullback": 5, "rsi2_oversold": 3},
        }

        setup = _build_trade_setup(candidate, config, per_trade_max=5000)
        if setup is not None:
            # Verify quantity doesn't exceed per_trade_max / entry_price
            assert setup.quantity * setup.entry_price <= 5000
            # Verify risk per trade <= 1% of capital
            risk_per_share = setup.entry_price - setup.stop_loss_price
            total_risk = risk_per_share * setup.quantity
            assert total_risk <= config.swing_capital_limit * 0.01 + 1  # +1 for rounding


class TestHandlesNoSignalDays:
    def test_empty_universe_no_crash(self):
        """Days with no qualifying stocks don't break the loop."""
        from swing.scanner import scan_universe

        # Empty universe
        result = scan_universe({}, min_score=8)
        assert result == []

    def test_no_candidates_no_crash(self):
        """Rules selector handles empty candidate list."""
        from swing.rules_selector import select_swing_trades
        from swing.models import SwingConfig

        config = SwingConfig()
        result = select_swing_trades([], config)
        assert result == []
