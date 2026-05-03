"""Data models for swing trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class SwingConfig:
    """Configuration for swing trading."""

    broker: str = "dhan"
    daily_capital_limit: float = 100_000.0
    per_trade_max_capital: float = 30_000.0
    max_open_positions: int = 5
    min_confidence_score: int = 6
    max_hold_days: int = 15
    target_pct: float = 8.0        # 8% target
    stop_loss_pct: float = 4.0     # 4% stop loss (R:R = 2:1)
    trailing_sl_trigger_pct: float = 5.0  # Trail after 5% gain
    price_range_min: float = 50.0
    price_range_max: float = 5000.0
    scan_time: str = "15:30"       # Scan after market close
    monitor_time: str = "09:30"    # Check positions after open


@dataclass
class SwingSetup:
    """A swing trade candidate selected by LLM."""

    nse_symbol: str
    stock_name: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    confidence_score: int
    strategy_type: str  # BREAKOUT, PULLBACK, REVERSAL, MOMENTUM
    rationale: str
    expected_hold_days: int = 5
    risk_reward_ratio: float = 2.0
    sector: str = ""


@dataclass
class SwingPosition:
    """An active swing position."""

    id: int = 0
    nse_symbol: str = ""
    entry_price: float = 0.0
    entry_date: str = ""
    target_price: float = 0.0
    stop_loss_price: float = 0.0
    current_price: float = 0.0
    quantity: int = 0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED_OUT, EXPIRED
    pnl: float = 0.0
    exit_price: float = 0.0
    exit_date: str = ""
    strategy_type: str = ""
    confidence_score: int = 0
    days_held: int = 0
