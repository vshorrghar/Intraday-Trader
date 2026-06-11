"""Tests for Phase 5: Paper Mode Real Pricing + Improved Exit Rules.

Validates that paper mode uses real chain prices (not simulation)
and that exit rules hold positions for meaningful theta capture.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from fno.monitor import FnO_Position_Monitor
from fno.rules_strategy_engine import get_exit_rules, EXIT_RULES

IST = timezone(timedelta(hours=5, minutes=30))


def _make_config():
    config = MagicMock()
    config.force_exit_time = "15:15"
    config.trailing_sl_trigger_pct = 150
    config.partial_book_pct = 50
    config.max_delta_exposure = 100
    config.max_vega_exposure = 100
    config.broker = "dhan"
    return config


def _make_strategy(
    strategy_type="IRON_CONDOR",
    net_premium=500,
    max_profit=500,
    status="OPEN",
    expiry_date="2026-06-10",
):
    """Create a mock strategy dict."""
    legs = [
        {"strike": 24200, "option_type": "CE", "transaction_type": "SELL",
         "num_lots": 1, "lot_size": 25, "expiry_date": expiry_date},
        {"strike": 24400, "option_type": "CE", "transaction_type": "BUY",
         "num_lots": 1, "lot_size": 25, "expiry_date": expiry_date},
        {"strike": 23800, "option_type": "PE", "transaction_type": "SELL",
         "num_lots": 1, "lot_size": 25, "expiry_date": expiry_date},
        {"strike": 23600, "option_type": "PE", "transaction_type": "BUY",
         "num_lots": 1, "lot_size": 25, "expiry_date": expiry_date},
    ]
    return {
        "id": 1,
        "strategy_type": strategy_type,
        "index_name": "NIFTY",
        "status": status,
        "net_premium": net_premium,
        "max_profit": max_profit,
        "max_loss": -5000,
        "legs_json": json.dumps(legs),
        "entry_time": datetime.now(IST).isoformat(),
        "net_theta": 45.0,
        "net_delta": -2.0,
        "trade_date": datetime.now(IST).strftime("%Y-%m-%d"),
    }


class TestPaperPricingRealChain:
    """Test that paper mode uses real chain prices, not simulation."""

    def test_paper_entry_uses_real_chain_mid_price(self):
        """Paper engine simulate_fill uses LTP from chain, not arbitrary values."""
        from fno.paper_engine import Paper_Trade_Engine
        from fno.models import FnOStrategySetup, StrategyLeg, OptionChainSnapshot, OptionStrike

        config = MagicMock()
        config.paper_capital = 500000
        config.broker = "dhan"

        db = MagicMock()
        db.insert_fno_strategy.return_value = 1
        db.insert_fno_trade.return_value = 1

        engine = Paper_Trade_Engine(config, db)

        # Create strategy with legs
        legs = [
            StrategyLeg(index="NIFTY", strike_price=24200, expiry_date="2026-06-10",
                        option_type="CE", transaction_type="SELL", lot_size=25, num_lots=1, entry_price=50.0),
            StrategyLeg(index="NIFTY", strike_price=24400, expiry_date="2026-06-10",
                        option_type="CE", transaction_type="BUY", lot_size=25, num_lots=1, entry_price=30.0),
        ]
        strategy = FnOStrategySetup(
            strategy_type="IRON_CONDOR", index="NIFTY", legs=legs,
            net_premium=500, max_profit=500, max_loss=-5000,
            net_delta=-2, net_gamma=-0.5, net_theta=45, net_vega=-15,
            confidence_score=8, rationale="test", market_regime="SIDEWAYS",
            confluence_score=60, expiry_date="2026-06-10",
        )

        # Create chain with specific LTPs
        chain = MagicMock()
        chain.strikes = [
            MagicMock(strike_price=24200, option_type="CE", ltp=55.0),
            MagicMock(strike_price=24400, option_type="CE", ltp=32.0),
        ]

        # Simulate fill
        result = engine.simulate_fill(strategy, chain=chain)

        assert result is not None
        # Verify insert_fno_trade was called with chain LTP, not leg.entry_price
        calls = db.insert_fno_trade.call_args_list
        assert len(calls) >= 2
        # First leg (CE SELL at 24200) should use chain LTP 55.0
        first_call_kwargs = calls[0][1]
        assert first_call_kwargs["entry_price"] == 55.0
        # Second leg (CE BUY at 24400) should use chain LTP 32.0
        second_call_kwargs = calls[1][1]
        assert second_call_kwargs["entry_price"] == 32.0

    def test_paper_mtm_refreshes_chain_prices(self):
        """MTM cycle should fetch real chain prices, not use random simulation."""
        config = _make_config()
        db = MagicMock()
        db.get_fno_strategies_for_date.return_value = [_make_strategy()]
        db.update_fno_strategy = MagicMock()
        db.insert_audit_log = MagicMock()

        # Mock broker with option chain
        broker = MagicMock()
        broker.get_option_chain.return_value = {
            "strikes": [
                {"strike_price": 24200, "option_type": "CE", "ltp": 40.0},
                {"strike_price": 24400, "option_type": "CE", "ltp": 25.0},
                {"strike_price": 23800, "option_type": "PE", "ltp": 35.0},
                {"strike_price": 23600, "option_type": "PE", "ltp": 20.0},
            ]
        }
        broker.get_fno_positions.return_value = []

        monitor = FnO_Position_Monitor(config, db, MagicMock(), broker=broker, paper_engine=None)

        strat = _make_strategy()
        positions = []

        # Patch the cache to force fresh fetch from broker
        with patch("fno.option_chain_cache.get_cached_chain", return_value=None):
            premium = monitor._compute_current_premium(strat, positions)

        # Premium should be computed from real chain values, not random
        # SELL CE 24200 (40×25=1000) + SELL PE 23800 (35×25=875) - BUY CE 24400 (25×25=625) - BUY PE 23600 (20×25=500)
        # = 1000 + 875 - 625 - 500 = 750 (absolute)
        assert premium == 750.0

    def test_paper_exit_uses_real_chain_mid_price(self):
        """Exit P&L should be computed from real chain prices at exit time."""
        from fno.paper_engine import Paper_Trade_Engine
        from fno.models import FnOStrategySetup, StrategyLeg

        config = MagicMock()
        config.paper_capital = 500000
        config.broker = "dhan"

        db = MagicMock()
        db.insert_fno_strategy.return_value = 1
        db.insert_fno_trade.return_value = 1
        db.update_fno_strategy = MagicMock()

        engine = Paper_Trade_Engine(config, db)

        # Create and fill a strategy
        legs = [
            StrategyLeg(index="NIFTY", strike_price=24200, expiry_date="2026-06-10",
                        option_type="CE", transaction_type="SELL", lot_size=25, num_lots=1, entry_price=50.0),
            StrategyLeg(index="NIFTY", strike_price=24400, expiry_date="2026-06-10",
                        option_type="CE", transaction_type="BUY", lot_size=25, num_lots=1, entry_price=30.0),
        ]
        strategy = FnOStrategySetup(
            strategy_type="IRON_CONDOR", index="NIFTY", legs=legs,
            net_premium=500, max_profit=500, max_loss=-5000,
            net_delta=-2, net_gamma=-0.5, net_theta=45, net_vega=-15,
            confidence_score=8, rationale="test", market_regime="SIDEWAYS",
            confluence_score=60, expiry_date="2026-06-10",
        )

        chain = MagicMock()
        chain.strikes = [
            MagicMock(strike_price=24200, option_type="CE", ltp=50.0),
            MagicMock(strike_price=24400, option_type="CE", ltp=30.0),
        ]
        engine.simulate_fill(strategy, chain=chain)

        # Close with exit prices (premium decayed)
        exit_prices = {(24200, "CE"): 25.0, (24400, "CE"): 15.0}
        pnl = engine.close_position(1, exit_prices=exit_prices)

        # SELL CE: (50 - 25) × 25 = 625
        # BUY CE: (15 - 30) × 25 = -375
        # Total = 250
        assert pnl == 250.0


class TestImprovedExitRules:
    """Test that exit rules hold positions for meaningful theta capture."""

    def test_iron_condor_50pct_profit_target_holds_longer(self):
        """IC should NOT exit at 10% profit — only at 50% of max_profit."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        strat = _make_strategy(net_premium=500, max_profit=500)
        now = datetime(2026, 6, 5, 12, 0, tzinfo=IST)  # Well before expiry

        # 10% profit: current_premium = 450 (entry was 500, profit = 50 = 10%)
        result = monitor._evaluate_exit_conditions(strat, 450, 500, now)
        assert result is None  # Should NOT exit at 10%

        # 50% profit: current_premium = 250 (profit = 250 = 50% of max_profit)
        result = monitor._evaluate_exit_conditions(strat, 250, 500, now)
        assert result == "CLOSED"  # Should exit at 50%

    def test_no_exit_on_every_mtm_tick(self):
        """Small premium changes should NOT trigger exit."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        strat = _make_strategy(net_premium=500, max_profit=500)
        now = datetime(2026, 6, 5, 12, 0, tzinfo=IST)

        # Premium barely changed: 495 (only 1% profit)
        result = monitor._evaluate_exit_conditions(strat, 495, 500, now)
        assert result is None

        # Premium slightly up (loss direction): 520 (4% loss, below 1.5× threshold)
        result = monitor._evaluate_exit_conditions(strat, 520, 500, now)
        assert result is None

    def test_exit_at_loss_threshold(self):
        """Should exit when premium expands beyond loss multiplier."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        strat = _make_strategy(net_premium=500, max_profit=500)
        now = datetime(2026, 6, 5, 12, 0, tzinfo=IST)

        # IC loss exit: 1.5× multiplier → threshold = 500 × (1 + 1.5) = 1250
        result = monitor._evaluate_exit_conditions(strat, 1300, 500, now)
        assert result == "STOPPED_OUT"

    def test_time_exit_1_day_before_expiry(self):
        """IC should exit 1 day before expiry."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        # Strategy expiring tomorrow, check at noon (before force_exit_time)
        tomorrow = (datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d")
        strat = _make_strategy(net_premium=500, max_profit=500, expiry_date=tomorrow)
        now = datetime.now(IST).replace(hour=12, minute=0, second=0)

        result = monitor._evaluate_exit_conditions(strat, 400, 500, now)
        assert result == "EXPIRED"  # DTE = 1, time_exit_dte = 1 for IC

    def test_spread_exits_2_days_before_expiry(self):
        """Spreads should exit 2 days before expiry."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        # Strategy expiring in 2 days, check at noon (before force_exit_time)
        in_2_days = (datetime.now(IST) + timedelta(days=2)).strftime("%Y-%m-%d")
        strat = _make_strategy(
            strategy_type="BULL_PUT_SPREAD",
            net_premium=400, max_profit=400, expiry_date=in_2_days,
        )
        now = datetime.now(IST).replace(hour=12, minute=0, second=0)

        result = monitor._evaluate_exit_conditions(strat, 300, 400, now)
        assert result == "EXPIRED"  # DTE = 2, time_exit_dte = 2 for spreads

    def test_exit_skipped_when_far_from_expiry(self):
        """Should NOT time-exit when DTE is well above threshold."""
        config = _make_config()
        db = MagicMock()

        monitor = FnO_Position_Monitor(config, db, MagicMock())

        # Strategy expiring in 7 days, check at noon (before force_exit_time)
        in_7_days = (datetime.now(IST) + timedelta(days=7)).strftime("%Y-%m-%d")
        strat = _make_strategy(net_premium=500, max_profit=500, expiry_date=in_7_days)
        now = datetime.now(IST).replace(hour=12, minute=0, second=0)

        # Premium unchanged — no exit trigger
        result = monitor._evaluate_exit_conditions(strat, 480, 500, now)
        assert result is None
