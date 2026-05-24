"""
Tests for swing/rules_selector.py (built by Kiro).
This file is a SKELETON — tests will pass once Kiro's file exists.
Verifies: deterministic picks, no LLM calls, R:R >= 2.0,
          confidence scoring rules, empty input handling.
"""
import pytest


def make_candidate(symbol, score, delta, rsi2, last_5d_ret,
                   turnover_cr, atr_pct, close=500.0):
    """Build a mock scanner candidate dict."""
    return {
        "symbol": symbol,
        "tradingsymbol": symbol,
        "score": score,
        "latest_close": close,
        "dma_20": close / (1 + delta/100),
        "dma_50": close * 0.95,
        "dma_200": close * 0.85,
        "rsi2": rsi2,
        "atr_pct": atr_pct,
        "avg_turnover_cr": turnover_cr,
        "sector": "PHARMA",
        "delta_from_20dma": delta,
        "last_5d_return": last_5d_ret,
        "signals": {"pullback": 5, "rsi2_oversold": 2,
                    "reversal_candle": 1, "defensive_sector": 3, "liquidity": 1},
        "penalties": {"falling_knife": 0, "weakening_trend": 0},
    }


@pytest.fixture
def good_candidates():
    return [
        make_candidate("RELIANCE", 14, -0.5, 7,  1.0, 50.0, 2.0),
        make_candidate("INFY",     12, -0.3, 12, 0.5, 80.0, 1.8),
        make_candidate("HDFCBANK", 10,  0.5, 22, 2.0, 200.0, 1.5),
        make_candidate("TCS",       8,  0.8, 28, 1.5, 150.0, 1.6),
        make_candidate("WIPRO",     6,  1.5, 35, 3.0, 40.0,  1.4),  # below min_score
    ]


@pytest.fixture
def swing_config():
    from swing.models import SwingConfig
    return SwingConfig(
        swing_min_score=8,
        swing_min_confidence=7,
        swing_min_confidence_live=8,
        swing_min_rr=2.0,
    )


class TestRulesSelectorExists:
    def test_import(self):
        """rules_selector.py must be importable."""
        try:
            from swing.rules_selector import select_swing_trades
            assert callable(select_swing_trades)
        except ImportError:
            pytest.skip("swing/rules_selector.py not yet built by Kiro")

    def test_no_bedrock_import(self):
        """rules_selector.py must not import boto3 or bedrock."""
        import importlib
        try:
            import swing.rules_selector as m
        except ImportError:
            pytest.skip("Not built yet")
        import inspect
        source = inspect.getsource(m)
        assert "import boto3" not in source and "from boto3" not in source, "boto3 imported in rules_selector.py"
        assert "import bedrock" not in source, "bedrock imported in rules_selector.py"
        assert "invoke_model" not in source


class TestRulesSelectorLogic:
    def test_empty_candidates_returns_empty(self, swing_config):
        """Empty candidate list returns empty list."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result = select_swing_trades([], swing_config)
        assert result == []

    def test_all_below_min_score_returns_empty(self, swing_config):
        """All candidates below min_score=8 returns empty."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        low_candidates = [make_candidate("X", 5, -0.5, 7, 1.0, 50.0, 2.0)]
        result = select_swing_trades(low_candidates, swing_config)
        assert result == []

    def test_returns_swing_trade_setup_objects(self, good_candidates, swing_config):
        """Returns list of SwingTradeSetup, not raw dicts."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        from swing.models import SwingTradeSetup
        result = select_swing_trades(good_candidates, swing_config)
        for trade in result:
            assert isinstance(trade, SwingTradeSetup)

    def test_rr_at_least_2(self, good_candidates, swing_config):
        """All returned trades must have R:R >= 2.0."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result = select_swing_trades(good_candidates, swing_config)
        for trade in result:
            rr = (trade.target_price - trade.entry_price) / \
                 (trade.entry_price - trade.stop_loss_price)
            assert rr >= 2.0, f"{trade.stock_name} R:R={rr:.2f} < 2.0"

    def test_max_3_trades_returned(self, good_candidates, swing_config):
        """Selector returns at most 3 trades."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result = select_swing_trades(good_candidates, swing_config)
        assert len(result) <= 3

    def test_confidence_score_14_gives_9(self, swing_config):
        """Score >= 14 → confidence = 9."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        candidates = [make_candidate("HIGH", 14, -0.5, 7, 1.0, 50.0, 2.0)]
        result = select_swing_trades(candidates, swing_config)
        if result:
            assert result[0].confidence_score == 9

    def test_confidence_score_10_gives_7(self, swing_config):
        """Score 10-11 → confidence = 7."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        candidates = [make_candidate("MED", 10, -0.5, 7, 1.0, 50.0, 2.0)]
        result = select_swing_trades(candidates, swing_config)
        if result:
            assert result[0].confidence_score == 7

    def test_deterministic_same_input_same_output(self, good_candidates, swing_config):
        """Same input always produces same output (no randomness)."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result1 = select_swing_trades(good_candidates, swing_config)
        result2 = select_swing_trades(good_candidates, swing_config)
        assert len(result1) == len(result2)
        for t1, t2 in zip(result1, result2):
            assert t1.stock_name == t2.stock_name
            assert t1.entry_price == t2.entry_price

    def test_stop_loss_below_entry(self, good_candidates, swing_config):
        """Stop loss must always be below entry price (LONG only)."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result = select_swing_trades(good_candidates, swing_config)
        for trade in result:
            assert trade.stop_loss_price < trade.entry_price

    def test_target_above_entry(self, good_candidates, swing_config):
        """Target must always be above entry price."""
        try:
            from swing.rules_selector import select_swing_trades
        except ImportError:
            pytest.skip("Not built yet")
        result = select_swing_trades(good_candidates, swing_config)
        for trade in result:
            assert trade.target_price > trade.entry_price
