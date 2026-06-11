"""Tests for V3 regime detector (merged: relaxed thresholds + full API)."""
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.regime import classify_regime, detect_regime, VOLATILE, TRENDING_UP, TRENDING_DOWN, RANGING, UNCLEAR


class TestClassifyRegime:
    def test_volatile_when_vix_high(self):
        # VIX > 25 (relaxed from 22)
        result = classify_regime(
            nifty_change_pct=0.5, nifty_30min_range_pct=0.8,
            breadth_pct=55, vix=26.0
        )
        assert result["regime"] == VOLATILE

    def test_volatile_when_range_high_no_longer_triggers(self):
        # Range check REMOVED (Option C fix 2026-05-30)
        # High range alone does NOT trigger VOLATILE anymore — only VIX > 25 does
        result = classify_regime(
            nifty_change_pct=0.2, nifty_30min_range_pct=1.5,
            breadth_pct=50, vix=16
        )
        # With VIX=16 and change=0.2, breadth=50 → RANGING (not VOLATILE)
        assert result["regime"] == RANGING

    def test_trending_up_clear_signal(self):
        # nifty > +0.25% (relaxed from +0.4%) AND breadth > 60%
        result = classify_regime(
            nifty_change_pct=0.3, nifty_30min_range_pct=0.5,
            breadth_pct=68, vix=15
        )
        assert result["regime"] == TRENDING_UP

    def test_trending_down(self):
        # nifty < -0.25% (relaxed from -0.4%) AND breadth < 40%
        result = classify_regime(
            nifty_change_pct=-0.3, nifty_30min_range_pct=0.8,
            breadth_pct=32, vix=19
        )
        assert result["regime"] == TRENDING_DOWN

    def test_ranging_when_flat(self):
        # |nifty| < 0.4% (relaxed from 0.3%) AND breadth 40-60% AND vix < 18
        result = classify_regime(
            nifty_change_pct=0.1, nifty_30min_range_pct=0.4,
            breadth_pct=52, vix=15
        )
        assert result["regime"] == RANGING

    def test_unclear_when_mixed(self):
        # Nifty up but breadth low — mixed signal
        result = classify_regime(
            nifty_change_pct=0.5, nifty_30min_range_pct=0.6,
            breadth_pct=45, vix=19
        )
        assert result["regime"] == UNCLEAR

    def test_unclear_when_flat_but_vix_high(self):
        # Would be RANGING but VIX too high (>18 for RANGING gate)
        result = classify_regime(
            nifty_change_pct=0.1, nifty_30min_range_pct=0.4,
            breadth_pct=50, vix=19
        )
        assert result["regime"] == UNCLEAR


class TestDetectRegimeLock:
    def test_locks_after_first_call_same_day(self, tmp_path):
        with patch("intraday.v3.regime.LOGS_DIR", tmp_path):
            # First call computes — nifty +0.3% with breadth 68% = TRENDING_UP
            r1 = detect_regime(0.3, 0.5, 68, 15, date="2026-05-27", force=False)
            assert r1["regime"] == TRENDING_UP

            # Second call returns cached (even with different inputs)
            r2 = detect_regime(-0.8, 1.5, 30, 26, date="2026-05-27", force=False)
            assert r2["regime"] == TRENDING_UP  # Still cached

    def test_force_recomputes(self, tmp_path):
        with patch("intraday.v3.regime.LOGS_DIR", tmp_path):
            r1 = detect_regime(0.3, 0.5, 68, 15, date="2026-05-27", force=False)
            assert r1["regime"] == TRENDING_UP

            # Force recompute with bearish inputs
            r2 = detect_regime(-0.5, 0.5, 30, 19, date="2026-05-27", force=True)
            assert r2["regime"] == TRENDING_DOWN
