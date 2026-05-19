"""
Swing module data models.
"""

from dataclasses import dataclass, field
from enum import Enum


class SwingPositionState(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL_BOOKED_TRAILING = "PARTIAL_BOOKED_TRAILING"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TIME_STOP_EXIT = "TIME_STOP_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"
    REVIEW_PENDING = "REVIEW_PENDING"
    TARGET_HIT = "TARGET_HIT"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class SwingTradeSetup:
    stock_name: str
    tradingsymbol: str
    nse_symbol: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    quantity: int
    confidence_score: int
    rationale: str
    holding_days_estimate: int
    thesis_invalidation: str
    sector: str = ""
    transaction_type: str = "BUY"  # LONG only for v0.1
    strategy_type: str = "PULLBACK"


@dataclass
class SwingConfig:
    """Swing trading configuration loaded from profile YAML."""
    swing_capital_limit: float = 50000.0
    swing_per_trade_max: float = 5000.0
    swing_max_open_positions: int = 5
    swing_daily_loss_limit: float = 1000.0
    swing_weekly_loss_limit_pct: float = 5.0
    sector_concentration_max: int = 2
    swing_min_score: int = 8
    swing_min_confidence: int = 7  # 8 for --live mode
    swing_min_confidence_live: int = 8
    swing_min_rr: float = 2.0
    swing_max_holding_days: int = 30  # smart time stop kicks in earlier
    broker: str = "dhan"
    profile: str = ""

    @classmethod
    def from_yaml(cls, profile_data: dict, profile_name: str = "") -> "SwingConfig":
        """Load SwingConfig from profile YAML swing section."""
        swing_cfg = profile_data.get("swing", {})
        return cls(
            swing_capital_limit=float(swing_cfg.get("swing_capital_limit", 50000)),
            swing_per_trade_max=float(swing_cfg.get("swing_per_trade_max", 5000)),
            swing_max_open_positions=int(swing_cfg.get("swing_max_open_positions", 5)),
            swing_daily_loss_limit=float(swing_cfg.get("swing_daily_loss_limit", 1000)),
            swing_weekly_loss_limit_pct=float(swing_cfg.get("swing_weekly_loss_limit_pct", 5.0)),
            sector_concentration_max=int(swing_cfg.get("sector_concentration_max", 2)),
            swing_min_score=int(swing_cfg.get("swing_min_score", 8)),
            swing_min_confidence=int(swing_cfg.get("swing_min_confidence", 7)),
            swing_min_confidence_live=int(swing_cfg.get("swing_min_confidence_live", 8)),
            swing_min_rr=float(swing_cfg.get("swing_min_rr", 2.0)),
            swing_max_holding_days=int(swing_cfg.get("swing_max_holding_days", 30)),
            broker=profile_data.get("broker", "dhan"),
            profile=profile_name,
        )
