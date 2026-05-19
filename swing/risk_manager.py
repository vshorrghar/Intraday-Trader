"""
Swing module risk manager.
Position sizing, sector caps, regime check, drawdown limits.

# TODO Week 3: Replace 3-signal regime with 8-signal institutional version
# TODO Week 3: Add Half-Kelly position sizing
# TODO Week 3: Add full correlation matrix (replace sector cap)
# TODO Week 3: Add 5-level drawdown circuit breakers
"""

import logging
from swing.models import SwingConfig, SwingTradeSetup
from swing.sector_map import SECTOR_MAP

logger = logging.getLogger(__name__)


def compute_position_size(trade: SwingTradeSetup, capital_limit: float) -> int:
    """Flat 1% risk position sizing. Kelly comes Week 3."""
    risk_amount = capital_limit * 0.01  # 1% rule
    risk_per_share = trade.entry_price - trade.stop_loss_price
    if risk_per_share <= 0:
        logger.warning("Invalid risk_per_share for %s: entry=%.2f sl=%.2f",
                       trade.nse_symbol, trade.entry_price, trade.stop_loss_price)
        return 0
    quantity = int(risk_amount / risk_per_share)
    # Cap by per-trade max capital
    max_qty_by_capital = int(capital_limit * 0.1 / trade.entry_price)  # max 10% in one stock
    quantity = min(quantity, max_qty_by_capital)
    return max(1, quantity)


def check_sector_cap(symbol: str, open_positions: list, max_per_sector: int = 2) -> tuple:
    """Check sector concentration. Max 2 positions per sector."""
    symbol_sector = SECTOR_MAP.get(symbol, "UNKNOWN")
    sector_count = sum(
        1 for p in open_positions
        if SECTOR_MAP.get(p.get("symbol", ""), "UNKNOWN") == symbol_sector
    )
    if sector_count >= max_per_sector:
        return False, f"Sector {symbol_sector} already has {sector_count} positions (max {max_per_sector})"
    return True, None


def check_max_positions(open_positions: list, max_positions: int = 5) -> tuple:
    """Check max open positions gate."""
    if len(open_positions) >= max_positions:
        return False, f"Already at {len(open_positions)} positions (max {max_positions})"
    return True, None


def check_daily_loss(today_pnl: float, daily_loss_limit: float) -> tuple:
    """Check daily loss limit."""
    if today_pnl < 0 and abs(today_pnl) >= daily_loss_limit:
        return False, f"Daily loss Rs.{abs(today_pnl):.0f} >= limit Rs.{daily_loss_limit:.0f}"
    return True, None


def check_weekly_loss(week_pnl: float, capital_limit: float, max_pct: float = 5.0) -> tuple:
    """Check weekly loss limit (5% default)."""
    if capital_limit <= 0:
        return True, None
    weekly_loss_pct = abs(week_pnl) / capital_limit * 100
    if week_pnl < 0 and weekly_loss_pct >= max_pct:
        return False, f"Weekly loss {weekly_loss_pct:.1f}% >= {max_pct}% — halve sizes"
    return True, None


def check_regime(vix: float, nifty_close: float = 0, nifty_50dma: float = 0, nifty_200dma: float = 0) -> tuple:
    """
    3-signal regime check. Returns (status, reason).
    status: True (proceed), False (skip), "REDUCE" (halve size)

    # TODO Week 3: Replace 3-signal regime with 8-signal institutional version
    """
    if vix > 25:
        return False, "VIX > 25 — skip swing entries"
    if nifty_200dma > 0 and nifty_close < nifty_200dma:
        return False, "Nifty below 200-DMA — bear regime"
    if vix > 22:
        return "REDUCE", "VIX > 22 — halve position size"
    if nifty_50dma > 0 and nifty_close < nifty_50dma:
        return "REDUCE", "Nifty below 50-DMA — caution"
    return True, None


class SwingRiskManager:
    """Orchestrates all risk checks for swing module."""

    def __init__(self, config: SwingConfig, db=None):
        self.config = config
        self.db = db
        self._today_pnl = 0.0
        self._week_pnl = 0.0
        self._open_positions = []

    def load_state(self):
        """Load open positions and P&L from DB."""
        if not self.db:
            return
        # Load open swing positions
        try:
            self._open_positions = self.db.get_open_swing_trades() or []
        except Exception:
            self._open_positions = []
        # Load today's closed P&L
        try:
            self._today_pnl = self.db.get_swing_today_pnl() or 0.0
        except Exception:
            self._today_pnl = 0.0
        # Load week P&L
        try:
            self._week_pnl = self.db.get_swing_week_pnl() or 0.0
        except Exception:
            self._week_pnl = 0.0

    def can_enter_trade(self, trade: SwingTradeSetup, vix: float = 15.0,
                        nifty_close: float = 0, nifty_50dma: float = 0,
                        nifty_200dma: float = 0) -> tuple:
        """Run all pre-trade gates. Returns (allowed: bool, reason: str|None)."""
        # Gate 1: Regime
        regime_ok, regime_reason = check_regime(vix, nifty_close, nifty_50dma, nifty_200dma)
        if regime_ok is False:
            return False, regime_reason

        # Gate 2: Max positions
        ok, reason = check_max_positions(self._open_positions, self.config.swing_max_open_positions)
        if not ok:
            return False, reason

        # Gate 3: Sector cap
        ok, reason = check_sector_cap(trade.nse_symbol, self._open_positions,
                                      self.config.sector_concentration_max)
        if not ok:
            return False, reason

        # Gate 4: Daily loss
        ok, reason = check_daily_loss(self._today_pnl, self.config.swing_daily_loss_limit)
        if not ok:
            return False, reason

        # Gate 5: Weekly loss
        ok, reason = check_weekly_loss(self._week_pnl, self.config.swing_capital_limit,
                                       self.config.swing_weekly_loss_limit_pct)
        if not ok:
            return False, reason

        # If regime says REDUCE, halve position size (caller handles)
        if regime_ok == "REDUCE":
            return "REDUCE", regime_reason

        return True, None

    def size_position(self, trade: SwingTradeSetup, reduce: bool = False) -> int:
        """Compute position size. Halve if reduce=True."""
        qty = compute_position_size(trade, self.config.swing_capital_limit)
        if reduce:
            qty = max(1, qty // 2)
        return qty
