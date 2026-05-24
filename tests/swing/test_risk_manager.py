"""
Tests for swing/risk_manager.py
Covers: position sizing (1% rule + per_trade_max cap),
        sector cap, daily loss limit, weekly loss limit, VIX regime gate.
"""
import pytest


class TestPositionSizing:
    def test_position_size_limits_risk_to_1_pct(self):
        """
        1% risk rule: risk_amount = capital × 0.01
        qty = floor(risk_amount / risk_per_share)
        per_trade_max must not override the risk-rule result
        when risk-rule qty × entry_price <= per_trade_max.
        """
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="RELIANCE", tradingsymbol="RELIANCE",
            nse_symbol="RELIANCE",
            entry_price=2800.0, target_price=3000.0,
            stop_loss_price=2680.0,  # Rs.120 risk per share
            quantity=0, confidence_score=8,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        # Capital = Rs.1,00,000  →  1% = Rs.1,000
        # risk_per_share = 2800 - 2680 = 120
        # qty_by_risk = int(1000 / 120) = 8
        # per_trade_max = Rs.50,000  →  max_qty = int(50000/2800) = 17
        # min(8, 17) = 8  ← risk rule wins correctly
        qty = compute_position_size(
            trade,
            capital_limit=100000.0,
            per_trade_max=50000.0,
        )
        assert qty == 8, f"Expected 8 (1% risk rule), got {qty}"

    def test_per_trade_max_caps_when_risk_qty_too_large(self):
        """
        When 1% risk rule allows more shares than per_trade_max,
        per_trade_max cap must win.

        Example: cheap stock Rs.10, SL at Rs.9.50 (risk=0.50)
          1% of Rs.1L = Rs.1,000 → qty_by_risk = 2000 shares
          per_trade_max = Rs.10,000 → max_qty = 1000 shares
          Result must be 1000, not 2000.
        """
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="CHEAPSTOCK", tradingsymbol="CHEAPSTOCK",
            nse_symbol="CHEAPSTOCK",
            entry_price=10.0, target_price=11.0,
            stop_loss_price=9.50,  # Rs.0.50 risk
            quantity=0, confidence_score=7,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        qty = compute_position_size(
            trade,
            capital_limit=100000.0,
            per_trade_max=10000.0,
        )
        # qty_by_risk = int(1000 / 0.50) = 2000
        # max_qty = int(10000 / 10) = 1000
        # min(2000, 1000) = 1000
        assert qty == 1000, f"Expected 1000 (per_trade_max cap), got {qty}"

    def test_fallback_when_per_trade_max_zero(self):
        """
        per_trade_max=0 triggers fallback to 20% of capital_limit.
        Must not crash and must return a positive quantity.
        """
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="TEST", tradingsymbol="TEST", nse_symbol="TEST",
            entry_price=500.0, target_price=540.0,
            stop_loss_price=480.0,
            quantity=0, confidence_score=7,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        qty = compute_position_size(trade, capital_limit=100000.0, per_trade_max=0.0)
        assert qty >= 1

    def test_old_10pct_bug_no_longer_present(self):
        """
        Regression test: the old code used int(capital × 0.1 / entry_price)
        as the cap, which gave qty=3 for RELIANCE instead of 8.
        This test proves the bug is gone.
        """
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="RELIANCE", tradingsymbol="RELIANCE",
            nse_symbol="RELIANCE",
            entry_price=2800.0, target_price=3000.0,
            stop_loss_price=2680.0,
            quantity=0, confidence_score=8,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        qty = compute_position_size(
            trade,
            capital_limit=100000.0,
            per_trade_max=50000.0,
        )
        # Old bug returned 3. Correct answer is 8.
        assert qty != 3, "Old 10% cap bug is back"
        assert qty == 8

    def test_position_size_always_at_least_1(self):
        """Position size must always be >= 1 even on very expensive stocks."""
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="MRF", tradingsymbol="MRF", nse_symbol="MRF",
            entry_price=150000.0, target_price=160000.0,
            stop_loss_price=144000.0,
            quantity=0, confidence_score=7,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        qty = compute_position_size(
            trade,
            capital_limit=100000.0,
            per_trade_max=50000.0,
        )
        assert qty >= 1

    def test_invalid_sl_above_entry_returns_zero(self):
        """SL >= entry (invalid trade setup) returns 0, not a crash."""
        from swing.risk_manager import compute_position_size
        from swing.models import SwingTradeSetup
        trade = SwingTradeSetup(
            stock_name="BAD", tradingsymbol="BAD", nse_symbol="BAD",
            entry_price=100.0, target_price=110.0,
            stop_loss_price=105.0,  # SL ABOVE entry — invalid
            quantity=0, confidence_score=7,
            rationale="test", holding_days_estimate=10,
            thesis_invalidation="test",
        )
        qty = compute_position_size(
            trade,
            capital_limit=100000.0,
            per_trade_max=50000.0,
        )
        assert qty == 0


class TestSectorCap:
    def test_sector_cap_blocks_3rd_position(self):
        """Max 2 positions per sector — 3rd should be blocked."""
        from swing.risk_manager import check_sector_cap
        symbol = "RELIANCE"
        open_positions = [{"symbol": symbol}, {"symbol": symbol}]
        ok, reason = check_sector_cap(symbol, open_positions, max_per_sector=2)
        assert ok is False
        assert reason is not None

    def test_first_position_in_sector_allowed(self):
        """First stock in sector should always be allowed."""
        from swing.risk_manager import check_sector_cap
        ok, _ = check_sector_cap("RELIANCE", [], max_per_sector=2)
        assert ok is True

    def test_second_position_in_sector_allowed(self):
        """Second stock in same sector is allowed (max=2)."""
        from swing.risk_manager import check_sector_cap
        ok, _ = check_sector_cap("RELIANCE", [{"symbol": "RELIANCE"}], max_per_sector=2)
        assert ok is True


class TestDailyLossLimit:
    def test_loss_at_limit_blocks_trade(self):
        """Today P&L exactly at daily loss limit blocks new trades."""
        from swing.risk_manager import check_daily_loss
        ok, reason = check_daily_loss(today_pnl=-1000.0, daily_loss_limit=1000.0)
        assert ok is False
        assert "1000" in reason

    def test_loss_below_limit_allows_trade(self):
        """Today P&L below limit allows new trades."""
        from swing.risk_manager import check_daily_loss
        ok, _ = check_daily_loss(today_pnl=-500.0, daily_loss_limit=1000.0)
        assert ok is True

    def test_positive_pnl_always_allows(self):
        """Positive P&L always allows new trades."""
        from swing.risk_manager import check_daily_loss
        ok, _ = check_daily_loss(today_pnl=500.0, daily_loss_limit=1000.0)
        assert ok is True

    def test_zero_pnl_allows(self):
        """Zero P&L allows new trades."""
        from swing.risk_manager import check_daily_loss
        ok, _ = check_daily_loss(today_pnl=0.0, daily_loss_limit=1000.0)
        assert ok is True


class TestWeeklyLossLimit:
    def test_weekly_loss_5pct_blocks(self):
        """Weekly loss >= 5% of capital blocks trades."""
        from swing.risk_manager import check_weekly_loss
        ok, reason = check_weekly_loss(
            week_pnl=-5000.0,
            capital_limit=100000.0,
            max_pct=5.0,
        )
        assert ok is False

    def test_weekly_loss_below_threshold_allows(self):
        """Weekly loss < 5% allows trades."""
        from swing.risk_manager import check_weekly_loss
        ok, _ = check_weekly_loss(
            week_pnl=-4000.0,
            capital_limit=100000.0,
            max_pct=5.0,
        )
        assert ok is True

    def test_zero_capital_never_blocks(self):
        """Capital limit = 0 skips weekly loss check (avoid divide by zero)."""
        from swing.risk_manager import check_weekly_loss
        ok, _ = check_weekly_loss(week_pnl=-99999.0, capital_limit=0.0)
        assert ok is True


class TestVIXGate:
    def test_vix_above_25_blocks_all(self):
        """VIX > 25 = skip swing entries."""
        from swing.risk_manager import check_regime
        ok, reason = check_regime(vix=26.0)
        assert ok is False
        assert reason is not None

    def test_vix_22_to_25_reduces_size(self):
        """VIX 22-25 = REDUCE signal, not full block."""
        from swing.risk_manager import check_regime
        ok, reason = check_regime(vix=23.0)
        assert ok == "REDUCE"

    def test_vix_normal_allows_entries(self):
        """VIX = 15, Nifty above all MAs = proceed."""
        from swing.risk_manager import check_regime
        ok, _ = check_regime(
            vix=15.0,
            nifty_close=24000,
            nifty_50dma=23000,
            nifty_200dma=22000,
        )
        assert ok is True

    def test_nifty_below_200dma_blocks(self):
        """Nifty below 200-DMA = bear regime = skip."""
        from swing.risk_manager import check_regime
        ok, reason = check_regime(
            vix=15.0,
            nifty_close=21000,
            nifty_50dma=22000,
            nifty_200dma=22500,
        )
        assert ok is False

    def test_nifty_below_50dma_reduces(self):
        """Nifty below 50-DMA but above 200-DMA = REDUCE."""
        from swing.risk_manager import check_regime
        ok, _ = check_regime(
            vix=15.0,
            nifty_close=22000,
            nifty_50dma=23000,
            nifty_200dma=21000,
        )
        assert ok == "REDUCE"
