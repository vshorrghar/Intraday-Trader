"""Positional trade monitor — weekly position review.

Runs weekly (Friday after close) to:
- Check all open positions against current prices
- Apply trailing stop losses
- Close positions hitting target or max hold period
- Rebalance portfolio if needed
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from positional.models import PositionalConfig, PositionalPosition

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


class PositionalMonitor:
    """Weekly monitor for positional positions."""

    def __init__(self, config: PositionalConfig, db=None) -> None:
        self.config = config
        self.db = db

    def review_positions(self, positions: list[PositionalPosition]) -> list[PositionalPosition]:
        """Weekly review of all open positions."""
        if not positions:
            logger.info("No open positional positions")
            return positions

        logger.info("Reviewing %d positional positions…", len(positions))

        prices = self._fetch_prices([p.nse_symbol for p in positions])

        for pos in positions:
            if pos.status != "OPEN":
                continue

            current = prices.get(pos.nse_symbol, 0)
            if current <= 0:
                continue

            pos.current_price = current
            pos.weeks_held = self._calc_weeks_held(pos.entry_date)

            # Stop loss
            if current <= pos.stop_loss_price:
                pos.status = "STOPPED_OUT"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info("🛑 %s STOPPED OUT @ ₹%.2f | P&L: ₹%.2f | Week %d", pos.nse_symbol, current, pos.pnl, pos.weeks_held)
                continue

            # Target
            if current >= pos.target_price:
                pos.status = "CLOSED"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info("🎯 %s TARGET HIT @ ₹%.2f | P&L: ₹%.2f | Week %d", pos.nse_symbol, current, pos.pnl, pos.weeks_held)
                continue

            # Max hold period
            if pos.weeks_held >= self.config.max_hold_weeks:
                pos.status = "EXPIRED"
                pos.exit_price = current
                pos.exit_date = datetime.now(IST).strftime("%Y-%m-%d")
                pos.pnl = round((current - pos.entry_price) * pos.quantity, 2)
                logger.info("⏰ %s EXPIRED (week %d) @ ₹%.2f | P&L: ₹%.2f", pos.nse_symbol, pos.weeks_held, current, pos.pnl)
                continue

            # Trailing SL
            gain_pct = (current - pos.entry_price) / pos.entry_price * 100
            if gain_pct >= self.config.trailing_sl_trigger_pct:
                new_sl = pos.entry_price + 0.6 * (current - pos.entry_price)
                if new_sl > pos.stop_loss_price:
                    pos.stop_loss_price = round(new_sl, 2)
                    logger.info("📈 %s trailing SL → ₹%.2f (gain %.1f%%)", pos.nse_symbol, new_sl, gain_pct)

        return positions

    def _fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        """Fetch current prices from NSE."""
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
                        ltp = float(r.json().get("priceInfo", {}).get("lastPrice", 0) or 0)
                        if ltp > 0:
                            prices[sym] = ltp
                    time.sleep(0.3)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Positional price fetch failed: %s", e)
        return prices

    @staticmethod
    def _calc_weeks_held(entry_date_str: str) -> int:
        """Calculate weeks held."""
        try:
            entry = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
            today = datetime.now(IST).date()
            return max(0, (today - entry).days // 7)
        except Exception:
            return 0
