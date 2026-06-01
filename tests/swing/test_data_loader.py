"""Unit tests for swing/data_loader.py."""

import json
import os
import time
from pathlib import Path

import pytest

from swing.data_loader import (
    load_daily_candles,
    load_scanner_format,
    get_universe_with_data,
    is_data_fresh,
)


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Create a temporary cache directory and patch CACHE_DIR."""
    import swing.data_loader as dl
    monkeypatch.setattr(dl, "CACHE_DIR", tmp_path)
    return tmp_path


def _make_candles(n: int, base_price: float = 100.0) -> list[dict]:
    """Generate N sample candles for testing."""
    candles = []
    for i in range(n):
        price = base_price + i * 0.5
        candles.append({
            "date": f"2025-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
            "open": price - 0.5,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000000 + i * 10000,
        })
    return candles


def _write_cache(cache_dir: Path, symbol: str, candles: list[dict]):
    """Write a cache file for a symbol."""
    cache_file = cache_dir / f"{symbol}.json"
    data = {
        "symbol": symbol,
        "security_id": "12345",
        "fetched_at": "2026-05-27T18:00:00+05:30",
        "candles": candles,
    }
    with open(cache_file, "w") as f:
        json.dump(data, f)


class TestLoadDailyCandles:
    def test_load_existing_symbol(self, tmp_cache):
        """Loading a cached symbol returns candles list."""
        candles = _make_candles(250)
        _write_cache(tmp_cache, "TCS", candles)

        result = load_daily_candles("TCS")
        assert len(result) == 200  # default lookback_days=200
        assert result[0]["date"] == candles[50]["date"]  # skips first 50
        assert result[-1]["close"] == candles[-1]["close"]

    def test_load_missing_symbol_returns_empty(self, tmp_cache):
        """Loading a non-existent symbol returns empty list."""
        result = load_daily_candles("NONEXISTENT")
        assert result == []

    def test_load_with_custom_lookback(self, tmp_cache):
        """Custom lookback_days limits returned candles."""
        candles = _make_candles(300)
        _write_cache(tmp_cache, "INFY", candles)

        result = load_daily_candles("INFY", lookback_days=100)
        assert len(result) == 100

    def test_load_fewer_candles_than_lookback(self, tmp_cache):
        """If fewer candles than lookback, return all."""
        candles = _make_candles(50)
        _write_cache(tmp_cache, "SMALL", candles)

        result = load_daily_candles("SMALL", lookback_days=200)
        assert len(result) == 50


class TestLoadScannerFormat:
    def test_returns_flat_lists(self, tmp_cache):
        """Scanner format returns dict with flat lists."""
        candles = _make_candles(250)
        _write_cache(tmp_cache, "RELIANCE", candles)

        result = load_scanner_format("RELIANCE")
        assert "open" in result
        assert "high" in result
        assert "low" in result
        assert "close" in result
        assert "volume" in result
        # 250 candles available, lookback=270 returns all 250
        assert len(result["close"]) == 250

    def test_insufficient_data_returns_empty(self, tmp_cache):
        """Less than 200 candles returns empty dict."""
        candles = _make_candles(150)
        _write_cache(tmp_cache, "TINY", candles)

        result = load_scanner_format("TINY")
        assert result == {}

    def test_missing_symbol_returns_empty(self, tmp_cache):
        """Non-existent symbol returns empty dict."""
        result = load_scanner_format("GHOST")
        assert result == {}


class TestGetUniverseWithData:
    def test_returns_symbols_with_enough_data(self, tmp_cache):
        """Only symbols with >= min_candles are returned."""
        _write_cache(tmp_cache, "GOOD1", _make_candles(250))
        _write_cache(tmp_cache, "GOOD2", _make_candles(220))
        _write_cache(tmp_cache, "BAD", _make_candles(100))

        result = get_universe_with_data(min_candles=200)
        assert "GOOD1" in result
        assert "GOOD2" in result
        assert "BAD" not in result

    def test_empty_cache_returns_empty(self, tmp_cache):
        """Empty cache directory returns empty list."""
        result = get_universe_with_data()
        assert result == []


class TestIsDataFresh:
    def test_fresh_file(self, tmp_cache):
        """Recently written file is fresh."""
        _write_cache(tmp_cache, "FRESH", _make_candles(10))
        assert is_data_fresh("FRESH", max_age_hours=24) is True

    def test_stale_file(self, tmp_cache):
        """Old file is not fresh."""
        _write_cache(tmp_cache, "STALE", _make_candles(10))
        # Backdate the file modification time by 48 hours
        cache_file = tmp_cache / "STALE.json"
        old_time = time.time() - (48 * 3600)
        os.utime(cache_file, (old_time, old_time))

        assert is_data_fresh("STALE", max_age_hours=24) is False

    def test_missing_file_not_fresh(self, tmp_cache):
        """Non-existent file is not fresh."""
        assert is_data_fresh("MISSING", max_age_hours=24) is False
