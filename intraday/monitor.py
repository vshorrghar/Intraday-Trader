"""Position monitor with state machine for the intraday auto-trader.

Tracks open positions, implements trailing SL, partial profit booking,
and force-exit at the configured deadline.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from intraday.broker_base import BrokerClient
from intraday.models import IntraConfig, PositionState

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ------------------------------------------------------------------
# Pure calculation helpers (used by property tests too)
# ------------------------------------------------------------------

def calc_trailing_sl(
    entry_price: float,
    current_price: float,
    trailing_sl_trigger_pct: float,
) -> float | None:
    """Return new SL if trailing trigger is met, else None.

    New SL = entry + 0.5 × (current − entry), always ≥ entry.
    """
    if entry_price <= 0 or current_price <= entry_price:
        return None
    gain_pct = (current_price - entry_price) / entry_price * 100
    if gain_pct <= trailing_sl_trigger_pct:
        return None
    new_sl = entry_price + 0.5 * (current_price - entry_price)
    return max(new_sl, entry_price)


def calc_partial_book(
    entry_price: float,
    target_price: float,
    current_price: float,
    total_quantity: int,
    partial_book_pct: float,
) -> dict | None:
    """Return partial booking details if midpoint is reached, else None.

    Midpoint = entry + 0.5 × (target − entry).
    Sell qty = floor(total_quantity × partial_book_pct / 100).
    Remainder SL moves to entry (breakeven).
    """
    if target_price <= entry_price or total_quantity <= 0:
        return None
    midpoint = entry_price + 0.5 * (target_price - entry_price)
    if current_price < midpoint:
        return None
    sell_qty = math.floor(total_quantity * partial_book_pct / 100)
    if sell_qty <= 0:
        return None
    return {
        "sell_qty": sell_qty,
        "remaining_qty": total_quantity - sell_qty,
        "new_sl": entry_price,  # breakeven
        "midpoint": midpoint,
    }


# ------------------------------------------------------------------
# Position Monitor
# ------------------------------------------------------------------

class Position_Monitor:
    """Monitors open positions and manages state transitions."""

    def __init__(
        self,
        broker: BrokerClient,
        config: IntraConfig,
        db: Any = None,
        risk_manager: Any = None,
        dry_run: bool = True,
    ) -> None:
        self.broker = broker
        self.config = config
        self.db = db
        self.risk_manager = risk_manager
        self.dry_run = dry_run
        self._active_trades: list[dict] = []

    def set_trades(self, trades: list[dict]) -> None:
        """Set the list of active trade records to monitor."""
        self._active_trades = [
            t for t in trades
            if t.get("status") in (PositionState.PENDING.value, PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value)
        ]

    def run_monitoring_loop(self, force_exit_only: bool = False) -> list[dict]:
        """Run the position monitoring loop until all positions are closed.

        In dry-run mode, simulates price movement using a simple model.
        """
        if not self._active_trades:
            logger.info("No active trades to monitor")
            return self._active_trades

        logger.info("🔍 Starting position monitor for %d trade(s)…", len(self._active_trades))

        # Immediately transition PENDING → OPEN (simulating fill)
        for t in self._active_trades:
            if t["status"] == PositionState.PENDING.value:
                t["status"] = PositionState.OPEN.value
                t["current_price"] = t["entry_price"]
                self._update_db(t, PositionState.OPEN)

        iteration = 0

        # Persistent monitoring: dry-run also watches real NSE prices
        # until force-exit time, just like a live trader would.
        # Only fall back to simulation if market is closed (no live data).
        use_live_nse = self._is_market_hours()

        if self.dry_run and use_live_nse:
            logger.info(
                "📡 Dry-run with LIVE NSE prices — monitoring every %ds until %s IST",
                self.config.monitor_interval_seconds, self.config.force_exit_time,
            )

        while self._has_open_positions():
            iteration += 1
            now = datetime.now(IST)

            # --- Force exit check ---
            if self._is_force_exit_time(now):
                logger.info("⏰ Force exit time reached — closing all positions")
                self._force_exit_all()
                break

            # --- Fetch current prices ---
            if self.dry_run:
                if use_live_nse:
                    self._fetch_nse_live_quotes()
                else:
                    self._simulate_prices(iteration)
                    # Safety cap for offline simulation only
                    if iteration >= 100:
                        logger.info("Simulation cap reached (market closed) — force exiting")
                        self._force_exit_all()
                        break
            else:
                self._fetch_live_prices()

            # --- Check each position ---
            for trade in self._active_trades:
                if trade["status"] not in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value):
                    continue
                self._check_position(trade)

            # --- Loss cap check ---
            if self.risk_manager:
                total_unrealized = sum(
                    self._calc_unrealized_pnl(t) for t in self._active_trades
                    if t["status"] in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value)
                )
                loss_info = self.risk_manager.check_loss_warning(total_unrealized)
                if loss_info["breach"]:
                    logger.error("💀 Loss cap breached during monitoring — force exiting all")
                    self._force_exit_all()
                    break

            if force_exit_only:
                break

            # --- Log progress every 10 iterations ---
            if iteration % 10 == 0:
                open_count = sum(
                    1 for t in self._active_trades
                    if t["status"] in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value)
                )
                total_pnl = sum(self._calc_unrealized_pnl(t) for t in self._active_trades
                                if t["status"] in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value))
                logger.info(
                    "📊 Monitor cycle %d | %d open | unrealized P&L: ₹%.2f | %s IST",
                    iteration, open_count, total_pnl, now.strftime("%H:%M:%S"),
                )

            # Sleep between checks — ALWAYS use real interval for persistent monitoring
            if self.dry_run and use_live_nse:
                time.sleep(self.config.monitor_interval_seconds)
            elif not self.dry_run:
                time.sleep(self.config.monitor_interval_seconds)
            else:
                time.sleep(0.01)  # offline simulation only

        return self._active_trades

    def _has_open_positions(self) -> bool:
        return any(
            t["status"] in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value)
            for t in self._active_trades
        )

    def _is_force_exit_time(self, now: datetime) -> bool:
        parts = self.config.force_exit_time.split(":")
        exit_h, exit_m = int(parts[0]), int(parts[1])
        return now.hour > exit_h or (now.hour == exit_h and now.minute >= exit_m)

    def _is_market_hours(self) -> bool:
        """Check if we're within NSE market hours (9:15 - 15:30 IST, weekday)."""
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 15):
            return False
        if hour > 15 or (hour == 15 and minute > 30):
            return False
        return True

    def _fetch_nse_live_quotes(self) -> None:
        """Fetch live NSE quotes for tracked symbols during market hours.

        Uses NSE quote API to get real-time LTP for each position.
        Falls back to simulation if NSE is unreachable.
        """
        import requests

        symbols = set()
        for t in self._active_trades:
            if t["status"] in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value):
                sym = t.get("nse_symbol") or t.get("tradingsymbol", "")
                if sym:
                    symbols.add(sym)

        if not symbols:
            return

        nse_base = "https://www.nseindia.com"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }

        try:
            session = requests.Session()
            session.headers.update(headers)
            session.get(nse_base, timeout=10)  # get cookies

            updated = 0
            for sym in symbols:
                try:
                    r = session.get(
                        f"{nse_base}/api/quote-equity?symbol={sym}",
                        timeout=10,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        price_info = data.get("priceInfo", {})
                        ltp = float(price_info.get("lastPrice", 0))
                        if ltp > 0:
                            for t in self._active_trades:
                                t_sym = t.get("nse_symbol") or t.get("tradingsymbol", "")
                                if t_sym == sym:
                                    t["current_price"] = ltp
                                    updated += 1
                    time.sleep(0.3)  # rate limit
                except Exception:
                    pass

            if updated > 0:
                logger.debug("Updated %d positions with live NSE quotes", updated)
            else:
                logger.warning("No live quotes fetched — NSE may be down, using last known prices")

        except Exception as exc:
            logger.warning("NSE session failed: %s — keeping last known prices", exc)

    def _simulate_prices(self, iteration: int) -> None:
        """Simulate price movement for dry-run mode.

        When trade has demo OHLCV data (demo_high, demo_low, demo_ltp),
        uses realistic intraday simulation based on actual day's range:
        - Iteration 1-30: price moves from open toward high (gainer) or low (loser)
        - Iteration 30-70: price oscillates between high and low
        - Iteration 70-100: price converges toward ltp (closing price)

        Otherwise falls back to simple random drift model.
        """
        import random
        for t in self._active_trades:
            if t["status"] not in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value):
                continue

            entry = t["entry_price"]
            target = t["target_price"]
            sl = t["stop_loss_price"]

            # Check if we have demo OHLCV data for realistic simulation
            demo_high = t.get("demo_high", 0)
            demo_low = t.get("demo_low", 0)
            demo_ltp = t.get("demo_ltp", 0)
            demo_open = t.get("demo_open", 0)

            if demo_high > 0 and demo_low > 0 and demo_ltp > 0:
                # Realistic OHLCV-based simulation
                is_gainer = t.get("demo_change_pct", 0) > 0
                progress = iteration / 100.0  # 0.0 to 1.0
                noise = random.uniform(-0.002, 0.002) * entry  # small noise

                if iteration <= 30:
                    # Phase 1: Move from entry toward high (gainer) or low (loser)
                    phase_progress = iteration / 30.0
                    if is_gainer:
                        current = entry + (demo_high - entry) * phase_progress + noise
                    else:
                        current = entry + (demo_low - entry) * phase_progress + noise

                elif iteration <= 70:
                    # Phase 2: Oscillate between high and low
                    phase_progress = (iteration - 30) / 40.0
                    mid = (demo_high + demo_low) / 2.0
                    amplitude = (demo_high - demo_low) / 2.0
                    # Sine-wave oscillation
                    import math
                    osc = math.sin(phase_progress * math.pi * 2.5)
                    current = mid + amplitude * osc * 0.7 + noise

                else:
                    # Phase 3: Converge toward closing price (ltp)
                    phase_progress = (iteration - 70) / 30.0
                    prev_price = t.get("current_price", entry)
                    current = prev_price + (demo_ltp - prev_price) * phase_progress * 0.5 + noise

                # Clamp within day's actual range (with tiny buffer)
                current = max(demo_low * 0.998, min(current, demo_high * 1.002))
                t["current_price"] = round(current, 2)

            else:
                # Fallback: simple random drift model
                direction = 1 if random.random() < 0.6 else -1
                move_pct = random.uniform(0.1, 0.5)
                move = entry * move_pct / 100 * direction

                current = t.get("current_price", entry) + move
                # Clamp between SL - 1% and target + 1%
                current = max(sl * 0.99, min(current, target * 1.01))
                t["current_price"] = round(current, 2)

    def _fetch_live_prices(self) -> None:
        """Fetch live positions from broker and update current prices."""
        try:
            positions = self.broker.get_positions()
            pos_map = {p.get("tradingsymbol", ""): p for p in positions}
            for t in self._active_trades:
                sym = t.get("tradingsymbol", "")
                if sym in pos_map:
                    p = pos_map[sym]
                    t["current_price"] = p.get("buy_avg", t["entry_price"])
        except Exception as exc:
            logger.error("Failed to fetch positions: %s — will retry", exc)

    def _check_position(self, trade: dict) -> None:
        """Check a single position for target/SL/trailing/partial triggers."""
        current = trade.get("current_price", trade["entry_price"])
        entry = trade["entry_price"]
        target = trade["target_price"]
        sl = trade["stop_loss_price"]
        qty = trade["quantity"]

        # --- Stop loss hit ---
        if current <= sl:
            pnl = (current - entry) * qty
            trade["pnl"] = round(pnl, 2)
            trade["exit_price"] = current
            trade["status"] = PositionState.STOPPED_OUT.value
            self._update_db(trade, PositionState.STOPPED_OUT)
            if self.risk_manager:
                self.risk_manager.record_trade_closed(pnl)
            logger.info("🛑 %s STOPPED OUT @ ₹%.2f | P&L: ₹%.2f", trade["tradingsymbol"], current, pnl)
            return

        # --- Target hit ---
        if current >= target:
            pnl = (current - entry) * qty
            trade["pnl"] = round(pnl, 2)
            trade["exit_price"] = current
            trade["status"] = PositionState.CLOSED.value
            self._update_db(trade, PositionState.CLOSED)
            if self.risk_manager:
                self.risk_manager.record_trade_closed(pnl)
            logger.info("🎯 %s TARGET HIT @ ₹%.2f | P&L: ₹%.2f", trade["tradingsymbol"], current, pnl)
            if self.broker:
                try:
                    self.broker.place_order(
                        symbol=trade["tradingsymbol"],
                        exchange="NSE",
                        transaction_type="SELL",
                        order_type="MARKET",
                        product_type="INTRADAY",
                        quantity=trade["quantity"],
                        price=0.0,
                    )
                    logger.info("✅ %s target exit order placed at broker", trade["tradingsymbol"])
                except Exception as e:
                    logger.error("❌ %s target exit broker order failed: %s", trade["tradingsymbol"], e)
            return

        # --- Partial profit booking (only if not already partially booked) ---
        if trade["status"] == PositionState.OPEN.value:
            partial = calc_partial_book(entry, target, current, qty, self.config.partial_book_pct)
            if partial:
                partial_pnl = (current - entry) * partial["sell_qty"]
                trade["status"] = PositionState.PARTIAL_BOOKED.value
                trade["stop_loss_price"] = partial["new_sl"]  # breakeven
                trade["quantity"] = partial["remaining_qty"]
                trade["pnl"] = round(partial_pnl, 2)
                self._update_db(trade, PositionState.PARTIAL_BOOKED)
                logger.info(
                    "📊 %s PARTIAL BOOK: sold %d @ ₹%.2f, remaining %d, SL → ₹%.2f (breakeven)",
                    trade["tradingsymbol"], partial["sell_qty"], current,
                    partial["remaining_qty"], partial["new_sl"],
                )
                return

        # --- Trailing SL ---
        new_sl = calc_trailing_sl(entry, current, self.config.trailing_sl_trigger_pct)
        if new_sl and new_sl > sl:
            trade["stop_loss_price"] = round(new_sl, 2)
            logger.info("📈 %s trailing SL moved: ₹%.2f → ₹%.2f", trade["tradingsymbol"], sl, new_sl)
            if self.db:
                self._audit("SL_ADJUST", {"symbol": trade["tradingsymbol"], "old_sl": sl, "new_sl": new_sl})

    def _force_exit_all(self) -> None:
        """Force-exit all open positions."""
        for trade in self._active_trades:
            if trade["status"] not in (PositionState.OPEN.value, PositionState.PARTIAL_BOOKED.value):
                continue
            current = trade.get("current_price", trade["entry_price"])
            pnl = (current - trade["entry_price"]) * trade["quantity"]
            trade["pnl"] = round((trade.get("pnl", 0) or 0) + pnl, 2)
            trade["exit_price"] = current
            trade["status"] = PositionState.FORCE_EXITED.value
            self._update_db(trade, PositionState.FORCE_EXITED)
            if self.risk_manager:
                self.risk_manager.record_trade_closed(pnl)
            logger.info("⏰ %s FORCE EXITED @ ₹%.2f | P&L: ₹%.2f", trade["tradingsymbol"], current, trade["pnl"])
            if self.broker:
                try:
                    self.broker.place_order(
                        symbol=trade["tradingsymbol"],
                        exchange="NSE",
                        transaction_type="SELL",
                        order_type="MARKET",
                        product_type="INTRADAY",
                        quantity=trade["quantity"],
                        price=0.0,
                    )
                    logger.info("✅ %s force exit order placed at broker", trade["tradingsymbol"])
                except Exception as e:
                    logger.error("❌ %s force exit broker order failed: %s", trade["tradingsymbol"], e)

    def _calc_unrealized_pnl(self, trade: dict) -> float:
        current = trade.get("current_price", trade["entry_price"])
        return (current - trade["entry_price"]) * trade["quantity"]

    def _update_db(self, trade: dict, new_state: PositionState) -> None:
        if self.db and trade.get("trade_id"):
            self.db.update_intraday_trade(
                trade["trade_id"],
                status=new_state.value,
                exit_price=trade.get("exit_price"),
                pnl=trade.get("pnl"),
                stop_loss_price=trade.get("stop_loss_price"),
                quantity=trade.get("quantity"),
            )

    def _audit(self, event_type: str, details: dict, trade_id: int | None = None) -> None:
        if self.db:
            try:
                self.db.insert_audit_log(event_type, json.dumps(details, default=str), trade_id)
            except Exception:
                pass
