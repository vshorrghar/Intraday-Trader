"""Property-based tests for configuration loading.

**Validates: Requirements 24.1, 24.2, 24.3, 24.4**

Tests Property 29 (Configuration loading completeness) and
Property 30 (Configuration missing key error) from the design document.
"""

import os
import tempfile

import yaml
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from config.config_loader import load_config, AppConfig, _REQUIRED_KEYS


# ── Strategies ───────────────────────────────────────────────────────

_non_empty_str = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

_positive_float = st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False)


@st.composite
def valid_config_dict(draw):
    """Generate a complete, valid YAML config dictionary with all required keys."""
    return {
        "aws": {
            "region": draw(_non_empty_str),
            "s3_bucket": draw(_non_empty_str),
            "ses_sender": draw(_non_empty_str),
            "ses_recipient": draw(_non_empty_str),
            "bedrock_model_id": draw(_non_empty_str),
            "bedrock_region": draw(_non_empty_str),
        },
        "portfolio": {
            "stocks_xlsx": draw(_non_empty_str),
            "mf_xlsx": draw(_non_empty_str),
            "pnl_xlsx": draw(_non_empty_str),
            "invit_isins": [draw(_non_empty_str)],
        },
        "investor": {
            "name": draw(_non_empty_str),
        },
        "schedule": {
            "morning_brief": draw(_non_empty_str),
            "midday_snapshot": draw(_non_empty_str),
            "eod_report": draw(_non_empty_str),
            "midday_threshold_pct": draw(_positive_float),
        },
        "database": {
            "path": draw(_non_empty_str),
        },
        "cache": {
            "dir": draw(_non_empty_str),
        },
        "dashboard": {
            "output_dir": draw(_non_empty_str),
        },
    }


def _write_yaml_to_tmpfile(data: dict) -> str:
    """Write a dict as YAML to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f)
    return path


# ── Property 29: Configuration loading completeness ──────────────────
# **Validates: Requirements 24.1, 24.2, 24.3**


@given(config_data=valid_config_dict())
@settings(max_examples=50, deadline=None)
def test_property_29_config_loading_completeness(config_data):
    """For any valid YAML configuration file containing all required keys,
    loading should produce an AppConfig with all fields populated and non-empty.

    **Validates: Requirements 24.1, 24.2, 24.3**
    """
    path = _write_yaml_to_tmpfile(config_data)
    try:
        cfg = load_config(path)

        # Must return an AppConfig instance
        assert isinstance(cfg, AppConfig)

        # All string fields must be non-empty
        assert cfg.aws_region
        assert cfg.s3_bucket
        assert cfg.ses_sender
        assert cfg.ses_recipient
        assert cfg.bedrock_model_id
        assert cfg.bedrock_region
        assert cfg.stocks_xlsx
        assert cfg.mf_xlsx
        assert cfg.pnl_xlsx
        assert cfg.db_path
        assert cfg.cache_dir
        assert cfg.dashboard_output_dir
        assert cfg.investor_name
        assert cfg.schedule_morning
        assert cfg.schedule_midday
        assert cfg.schedule_eod

        # Numeric field must be populated
        assert cfg.midday_threshold_pct > 0

        # List field must exist (may be empty or populated)
        assert isinstance(cfg.invit_isins, list)
    finally:
        os.unlink(path)


# ── Property 30: Configuration missing key error ─────────────────────
# **Validates: Requirements 24.4**

# Strategy: pick one required key path to remove
_required_key_index = st.integers(min_value=0, max_value=len(_REQUIRED_KEYS) - 1)


@given(config_data=valid_config_dict(), key_idx=_required_key_index)
@settings(max_examples=50, deadline=None)
def test_property_30_config_missing_key_error(config_data, key_idx):
    """For any YAML configuration file missing at least one required key,
    load_config should raise a ValueError whose message contains the name
    of the missing key.

    **Validates: Requirements 24.4**
    """
    key_path = _REQUIRED_KEYS[key_idx]

    # Remove the chosen required key from the config dict
    current = config_data
    for part in key_path[:-1]:
        current = current[part]
    removed_key = key_path[-1]
    del current[removed_key]

    path = _write_yaml_to_tmpfile(config_data)
    try:
        with pytest.raises(ValueError) as exc_info:
            load_config(path)

        # The error message must contain the dotted key name
        dotted = ".".join(key_path)
        assert dotted in str(exc_info.value), (
            f"Expected '{dotted}' in error message, got: {exc_info.value}"
        )
    finally:
        os.unlink(path)
