"""Shared data models for the F&O auto-trader.

All dataclasses used across the fno/ package — strategy legs, position states,
market regimes, option chain snapshots, quant signals, and Greeks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ── Strategy Leg ──────────────────────────────────────────────────────────


@dataclass
class StrategyLeg:
    """A single leg of a multi-leg F&O strategy."""

    index: str                  # "NIFTY", "BANKNIFTY", "FINNIFTY"
    strike_price: float
    expiry_date: str            # "YYYY-MM-DD"
    option_type: str            # "CE", "PE", "FUT"
    transaction_type: str       # "BUY" or "SELL"
    lot_size: int               # Exchange lot size (e.g., 25 for Nifty)
    num_lots: int
    entry_price: float          # Premium per unit
    tradingsymbol: str = ""     # Broker-specific symbol (filled by Symbol_Builder)

    @property
    def quantity(self) -> int:
        """Total units = lot_size × num_lots."""
        return self.lot_size * self.num_lots

    @property
    def is_sell(self) -> bool:
        """True if this leg is a sell (short) position."""
        return self.transaction_type == "SELL"


# ── Enums ─────────────────────────────────────────────────────────────────


class FnOPositionState(str, Enum):
    """State machine states for an F&O strategy position."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL_BOOKED = "PARTIAL_BOOKED"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    FORCE_EXITED = "FORCE_EXITED"
    EXPIRED = "EXPIRED"


class MarketRegime(str, Enum):
    """Market regime classification for strategy selection."""

    SIDEWAYS = "SIDEWAYS"
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


# ── Strategy Setup ────────────────────────────────────────────────────────


@dataclass
class FnOStrategySetup:
    """A complete multi-leg F&O strategy ready for execution."""

    strategy_type: str          # "IRON_CONDOR", "SHORT_STRANGLE", etc.
    index: str
    legs: list[StrategyLeg]
    net_premium: float          # Positive = credit, negative = debit
    max_profit: float
    max_loss: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    confidence_score: int
    rationale: str
    market_regime: str
    confluence_score: float     # From Quant Edge Engine
    expiry_date: str


# ── Option Chain Models ───────────────────────────────────────────────────


@dataclass
class OptionStrike:
    """A single option contract from the option chain."""

    strike_price: float
    expiry_date: str
    option_type: str            # "CE" or "PE"
    ltp: float                  # Last traded price
    bid_price: float
    ask_price: float
    open_interest: int
    oi_change: int              # Change from previous day
    volume: int
    iv: float                   # Implied volatility (%)
    bid_ask_spread: float = 0.0


@dataclass
class OptionChainSnapshot:
    """Complete option chain snapshot for one index at one point in time."""

    index: str
    spot_price: float
    timestamp: str              # ISO 8601 IST
    expiry_date: str
    lot_size: int
    strikes: list[OptionStrike]
    atm_strike: float
    pcr: float                  # Put-Call Ratio
    max_pain: float
    highest_call_oi_strike: float
    highest_put_oi_strike: float


# ── Quant Signals ─────────────────────────────────────────────────────────


@dataclass
class QuantSignals:
    """All quantitative signals computed by the Quant Edge Engine."""

    iv_percentile: float        # 0-100
    iv_percentile_signal: str   # "SELL_PREMIUM", "BUY_PREMIUM", "USE_SPREADS"
    oi_velocity_support: list[dict] = field(default_factory=list)
    oi_velocity_resistance: list[dict] = field(default_factory=list)
    iv_skew: float = 0.0       # Put IV - Call IV (25-delta)
    iv_skew_signal: str = "NEUTRAL"  # "BEARISH", "BULLISH", "NEUTRAL"
    gex_map: list[dict] = field(default_factory=list)
    gex_gravity_center: float = 0.0
    gex_regime: str = "PINNED"  # "PINNED" or "TRENDING"
    vrp: float = 0.0           # IV - RV (percentage points)
    vrp_signal: str = "WEAK_EDGE"  # "STRONG_SELL", "MODERATE_SELL", "WEAK_EDGE", "BUY_PREMIUM"
    confluence_score: float = 0.0  # 0-100 composite
    confluence_breakdown: dict = field(default_factory=dict)


# ── Greeks ────────────────────────────────────────────────────────────────


@dataclass
class Greeks:
    """Option Greeks for a single contract or aggregated portfolio."""

    delta: float
    gamma: float
    theta: float
    vega: float
