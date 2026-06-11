"""
Swing position monitor.
Runs 2x daily: 9:30 AM IST (post-open) + 3:15 PM IST (pre-close).
NO 5-minute cycles. NO force exit at 15:15.

# TODO Week 3: Add tiered review schedule (new positions = 2x/day, extended = weekly)
# TODO Week 4: Add tax-aware LTCG conversion logic for big winners > 60 days
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

from swing.models import SwingPositionState, SwingConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def should_time_exit(days_held: int, pnl_pct: float) -> tuple:
    """
    Smart time stop. NEVER auto-sells winners.
    Time stops only kill losers and dead capital.
    Returns: (action, reason) where action is "EXIT" or "HOLD"
    """
    if days_held >= 30:
        return ("EXIT", "30_DAY_HARD_LIMIT")
    if days_held >= 21 and pnl_pct < 3:
        return ("EXIT", "21_DAY_LOW_PROGRESS")
    if days_held >= 15 and pnl_pct < 0:
        return ("EXIT", "15_DAY_LOSING")
    if days_held >= 10 and -1 <= pnl_pct <= 1:
        return ("EXIT", "10_DAY_FLAT")
    if days_held >= 7 and pnl_pct <= -3:
        return ("EXIT", "7_DAY_DRAWDOWN")
    # All winning trades or recently opened: HOLD
    return ("HOLD", None)


def needs_review(days_held: int, pnl_pct: float) -> tuple:
    """Alert-only logic for manual review."""
    if days_held >= 30 and pnl_pct >= 50:
        return True, "BIG_WINNER_LTCG_CANDIDATE"
    if days_held >= 20 and pnl_pct > 10:
        return True, "EXTENDED_WINNER_REVIEW"
    return False, None


class SwingMonitor:
    """Monitor open swing positions. Run 2x daily."""

    def __init__(self, config: SwingConfig, broker=None, db=None, telegram=None):
        self.config = config
        self.broker = broker
        self.db = db
        self.telegram = telegram
        self._active_trades = []

    def load_open_positions(self):
        """Load open swing trades from DB."""
        if not self.db:
            self._active_trades = []
            return
        try:
            trades = self.db.get_open_swing_trades() or []
            self._active_trades = trades
            logger.info("Loaded %d open swing positions", len(trades))
        except Exception as e:
            logger.error("Failed to load swing positions: %s", e)
            self._active_trades = []

    def _get_current_price(self, symbol: str) -> float:
        """Get current price from broker positions or LTP."""
        if not self.broker:
            return 0.0
        try:
            if hasattr(self.broker, "get_positions"):
                positions = self.broker.get_positions()
                for pos in positions:
                    if pos.get("tradingsymbol", "").upper() == symbol.upper():
                        # Use buy_avg as proxy if no LTP available
                        return float(pos.get("pnl", 0)) / max(int(pos.get("quantity", 1)), 1) + float(pos.get("buy_avg", 0))
        except Exception as e:
            logger.warning("get_positions failed for %s: %s", symbol, e)
        return 0.0

    def _place_exit_order(self, trade: dict, reason: str) -> tuple:
        """Place MARKET SELL order for CNC exit. Returns (fill_price, fill_status)."""
        if not self.broker:
            return trade.get("current_price", trade["entry_price"]), "no_broker"

        fallback_price = trade.get("current_price", trade["entry_price"])
        try:
            result = self.broker.place_order(
                symbol=trade.get("tradingsymbol", trade.get("symbol", "")),
                exchange="NSE",
                transaction_type="SELL",
                order_type="MARKET",
                product_type="CNC",
                quantity=trade["quantity"],
            )
            order_id = result.get("broker_order_id", "") if isinstance(result, dict) else ""
            logger.info("Swing exit order placed: %s (%s) order_id=%s reason=%s",
                        trade.get("tradingsymbol", trade.get("symbol", "")), "SELL", order_id, reason)

            if not order_id or not hasattr(self.broker, "get_order_list"):
                return fallback_price, "no_poll"

            # Poll for fill
            for _ in range(5):
                time.sleep(2)
                try:
                    orders = self.broker.get_order_list()
                    for o in orders:
                        if str(o.get("orderId", "")) == str(order_id):
                            if o.get("orderStatus") == "TRADED":
                                avg_price = float(o.get("averageTradedPrice", 0) or 0)
                                if avg_price > 0:
                                    return avg_price, "filled"
                except Exception as e:
                    logger.warning("Exit fill poll failed: %s", e)
                    break
            return fallback_price, "timeout"
        except Exception as e:
            logger.error("Swing exit order FAILED: %s — %s", trade.get("tradingsymbol", trade.get("symbol", "")), e)
            return fallback_price, "order_failed"

    def _calculate_charges(self, buy_price: float, sell_price: float, qty: int) -> float:
        """CNC delivery charges estimate."""
        buy_value = buy_price * qty
        sell_value = sell_price * qty
        # Brokerage: Rs.20 flat per leg
        brokerage = 40.0
        # STT: 0.1% on sell side (CNC)
        stt = sell_value * 0.001
        # Exchange + SEBI: ~0.003%
        exchange = (buy_value + sell_value) * 0.00003
        # GST on brokerage: 18%
        gst = brokerage * 0.18
        # Stamp duty: 0.015% on buy
        stamp = buy_value * 0.00015
        return round(brokerage + stt + exchange + gst + stamp, 2)

    def _update_db(self, trade: dict, status: SwingPositionState, exit_price: float = 0,
                   exit_reason: str = "", pnl: float = 0, charges: float = 0):
        """Update trade in DB."""
        if not self.db:
            return
        try:
            self.db.update_swing_trade(
                trade_id=trade["id"],
                status=status.value,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl=pnl,
                charges=charges,
                days_held=trade.get("days_held", 0),
                exit_date=date.today().isoformat() if exit_price > 0 else None,
            )
        except Exception as e:
            logger.error("DB update failed for swing trade %s: %s", trade.get("id"), e)

    def _send_alert(self, message: str):
        """Send Telegram alert if configured."""
        if self.telegram:
            try:
                self.telegram(message)
            except Exception as e:
                logger.warning("Telegram alert failed: %s", e)

    def _audit(self, event_type: str, details: dict, trade_id=None):
        """Write audit log."""
        if self.db:
            try:
                self.db.insert_swing_audit(event_type, json.dumps(details, default=str), trade_id)
            except Exception:
                pass

    def run_monitor_cycle(self):
        """Main monitor cycle. Called 2x daily."""
        self.load_open_positions()
        if not self._active_trades:
            logger.info("No open swing positions to monitor")
            return

        logger.info("Monitoring %d open swing positions", len(self._active_trades))

        for trade in self._active_trades:
            self._check_position(trade)

    def _check_position(self, trade: dict):
        """Check single position for exit triggers."""
        symbol = trade.get("tradingsymbol", trade.get("symbol", ""))
        entry = trade["entry_price"]
        sl = trade["stop_loss_price"]
        target = trade["target_price"]
        qty = trade["quantity"]

        # Update days_held
        try:
            entry_date = datetime.strptime(str(trade.get("entry_date", "")), "%Y-%m-%d").date()
            days_held = (date.today() - entry_date).days
        except (ValueError, TypeError):
            days_held = trade.get("days_held", 0)
        trade["days_held"] = days_held

        # Get current price
        current = self._get_current_price(symbol)
        if current <= 0:
            logger.warning("No current price for %s — skipping", symbol)
            return
        trade["current_price"] = current

        pnl_pct = (current - entry) / entry * 100

        # --- Priority 1: SL hit ---
        if current <= sl:
            exit_price, fill_status = self._place_exit_order(trade, "SL_HIT")
            # Bug 3 fix: check fill_status before recording P&L
            if fill_status in ("order_failed", "no_broker"):
                logger.error(
                    "🚨 %s SL HIT but exit FAILED (status=%s). Position remains OPEN.",
                    symbol, fill_status
                )
                self._audit("EXIT_FAILED", {"symbol": symbol, "trigger": "SL_HIT", "fill_status": fill_status})
                return
            gross_pnl = (exit_price - entry) * qty
            charges = self._calculate_charges(entry, exit_price, qty)
            net_pnl = gross_pnl - charges
            self._update_db(trade, SwingPositionState.STOPPED_OUT, exit_price, "SL_HIT", net_pnl, charges)
            self._send_alert(f"🛑 SWING SL HIT: {symbol} @ Rs.{exit_price:.2f} | P&L Rs.{net_pnl:.0f} | {days_held}d held")
            self._audit("SL_HIT", {"symbol": symbol, "exit_price": exit_price, "pnl": net_pnl}, trade.get("id"))
            logger.info("🛑 %s STOPPED OUT @ Rs.%.2f | P&L Rs.%.0f | %dd", symbol, exit_price, net_pnl, days_held)
            return

        # --- Priority 2: Target hit (partial book 50% + trail rest) ---
        if current >= target and trade.get("status") != SwingPositionState.PARTIAL_BOOKED_TRAILING.value:
            # Book 50%, trail rest with 10-EMA (simplified: trail at entry + 50% of gain)
            partial_qty = max(1, qty // 2)
            exit_price, fill_status = self._place_exit_order(
                {**trade, "quantity": partial_qty}, "TARGET_HIT_PARTIAL"
            )
            if fill_status in ("order_failed", "no_broker"):
                logger.error("🚨 %s TARGET HIT but partial exit FAILED.", symbol)
                self._audit("EXIT_FAILED", {"symbol": symbol, "trigger": "TARGET_HIT", "fill_status": fill_status})
                return
            gross_pnl = (exit_price - entry) * partial_qty
            charges = self._calculate_charges(entry, exit_price, partial_qty)
            net_pnl = gross_pnl - charges
            # Update: remaining qty, new trailing SL
            new_sl = entry + (current - entry) * 0.5  # trail at 50% of gain
            trade["quantity"] = qty - partial_qty
            trade["stop_loss_price"] = new_sl
            self._update_db(trade, SwingPositionState.PARTIAL_BOOKED_TRAILING, exit_price, "TARGET_PARTIAL", net_pnl, charges)
            self._send_alert(f"🎯 SWING T1 HIT: {symbol} | Booked {partial_qty} @ Rs.{exit_price:.2f} | Trail SL Rs.{new_sl:.2f}")
            logger.info("🎯 %s TARGET partial %d @ Rs.%.2f | Trail SL Rs.%.2f", symbol, partial_qty, exit_price, new_sl)
            return

        # --- Priority 3: Smart time stop ---
        action, reason = should_time_exit(days_held, pnl_pct)
        if action == "EXIT":
            exit_price, fill_status = self._place_exit_order(trade, f"TIME_STOP_{reason}")
            if fill_status in ("order_failed", "no_broker"):
                logger.error("🚨 %s TIME STOP but exit FAILED.", symbol)
                self._audit("EXIT_FAILED", {"symbol": symbol, "trigger": "TIME_STOP", "fill_status": fill_status})
                return
            gross_pnl = (exit_price - entry) * qty
            charges = self._calculate_charges(entry, exit_price, qty)
            net_pnl = gross_pnl - charges
            self._update_db(trade, SwingPositionState.TIME_STOP_EXIT, exit_price, reason, net_pnl, charges)
            self._send_alert(f"⏰ SWING TIME STOP: {symbol} | {reason} | {days_held}d | P&L Rs.{net_pnl:.0f}")
            logger.info("⏰ %s TIME STOP (%s) @ Rs.%.2f | %dd | P&L Rs.%.0f", symbol, reason, exit_price, days_held, net_pnl)
            return

        # --- Priority 4: Earnings approaching ---
        from fetchers.swing_earnings_list import get_earnings_within_days
        if get_earnings_within_days(trade.get("symbol", symbol), days=1):
            exit_price, fill_status = self._place_exit_order(trade, "EARNINGS_EXIT")
            if fill_status in ("order_failed", "no_broker"):
                logger.error("🚨 %s EARNINGS EXIT FAILED.", symbol)
                self._audit("EXIT_FAILED", {"symbol": symbol, "trigger": "EARNINGS", "fill_status": fill_status})
                return
            gross_pnl = (exit_price - entry) * qty
            charges = self._calculate_charges(entry, exit_price, qty)
            net_pnl = gross_pnl - charges
            self._update_db(trade, SwingPositionState.CLOSED, exit_price, "EARNINGS_EXIT", net_pnl, charges)
            self._send_alert(f"📅 SWING EARNINGS EXIT: {symbol} | P&L Rs.{net_pnl:.0f}")
            logger.info("📅 %s EARNINGS EXIT @ Rs.%.2f | P&L Rs.%.0f", symbol, exit_price, net_pnl)
            return

        # --- Priority 5: Review alerts (no action, just notify) ---
        review_needed, review_reason = needs_review(days_held, pnl_pct)
        if review_needed:
            self._send_alert(f"👀 SWING REVIEW: {symbol} | {review_reason} | {days_held}d | +{pnl_pct:.1f}%")
            logger.info("👀 %s needs review: %s (%dd, +%.1f%%)", symbol, review_reason, days_held, pnl_pct)

        # --- No exit: log status ---
        logger.info("📊 %s: %dd held | Rs.%.2f (%.1f%%) | SL Rs.%.2f | Target Rs.%.2f",
                    symbol, days_held, current, pnl_pct, sl, target)
