"""Configuration loader for Wealth Builder Pro.

Reads a YAML configuration file and produces a validated AppConfig dataclass.
Raises ValueError at startup if any required key is missing.
"""

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class AlertsConfig:
    """Configuration for portfolio alert thresholds."""

    pnl_drop_pct: float = 5.0
    pnl_spike_pct: float = 10.0
    volume_spike_multiplier: float = 3.0


@dataclass
class AnalysisConfig:
    """Configuration for AI analysis parameters."""

    max_intraday_setups: int = 5
    tax_harvest_short_term_months_stocks: int = 12
    tax_harvest_short_term_months_debt_mf: int = 36


@dataclass
class AppConfig:
    """Application configuration for Wealth Builder Pro."""

    # AWS settings
    aws_region: str
    s3_bucket: str
    ses_sender: str
    ses_recipient: str
    bedrock_model_id: str
    bedrock_region: str

    # Portfolio file paths
    stocks_xlsx: str
    mf_xlsx: str
    pnl_xlsx: str
    invit_isins: list[str]

    # Storage paths
    db_path: str
    cache_dir: str
    dashboard_output_dir: str

    # User info
    investor_name: str

    # Schedule (UTC times for cron)
    schedule_morning: str
    schedule_midday: str
    schedule_eod: str

    # Thresholds
    midday_threshold_pct: float

    # Nested configs
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)


# Keys that must be present in the YAML config, expressed as dot-separated paths.
_REQUIRED_KEYS: list[tuple[str, ...]] = [
    ("aws", "region"),
    ("aws", "s3_bucket"),
    ("aws", "ses_sender"),
    ("aws", "ses_recipient"),
    ("aws", "bedrock_model_id"),
    ("aws", "bedrock_region"),
    ("portfolio", "stocks_xlsx"),
    ("portfolio", "mf_xlsx"),
    ("portfolio", "pnl_xlsx"),
    ("database", "path"),
    ("cache", "dir"),
    ("dashboard", "output_dir"),
    ("investor", "name"),
    ("schedule", "morning_brief"),
    ("schedule", "midday_snapshot"),
    ("schedule", "eod_report"),
    ("schedule", "midday_threshold_pct"),
]


def _get_nested(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Traverse nested dict by key path. Returns None if any key is missing."""
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _validate_required_keys(data: dict[str, Any]) -> None:
    """Raise ValueError naming the first missing required key."""
    for key_path in _REQUIRED_KEYS:
        value = _get_nested(data, key_path)
        if value is None:
            dotted = ".".join(key_path)
            raise ValueError(f"Missing required configuration key: {dotted}")


def load_config(config_path: str) -> AppConfig:
    """Load and validate YAML config file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A fully populated AppConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If a required configuration key is missing.
    """
    with open(config_path, "r") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Configuration file must contain a YAML mapping")

    _validate_required_keys(data)

    aws = data["aws"]
    portfolio = data["portfolio"]
    schedule = data["schedule"]
    database = data["database"]
    cache = data["cache"]
    dashboard = data["dashboard"]
    investor = data["investor"]

    # Build nested configs from optional sections, falling back to defaults.
    alerts_data = data.get("alerts", {})
    alerts = AlertsConfig(
        pnl_drop_pct=float(alerts_data.get("pnl_drop_pct", 5.0)),
        pnl_spike_pct=float(alerts_data.get("pnl_spike_pct", 10.0)),
        volume_spike_multiplier=float(alerts_data.get("volume_spike_multiplier", 3.0)),
    )

    analysis_data = data.get("analysis", {})
    analysis = AnalysisConfig(
        max_intraday_setups=int(analysis_data.get("max_intraday_setups", 5)),
        tax_harvest_short_term_months_stocks=int(
            analysis_data.get("tax_harvest_short_term_months_stocks", 12)
        ),
        tax_harvest_short_term_months_debt_mf=int(
            analysis_data.get("tax_harvest_short_term_months_debt_mf", 36)
        ),
    )

    return AppConfig(
        aws_region=str(aws["region"]),
        s3_bucket=str(aws["s3_bucket"]),
        ses_sender=str(aws["ses_sender"]),
        ses_recipient=str(aws["ses_recipient"]),
        bedrock_model_id=str(aws["bedrock_model_id"]),
        bedrock_region=str(aws["bedrock_region"]),
        stocks_xlsx=str(portfolio["stocks_xlsx"]),
        mf_xlsx=str(portfolio["mf_xlsx"]),
        pnl_xlsx=str(portfolio["pnl_xlsx"]),
        invit_isins=list(portfolio.get("invit_isins", [])),
        db_path=str(database["path"]),
        cache_dir=str(cache["dir"]),
        dashboard_output_dir=str(dashboard["output_dir"]),
        investor_name=str(investor["name"]),
        schedule_morning=str(schedule["morning_brief"]),
        schedule_midday=str(schedule["midday_snapshot"]),
        schedule_eod=str(schedule["eod_report"]),
        midday_threshold_pct=float(schedule["midday_threshold_pct"]),
        alerts=alerts,
        analysis=analysis,
    )
