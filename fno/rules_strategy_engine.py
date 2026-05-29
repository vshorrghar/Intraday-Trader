"""F&O Rules-Based Strategy Engine — deterministic, no LLM.

Replaces LLM-driven strategy selection with pure quantitative rules.
Same inputs (option chain, quant signals, VIX) → deterministic output.

PAPER PHASE: Relaxed filters for flow. After 30+ trades,
we'll evaluate which filters to tighten based on real data.

The goal is enough trades to know if Iron Condors actually work
in current Indian market conditions.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fno.models import (
    FnOStrategySetup,
    MarketRegime,
    QuantSignals,
    StrategyLeg,
)

if TYPE_CHECKING:
    from fno.config import FnO_Config
    from fno.greeks import FnO_Greeks_Calculator
    from fno.models import OptionChainSnapshot

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Lot sizes per index
LOT_SIZES = {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 25}

# Strike intervals per index
STRIKE_INTERVALS = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}


# ═══════════════════════════════════════════════════════════════
# STRATEGY DECISION TREE
# ═══════════════════════════════════════════════════════════════


def select_strategy_type(
    vix: float,
    regime: MarketRegime,
    signals: QuantSignals,
    dte: int,
    is_event_day: bool = False,
) -> str | None:
    """Deterministic strategy selection.

    PAPER PHASE: Relaxed filters for flow. After 30+ trades,
    we'll evaluate which filters to tighten based on real data.

    Returns strategy type string or None for NO_TRADE.
    """
    ivp = signals.iv_percentile
    vrp = signals.vrp
    confluence = signals.confluence_score

    # Gate 1: Hard skip conditions
    # 2026-05-28: VIX max stays 25 (unchanged — already relaxed)
    if vix > 25:
        logger.info("RULES: NO_TRADE — VIX %.1f > 25", vix)
        return None

    # 2026-05-28: Confluence min relaxed 12 → 8 (universal relaxation pass)
    if confluence < 8:
        logger.info("RULES: NO_TRADE — confluence %.1f < 8", confluence)
        return None

    # Gate 2: Strategy selection
    # 2026-05-28: Universal relaxation — IVP 50→40, VRP 1.0→0.5, DTE 4-10→3-12
    # 2026-05-28: Regime expanded — SIDEWAYS + HIGH_VOLATILITY (VIX 20-25 still allows IC)
    # RANGING and UNCLEAR map to SIDEWAYS in classifier. HIGH_VOLATILITY added because
    # IC works in any low-movement regime — VIX 20-25 just needs wider strikes (handled by sigma).
    if regime in (MarketRegime.SIDEWAYS, MarketRegime.HIGH_VOLATILITY) and ivp >= 40 and vrp >= 0.5 and 3 <= dte <= 12:
        logger.info(
            "RULES: IRON_CONDOR — regime=%s, IVP=%.1f, VRP=%.1f, DTE=%d",
            regime.value, ivp, vrp, dte,
        )
        return "IRON_CONDOR"

    # 2026-05-28: DTE relaxed 5-14 → 4-15
    if regime == MarketRegime.TRENDING_UP and ivp >= 45 and 4 <= dte <= 15:
        logger.info(
            "RULES: BULL_PUT_SPREAD — regime=%s, IVP=%.1f, DTE=%d",
            regime.value, ivp, dte,
        )
        return "BULL_PUT_SPREAD"

    # 2026-05-28: DTE relaxed 5-14 → 4-15
    if regime == MarketRegime.TRENDING_DOWN and ivp >= 45 and 4 <= dte <= 15:
        logger.info(
            "RULES: BEAR_CALL_SPREAD — regime=%s, IVP=%.1f, DTE=%d",
            regime.value, ivp, dte,
        )
        return "BEAR_CALL_SPREAD"

    if is_event_day and ivp <= 30:
        logger.info(
            "RULES: LONG_STRADDLE — event_day=True, IVP=%.1f <= 30",
            ivp,
        )
        return "LONG_STRADDLE"

    logger.info(
        "RULES: NO_TRADE — no rule matched (regime=%s, IVP=%.1f, VRP=%.1f, DTE=%d)",
        regime.value, ivp, vrp, dte,
    )
    return None


# ═══════════════════════════════════════════════════════════════
# STRIKE SELECTION
# ═══════════════════════════════════════════════════════════════


def select_iron_condor_strikes(
    chain: "OptionChainSnapshot",
    greeks_calc: "FnO_Greeks_Calculator",
    sigma_multiplier: float = 0.5,  # 2026-05-28: relaxed 0.7 → 0.5 (universal relaxation pass)
    wing_width_pts: int = 0,
) -> dict | None:
    """Select Iron Condor strikes deterministically.

    Short strikes at ~0.7-sigma each side of spot.
    Wings 200-300pts away (NIFTY/FINNIFTY) or 300-500pts (BANKNIFTY).

    Returns dict with ce_sell, ce_buy, pe_sell, pe_buy strikes, or None.
    """
    spot = chain.spot_price
    index = chain.index
    interval = STRIKE_INTERVALS.get(index, 50)

    # Compute 1-sigma move from ATM IV
    atm_ivs = [s.iv for s in chain.strikes if s.strike_price == chain.atm_strike and s.iv > 0]
    atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else 15.0

    # Compute DTE for sigma calculation
    try:
        expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d")
        now = datetime.now(IST)
        dte_days = max(1, (expiry_dt.date() - now.date()).days)
    except Exception:
        dte_days = 7

    # 1-sigma move = spot × IV × sqrt(DTE/365)
    one_sigma = spot * (atm_iv / 100) * math.sqrt(dte_days / 365)
    target_distance = one_sigma * sigma_multiplier

    # Wing width: 200pts for NIFTY/FINNIFTY, 300pts for BANKNIFTY
    if wing_width_pts <= 0:
        wing_width_pts = 300 if index == "BANKNIFTY" else 200

    # Round to nearest strike interval
    ce_sell_strike = _round_to_strike(spot + target_distance, interval, direction="up")
    pe_sell_strike = _round_to_strike(spot - target_distance, interval, direction="down")
    ce_buy_strike = ce_sell_strike + wing_width_pts
    pe_buy_strike = pe_sell_strike - wing_width_pts

    # Validate all strikes exist in chain
    valid_strikes = {s.strike_price for s in chain.strikes}
    for strike in [ce_sell_strike, ce_buy_strike, pe_sell_strike, pe_buy_strike]:
        if strike not in valid_strikes:
            logger.warning("Strike %.0f not in chain for %s — adjusting", strike, index)
            # Find nearest valid strike
            nearest = min(valid_strikes, key=lambda x: abs(x - strike))
            if strike == ce_sell_strike:
                ce_sell_strike = nearest
            elif strike == ce_buy_strike:
                ce_buy_strike = nearest
            elif strike == pe_sell_strike:
                pe_sell_strike = nearest
            elif strike == pe_buy_strike:
                pe_buy_strike = nearest

    # Sanity: short strikes must be between spot and wings
    if not (pe_buy_strike < pe_sell_strike < spot < ce_sell_strike < ce_buy_strike):
        logger.warning(
            "Iron Condor strikes invalid: PE_buy=%.0f PE_sell=%.0f spot=%.0f CE_sell=%.0f CE_buy=%.0f",
            pe_buy_strike, pe_sell_strike, spot, ce_sell_strike, ce_buy_strike,
        )
        return None

    return {
        "ce_sell": ce_sell_strike,
        "ce_buy": ce_buy_strike,
        "pe_sell": pe_sell_strike,
        "pe_buy": pe_buy_strike,
    }


def select_spread_strikes(
    chain: "OptionChainSnapshot",
    greeks_calc: "FnO_Greeks_Calculator",
    spread_type: str,
    target_short_delta: float = 0.30,
    target_long_delta: float = 0.15,
) -> dict | None:
    """Select spread strikes by delta targeting.

    BULL_PUT_SPREAD: sell higher put, buy lower put.
    BEAR_CALL_SPREAD: sell lower call, buy higher call.

    Returns dict with short_strike, long_strike, or None.
    """
    spot = chain.spot_price
    index = chain.index
    interval = STRIKE_INTERVALS.get(index, 50)

    try:
        expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d")
        now = datetime.now(IST)
        tte = max((expiry_dt - now).total_seconds() / (365.25 * 86400), 0.001)
    except Exception:
        tte = 7 / 365.25

    if spread_type == "BULL_PUT_SPREAD":
        option_type = "PE"
        # Find put with delta closest to -0.30
        best_short = _find_strike_by_delta(
            chain, greeks_calc, "PE", target_short_delta, spot, tte,
        )
        best_long = _find_strike_by_delta(
            chain, greeks_calc, "PE", target_long_delta, spot, tte,
        )
        if best_short and best_long and best_long < best_short:
            return {"short_strike": best_short, "long_strike": best_long, "option_type": "PE"}

    elif spread_type == "BEAR_CALL_SPREAD":
        # Find call with delta closest to 0.30
        best_short = _find_strike_by_delta(
            chain, greeks_calc, "CE", target_short_delta, spot, tte,
        )
        best_long = _find_strike_by_delta(
            chain, greeks_calc, "CE", target_long_delta, spot, tte,
        )
        if best_short and best_long and best_long > best_short:
            return {"short_strike": best_short, "long_strike": best_long, "option_type": "CE"}

    return None


def select_straddle_strikes(chain: "OptionChainSnapshot") -> dict:
    """Select ATM strike for straddle. Simple."""
    return {"atm_strike": chain.atm_strike}


# ═══════════════════════════════════════════════════════════════
# EXIT RULES (IMPROVED — captures more theta)
# ═══════════════════════════════════════════════════════════════

# These replace the old exit thresholds that were capturing only 5-10% of premium.

EXIT_RULES = {
    "IRON_CONDOR": {
        "profit_target_pct": 50,    # Exit at 50% of max_profit (was ~10%)
        "loss_exit_multiplier": 1.5,  # Exit at 1.5× max_profit loss
        "time_exit_dte": 1,         # Exit 1 day before expiry
        "max_checks_per_day": 4,    # Don't over-monitor
    },
    "BULL_PUT_SPREAD": {
        "profit_target_pct": 70,    # Exit at 70% of credit
        "loss_exit_multiplier": 1.0,  # Exit at full max_loss
        "time_exit_dte": 2,         # Exit 2 days before expiry
        "max_checks_per_day": 4,
    },
    "BEAR_CALL_SPREAD": {
        "profit_target_pct": 70,
        "loss_exit_multiplier": 1.0,
        "time_exit_dte": 2,
        "max_checks_per_day": 4,
    },
    "SHORT_STRADDLE": {
        "profit_target_pct": 30,    # Exit at 30% of credit
        "loss_exit_multiplier": 2.0,  # Exit at 2× credit loss
        "time_exit_dte": 0,         # Exit expiry day 3:30 PM
        "max_checks_per_day": 4,
    },
    "LONG_STRADDLE": {
        "profit_target_pct": 50,    # Exit at 50% gain
        "loss_exit_multiplier": 0.3,  # Exit at 30% premium loss
        "time_exit_dte": 1,
        "max_checks_per_day": 4,
    },
}


def get_exit_rules(strategy_type: str) -> dict:
    """Get exit rules for a strategy type. Falls back to Iron Condor defaults."""
    return EXIT_RULES.get(strategy_type, EXIT_RULES["IRON_CONDOR"])


# ═══════════════════════════════════════════════════════════════
# MAIN ENGINE CLASS
# ═══════════════════════════════════════════════════════════════


class FnO_Rules_Strategy_Engine:
    """Deterministic F&O strategy engine. No LLM calls."""

    def __init__(
        self,
        config: "FnO_Config",
        greeks_calc: "FnO_Greeks_Calculator",
    ) -> None:
        self.config = config
        self.greeks_calc = greeks_calc

    def select_strategies(
        self,
        chains: dict[str, "OptionChainSnapshot"],
        quant_signals: dict[str, QuantSignals],
        vix: float,
        current_time: datetime | None = None,
        is_event_day: bool = False,
    ) -> list[FnOStrategySetup]:
        """Run deterministic strategy selection.

        Returns list of FnOStrategySetup objects ready for execution.
        """
        now = current_time or datetime.now(IST)
        results: list[FnOStrategySetup] = []

        for index, chain in chains.items():
            signals = quant_signals.get(index)
            if signals is None:
                continue

            # Compute DTE
            try:
                expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d")
                dte = max(0, (expiry_dt.date() - now.date()).days)
            except Exception:
                dte = 7

            # Classify regime
            from fno.strategy_engine import MarketRegimeClassifier
            regime = MarketRegimeClassifier.classify(
                vix=vix,
                spot_prices_3d=[],
                oi_support=signals.oi_velocity_support,
                oi_resistance=signals.oi_velocity_resistance,
            )

            # Select strategy type
            strategy_type = select_strategy_type(
                vix=vix,
                regime=regime,
                signals=signals,
                dte=dte,
                is_event_day=is_event_day,
            )

            if strategy_type is None:
                continue

            # Select strikes
            setup = self._build_strategy(
                strategy_type, chain, signals, regime, dte, now,
            )
            if setup:
                results.append(setup)

        return results

    def _build_strategy(
        self,
        strategy_type: str,
        chain: "OptionChainSnapshot",
        signals: QuantSignals,
        regime: MarketRegime,
        dte: int,
        now: datetime,
    ) -> FnOStrategySetup | None:
        """Build a complete strategy setup with strikes and legs."""
        index = chain.index
        lot_size = LOT_SIZES.get(index, 25)
        num_lots = min(1, self.config.max_lots_per_trade)  # Start with 1 lot

        if strategy_type == "IRON_CONDOR":
            strikes = select_iron_condor_strikes(chain, self.greeks_calc)
            if not strikes:
                return None
            legs = self._build_iron_condor_legs(
                index, chain, strikes, lot_size, num_lots,
            )

        elif strategy_type == "BULL_PUT_SPREAD":
            strikes = select_spread_strikes(
                chain, self.greeks_calc, "BULL_PUT_SPREAD",
            )
            if not strikes:
                return None
            legs = self._build_spread_legs(
                index, chain, strikes, lot_size, num_lots, "BULL_PUT_SPREAD",
            )

        elif strategy_type == "BEAR_CALL_SPREAD":
            strikes = select_spread_strikes(
                chain, self.greeks_calc, "BEAR_CALL_SPREAD",
            )
            if not strikes:
                return None
            legs = self._build_spread_legs(
                index, chain, strikes, lot_size, num_lots, "BEAR_CALL_SPREAD",
            )

        elif strategy_type == "LONG_STRADDLE":
            strikes = select_straddle_strikes(chain)
            legs = self._build_straddle_legs(
                index, chain, strikes, lot_size, num_lots,
            )

        else:
            return None

        if not legs:
            return None

        # Compute net premium
        net_premium = sum(
            leg.entry_price * leg.quantity * (1 if leg.is_sell else -1)
            for leg in legs
        )

        # Compute max loss/profit
        max_profit, max_loss = self._compute_bounds(strategy_type, legs, net_premium, lot_size)

        # Validate max_loss within per_trade_max_capital
        if abs(max_loss) > self.config.per_trade_max_capital:
            logger.warning(
                "RULES: %s %s max_loss ₹%.0f > per_trade_max ₹%.0f — SKIP",
                strategy_type, index, abs(max_loss), self.config.per_trade_max_capital,
            )
            return None

        # Compute Greeks
        greeks = self.greeks_calc.strategy_greeks(legs, chain.spot_price)

        # Confidence = deterministic from confluence score
        confidence = min(10, max(6, int(signals.confluence_score / 10)))

        setup = FnOStrategySetup(
            strategy_type=strategy_type,
            index=index,
            legs=legs,
            net_premium=round(net_premium, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            net_delta=round(greeks.delta, 4),
            net_gamma=round(greeks.gamma, 4),
            net_theta=round(greeks.theta, 4),
            net_vega=round(greeks.vega, 4),
            confidence_score=confidence,
            rationale=f"RULES: {strategy_type} selected — regime={regime.value}, IVP={signals.iv_percentile:.0f}, VRP={signals.vrp:.1f}",
            market_regime=regime.value,
            confluence_score=signals.confluence_score,
            expiry_date=chain.expiry_date,
        )

        logger.info(
            "RULES: Built %s %s — premium=₹%.0f, max_loss=₹%.0f, conf=%d",
            strategy_type, index, net_premium, max_loss, confidence,
        )
        return setup

    # ──────────────────────────────────────────────────────────
    # Leg Builders
    # ──────────────────────────────────────────────────────────

    def _build_iron_condor_legs(
        self, index: str, chain, strikes: dict, lot_size: int, num_lots: int,
    ) -> list[StrategyLeg]:
        """Build 4 legs for Iron Condor."""
        legs = []
        for strike_key, txn, opt_type in [
            ("ce_sell", "SELL", "CE"),
            ("ce_buy", "BUY", "CE"),
            ("pe_sell", "SELL", "PE"),
            ("pe_buy", "BUY", "PE"),
        ]:
            strike = strikes[strike_key]
            entry_price = self._get_premium_from_chain(chain, strike, opt_type)
            if entry_price <= 0:
                logger.warning("No premium for %s %s %.0f — using estimate", index, opt_type, strike)
                entry_price = 5.0  # Minimum fallback

            legs.append(StrategyLeg(
                index=index,
                strike_price=strike,
                expiry_date=chain.expiry_date,
                option_type=opt_type,
                transaction_type=txn,
                lot_size=lot_size,
                num_lots=num_lots,
                entry_price=entry_price,
            ))
        return legs

    def _build_spread_legs(
        self, index: str, chain, strikes: dict, lot_size: int, num_lots: int,
        spread_type: str,
    ) -> list[StrategyLeg]:
        """Build 2 legs for credit spread."""
        opt_type = strikes["option_type"]
        short_strike = strikes["short_strike"]
        long_strike = strikes["long_strike"]

        short_price = self._get_premium_from_chain(chain, short_strike, opt_type)
        long_price = self._get_premium_from_chain(chain, long_strike, opt_type)

        if short_price <= 0 or long_price <= 0:
            return []

        return [
            StrategyLeg(
                index=index, strike_price=short_strike, expiry_date=chain.expiry_date,
                option_type=opt_type, transaction_type="SELL",
                lot_size=lot_size, num_lots=num_lots, entry_price=short_price,
            ),
            StrategyLeg(
                index=index, strike_price=long_strike, expiry_date=chain.expiry_date,
                option_type=opt_type, transaction_type="BUY",
                lot_size=lot_size, num_lots=num_lots, entry_price=long_price,
            ),
        ]

    def _build_straddle_legs(
        self, index: str, chain, strikes: dict, lot_size: int, num_lots: int,
    ) -> list[StrategyLeg]:
        """Build 2 legs for long straddle (buy ATM CE + PE)."""
        atm = strikes["atm_strike"]
        ce_price = self._get_premium_from_chain(chain, atm, "CE")
        pe_price = self._get_premium_from_chain(chain, atm, "PE")

        if ce_price <= 0 or pe_price <= 0:
            return []

        return [
            StrategyLeg(
                index=index, strike_price=atm, expiry_date=chain.expiry_date,
                option_type="CE", transaction_type="BUY",
                lot_size=lot_size, num_lots=num_lots, entry_price=ce_price,
            ),
            StrategyLeg(
                index=index, strike_price=atm, expiry_date=chain.expiry_date,
                option_type="PE", transaction_type="BUY",
                lot_size=lot_size, num_lots=num_lots, entry_price=pe_price,
            ),
        ]

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_premium_from_chain(chain, strike: float, option_type: str) -> float:
        """Get LTP for a specific strike from the chain."""
        for s in chain.strikes:
            if abs(s.strike_price - strike) < 0.01 and s.option_type == option_type:
                if s.ltp > 0:
                    return s.ltp
                # Use mid of bid/ask if LTP is 0
                if s.bid_price > 0 and s.ask_price > 0:
                    return (s.bid_price + s.ask_price) / 2
        return 0.0

    @staticmethod
    def _compute_bounds(
        strategy_type: str, legs: list[StrategyLeg], net_premium: float, lot_size: int,
    ) -> tuple[float, float]:
        """Compute (max_profit, max_loss) for a strategy."""
        if strategy_type == "IRON_CONDOR":
            ce_sells = [l for l in legs if l.option_type == "CE" and l.is_sell]
            ce_buys = [l for l in legs if l.option_type == "CE" and not l.is_sell]
            pe_sells = [l for l in legs if l.option_type == "PE" and l.is_sell]
            pe_buys = [l for l in legs if l.option_type == "PE" and not l.is_sell]

            call_width = abs(ce_buys[0].strike_price - ce_sells[0].strike_price) if ce_sells and ce_buys else 0
            put_width = abs(pe_sells[0].strike_price - pe_buys[0].strike_price) if pe_sells and pe_buys else 0
            max_spread = max(call_width, put_width)
            num_lots = legs[0].num_lots if legs else 1
            max_loss = max_spread * num_lots * lot_size - abs(net_premium)
            max_profit = abs(net_premium)
            return max_profit, -max_loss

        elif strategy_type in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            sells = [l for l in legs if l.is_sell]
            buys = [l for l in legs if not l.is_sell]
            if sells and buys:
                width = abs(sells[0].strike_price - buys[0].strike_price)
                num_lots = legs[0].num_lots
                max_loss = width * num_lots * lot_size - abs(net_premium)
                return abs(net_premium), -max_loss
            return abs(net_premium), -abs(net_premium)

        elif strategy_type == "LONG_STRADDLE":
            # Max loss = premium paid, max profit = unlimited (estimate 3×)
            return abs(net_premium) * 3, -abs(net_premium)

        return abs(net_premium), -abs(net_premium) * 2


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════


def _round_to_strike(value: float, interval: float, direction: str = "nearest") -> float:
    """Round a value to the nearest valid strike price."""
    if direction == "up":
        return math.ceil(value / interval) * interval
    elif direction == "down":
        return math.floor(value / interval) * interval
    return round(value / interval) * interval


def _find_strike_by_delta(
    chain, greeks_calc, option_type: str, target_delta: float,
    spot: float, tte: float,
) -> float | None:
    """Find the strike closest to a target delta."""
    best_strike = None
    best_diff = float("inf")

    for s in chain.strikes:
        if s.option_type != option_type or s.iv <= 0 or s.ltp <= 0.05:
            continue
        try:
            greeks = greeks_calc.compute_greeks(
                spot, s.strike_price, tte, s.iv / 100, option_type,
            )
            actual_delta = abs(greeks.delta)
            diff = abs(actual_delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_strike = s.strike_price
        except Exception:
            continue

    return best_strike
