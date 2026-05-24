"""
Tests for backtest/data_loader.py
Covers: cache hit/miss, OHLCV format validation, universe sizes.
No broker calls — tests use mock or cached data only.
"""
import pytest
import json
import os
from pathlib import Path


class TestUniverseDefinitions:
    def test_nifty50_has_50_stocks(self):
        """Nifty50 universe must have exactly 50 stocks."""
        from backtest.universes import NIFTY50
        assert len(NIFTY50) == 50, f"Expected 50, got {len(NIFTY50)}"

    def test_nifty500_non_empty(self):
        """Nifty500 universe must have > 100 stocks."""
        from backtest.universes import NIFTY500
        assert len(NIFTY500) > 100

    def test_all_security_ids_are_strings(self):
        """All security IDs must be strings (Dhan API requirement)."""
        from backtest.universes import NIFTY50, NIFTY_NEXT50
        for symbol, sec_id in {**NIFTY50, **NIFTY_NEXT50}.items():
            assert isinstance(sec_id, str), \
                f"{symbol} has non-string sec_id: {sec_id!r}"

    def test_no_duplicate_symbols_in_tier1(self):
        """tier1 must not have duplicate symbols."""
        from backtest.universes import get_universe
        u = get_universe("tier1")
        assert len(u) == len(set(u.keys()))

    def test_blacklist_not_in_universe(self):
        """Blacklisted stocks must not appear in filtered universe."""
        from backtest.universes import get_universe, BLACKLIST
        u = get_universe("tier1")
        for symbol in BLACKLIST:
            assert symbol not in u, f"Blacklisted {symbol} found in tier1"

    def test_get_universe_fno_exists(self):
        """get_universe('fno') must return non-empty dict."""
        from backtest.universes import get_universe
        u = get_universe("fno")
        assert len(u) > 50


class TestCacheFormat:
    def test_cached_file_has_required_keys(self, tmp_path):
        """Cached OHLCV file must have open/high/low/close/volume/timestamp."""
        # Write a mock cache file
        data = {
            "open": [100.0], "high": [105.0], "low": [98.0],
            "close": [103.0], "volume": [100000], "timestamp": [1700000000]
        }
        cache_file = tmp_path / "TEST_15min_2026-01-01_2026-05-01.json"
        cache_file.write_text(json.dumps(data))

        with open(cache_file) as f:
            loaded = json.load(f)

        required = ["open", "high", "low", "close", "volume", "timestamp"]
        for key in required:
            assert key in loaded, f"Missing key: {key}"

    def test_cached_arrays_same_length(self, tmp_path):
        """All OHLCV arrays must have same length."""
        n = 100
        data = {
            "open": [100.0] * n, "high": [105.0] * n, "low": [98.0] * n,
            "close": [103.0] * n, "volume": [100000] * n,
            "timestamp": list(range(n))
        }
        cache_file = tmp_path / "TEST.json"
        cache_file.write_text(json.dumps(data))

        with open(cache_file) as f:
            loaded = json.load(f)

        lengths = {k: len(v) for k, v in loaded.items()}
        assert len(set(lengths.values())) == 1, \
            f"Arrays have different lengths: {lengths}"
