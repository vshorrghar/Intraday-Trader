"""
Swing executor — places CNC Super Orders (entry + SL + target at broker).

CRITICAL SAFETY: SL lives at Dhan broker, NOT in our software monitor.
If EC2 dies, cron fails, or monitor crashes — the SL still protects capital.

Uses Dhan Super Order API: POST /v2/super/orders
  - Entry leg: CNC BUY at limit price
  - Stop Loss leg: rests at broker, triggers automatically
  - Target leg: rests at broker, triggers automatically

The monitor is a BACKUP — it checks time-stops and can modify the SL,
but the primary SL protection is at the broker.
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from swing.models import SwingTradeSetup, SwingPositionState, SwingConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
SUPER_ORDER_URL = "https://api.dhan.co/v2/super/orders"


class SwingExecutor:
    """Execute swing CNC Super Orders (entry + broker SL + target)."""

    def __init__(self, config: SwingConfig, broker=None, db=None, dry_run: bool = True):
        self.config = config
        self.broker = broker
        self.db = db
        self.dry_run = dry_run
        self._placed_trades = []
        self._total_deployed = 0.0

    def _tick_align(self, price: float) -> float:
        """Round to NSE tick size Rs.0.05."""
        return round(round(price * 20) / 20, 2)

    def _get_security_id(self, symbol: str) -> str | None:
        """Look up Dhan security ID for a symbol."""
        try:
            with open("config/nse_security_ids.json") as f:
                ids = json.load(f)
            return ids.get(symbol, None)
        except Exception:
            return None

    def _place_super_order(self, trade: SwingTradeSetup) -> dict | None:
        """Place Dhan Super Order: entry + SL + target in ONE atomic request.

        The SL rests at Dhan broker — survives EC2 death.
        Super Orders are atomic: if rejected, NOTHING fills (no orphan positions).
        """
        entry_price = self._tick_align(trade.entry_price * 1.003)
        sl_price = self._tick_align(trade.stop_loss_price)
        target_price = self._tick_align(trade.target_price)

        # HARD GUARD: NEVER place a CNC order without a real SL (the Rs910 fix)
        if sl_price <= 0:
            logger.error(
                "ZERO-SL GUARD: %s has stopLossPrice=%.2f — REFUSING to place order. "
                "No CNC position without broker SL. Ever.", trade.nse_symbol, sl_price)
            self._audit("ZERO_SL_BLOCKED", {"symbol": trade.nse_symbol, "sl_price": sl_price})
            return None

        if target_price <= entry_price:
            logger.error("INVALID TARGET: %s target=%.2f <= entry=%.2f — skipping",
                         trade.nse_symbol, target_price, entry_price)
            return None

        sec_id = self._get_security_id(trade.nse_symbol)
        if not sec_id:
            logger.error("No security ID for %s", trade.nse_symbol)
            return None

        payload = {
            "transactionType": "BUY",
            "exchangeSegment": "NSE_EQ",
            "productType": "CNC",
            "orderType": "LIMIT",
            "securityId": str(sec_id),
            "quantity": trade.quantity,
            "price": entry_price,
            "targetPrice": target_price,
            "stopLossPrice": sl_price,
            "trailingJump": 0,
        }

        if self.dry_run:
            order_id = f"DRY-SUPER-{int(time.time())}"
            logger.info("DryRun Super Order: %s qty=%d entry=%.2f sl=%.2f target=%.2f",
                        trade.nse_symbol, trade.quantity, entry_price, sl_price, target_price)
            return {
                "order_id": order_id,
                "status": "PENDING",
                "entry_price": entry_price,
                "sl_price": sl_price,
                "target_price": target_price,
                "payload": payload,
            }

        # LIVE: call Dhan Super Order API
        try:
            import requests
            headers = self.broker._headers()
            resp = requests.post(SUPER_ORDER_URL, headers=headers, json=payload, timeout=15)

            if resp.status_code in (200, 201):
                data = resp.json()
                order_id = str(data.get("orderId", ""))
                order_status = data.get("orderStatus", "UNKNOWN")
                logger.info("Super Order placed: %s id=%s status=%s (SL at broker: Rs.%.2f)",
                            trade.nse_symbol, order_id, order_status, sl_price)
                return {
                    "order_id": order_id,
                    "status": order_status,
                    "entry_price": entry_price,
                    "sl_price": sl_price,
                    "target_price": target_price,
                    "payload": payload,
                }
            else:
                error_msg = resp.text[:200]
                logger.error("Super Order REJECTED for %s: HTTP %d — %s",
                             trade.nse_symbol, resp.status_code, error_msg)
                # Super Orders are ATOMIC on Dhan: rejection = nothing fills.
                # No orphan position possible. Safe to return None.
                self._audit("SUPER_ORDER_REJECTED", {
                    "symbol": trade.nse_symbol,
                    "http_status": resp.status_code,
                    "error": error_msg,
                })
                return None

        except Exception as e:
            logger.error("Super Order exception for %s: %s", trade.nse_symbol, e)
            return None

    def _place_single_trade(self, trade: SwingTradeSetup, mode: str) -> dict | None:
        """Place a single swing trade via Super Order."""
        result = self._place_super_order(trade)
        if not result:
            return None

        order_id = result["order_id"]
        actual_entry = result["entry_price"]
        actual_sl = result["sl_price"]
        actual_target = result["target_price"]
        deployed = actual_entry * trade.quantity
        self._total_deployed += deployed

        # Store in DB
        trade_id = None
        if self.db:
            try:
                trade_id = self.db.insert_swing_trade(
                    symbol=trade.nse_symbol,
                    nse_symbol=trade.nse_symbol,
                    entry_price=actual_entry,
                    entry_date=datetime.now(IST).strftime("%Y-%m-%d"),
                    target_price=actual_target,
                    stop_loss_price=actual_sl,
                    quantity=trade.quantity,
                    status=SwingPositionState.OPEN.value,
                    confidence_score=trade.confidence_score,
                    strategy_type=trade.strategy_type,
                )
            except Exception as e:
                logger.error("DB insert failed for %s: %s", trade.nse_symbol, e)

        record = {
            "trade_id": trade_id,
            "symbol": trade.nse_symbol,
            "nse_symbol": trade.nse_symbol,
            "entry_price": actual_entry,
            "target_price": actual_target,
            "stop_loss_price": actual_sl,
            "quantity": trade.quantity,
            "super_order_id": order_id,
            "confidence_score": trade.confidence_score,
            "strategy_type": trade.strategy_type,
            "status": SwingPositionState.OPEN.value,
            "mode": mode,
            "broker_sl_confirmed": True,
        }

        self._audit("SWING_SUPER_ORDER_ENTRY", {
            "symbol": trade.nse_symbol,
            "super_order_id": order_id,
            "qty": trade.quantity,
            "entry": actual_entry,
            "target": actual_target,
            "sl_at_broker": actual_sl,
            "deployed": deployed,
            "total_deployed": self._total_deployed,
        }, trade_id=trade_id)

        logger.info(
            "📋 SWING SUPER ORDER: %s %d × Rs.%.2f | Target Rs.%.2f | SL Rs.%.2f (BROKER-HELD) | %s",
            trade.nse_symbol, trade.quantity, actual_entry,
            actual_target, actual_sl,
            "🧪 DRY-RUN" if mode == "DRY_RUN" else "🔴 LIVE",
        )
        return record

    def execute_trades(self, trades: list, risk_manager=None) -> list:
        """Place Super Orders, enforcing capital limit."""
        placed = []
        mode = "DRY_RUN" if self.dry_run else "LIVE"
        capital_limit = self.config.swing_capital_limit

        self._total_deployed = self._get_existing_deployed()

        for trade in trades:
            # CAPITAL LIMIT ENFORCEMENT (Blocker 2 fix)
            projected_cost = trade.entry_price * trade.quantity
            if self._total_deployed + projected_cost > capital_limit:
                logger.warning(
                    "CAPITAL LIMIT: %s would deploy Rs.%.0f (total Rs.%.0f > limit Rs.%.0f) — BLOCKED",
                    trade.nse_symbol, projected_cost,
                    self._total_deployed + projected_cost, capital_limit,
                )
                continue

            if risk_manager:
                can_enter, reason = risk_manager.can_enter_trade(trade)
                if can_enter is False:
                    logger.warning("Risk gate blocked %s: %s", trade.nse_symbol, reason)
                    continue

            try:
                record = self._place_single_trade(trade, mode)
                if record:
                    placed.append(record)
            except Exception as exc:
                logger.error("Failed to place swing order for %s: %s", trade.nse_symbol, exc)
                continue

        self._placed_trades = placed
        logger.info("Placed %d / %d swing orders (%s). Deployed: Rs.%.0f / Rs.%.0f",
                    len(placed), len(trades), mode, self._total_deployed, capital_limit)
        return placed

    def _get_existing_deployed(self) -> float:
        """Get currently deployed capital from open positions in DB."""
        if not self.db:
            return 0.0
        try:
            open_trades = self.db.get_open_swing_trades() or []
            return sum(
                float(t.get("entry_price", 0)) * int(t.get("quantity", 0))
                for t in open_trades
            )
        except Exception:
            return 0.0

    @property
    def placed_trades(self) -> list:
        return self._placed_trades

    @property
    def total_deployed(self) -> float:
        return self._total_deployed

    def _audit(self, event_type: str, details: dict, trade_id=None):
        if self.db:
            try:
                self.db.insert_swing_audit(event_type, json.dumps(details, default=str), trade_id)
            except Exception:
                pass
