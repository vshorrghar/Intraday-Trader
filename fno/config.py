"""F&O Auto-Trader configuration loader and validation.

Loads the ``fno`` section from ``config/config.yaml``, validates every key
against its documented range, and falls back to defaults for missing or
invalid values.  Exits with a clear error if the selected broker's config
section is missing.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FnO_Config:
    """Configuration for the F&O auto-trader.

    All monetary values are in INR.  All times are IST.
    """

    broker: str = "dhan"
    mode: str = "paper"                    # "paper" or "live"
    paper_capital: float = 500_000.0       # ₹5L virtual capital
    daily_capital_limit: float = 500_000.0
    per_trade_max_capital: float = 100_000.0
    max_positions: int = 3
    allowed_indices: list[str] = field(
        default_factory=lambda: ["NIFTY", "BANKNIFTY", "FINNIFTY"]
    )
    allowed_strategies: list[str] = field(
        default_factory=lambda: [
            "STRADDLE", "STRANGLE", "IRON_CONDOR",
            "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", "NAKED_CE", "NAKED_PE",
        ]
    )
    max_lots_per_trade: int = 1
    force_exit_time: str = "15:15"
    entry_delay_minutes: int = 10
    monitor_interval_seconds: int = 60
    daily_loss_limit: float = 5_000.0
    max_delta_exposure: float = 50.0
    max_vega_exposure: float = 500.0
    min_days_to_expiry: int = 1
    target_profit_per_day: float = 5_000.0
    trailing_sl_trigger_pct: float = 50.0  # % of premium collected
    partial_book_pct: float = 50.0
    min_confidence_score: int = 7
    vix_threshold: float = 20.0
    paper_trading_weeks: int = 3


# ── Per-key validators ────────────────────────────────────────────────────
# Each returns True when the raw value is acceptable.

_FNO_VALIDATORS: dict[str, Any] = {
    "broker": lambda v: isinstance(v, str) and v in ("dhan", "zerodha"),
    "mode": lambda v: isinstance(v, str) and v in ("paper", "live"),
    "paper_capital": lambda v: isinstance(v, (int, float)) and v > 0,
    "daily_capital_limit": lambda v: isinstance(v, (int, float)) and v > 0,
    "per_trade_max_capital": lambda v: isinstance(v, (int, float)) and v > 0,
    "max_positions": lambda v: isinstance(v, int) and v > 0,
    "allowed_indices": lambda v: isinstance(v, list) and len(v) > 0 and all(isinstance(i, str) for i in v),
    "allowed_strategies": lambda v: isinstance(v, list) and len(v) > 0 and all(isinstance(i, str) for i in v),
    "max_lots_per_trade": lambda v: isinstance(v, int) and v >= 1,
    "force_exit_time": lambda v: isinstance(v, str) and len(v) >= 4,
    "entry_delay_minutes": lambda v: isinstance(v, int) and v >= 0,
    "monitor_interval_seconds": lambda v: isinstance(v, int) and v > 0,
    "daily_loss_limit": lambda v: isinstance(v, (int, float)) and v > 0,
    "max_delta_exposure": lambda v: isinstance(v, (int, float)) and v > 0,
    "max_vega_exposure": lambda v: isinstance(v, (int, float)) and v > 0,
    "min_days_to_expiry": lambda v: isinstance(v, int) and v >= 0,
    "target_profit_per_day": lambda v: isinstance(v, (int, float)) and v > 0,
    "trailing_sl_trigger_pct": lambda v: isinstance(v, (int, float)) and 0 < v <= 100,
    "partial_book_pct": lambda v: isinstance(v, (int, float)) and 0 < v <= 100,
    "min_confidence_score": lambda v: isinstance(v, int) and 1 <= v <= 10,
    "vix_threshold": lambda v: isinstance(v, (int, float)) and v > 0,
    "paper_trading_weeks": lambda v: isinstance(v, int) and v >= 0,
}

# Broker-specific required keys
_BROKER_REQUIRED_KEYS: dict[str, list[str]] = {
    "dhan": ["client_id", "api_key", "api_secret"],
    "zerodha": ["api_key", "api_secret", "user_id"],
}


def load_fno_config(yaml_dict: dict[str, Any]) -> FnO_Config:
    """Load and validate the ``fno`` section from a parsed YAML dict.

    Parameters
    ----------
    yaml_dict:
        The full parsed YAML dict (top-level keys include ``fno``, ``dhan``,
        ``zerodha``, etc.).

    Returns
    -------
    FnO_Config
        A validated configuration instance.

    Raises
    ------
    SystemExit
        If the selected broker's config section is missing or incomplete.
    """
    fno_data: dict[str, Any] | None = yaml_dict.get("fno")

    if fno_data is None:
        logger.warning(
            "No 'fno' section found in config — using all defaults"
        )
        fno_data = {}

    defaults = FnO_Config()
    resolved: dict[str, Any] = {}

    for key in FnO_Config.__dataclass_fields__:
        default_val = getattr(defaults, key)

        if key not in fno_data:
            resolved[key] = default_val
            continue

        raw = fno_data[key]
        validator = _FNO_VALIDATORS.get(key)

        if validator is not None and not validator(raw):
            logger.error(
                "Invalid fno config value %s=%r — using default %r",
                key, raw, default_val,
            )
            resolved[key] = default_val
            continue

        resolved[key] = raw

    # ── Broker config validation ──────────────────────────────────────
    broker = resolved["broker"]
    required_keys = _BROKER_REQUIRED_KEYS.get(broker, [])
    broker_section = yaml_dict.get(broker)

    if broker_section is None or not isinstance(broker_section, dict):
        logger.error(
            "Broker '%s' selected but no '%s' config section found. "
            "Required keys: %s",
            broker, broker, ", ".join(required_keys),
        )
        sys.exit(1)

    missing = [k for k in required_keys if k not in broker_section]
    if missing:
        logger.error(
            "Broker '%s' config section is missing required keys: %s",
            broker, ", ".join(missing),
        )
        sys.exit(1)

    return FnO_Config(**resolved)


def verify_paper_history(db: Any, weeks: int = 3) -> bool:
    """Verify that sufficient profitable paper trading history exists.

    Checks the database for ``weeks`` worth of paper trading daily summaries
    with a positive cumulative P&L before allowing live mode.

    Parameters
    ----------
    db:
        DBManager instance.
    weeks : int
        Minimum number of weeks of paper trading required (default 3).

    Returns
    -------
    bool
        True if sufficient profitable paper history exists, False otherwise.
    """
    try:
        history = db.get_paper_trading_history(weeks=weeks)
    except Exception:
        logger.error("Failed to query paper trading history", exc_info=True)
        return False

    required_days = weeks * 5  # ~5 trading days per week
    if len(history) < required_days:
        logger.warning(
            "Insufficient paper history: %d days found, need %d (%d weeks)",
            len(history), required_days, weeks,
        )
        return False

    # Check cumulative P&L is positive
    cumulative_pnl = sum(float(row.get("total_pnl", 0) or 0) for row in history)
    if cumulative_pnl <= 0:
        logger.warning(
            "Paper trading cumulative P&L is ₹%.2f (not positive) — "
            "live mode requires profitable paper history",
            cumulative_pnl,
        )
        return False

    logger.info(
        "Paper history verified: %d days, cumulative P&L ₹%.2f",
        len(history), cumulative_pnl,
    )
    return True
