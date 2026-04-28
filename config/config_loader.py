"""Configuration loader for Wealth Builder Pro.

Reads a YAML configuration file and produces a validated AppConfig dataclass.
Raises ValueError at startup if any required key is missing.
"""

from dataclasses import dataclass, field
from typing import Any
import logging

import yaml

from intraday.models import IntraConfig

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Intraday config validation rules
# ---------------------------------------------------------------------------

# Each entry: (key, validator_fn) — returns True if the value is valid.
_INTRA_VALIDATORS: dict[str, Any] = {
    "daily_capital_limit": lambda v: isinstance(v, (int, float)) and v > 0,
    "per_trade_max_capital": lambda v: isinstance(v, (int, float)) and v > 0,
    "max_trades_per_day": lambda v: isinstance(v, int) and v > 0,
    "price_range_min": lambda v: isinstance(v, (int, float)) and v > 0,
    "monitor_interval_seconds": lambda v: isinstance(v, int) and v > 0,
    "min_confidence_score": lambda v: isinstance(v, int) and 1 <= v <= 10,
    "vix_threshold": lambda v: isinstance(v, (int, float)) and v > 0,
    "target_profit_per_day": lambda v: isinstance(v, (int, float)) and v > 0,
    "trailing_sl_trigger_pct": lambda v: isinstance(v, (int, float)) and 0 < v <= 10,
    "partial_book_pct": lambda v: isinstance(v, (int, float)) and 0 < v <= 100,
    "daily_loss_limit": lambda v: isinstance(v, (int, float)) and v > 0,
    "broker": lambda v: isinstance(v, str) and v in ("dhan", "zerodha"),
}

# Broker-specific required keys
_BROKER_REQUIRED_KEYS: dict[str, list[str]] = {
    "dhan": ["client_id", "api_key", "api_secret"],
    "zerodha": ["api_key", "api_secret", "user_id"],
}


def load_intraday_config(config_path: str) -> IntraConfig:
    """Load and validate the ``intraday`` section of *config_path*.

    * When the ``intraday`` section is missing entirely, all defaults from
      :class:`IntraConfig` are used and a warning is logged.
    * Individual keys that are missing or have out-of-range values are
      replaced with their defaults and an error is logged.
    * ``price_range_max`` is validated to be greater than ``price_range_min``.
    * The selected broker's config section must exist with all required keys;
      a :class:`ValueError` is raised otherwise.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        A validated :class:`IntraConfig` instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the selected broker's config section is missing or
            incomplete.
    """
    with open(config_path, "r") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Configuration file must contain a YAML mapping")

    intra_data: dict[str, Any] = data.get("intraday", None)

    if intra_data is None:
        logger.warning(
            "No 'intraday' section found in %s — using all defaults", config_path
        )
        intra_data = {}

    defaults = IntraConfig()
    resolved: dict[str, Any] = {}

    # --- validate each key against its rule, falling back to default --------
    for key in IntraConfig.__dataclass_fields__:
        default_val = getattr(defaults, key)

        if key not in intra_data:
            resolved[key] = default_val
            continue

        raw = intra_data[key]

        # Use the per-key validator if one exists
        validator = _INTRA_VALIDATORS.get(key)
        if validator is not None:
            if not validator(raw):
                logger.error(
                    "Invalid intraday config value %s=%r — using default %r",
                    key,
                    raw,
                    default_val,
                )
                resolved[key] = default_val
                continue

        resolved[key] = raw

    # --- cross-field validation: price_range_max > price_range_min ----------
    prmin = resolved["price_range_min"]
    prmax = resolved.get("price_range_max", getattr(defaults, "price_range_max"))

    # Validate price_range_max itself (must be positive number)
    raw_prmax = intra_data.get("price_range_max", getattr(defaults, "price_range_max"))
    if not (isinstance(raw_prmax, (int, float)) and raw_prmax > 0):
        logger.error(
            "Invalid intraday config value price_range_max=%r — using default %r",
            raw_prmax,
            getattr(defaults, "price_range_max"),
        )
        resolved["price_range_max"] = getattr(defaults, "price_range_max")
    else:
        resolved["price_range_max"] = raw_prmax

    if resolved["price_range_max"] <= prmin:
        logger.error(
            "Invalid intraday config: price_range_max (%r) must be > price_range_min (%r) — using defaults",
            resolved["price_range_max"],
            prmin,
        )
        resolved["price_range_min"] = getattr(defaults, "price_range_min")
        resolved["price_range_max"] = getattr(defaults, "price_range_max")

    # --- broker config validation -------------------------------------------
    broker = resolved["broker"]
    required_keys = _BROKER_REQUIRED_KEYS.get(broker, [])
    broker_section = data.get(broker, None)

    if broker_section is None or not isinstance(broker_section, dict):
        raise ValueError(
            f"Broker '{broker}' selected but no '{broker}' config section found in "
            f"{config_path}. Required keys: {', '.join(required_keys)}"
        )

    missing = [k for k in required_keys if k not in broker_section]
    if missing:
        raise ValueError(
            f"Broker '{broker}' config section is missing required keys: "
            f"{', '.join(missing)}. Please add them to the '{broker}' section in "
            f"{config_path}"
        )

    return IntraConfig(**resolved)
