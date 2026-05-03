"""Swing position monitor — checks open positions daily.

Runs every morning at 9:30 AM IST to:
- Fetch current prices for all open swing positions
- Check if target or stop loss is hit
- Apply trailing stop loss for positions in profit
- Close positions that exceed max hold days
- Log P&L and update dashboard
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from swing.models import SwingConfig, SwingPosition

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


class SwingMonitor:
    """Monitors open swing positions and manages exits."""

    def __init__(self, config: SwingConfig, db=None) -> None:
        self.config = config
        self.db = db

    def check_positions(self, positions: list[SwingPosition]) -> list[SwingPosition]:
        """Check all open positions against current prices.

        Returns updated positions with status changes.
        """
        if not positions:
            logger.info("No open swing positions to check")
            return positions

        logger.info("Checking %d open swing positions…", len(positions))

        # Fetch live prices
        prices = self._fetch_prices([p.nse_symbol for p in positions])

        for pos in positions:
            if pos.status != "OPEN":
                continue

            current = prices.get(pos.nse_symbol, 0)
            if current <= 0:
                continue

            pos.current_price = current
            pos.days_held = self._calc_days_held(pos.entry_date)

            # Check stop loss
            if current <= pos.stop_loss_price:
                pos.status = "STOPPED_OUT"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info(
                    "🛑 %s STOPPED OUT @ ₹%.2f | P&L: ₹%.2f | Held %d days",
                    pos.nse_symbol, current, pos.pnl, pos.days_held,
                )
                continue

            # Check target
            if current >= pos.target_price:
                pos.status = "CLOSED"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info(
                    "🎯 %s TARGET HIT @ ₹%.2f | P&L: ₹%.2f | Held %d days",
                    pos.nse_symbol, current, pos.pnl, pos.days_held,
                )
                continue

            # Check max hold days
            if pos.days_held >= self.config.max_hold_days:
                pos.status = "EXPIRED"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info(
                    "⏰ %s EXPIRED (max %d days) @ ₹%.2f | P&L: ₹%.2f",
                    pos.nse_symbol, self.config.max_hold_days, current, pos.pnl,
                )
                continue

            # Trailing stop loss
            gain_pct = (current - pos.entry_price) / pos.entry_price * 100
            if gain_pct >= self.config.trailing_sl_trigger_pct:
                new_sl = pos.entry_price + 0.5 * (current - pos.entry_price)
                if new_sl > pos.stop_loss_price:
                    old_sl = pos.stop_loss_price
                    pos.stop_loss_price = round(new_sl, 2)
                    logger.info(
                        "📈 %s trailing SL: ₹%.2f → ₹%.2f (gain %.1f%%)",
                        pos.nse_symbol, old_sl, new_sl, gain_pct,
                    )

        return positions

    def _fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        """Fetch current prices from NSE for given symbols."""
        prices = {}
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            session.get(NSE_BASE, timeout=10)
            time.sleep(0.5)

            for sym in symbols:
                try:
                    r = session.get(f"{NSE_BASE}/api/quote-equity?symbol={sym}", timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        ltp = float(data.get("priceInfo", {}).get("lastPrice", 0) or 0)
                        if ltp > 0:
                            prices[sym] = ltp
                    time.sleep(0.3)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Failed to fetch swing prices: %s", e)

        return prices

    @staticmethod
    def _calc_days_held(entry_date_str: str) -> int:
        """Calculate trading days held (approximate)."""
        try:
            entry = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
            today = datetime.now(IST).date()
            delta = (today - entry).days
            # Approximate trading days (exclude weekends)
            return max(0, delta - (delta // 7) * 2)
        except Exception:
            return 0
