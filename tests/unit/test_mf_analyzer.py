"""Unit tests for the MF Analyzer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fetchers.models import NAVRecord
from llm.mf_analyzer import analyze_mutual_funds
from llm.models import MFRecommendation
from parsers.models import MFHolding


def _make_mf_holding(scheme_name="Axis Bluechip Fund", scheme_code="120503") -> MFHolding:
    return MFHolding(
        scheme_name=scheme_name, amc="Axis", category="Equity",
        sub_category="Large Cap", folio_no="1234567890", source="SIP",
        units=100.0, invested_value=50000.0, current_value=55000.0,
        returns_absolute=5000.0, xirr=12.5, returns_percent=10.0,
        current_nav=None, scheme_code=scheme_code,
    )


def _make_nav_data() -> dict[str, NAVRecord]:
    return {
        "120503": NAVRecord("120503", "Axis Bluechip Fund", 55.0, "2025-01-15"),
    }


def _make_client_returning(items: list[dict]) -> MagicMock:
    client = MagicMock()
    client.invoke.return_value = {"items": items}
    return client


class TestAnalyzeMutualFunds:
    """Tests for analyze_mutual_funds."""

    def test_continue_recommendation(self):
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "continue",
            "alternative_scheme": None,
            "rationale": "Consistent top-quartile performance",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)

        assert len(result) == 1
        assert isinstance(result[0], MFRecommendation)
        assert result[0].recommendation == "continue"
        assert result[0].alternative_scheme is None

    def test_switch_recommendation_with_alternative(self):
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "switch",
            "alternative_scheme": "Mirae Asset Large Cap Fund",
            "rationale": "Underperforming category average",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)

        assert len(result) == 1
        assert result[0].recommendation == "switch"
        assert result[0].alternative_scheme == "Mirae Asset Large Cap Fund"

    def test_switch_without_alternative_skipped(self):
        """Switch recommendation without alternative_scheme should be skipped."""
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "switch",
            "alternative_scheme": None,
            "rationale": "Underperforming",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)
        assert result == []

    def test_stop_recommendation(self):
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "stop",
            "alternative_scheme": None,
            "rationale": "Persistent underperformance",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)

        assert len(result) == 1
        assert result[0].recommendation == "stop"
        assert result[0].alternative_scheme is None

    def test_continue_strips_alternative_scheme(self):
        """For continue/stop, alternative_scheme should be forced to None."""
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "continue",
            "alternative_scheme": "Some Other Fund",
            "rationale": "Good fund",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)
        assert len(result) == 1
        assert result[0].alternative_scheme is None

    def test_empty_holdings_returns_empty(self):
        client = MagicMock()
        result = analyze_mutual_funds([], _make_nav_data(), client)
        assert result == []
        client.invoke.assert_not_called()

    def test_bedrock_failure_returns_empty(self):
        client = MagicMock()
        client.invoke.side_effect = RuntimeError("API down")

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)
        assert result == []

    def test_empty_response_returns_empty(self):
        client = MagicMock()
        client.invoke.return_value = {}

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)
        assert result == []

    def test_invalid_recommendation_skipped(self):
        client = _make_client_returning([{
            "scheme_name": "Axis Bluechip Fund",
            "recommendation": "upgrade",
            "alternative_scheme": None,
            "rationale": "Invalid rec",
        }])

        result = analyze_mutual_funds([_make_mf_holding()], _make_nav_data(), client)
        assert result == []
