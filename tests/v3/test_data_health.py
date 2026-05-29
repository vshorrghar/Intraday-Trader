"""Tests for V3 data health gate and funnel logger."""
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.data_health import check_data_health
from intraday.v3.funnel_logger import FunnelLogger


class TestDataHealth:
    def test_healthy_when_80_pct_valid(self):
        candidates = [
            {"symbol": f"STOCK{i}", "open": 100.0, "volume": 1000000, "ltp": 101.0}
            for i in range(80)
        ] + [
            {"symbol": f"BAD{i}", "open": 0, "volume": 0, "ltp": 0}
            for i in range(20)
        ]
        result = check_data_health(candidates)
        assert result["healthy"] is True
        assert result["valid_count"] == 80
        assert result["total"] == 100
        assert result["valid_ratio"] == 0.8

    def test_unhealthy_when_below_80_pct(self):
        candidates = [
            {"symbol": f"STOCK{i}", "open": 100.0, "volume": 1000000, "ltp": 101.0}
            for i in range(50)
        ] + [
            {"symbol": f"BAD{i}", "open": 0, "volume": 0, "ltp": 0}
            for i in range(50)
        ]
        result = check_data_health(candidates)
        assert result["healthy"] is False
        assert result["valid_count"] == 50
        assert result["valid_ratio"] == 0.5

    def test_drop_reasons_enumerated_correctly(self):
        candidates = [
            {"symbol": "A", "open": 0, "volume": 1000, "ltp": 100},  # zero_open
            {"symbol": "B", "open": 100, "volume": 0, "ltp": 100},   # zero_volume
            {"symbol": "C", "open": 100, "volume": 1000, "ltp": 0},  # zero_ltp
            {"symbol": "D", "open": 100, "volume": 1000, "ltp": 100},  # valid
        ]
        result = check_data_health(candidates)
        assert result["drop_reasons"]["zero_open"] == 1
        assert result["drop_reasons"]["zero_volume"] == 1
        assert result["drop_reasons"]["zero_ltp"] == 1
        assert result["valid_count"] == 1

    def test_empty_candidates(self):
        result = check_data_health([])
        assert result["healthy"] is False
        assert result["total"] == 0


class TestFunnelLogger:
    def test_log_stage_records_correctly(self):
        funnel = FunnelLogger(date="2026-05-27", profile="test")
        funnel.log_stage("universe_loaded", 504)
        funnel.log_stage("data_available", 487, drop_reasons={"no_data": 17})
        assert len(funnel.stages) == 2
        assert funnel.stages[0]["passed"] == 504
        assert funnel.stages[1]["drop_reasons"]["no_data"] == 17

    def test_write_daily_json(self, tmp_path):
        with patch("intraday.v3.funnel_logger.LOGS_DIR", tmp_path):
            funnel = FunnelLogger(date="2026-05-27", profile="test")
            funnel.log_stage("universe_loaded", 504)
            funnel.set_regime("TRENDING_UP")
            path = funnel.write_daily_json()
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["regime"] == "TRENDING_UP"
            assert data["stages"]["universe_loaded"] == 504

    def test_summary_line(self):
        funnel = FunnelLogger(date="2026-05-27", profile="test")
        funnel.log_stage("universe_loaded", 504)
        funnel.set_regime("RANGING")
        line = funnel.get_summary_line()
        assert "RANGING" in line
        assert "504" in line
