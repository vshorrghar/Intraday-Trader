"""
Tests for fno/rules_strategy_engine.py (built by Kiro).
Skeleton — tests activate once Kiro's file exists.
Covers: all 6 rule table conditions, strike selection, no LLM calls.
"""
import pytest


def make_mock_chain(index="NIFTY", spot=24000, atm=24000,
                    expiry="2026-05-29", dte=7):
    """Build a minimal OptionChainSnapshot for testing."""
    from fno.models import OptionChainSnapshot, OptionStrike
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    interval = 50 if index in ("NIFTY", "FINNIFTY") else 100
    strikes = []
    for i in range(-5, 6):
        sp = atm + i * interval
        for opt in ("CE", "PE"):
            ltp = max(1.0, 100.0 - abs(i) * 15)
            strikes.append(OptionStrike(
                sp, expiry, opt, ltp, ltp-1, ltp+1,
                500000, 0, 100000, 15.0
            ))

    return OptionChainSnapshot(
        index, float(spot),
        "2026-04-15T09:30:00+05:30", expiry,
        25, strikes, float(atm),
        1.0, float(atm), float(atm + 200), float(atm - 200)
    )


def make_mock_signals(ivp=75, vrp=3.0, gex_regime="PINNED",
                      iv_skew=1.0, iv_skew_signal="NEUTRAL",
                      confluence=65, oi_support=None, oi_resistance=None):
    """Build a QuantSignals object for testing."""
    from fno.models import QuantSignals
    return QuantSignals(
        iv_percentile=ivp,
        iv_percentile_signal="SELL_PREMIUM" if ivp > 70 else "USE_SPREADS",
        oi_velocity_support=oi_support or [{"strike": 23800, "oi_change_30m": 600000}],
        oi_velocity_resistance=oi_resistance or [{"strike": 24200, "oi_change_30m": 600000}],
        iv_skew=iv_skew,
        iv_skew_signal=iv_skew_signal,
        gex_map=[],
        gex_gravity_center=24000.0,
        gex_regime=gex_regime,
        vrp=vrp,
        vrp_signal="STRONG_SELL" if vrp > 5 else "MODERATE_SELL",
        confluence_score=confluence,
        confluence_breakdown={},
    )


class TestRulesEngineExists:
    def test_import(self):
        """rules_strategy_engine.py must be importable."""
        try:
            from fno.rules_strategy_engine import FnO_Rules_Strategy_Engine
            assert callable(FnO_Rules_Strategy_Engine)
        except ImportError:
            pytest.skip("fno/rules_strategy_engine.py not yet built by Kiro")

    def test_no_bedrock_import(self):
        """Must not contain boto3 or bedrock calls."""
        try:
            import fno.rules_strategy_engine as m
        except ImportError:
            pytest.skip("Not built yet")
        import inspect
        src = inspect.getsource(m)
        assert "import boto3" not in src and "from boto3" not in src
        assert "invoke_model" not in src
        assert "import bedrock" not in src


class TestRuleTable:
    def _get_engine(self):
        try:
            from fno.rules_strategy_engine import FnO_Rules_Strategy_Engine
            from database.db_manager import DBManager
            from fno.config import FnO_Config
            from fno.greeks import FnO_Greeks_Calculator
            db = DBManager(":memory:")
            cfg = FnO_Config()
            greeks = FnO_Greeks_Calculator()
            return FnO_Rules_Strategy_Engine(cfg, db, greeks)
        except ImportError:
            return None

    def test_high_vix_returns_no_trade(self):
        """VIX > 20 → no strategies returned."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        from fno.models import MarketRegime
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=75, vrp=3.0, confluence=65)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=25.0,  # HIGH
        )
        assert result == [], "VIX > 20 should return no strategies"

    def test_sideways_high_ivp_gives_iron_condor(self):
        """SIDEWAYS + IVP >= 65 + VRP >= 2 + GEX=PINNED + conf >= 55 → IRON_CONDOR."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=75, vrp=3.0, gex_regime="PINNED", confluence=65)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
        )
        types = [s.strategy_type for s in result]
        assert "IRON_CONDOR" in types, f"Expected IRON_CONDOR, got {types}"

    def test_trending_up_gives_bull_put_spread(self):
        """TRENDING_UP + IVP >= 55 + VRP >= 1 + conf >= 50 → BULL_PUT_SPREAD."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=60, vrp=1.5,
                                    iv_skew=0.5, iv_skew_signal="BULLISH",
                                    confluence=55)
        # Force TRENDING_UP by passing 3 rising closes
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
            spot_prices_3d={"NIFTY": [23800.0, 23900.0, 24000.0]},
        )
        types = [s.strategy_type for s in result]
        assert "BULL_PUT_SPREAD" in types, f"Expected BULL_PUT_SPREAD, got {types}"

    def test_low_confluence_returns_no_trade(self):
        """Confluence < 40 → no strategies."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=50, vrp=1.0, confluence=35)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
        )
        assert result == []

    def test_event_day_low_ivp_gives_long_straddle(self):
        """is_event_day=True + IVP < 50 + VRP < 0 → LONG_STRADDLE."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=40, vrp=-1.0, confluence=55)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
            is_event_day=True,
        )
        types = [s.strategy_type for s in result]
        assert "LONG_STRADDLE" in types, f"Expected LONG_STRADDLE, got {types}"

    def test_result_is_list_of_fno_strategy_setup(self):
        """All returned items must be FnOStrategySetup objects."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        from fno.models import FnOStrategySetup
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=75, vrp=3.0, confluence=65)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
        )
        for item in result:
            assert isinstance(item, FnOStrategySetup)

    def test_iron_condor_has_4_legs(self):
        """Iron Condor must have exactly 4 legs."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=75, vrp=3.0, confluence=65)
        result = engine.select_strategies(
            chains={"NIFTY": chain},
            quant_signals={"NIFTY": signals},
            vix=15.0,
        )
        ic = [s for s in result if s.strategy_type == "IRON_CONDOR"]
        if ic:
            assert len(ic[0].legs) == 4

    def test_same_input_same_output(self):
        """Deterministic: same signals always produce same strategy."""
        engine = self._get_engine()
        if engine is None:
            pytest.skip("Not built yet")
        chain = make_mock_chain()
        signals = make_mock_signals(ivp=75, vrp=3.0, confluence=65)
        r1 = engine.select_strategies({"NIFTY": chain}, {"NIFTY": signals}, 15.0)
        r2 = engine.select_strategies({"NIFTY": chain}, {"NIFTY": signals}, 15.0)
        assert [s.strategy_type for s in r1] == [s.strategy_type for s in r2]
