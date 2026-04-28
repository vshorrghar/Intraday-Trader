"""F&O Order Executor — multi-leg strategy order placement.

Places all legs of a strategy through the BrokerClient ABC, starting with
SELL legs (premium collection) then BUY legs.  Rolls back on partial failure.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fno.symbols import Symbol_Builder

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.models import FnOStrategySetup, StrategyLeg
    from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

LIVE_WARNING_BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║  ⚠️  LIVE F&O TRADING MODE — REAL MONEY AT RISK                ║
║  F&O trading involves significant risk of loss.                 ║
║  Naked option selling can result in losses exceeding capital.   ║
╚══════════════════════════════════════════════════════════════════╝
"""


class FnO_Order_Executor:
    """Places multi-leg F&O strategy orders through the broker."""

    def __init__(
        self,
        config: FnO_Config,
        db: DBManager,
        broker: BrokerClient | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.broker = broker
        self._warned_live = False

    def execute_strategy(
        self,
        strategy: FnOStrategySetup,
        broker: BrokerClient | None = None,
    ) -> int | None:
        """Execute all legs of a strategy.

        Places SELL legs first, then BUY legs.  On partial failure,
        attempts to cancel all previously placed legs.

        Parameters
        ----------
        strategy : FnOStrategySetup
            Validated strategy to execute.
        broker : BrokerClient | None
            Override broker (uses self.broker if None).

        Returns
        -------
        int | None
            The strategy_id from the database, or None on failure.
        """
        broker = broker or self.broker
        is_live = self.config.mode == "live"

        # Live mode warning banner
        if is_live and not self._warned_live:
            logger.warning(LIVE_WARNING_BANNER)
            print(LIVE_WARNING_BANNER)
            self._warned_live = True

        # Wait entry_delay_minutes after 9:15 AM
        self._wait_entry_delay()

        # Insert strategy into DB
        now = datetime.now(IST)
        strategy_id = self.db.insert_fno_strategy(
            trade_date=now.strftime("%Y-%m-%d"),
            timestamp=now.isoformat(),
            strategy_type=strategy.strategy_type,
            index_name=strategy.index,
            legs_json=json.dumps([
                {
                    "strike": leg.strike_price,
                    "option_type": leg.option_type,
                    "transaction_type": leg.transaction_type,
                    "num_lots": leg.num_lots,
                    "entry_price": leg.entry_price,
                }
                for leg in strategy.legs
            ]),
            net_premium=strategy.net_premium,
            max_profit=strategy.max_profit,
            max_loss=strategy.max_loss,
            net_delta=strategy.net_delta,
            net_gamma=strategy.net_gamma,
            net_theta=strategy.net_theta,
            net_vega=strategy.net_vega,
            status="PENDING",
            entry_time=now.isoformat(),
            mode="LIVE" if is_live else "PAPER",
            confidence_score=strategy.confidence_score,
            confluence_score=strategy.confluence_score,
            rationale=strategy.rationale,
        )

        if strategy_id is None:
            logger.error("Failed to insert strategy into DB")
            return None

        # Sort legs: SELL first, then BUY
        sell_legs = [l for l in strategy.legs if l.is_sell]
        buy_legs = [l for l in strategy.legs if not l.is_sell]
        ordered_legs = sell_legs + buy_legs

        placed_orders: list[dict] = []  # {"order_id": str, "trade_id": int, "leg": StrategyLeg}

        for leg in ordered_legs:
            try:
                result = self._place_leg(leg, broker, strategy_id, is_live)
                if result and result.get("broker_order_id"):
                    placed_orders.append(result)
                    self.db.insert_audit_log(
                        "FNO_ORDER_PLACED",
                        json.dumps({
                            "strategy_id": strategy_id,
                            "tradingsymbol": leg.tradingsymbol or f"{leg.index}_{leg.strike_price}_{leg.option_type}",
                            "transaction_type": leg.transaction_type,
                            "quantity": leg.quantity,
                            "price": leg.entry_price,
                            "broker_order_id": result.get("broker_order_id", ""),
                        }),
                    )
                else:
                    raise RuntimeError(f"Order placement returned no order_id for {leg}")
            except Exception as exc:
                logger.error("Leg placement failed: %s — rolling back", exc)
                self.db.insert_audit_log(
                    "FNO_ERROR",
                    json.dumps({
                        "error": f"Leg failed: {exc}",
                        "strategy_id": strategy_id,
                    }),
                )
                # Rollback: cancel all previously placed legs
                self._rollback(placed_orders, broker, is_live)
                self.db.update_fno_strategy(strategy_id, status="CLOSED")
                return None

        # All legs placed successfully
        self.db.update_fno_strategy(strategy_id, status="OPEN")
        logger.info(
            "Strategy %s (%s) executed — %d legs placed",
            strategy.strategy_type, strategy.index, len(ordered_legs),
        )
        return strategy_id

    def _place_leg(
        self,
        leg: StrategyLeg,
        broker: BrokerClient | None,
        strategy_id: int,
        is_live: bool,
    ) -> dict:
        """Place a single leg order."""
        # Build trading symbol
        expiry = datetime.strptime(leg.expiry_date, "%Y-%m-%d").date()
        broker_name = self.config.broker.lower()

        if leg.option_type in ("CE", "PE"):
            if broker_name == "dhan":
                tradingsymbol = Symbol_Builder.build_dhan(
                    leg.index, expiry, leg.strike_price, leg.option_type,
                )
            else:
                tradingsymbol = Symbol_Builder.build_zerodha(
                    leg.index, expiry, leg.strike_price, leg.option_type,
                )
        else:
            # Futures
            if broker_name == "dhan":
                tradingsymbol = Symbol_Builder.build_futures_dhan(leg.index, expiry)
            else:
                tradingsymbol = Symbol_Builder.build_futures_zerodha(leg.index, expiry)

        leg.tradingsymbol = tradingsymbol

        # Insert trade into DB
        now = datetime.now(IST)
        trade_id = self.db.insert_fno_trade(
            trade_date=now.strftime("%Y-%m-%d"),
            timestamp=now.isoformat(),
            index_name=leg.index,
            tradingsymbol=tradingsymbol,
            option_type=leg.option_type,
            strike_price=leg.strike_price,
            expiry_date=leg.expiry_date,
            action=leg.transaction_type,
            order_type="MARKET",
            quantity=leg.quantity,
            lots=leg.num_lots,
            price=leg.entry_price,
            trigger_price=0,
            broker_name=self.config.broker,
            status="PENDING",
            entry_price=leg.entry_price,
            mode="LIVE" if is_live else "PAPER",
            strategy_id=strategy_id,
        )

        if not is_live or broker is None:
            # Paper mode — simulate fill
            broker_order_id = f"PAPER_{trade_id}"
            if trade_id:
                self.db.update_fno_trade(
                    trade_id,
                    status="OPEN",
                    broker_order_id=broker_order_id,
                )
            return {"broker_order_id": broker_order_id, "trade_id": trade_id, "leg": leg}

        # Live mode — place real order
        exchange = "NSE_FNO" if broker_name == "dhan" else "NFO"
        result = broker.place_fno_order(
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            transaction_type=leg.transaction_type,
            order_type="MARKET",
            product_type="NRML",
            quantity=leg.quantity,
            price=leg.entry_price,
        )

        broker_order_id = result.get("broker_order_id", "")
        if trade_id:
            self.db.update_fno_trade(
                trade_id,
                status="OPEN" if broker_order_id else "error",
                broker_order_id=broker_order_id,
            )

        result["trade_id"] = trade_id
        result["leg"] = leg
        return result

    def _rollback(
        self,
        placed_orders: list[dict],
        broker: BrokerClient | None,
        is_live: bool,
    ) -> None:
        """Cancel all previously placed legs on partial failure."""
        for order in placed_orders:
            order_id = order.get("broker_order_id", "")
            trade_id = order.get("trade_id")
            if not order_id or order_id.startswith("PAPER_"):
                if trade_id:
                    self.db.update_fno_trade(trade_id, status="CLOSED")
                continue

            if is_live and broker:
                try:
                    broker.cancel_order(order_id)
                    logger.info("Rolled back order %s", order_id)
                except Exception as exc:
                    logger.error("Rollback failed for order %s: %s", order_id, exc)

            if trade_id:
                self.db.update_fno_trade(trade_id, status="CLOSED")

            self.db.insert_audit_log(
                "FNO_ORDER_CANCELLED",
                json.dumps({"broker_order_id": order_id, "reason": "rollback"}),
            )

    def _wait_entry_delay(self) -> None:
        """Wait until entry_delay_minutes after 9:15 AM IST."""
        now = datetime.now(IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        earliest_entry = market_open + timedelta(minutes=self.config.entry_delay_minutes)

        if now < earliest_entry:
            wait_seconds = (earliest_entry - now).total_seconds()
            if wait_seconds > 0:
                logger.info(
                    "Waiting %.0f seconds for entry delay (until %s)",
                    wait_seconds, earliest_entry.strftime("%H:%M"),
                )
                time.sleep(min(wait_seconds, 1))  # Cap at 1s for non-blocking in paper mode
