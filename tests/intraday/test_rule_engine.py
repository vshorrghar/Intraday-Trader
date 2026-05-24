"""
Tests for backtest/rule_engine.py
Covers: VWAP calculation, ATR calculation, opening range,
        relative volume, ORB signal generation (V4, V6)
All tests use synthetic data — no broker, no API calls.
"""
import pytest
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def make_candle(h, m, o, hi, lo, c, vol, date="2026-04-15"):
    dt = datetime.strptime(f"{date} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return {"time": dt, "open": o, "high": hi, "low": lo, "close": c, "volume": vol}


# ── VWAP ─────────────────────────────────────────────────────────────

class TestVWAP:
    def test_single_candle(self):
        """VWAP of one candle equals its typical price."""
        from backtest.rule_engine import calculate_vwap
        candles = [make_candle(9, 15, 100, 110, 90, 105, 1000)]
        result = calculate_vwap(candles)
        expected = (110 + 90 + 105) / 3
        assert len(result) == 1
        assert abs(result[0] - expected) < 0.01

    def test_vwap_rises_on_bullish_candles(self):
        """VWAP should increase as price trends up."""
        from backtest.rule_engine import calculate_vwap
        candles = [
            make_candle(9, 15, 100, 102, 98,  101, 1000),
            make_candle(9, 30, 101, 105, 100, 104, 2000),
            make_candle(9, 45, 104, 108, 103, 107, 3000),
        ]
        result = calculate_vwap(candles)
        assert len(result) == 3
        assert result[2] > result[0], "VWAP should rise on bullish candles"

    def test_zero_volume_handled(self):
        """Zero volume candle should not crash."""
        from backtest.rule_engine import calculate_vwap
        candles = [make_candle(9, 15, 100, 105, 95, 100, 0)]
        result = calculate_vwap(candles)
        assert len(result) == 1
        assert result[0] > 0

    def test_empty_candles(self):
        """Empty input returns empty list."""
        from backtest.rule_engine import calculate_vwap
        assert calculate_vwap([]) == []


# ── ATR ──────────────────────────────────────────────────────────────

class TestATR:
    def test_atr_positive(self):
        """ATR must always be positive."""
        from backtest.rule_engine import calculate_atr
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        # Use pre-built candles with valid times across multiple hours
        times = [
            (9,15),(9,30),(9,45),(10,0),(10,15),(10,30),(10,45),
            (11,0),(11,15),(11,30),(11,45),(12,0),(12,15),(12,30),
            (12,45),(13,0),(13,15),(13,30),(13,45),(14,0)
        ]
        candles = [make_candle(h, m, 100, 105, 95, 100, 1000) for h,m in times]
        result = calculate_atr(candles)
        assert all(v >= 0 for v in result)

    def test_atr_length_matches_candles(self):
        """ATR list length must equal candle count."""
        from backtest.rule_engine import calculate_atr
        times = [(9,15),(9,30),(9,45),(10,0),(10,15),(10,30),(10,45),(11,0),(11,15),(11,30)]
        candles = [make_candle(h, m, 100, 105, 95, 100, 1000) for h,m in times]
        result = calculate_atr(candles, period=5)
        assert len(result) == len(candles)

    def test_high_volatility_means_higher_atr(self):
        """Wider candles should produce higher ATR."""
        from backtest.rule_engine import calculate_atr
        times = [
            (9,15),(9,30),(9,45),(10,0),(10,15),(10,30),(10,45),
            (11,0),(11,15),(11,30),(11,45),(12,0),(12,15),(12,30),
            (12,45),(13,0),(13,15),(13,30),(13,45),(14,0)
        ]
        tight = [make_candle(h, m, 100, 101, 99,  100, 1000) for h,m in times]
        wide  = [make_candle(h, m, 100, 110, 90,  100, 1000) for h,m in times]
        assert calculate_atr(wide)[-1] > calculate_atr(tight)[-1]


# ── Opening Range ─────────────────────────────────────────────────────

class TestOpeningRange:
    def test_opening_range_uses_915_to_930(self):
        """Only candles 9:15-9:30 form the opening range."""
        from backtest.rule_engine import get_opening_range
        candles = [
            make_candle(9, 15, 100, 105, 95, 101, 1000),  # in range
            make_candle(9, 30, 101, 108, 98, 104, 1200),  # in range
            make_candle(9, 45, 104, 120, 90, 115, 2000),  # NOT in range
        ]
        result = get_opening_range(candles)
        assert result is not None
        assert result["high"] == 108, "High should be max of 9:15-9:30 only"
        assert result["low"] == 95,  "Low should be min of 9:15-9:30 only"

    def test_opening_range_width(self):
        """Width = high - low."""
        from backtest.rule_engine import get_opening_range
        candles = [
            make_candle(9, 15, 100, 110, 90, 100, 1000),
            make_candle(9, 30, 100, 112, 88, 100, 1000),
        ]
        result = get_opening_range(candles)
        assert result["width"] == 112 - 88

    def test_insufficient_candles_returns_none(self):
        """Less than 2 opening candles returns None."""
        from backtest.rule_engine import get_opening_range
        candles = [make_candle(9, 15, 100, 105, 95, 100, 1000)]
        assert get_opening_range(candles) is None

    def test_no_opening_candles_returns_none(self):
        """Only post-930 candles returns None."""
        from backtest.rule_engine import get_opening_range
        candles = [make_candle(10, 0, 100, 105, 95, 100, 1000)]
        assert get_opening_range(candles) is None


# ── Market Direction ──────────────────────────────────────────────────

class TestMarketDirection:
    def test_strong_bull_day(self):
        """Nifty up > 1.5% = BULL STRONG."""
        from backtest.rule_engine import get_market_direction
        # Build minimal ohlc with prev_close 100, price_at_930 = 102
        timestamps = [
            int(datetime(2026, 4, 14, 15, 30, tzinfo=IST).timestamp()),
            int(datetime(2026, 4, 15,  9, 30, tzinfo=IST).timestamp()),
        ]
        ohlc = {
            "close": [100.0, 102.0],
            "open":  [100.0, 101.0],
            "high":  [100.0, 102.5],
            "low":   [100.0, 100.5],
            "volume":[100000, 100000],
            "timestamp": timestamps,
        }
        result = get_market_direction(ohlc, "2026-04-15")
        assert result["direction"] == "BULL"
        assert result["strength"] == "STRONG"

    def test_flat_day_is_flat(self):
        """Nifty change <= 0.3% = FLAT."""
        from backtest.rule_engine import get_market_direction
        timestamps = [
            int(datetime(2026, 4, 14, 15, 30, tzinfo=IST).timestamp()),
            int(datetime(2026, 4, 15,  9, 30, tzinfo=IST).timestamp()),
        ]
        ohlc = {
            "close": [100.0, 100.2],
            "open":  [100.0, 100.1],
            "high":  [100.0, 100.3],
            "low":   [100.0, 100.0],
            "volume":[100000, 100000],
            "timestamp": timestamps,
        }
        result = get_market_direction(ohlc, "2026-04-15")
        assert result["direction"] == "FLAT"


# ── V6 Gap Filter ─────────────────────────────────────────────────────

class TestV6GapFilter:
    def test_v6_requires_gap_above_1_5_pct(self):
        """
        V6 strategy only fires when gap > 1.5%.
        A stock with 0.5% gap should produce no V6 signal.
        This is a smoke test — uses generate_orb_signals directly.
        """
        # TODO: build synthetic universe data and verify
        # V6 returns empty list when no stock has gap > 1.5%
        pass  # skeleton — fill after Kiro builds rules_selector

    def test_v4_fires_without_gap(self):
        """V4 can fire on any breakout day, gap not required."""
        pass  # skeleton


# ── Relative Volume ───────────────────────────────────────────────────

class TestRelativeVolume:
    def test_high_volume_returns_ratio_above_1(self):
        """Today 3x average should return ~3.0."""
        from backtest.rule_engine import calculate_relative_volume
        # Build ohlc with 20 days of 100k volume, today 300k
        import time as t
        base = int(datetime(2026, 3, 1, 9, 15, tzinfo=IST).timestamp())
        timestamps = []
        volumes = []
        for i in range(20):
            timestamps.append(base + i * 86400)
            volumes.append(100000)
        # Today
        today_ts = int(datetime(2026, 4, 15, 9, 15, tzinfo=IST).timestamp())
        ohlc = {
            "timestamp": timestamps + [today_ts],
            "volume": volumes + [300000],
            "open": [100.0] * 21, "high": [101.0] * 21,
            "low": [99.0] * 21, "close": [100.0] * 21,
        }
        today_candles = [make_candle(9, 15, 100, 101, 99, 100, 300000)]
        result = calculate_relative_volume(today_candles, ohlc, "2026-04-15")
        assert result > 1.0, f"Expected rel_vol > 1, got {result}"
