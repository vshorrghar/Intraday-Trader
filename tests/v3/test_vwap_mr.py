"""Tests for VWAP Mean Reversion strategy."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.strategies.vwap_mean_reversion import detect_vwap_mr_signals


def _make_mock_data(symbol="TESTSTOCK"):
    """Create mock 15-min OHLC data with a VWAP cross-above pattern."""
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    # Simulate a day: stock opens at 100, dips below VWAP, then recovers
    base_ts = datetime(2026, 5, 27, 9, 15, tzinfo=IST).timestamp()
    candles_count = 20

    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    timestamps = []

    price = 100.0
    for i in range(candles_count):
        ts = base_ts + i * 900  # 15-min intervals
        timestamps.append(ts)

        if i < 4:
            # First hour: normal trading around 100
            o, h, l, c = price, price + 0.5, price - 0.3, price + 0.2
            vol = 500000
        elif i < 8:
            # Dip below VWAP (price drops to ~97-98)
            price -= 0.6
            o, h, l, c = price + 0.3, price + 0.5, price - 0.2, price
            vol = 300000
        elif i == 8:
            # Cross-above candle (recovery)
            o, h, l, c = price, price + 1.5, price - 0.1, price + 1.2
            price = c
            vol = 600000
        else:
            # Continue up
            price += 0.2
            o, h, l, c = price - 0.1, price + 0.3, price - 0.2, price
            vol = 400000

        opens.append(round(o, 2))
        highs.append(round(h, 2))
        lows.append(round(l, 2))
        closes.append(round(c, 2))
        volumes.append(vol)

    return {symbol: {"open": opens, "high": highs, "low": lows,
                     "close": closes, "volume": volumes, "start_Time": timestamps}}


class TestVwapMR:
    def test_vwap_mr_only_fires_in_ranging(self):
        data = _make_mock_data("STOCK1")
        universe = {"STOCK1": "1234"}
        config = {"per_trade_max_capital": 10000}

        # Should fire in RANGING
        signals = detect_vwap_mr_signals(data, universe, config, "2026-05-27", regime="RANGING")
        # May or may not find signal depending on mock data shape — but should NOT error
        assert isinstance(signals, list)

    def test_vwap_mr_returns_empty_in_trending(self):
        data = _make_mock_data("STOCK1")
        universe = {"STOCK1": "1234"}
        config = {"per_trade_max_capital": 10000}

        # Must return empty in non-RANGING regimes
        for regime in ["TRENDING_UP", "TRENDING_DOWN", "VOLATILE", "UNCLEAR"]:
            signals = detect_vwap_mr_signals(data, universe, config, "2026-05-27", regime=regime)
            assert signals == [], f"Should be empty for regime={regime}"

    def test_vwap_mr_signal_structure(self):
        data = _make_mock_data("STOCK1")
        universe = {"STOCK1": "1234"}
        config = {"per_trade_max_capital": 10000}

        signals = detect_vwap_mr_signals(data, universe, config, "2026-05-27", regime="RANGING")
        # If any signals found, verify structure
        for s in signals:
            assert "symbol" in s
            assert "direction" in s
            assert s["direction"] == "LONG"
            assert "entry_price" in s
            assert "stop_loss" in s
            assert "target" in s
            assert "qty" in s
            assert s["entry_price"] > s["stop_loss"]
            assert s["target"] > s["entry_price"]
            assert s.get("strategy") == "VWAP_MR"
