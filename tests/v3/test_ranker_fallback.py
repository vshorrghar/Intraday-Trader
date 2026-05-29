"""Tests for V3 Claude ranker and V1 fallback."""
import json
import sqlite3
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from intraday.v3.ranker_claude import rank_top_3, _format_candidates_table
from intraday.v3.fallback_v1 import trigger_v1_fallback


def _mock_candidates():
    return [
        {"symbol": "RELIANCE", "score": 18, "sector": "Oil Gas", "mcap_bucket": "LARGE",
         "entry_price": 1350, "stop_loss": 1330, "target": 1390},
        {"symbol": "TCS", "score": 15, "sector": "IT", "mcap_bucket": "LARGE",
         "entry_price": 2300, "stop_loss": 2270, "target": 2360},
        {"symbol": "HDFCBANK", "score": 14, "sector": "Financial", "mcap_bucket": "LARGE",
         "entry_price": 770, "stop_loss": 755, "target": 800},
        {"symbol": "HINDALCO", "score": 12, "sector": "Metals", "mcap_bucket": "LARGE",
         "entry_price": 1100, "stop_loss": 1080, "target": 1140},
    ]


def _mock_bedrock_response():
    return {
        "content": json.dumps({
            "picks": [
                {"symbol": "RELIANCE", "rank": 1, "reasoning": "Best R:R with sector leadership"},
                {"symbol": "HINDALCO", "rank": 2, "reasoning": "Metals momentum, diversified from #1"},
                {"symbol": "TCS", "rank": 3, "reasoning": "IT sector strength"},
            ],
            "skip_reason": None,
        })
    }


class TestRankerClaude:
    def test_ranker_calls_bedrock_with_regime_context(self):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke.return_value = _mock_bedrock_response()

        candidates = _mock_candidates()
        result = rank_top_3(candidates, "TRENDING_UP", mock_bedrock)

        # Verify bedrock was called
        mock_bedrock.invoke.assert_called_once()
        call_args = mock_bedrock.invoke.call_args
        system_prompt = call_args[0][0]
        user_prompt = call_args[0][1]

        # Regime should be in prompts
        assert "TRENDING_UP" in system_prompt or "TRENDING_UP" in user_prompt

    def test_ranker_returns_top_3(self):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke.return_value = _mock_bedrock_response()

        candidates = _mock_candidates()
        result = rank_top_3(candidates, "TRENDING_UP", mock_bedrock)

        assert len(result) == 3
        assert result[0]["symbol"] == "RELIANCE"
        assert result[1]["symbol"] == "HINDALCO"
        assert result[2]["symbol"] == "TCS"
        assert result[0].get("claude_rank") == 1

    def test_ranker_handles_empty_candidates(self):
        mock_bedrock = MagicMock()
        result = rank_top_3([], "TRENDING_UP", mock_bedrock)
        assert result == []
        mock_bedrock.invoke.assert_not_called()

    def test_ranker_handles_skip_response(self):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke.return_value = {
            "content": json.dumps({"picks": [], "skip_reason": "No good setups"})
        }
        result = rank_top_3(_mock_candidates(), "TRENDING_UP", mock_bedrock)
        assert result == []


class TestFallbackV1:
    @pytest.fixture
    def db_path(self, tmp_path):
        path = str(tmp_path / "test.db")
        conn = sqlite3.connect(path)
        conn.execute("""
            CREATE TABLE intraday_trades (
                id INTEGER PRIMARY KEY, trade_date TEXT, symbol TEXT,
                pnl REAL, status TEXT DEFAULT 'CLOSED'
            )
        """)
        conn.commit()
        conn.close()
        return path

    def test_fallback_only_fires_in_trending_up(self, db_path):
        mock_bedrock = MagicMock()
        for regime in ["RANGING", "TRENDING_DOWN", "VOLATILE", "UNCLEAR"]:
            result = trigger_v1_fallback(
                _mock_candidates(), regime, mock_bedrock, db_path, today="2026-05-27"
            )
            assert result == [], f"Should not fire in {regime}"
        mock_bedrock.invoke.assert_not_called()

    def test_fallback_does_not_fire_in_ranging(self, db_path):
        mock_bedrock = MagicMock()
        result = trigger_v1_fallback(
            _mock_candidates(), "RANGING", mock_bedrock, db_path, today="2026-05-27"
        )
        assert result == []

    def test_fallback_max_1_per_day(self, db_path):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke.return_value = _mock_bedrock_response()

        # First call should fire
        r1 = trigger_v1_fallback(
            _mock_candidates(), "TRENDING_UP", mock_bedrock, db_path, today="2026-05-27"
        )
        assert len(r1) == 1  # Returns max 1 trade

        # Second call same day should NOT fire
        r2 = trigger_v1_fallback(
            _mock_candidates(), "TRENDING_UP", mock_bedrock, db_path, today="2026-05-27"
        )
        assert r2 == []

    def test_fallback_skipped_if_v2_already_traded(self, db_path):
        # Insert a trade for today
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO intraday_trades (trade_date, symbol, pnl, status) VALUES (?, ?, ?, ?)",
            ("2026-05-27", "BHEL", 100.0, "CLOSED")
        )
        conn.commit()
        conn.close()

        mock_bedrock = MagicMock()
        result = trigger_v1_fallback(
            _mock_candidates(), "TRENDING_UP", mock_bedrock, db_path, today="2026-05-27"
        )
        assert result == []
        mock_bedrock.invoke.assert_not_called()
