"""Unit tests for configuration loader.

Tests loading valid config, missing keys, invalid types, and malformed YAML.

Validates: Requirements 24.1, 24.4
"""

import os
import tempfile

import yaml
import pytest

from config.config_loader import load_config, AppConfig


def _write_yaml(data, suffix=".yaml"):
    """Write data as YAML to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        yaml.dump(data, f)
    return path


def _write_raw(content: str, suffix=".yaml"):
    """Write raw string content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


def _valid_config():
    """Return a minimal valid config dictionary."""
    return {
        "aws": {
            "region": "ap-south-1",
            "s3_bucket": "my-bucket",
            "ses_sender": "sender@example.com",
            "ses_recipient": "recipient@example.com",
            "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "bedrock_region": "ap-south-1",
        },
        "portfolio": {
            "stocks_xlsx": "input/stocks.xlsx",
            "mf_xlsx": "input/mf.xlsx",
            "pnl_xlsx": "input/pnl.xlsx",
            "invit_isins": ["INE183W23014"],
        },
        "investor": {"name": "TestUser"},
        "schedule": {
            "morning_brief": "03:15",
            "midday_snapshot": "07:00",
            "eod_report": "10:45",
            "midday_threshold_pct": 2.0,
        },
        "database": {"path": "database/portfolio.db"},
        "cache": {"dir": "cache"},
        "dashboard": {"output_dir": "dashboard"},
    }


# ── Valid config loading ─────────────────────────────────────────────


class TestLoadValidConfig:
    """Validates: Requirements 24.1"""

    def test_returns_app_config_instance(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert isinstance(cfg, AppConfig)
        finally:
            os.unlink(path)

    def test_aws_fields_populated(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.aws_region == "ap-south-1"
            assert cfg.s3_bucket == "my-bucket"
            assert cfg.ses_sender == "sender@example.com"
            assert cfg.ses_recipient == "recipient@example.com"
            assert cfg.bedrock_model_id == "anthropic.claude-3-sonnet-20240229-v1:0"
            assert cfg.bedrock_region == "ap-south-1"
        finally:
            os.unlink(path)

    def test_portfolio_fields_populated(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.stocks_xlsx == "input/stocks.xlsx"
            assert cfg.mf_xlsx == "input/mf.xlsx"
            assert cfg.pnl_xlsx == "input/pnl.xlsx"
            assert cfg.invit_isins == ["INE183W23014"]
        finally:
            os.unlink(path)

    def test_schedule_and_storage_fields(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.schedule_morning == "03:15"
            assert cfg.schedule_midday == "07:00"
            assert cfg.schedule_eod == "10:45"
            assert cfg.midday_threshold_pct == 2.0
            assert cfg.db_path == "database/portfolio.db"
            assert cfg.cache_dir == "cache"
            assert cfg.dashboard_output_dir == "dashboard"
            assert cfg.investor_name == "TestUser"
        finally:
            os.unlink(path)

    def test_optional_alerts_defaults(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.alerts.pnl_drop_pct == 5.0
            assert cfg.alerts.pnl_spike_pct == 10.0
            assert cfg.alerts.volume_spike_multiplier == 3.0
        finally:
            os.unlink(path)

    def test_optional_analysis_defaults(self, tmp_path):
        path = _write_yaml(_valid_config())
        try:
            cfg = load_config(path)
            assert cfg.analysis.max_intraday_setups == 5
            assert cfg.analysis.tax_harvest_short_term_months_stocks == 12
            assert cfg.analysis.tax_harvest_short_term_months_debt_mf == 36
        finally:
            os.unlink(path)

    def test_custom_alerts_override(self, tmp_path):
        data = _valid_config()
        data["alerts"] = {
            "pnl_drop_pct": 8.0,
            "pnl_spike_pct": 15.0,
            "volume_spike_multiplier": 5.0,
        }
        path = _write_yaml(data)
        try:
            cfg = load_config(path)
            assert cfg.alerts.pnl_drop_pct == 8.0
            assert cfg.alerts.pnl_spike_pct == 15.0
            assert cfg.alerts.volume_spike_multiplier == 5.0
        finally:
            os.unlink(path)

    def test_empty_invit_isins_list(self, tmp_path):
        data = _valid_config()
        data["portfolio"]["invit_isins"] = []
        path = _write_yaml(data)
        try:
            cfg = load_config(path)
            assert cfg.invit_isins == []
        finally:
            os.unlink(path)


# ── Missing required keys ────────────────────────────────────────────


class TestMissingRequiredKeys:
    """Validates: Requirements 24.4"""

    def test_missing_aws_region(self):
        data = _valid_config()
        del data["aws"]["region"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="aws.region"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_s3_bucket(self):
        data = _valid_config()
        del data["aws"]["s3_bucket"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="aws.s3_bucket"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_ses_sender(self):
        data = _valid_config()
        del data["aws"]["ses_sender"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="aws.ses_sender"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_bedrock_model_id(self):
        data = _valid_config()
        del data["aws"]["bedrock_model_id"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="aws.bedrock_model_id"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_stocks_xlsx(self):
        data = _valid_config()
        del data["portfolio"]["stocks_xlsx"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="portfolio.stocks_xlsx"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_database_path(self):
        data = _valid_config()
        del data["database"]["path"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="database.path"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_entire_aws_section(self):
        data = _valid_config()
        del data["aws"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="aws.region"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_schedule_morning_brief(self):
        data = _valid_config()
        del data["schedule"]["morning_brief"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="schedule.morning_brief"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_missing_investor_name(self):
        data = _valid_config()
        del data["investor"]["name"]
        path = _write_yaml(data)
        try:
            with pytest.raises(ValueError, match="investor.name"):
                load_config(path)
        finally:
            os.unlink(path)


# ── Invalid types and malformed YAML ─────────────────────────────────


class TestInvalidTypesAndMalformedYAML:
    """Validates: Requirements 24.1, 24.4"""

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_yaml_with_plain_string_content(self):
        path = _write_raw("just a plain string, not a mapping")
        try:
            with pytest.raises(ValueError, match="YAML mapping"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_yaml_with_list_content(self):
        path = _write_raw("- item1\n- item2\n")
        try:
            with pytest.raises(ValueError, match="YAML mapping"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_empty_yaml_file(self):
        path = _write_raw("")
        try:
            with pytest.raises(ValueError, match="YAML mapping"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_loads_actual_config_yaml(self):
        """Smoke test: the real config/config.yaml should load without error."""
        cfg = load_config("config/config.yaml")
        assert isinstance(cfg, AppConfig)
        assert cfg.aws_region
