"""Shared data models for the intraday auto-trader."""

from dataclasses import dataclass, field
from enum import Enum


@dataclass
class TradeSetup:
    """A single intraday trade candidate selected by the LLM."""

    stock_name: str
    nse_symbol: str
    tradingsymbol: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    confidence_score: int
    rationale: str
    strategy_type: str  # "MOMENTUM", "ORB", "GAP", "VWAP"
    quantity: int = 0  # Filled by Risk_Manager
    risk_reward_ratio: float = 0.0


class PositionState(str, Enum):
    """State machine states for an intraday position."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL_BOOKED = "PARTIAL_BOOKED"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    FORCE_EXITED = "FORCE_EXITED"


@dataclass
class IntraConfig:
    """Configuration for the intraday auto-trader.

    Loaded from the ``intraday`` section of config.yaml.
    All monetary values are in INR.
    """

    broker: str = "dhan"
    daily_capital_limit: float = 100000.0  # Max total capital deployed per day (₹1L for dry-run)
    per_trade_max_capital: float = 50000.0  # Max capital per single trade
    max_trades_per_day: int = 5
    price_range_min: float = 50.0
    price_range_max: float = 1000.0
    monitor_interval_seconds: int = 300
    force_exit_time: str = "15:15"
    entry_delay_minutes: int = 10
    min_confidence_score: int = 7
    vix_threshold: float = 20.0
    target_profit_per_day: float = 5000.0
    trailing_sl_trigger_pct: float = 0.5
    partial_book_pct: float = 50.0
    daily_loss_limit: float = 2500.0  # Max cumulative realized loss per day
