"""Data models for positional trading."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionalConfig:
    """Configuration for positional trading."""

    broker: str = "dhan"
    total_capital: float = 500_000.0     # ₹5L total portfolio
    per_stock_max: float = 100_000.0     # ₹1L max per stock
    max_positions: int = 10
    min_confidence_score: int = 7
    max_hold_weeks: int = 12             # 3 months max
    target_pct: float = 20.0             # 20% target
    stop_loss_pct: float = 8.0           # 8% stop loss (R:R = 2.5:1)
    trailing_sl_trigger_pct: float = 12.0  # Trail after 12% gain
    price_range_min: float = 100.0
    price_range_max: float = 10000.0
    rebalance_day: str = "Friday"        # Weekly rebalance day
    scan_frequency: str = "weekly"       # weekly or daily


@dataclass
class PositionalSetup:
    """A positional trade candidate."""

    nse_symbol: str
    stock_name: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    confidence_score: int
    strategy_type: str  # GROWTH, VALUE, MOMENTUM, SECTOR_ROTATION, EARNINGS
    rationale: str
    expected_hold_weeks: int = 8
    risk_reward_ratio: float = 2.5
    sector: str = ""
    market_cap: str = ""  # LARGE, MID, SMALL
    fundamentals: str = ""  # PE, ROCE, debt summary


@dataclass
class PositionalPosition:
    """An active positional position."""

    id: int = 0
    nse_symbol: str = ""
    entry_price: float = 0.0
    entry_date: str = ""
    target_price: float = 0.0
    stop_loss_price: float = 0.0
    current_price: float = 0.0
    quantity: int = 0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED_OUT, EXPIRED, REBALANCED
    pnl: float = 0.0
    exit_price: float = 0.0
    exit_date: str = ""
    strategy_type: str = ""
    confidence_score: int = 0
    weeks_held: int = 0
    sector: str = ""
    market_cap: str = ""
