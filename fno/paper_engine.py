"""Paper Trade Engine — virtual capital simulation for F&O strategies.

Simulates order fills at LTP from the option chain, tracks virtual capital,
deducts estimated margin on open, releases on close, and enforces all the
same risk rules as live trading.  All trades stored with mode="PAPER".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.models import FnOStrategySetup, OptionChainSnapshot

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


class Paper_Trade_Engine:
    """Virtual capital simulation engine for F&O paper trading."""

    def __init__(self, config: FnO_Config, db: DBManager) -> None:
        self.config = config
        self.db = db
        self.capital = config.paper_capital
        self.used_margin: float = 0.0
        self._positions: list[dict] = []  # Active paper positions

    @property
    def available_margin(self) -> float:
        """Available virtual margin."""
        return max(0.0, self.capital - self.used_margin)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_fill(
        self,
        strategy: FnOStrategySetup,
        chain: OptionChainSnapshot | None = None,
    ) -> int | None:
        """Simulate order fills for a strategy at LTP from option chain.

        Parameters
        ----------
        strategy : FnOStrategySetup
            Validated strategy to simulate.
        chain : OptionChainSnapshot | None
            Current option chain for LTP lookup. If None, uses leg entry_price.

        Returns
        -------
        int | None
            The strategy_id from the database, or None on failure.
        """
        # Build LTP lookup from chain
        ltp_map: dict[tuple[float, str], float] = {}
        if chain:
            for s in chain.strikes:
                ltp_map[(s.strike_price, s.option_type)] = s.ltp

        # Estimate margin for the strategy
        estimated_margin = self._estimate_margin(strategy)
        if estimated_margin > self.available_margin:
            logger.warning(
                "Paper: insufficient margin — need ₹%.0f, have ₹%.0f",
                estimated_margin, self.available_margin,
            )
            return None

        # Deduct margin
        self.used_margin += estimated_margin

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
                    "expiry_date": leg.expiry_date,
                    "lot_size": leg.lot_size,
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
            status="OPEN",
            entry_time=now.isoformat(),
            mode="PAPER",
            confidence_score=strategy.confidence_score,
            confluence_score=strategy.confluence_score,
            rationale=strategy.rationale,
        )

        if strategy_id is None:
            self.used_margin -= estimated_margin
            return None

        # Insert individual leg trades
        for leg in strategy.legs:
            fill_price = ltp_map.get(
                (leg.strike_price, leg.option_type), leg.entry_price
            )
            self.db.insert_fno_trade(
                trade_date=now.strftime("%Y-%m-%d"),
                timestamp=now.isoformat(),
                index_name=leg.index,
                tradingsymbol=f"PAPER_{leg.index}_{leg.strike_price}_{leg.option_type}",
                option_type=leg.option_type,
                strike_price=leg.strike_price,
                expiry_date=leg.expiry_date,
                action=leg.transaction_type,
                order_type="MARKET",
                quantity=leg.quantity,
                lots=leg.num_lots,
                price=fill_price,
                trigger_price=0,
                broker_order_id=f"PAPER_{strategy_id}_{leg.strike_price}",
                broker_name=self.config.broker,
                status="OPEN",
                entry_price=fill_price,
                mode="PAPER",
                strategy_id=strategy_id,
            )

        # Track position
        self._positions.append({
            "strategy_id": strategy_id,
            "strategy": strategy,
            "margin_used": estimated_margin,
            "entry_time": now,
        })

        logger.info(
            "Paper fill: %s %s — margin ₹%.0f, remaining ₹%.0f",
            strategy.strategy_type, strategy.index,
            estimated_margin, self.available_margin,
        )

        return strategy_id

    def close_position(
        self,
        strategy_id: int,
        exit_prices: dict[tuple[float, str], float] | None = None,
    ) -> float:
        """Close a paper position and compute realized P&L.

        Parameters
        ----------
        strategy_id : int
            The strategy to close.
        exit_prices : dict | None
            Map of (strike, option_type) → exit_price. If None, uses entry price (0 P&L).

        Returns
        -------
        float
            Realized P&L for the strategy.
        """
        exit_prices = exit_prices or {}
        now = datetime.now(IST)

        # Find the position
        pos = None
        for p in self._positions:
            if p["strategy_id"] == strategy_id:
                pos = p
                break

        if pos is None:
            logger.warning("Paper position %d not found", strategy_id)
            return 0.0

        strategy: FnOStrategySetup = pos["strategy"]
        total_pnl = 0.0

        for leg in strategy.legs:
            exit_price = exit_prices.get(
                (leg.strike_price, leg.option_type), leg.entry_price
            )
            if leg.is_sell:
                leg_pnl = (leg.entry_price - exit_price) * leg.quantity
            else:
                leg_pnl = (exit_price - leg.entry_price) * leg.quantity
            total_pnl += leg_pnl

        # Release margin
        self.used_margin = max(0.0, self.used_margin - pos["margin_used"])

        # Update DB
        self.db.update_fno_strategy(
            strategy_id,
            status="CLOSED",
            exit_time=now.isoformat(),
            realized_pnl=round(total_pnl, 2),
        )

        # Update capital
        self.capital += total_pnl

        # Remove from active positions
        self._positions = [p for p in self._positions if p["strategy_id"] != strategy_id]

        logger.info(
            "Paper close: strategy %d — P&L ₹%.2f, capital ₹%.0f",
            strategy_id, total_pnl, self.capital,
        )

        return round(total_pnl, 2)

    def get_positions(self) -> list[dict]:
        """Return current paper positions in broker-like format."""
        positions = []
        for pos in self._positions:
            strategy: FnOStrategySetup = pos["strategy"]
            for leg in strategy.legs:
                positions.append({
                    "tradingsymbol": f"PAPER_{leg.index}_{leg.strike_price}_{leg.option_type}",
                    "index_name": leg.index,
                    "option_type": leg.option_type,
                    "strike_price": leg.strike_price,
                    "expiry_date": leg.expiry_date,
                    "quantity": leg.quantity if not leg.is_sell else -leg.quantity,
                    "buy_avg": leg.entry_price if not leg.is_sell else 0,
                    "sell_avg": leg.entry_price if leg.is_sell else 0,
                    "pnl": 0.0,
                    "product_type": "NRML",
                    "strategy_id": pos["strategy_id"],
                })
        return positions

    def get_margins(self) -> dict:
        """Return paper margin info in broker-like format."""
        return {
            "available_margin": self.available_margin,
            "used_margin": self.used_margin,
            "span_margin": self.used_margin * 0.7,
            "exposure_margin": self.used_margin * 0.3,
        }

    # ------------------------------------------------------------------
    # Margin Estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_margin(strategy: FnOStrategySetup) -> float:
        """Estimate SPAN + exposure margin for a strategy.

        Uses simplified approximation:
        - Defined risk (spreads, iron condors): max_loss × 1.2
        - Undefined risk (strangles, straddles): max_loss × 2.0
        - Directional buys: premium paid
        """
        stype = strategy.strategy_type.upper()

        if stype in ("IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            return abs(strategy.max_loss) * 1.2

        if stype in ("SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
                      "NAKED_CE", "NAKED_PE"):
            return abs(strategy.max_loss) * 2.0

        # Directional buys: premium paid
        return abs(strategy.net_premium)
