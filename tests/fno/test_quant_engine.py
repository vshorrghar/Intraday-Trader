"""
Tests for fno/quant_engine.py
Covers: IVP signal, VRP signal, confluence score, OI velocity.
All tests use mock data — no broker, no option chain API calls.
"""
import pytest


class TestIVPSignal:
    def test_high_ivp_signals_sell_premium(self):
        """IVP > 70 → SELL_PREMIUM signal."""
        from fno.quant_engine import Quant_Edge_Engine
        assert Quant_Edge_Engine.ivp_signal(75.0) == "SELL_PREMIUM"

    def test_low_ivp_signals_buy_premium(self):
        """IVP < 30 → BUY_PREMIUM signal."""
        from fno.quant_engine import Quant_Edge_Engine
        assert Quant_Edge_Engine.ivp_signal(25.0) == "BUY_PREMIUM"

    def test_mid_ivp_signals_use_spreads(self):
        """30 <= IVP <= 70 → USE_SPREADS."""
        from fno.quant_engine import Quant_Edge_Engine
        assert Quant_Edge_Engine.ivp_signal(50.0) == "USE_SPREADS"


class TestVRPSignal:
    def test_high_vrp_strong_sell(self):
        """VRP > 5 → STRONG_SELL."""
        from fno.quant_engine import _vrp_signal
        assert _vrp_signal(6.0) == "STRONG_SELL"

    def test_moderate_vrp(self):
        """2 <= VRP <= 5 → MODERATE_SELL."""
        from fno.quant_engine import _vrp_signal
        assert _vrp_signal(3.0) == "MODERATE_SELL"

    def test_negative_vrp_buy_premium(self):
        """VRP < 0 → BUY_PREMIUM."""
        from fno.quant_engine import _vrp_signal
        assert _vrp_signal(-1.0) == "BUY_PREMIUM"


class TestConfluenceScore:
    def test_score_between_0_and_100(self):
        """Confluence score must always be in [0, 100]."""
        from fno.quant_engine import Quant_Edge_Engine
        from database.db_manager import DBManager
        from fno.config import FnO_Config
        db = DBManager(":memory:")
        cfg = FnO_Config()
        engine = Quant_Edge_Engine(db, cfg)
        score, _ = engine.compute_confluence_score(
            ivp=75, oi_support=[{"strike": 24000, "oi_change_30m": 600000}],
            oi_resistance=[], iv_skew=2.0, gex_regime="PINNED",
            vrp=3.0, pcr=1.1, max_pain=24000, spot=24050,
            strategy_type="IRON_CONDOR",
        )
        assert 0 <= score <= 100

    def test_high_signals_give_high_score(self):
        """All bullish signals should give confluence > 50."""
        from fno.quant_engine import Quant_Edge_Engine
        from database.db_manager import DBManager
        from fno.config import FnO_Config
        db = DBManager(":memory:")
        cfg = FnO_Config()
        engine = Quant_Edge_Engine(db, cfg)
        score, _ = engine.compute_confluence_score(
            ivp=80, oi_support=[{"strike": 24000, "oi_change_30m": 1000000}],
            oi_resistance=[{"strike": 24500, "oi_change_30m": 1000000}],
            iv_skew=1.0, gex_regime="PINNED", vrp=5.0,
            pcr=1.0, max_pain=24000, spot=24000,
            strategy_type="IRON_CONDOR",
        )
        assert score > 50


class TestOIVelocity:
    def test_large_put_oi_increase_flags_support(self):
        """Put OI increase > 500K at a strike flags institutional support."""
        from fno.quant_engine import Quant_Edge_Engine
        from fno.models import OptionChainSnapshot, OptionStrike
        from database.db_manager import DBManager
        from fno.config import FnO_Config

        def make_snapshot(pe_oi):
            strikes = [
                OptionStrike(24000, "2026-06-26", "PE", 50, 49, 51,
                             pe_oi, 0, 100000, 15.0),
                OptionStrike(24000, "2026-06-26", "CE", 50, 49, 51,
                             100000, 0, 100000, 15.0),
            ]
            return OptionChainSnapshot(
                "NIFTY", 24000, "2026-04-15T09:30:00+05:30", "2026-06-26",
                25, strikes, 24000, 1.0, 24000, 24000, 24000
            )

        db = DBManager(":memory:")
        cfg = FnO_Config()
        engine = Quant_Edge_Engine(db, cfg)
        snap_old = make_snapshot(pe_oi=500000)
        snap_new = make_snapshot(pe_oi=1100000)  # +600K = above threshold
        support, resistance = engine.compute_oi_velocity([snap_old, snap_new])
        assert len(support) >= 1, "Should detect institutional support"
        assert support[0]["strike"] == 24000
