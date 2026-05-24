"""
F&O Rules-Based Strategy Engine — deterministic replacement for LLM strategy selection.

Uses a priority-ordered rule table to select strategies based on quantitative signals.
No LLM calls. No Bedrock. No boto3. Same input = same output always.

Rule priority: VIX gate → Iron Condor → Bull Put → Bear Call → Long Straddle → No Trade
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fno.models import (
    FnOStrategySetup,
    MarketRegime,
    OptionChainSnapshot,
    OptionStrike,
    QuantSignals,
    StrategyLeg,
)

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.greeks import FnO_Greeks_Calculator

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Lot sizes per index
LOT_SIZES = {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 25}

# Strike intervals per index
STRIKE_INTERVALS = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}

# Strategies in the playbook
STRATEGY_PLAYBOOK = {
    "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
    "LONG_STRADDLE", "NO_TRADE",
}


class MarketRegimeClassifier:
    """Classify market regime from spot price history (deterministic).

    Uses 3-day spot price trend to determine regime:
    - TRENDING_UP: spot increased > 0.5% over 3 days
    - TRENDING_DOWN: spot decreased > 0.5% over 3 days
    - SIDEWAYS: spot within ±0.5% over 3 days
    - HIGH_VOLATILITY: VIX > 20
    """

    @staticmethod
    def classify(spot_prices_3d: list[float] | None, vix: float) -> MarketRegime:
        """Classify current market regime.

        Args:
            spot_prices_3d: last 3 days of closing spot prices [oldest, ..., newest]
            vix: current India VIX value

        Returns:
            MarketRegime enum value
        """
        if vix > 20:
            return MarketRegime.HIGH_VOLATILITY

        if not spot_prices_3d or len(spot_prices_3d) < 2:
            return MarketRegime.SIDEWAYS

        first = spot_prices_3d[0]
        last = spot_prices_3d[-1]
        if first <= 0:
            return MarketRegime.SIDEWAYS

        change_pct = (last - first) / first * 100

        if change_pct > 0.5:
            return MarketRegime.TRENDING_UP
        elif change_pct < -0.5:
            return MarketRegime.TRENDING_DOWN
        else:
            return MarketRegime.SIDEWAYS


class FnO_Rules_Strategy_Engine:
    """Deterministic F&O strategy selection using rule table.

    Replaces LLM-based strategy_engine.py. Same interface for drop-in replacement.
    """

    def __init__(self, config: "FnO_Config", db: "DBManager", greeks_calc: "FnO_Greeks_Calculator"):
        self.config = config
        self.db = db
        self.greeks_calc = greeks_calc

    def select_strategies(
        self,
        chains: dict[str, OptionChainSnapshot],
        quant_signals: dict[str, QuantSignals],
        vix: float,
        spot_prices_3d: dict[str, list[float]] | None = None,
        is_event_day: bool = False,
        current_time: datetime | None = None,
    ) -> list[FnOStrategySetup]:
        """Select strategies for all indices using deterministic rule table.

        Args:
            chains: {index: OptionChainSnapshot} for each tradeable index
            quant_signals: {index: QuantSignals} from quant engine
            vix: current India VIX
            spot_prices_3d: {index: [price_d-2, price_d-1, price_today]}
            is_event_day: True if major event (RBI, budget, election)
            current_time: override for testing (defaults to now IST)

        Returns:
            list of FnOStrategySetup objects (0-3, one per index max)
        """
        now = current_time or datetime.now(IST)
        strategies = []

        for index, chain in chains.items():
            signals = quant_signals.get(index)
            if signals is None:
                logger.warning("No quant signals for %s — skipping", index)
                continue

            spot_3d = (spot_prices_3d or {}).get(index)
            regime = MarketRegimeClassifier.classify(spot_3d, vix)

            setup = self._apply_rule_table(chain, signals, regime, vix, now, is_event_day)
            if setup is not None:
                strategies.append(setup)
                logger.info("Rule engine: %s → %s (conf=%d, confluence=%.1f)",
                            index, setup.strategy_type, setup.confidence_score,
                            setup.confluence_score)
            else:
                logger.info("Rule engine: %s → NO_TRADE (regime=%s, confluence=%.1f)",
                            index, regime.value, signals.confluence_score)

        return strategies

    def _apply_rule_table(
        self,
        chain: OptionChainSnapshot,
        signals: QuantSignals,
        regime: MarketRegime,
        vix: float,
        now: datetime,
        is_event_day: bool,
    ) -> FnOStrategySetup | None:
        """Apply rules 1-6 in priority order. Returns setup or None.

        Rule 1: HIGH VOLATILITY → NO TRADE
        Rule 2: IRON_CONDOR (sideways + high IVP + VRP + pinned GEX)
        Rule 3: BULL_PUT_SPREAD (trending up + bullish skew)
        Rule 4: BEAR_CALL_SPREAD (trending down + bearish skew)
        Rule 5: LONG_STRADDLE (event day + low IVP + negative VRP)
        Rule 6: NO TRADE (default)
        """
        index = chain.index
        ivp = signals.iv_percentile
        vrp = signals.vrp
        gex_regime = signals.gex_regime
        confluence = signals.confluence_score
        iv_skew = signals.iv_skew
        iv_skew_signal = signals.iv_skew_signal

        # Compute DTE from chain expiry
        try:
            expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d")
            dte = (expiry_dt - now.replace(tzinfo=None)).days
        except (ValueError, TypeError):
            dte = 0

        # ── Rule 1: HIGH VOLATILITY or EVENT DAY with high VIX ──
        if vix > 20 or (is_event_day and vix > 18):
            logger.debug("Rule 1: VIX=%.1f > 20 or event_day — NO TRADE", vix)
            return None

        # ── Rule 2: IRON CONDOR ──
        if (regime == MarketRegime.SIDEWAYS
                and ivp >= 65
                and vrp >= 2.0
                and gex_regime == "PINNED"
                and confluence >= 55
                and dte >= 3):
            confidence = _confluence_to_confidence(confluence)
            legs = self._build_legs("IRON_CONDOR", chain, confidence)
            if legs:
                return self._build_setup("IRON_CONDOR", index, chain, legs,
                                         signals, regime, confidence)

        # ── Rule 3: BULL PUT SPREAD ──
        if (regime == MarketRegime.TRENDING_UP
                and ivp >= 55
                and vrp >= 1.0
                and (iv_skew_signal == "BULLISH" or iv_skew <= 1.0)
                and confluence >= 50
                and len(signals.oi_velocity_support) >= 1):
            confidence = _confluence_to_confidence(confluence)
            legs = self._build_legs("BULL_PUT_SPREAD", chain, confidence,
                                    oi_support=signals.oi_velocity_support)
            if legs:
                return self._build_setup("BULL_PUT_SPREAD", index, chain, legs,
                                         signals, regime, confidence)

        # ── Rule 4: BEAR CALL SPREAD ──
        if (regime == MarketRegime.TRENDING_DOWN
                and ivp >= 55
                and vrp >= 1.0
                and (iv_skew_signal == "BEARISH" or iv_skew >= 3.0)
                and confluence >= 50
                and len(signals.oi_velocity_resistance) >= 1):
            confidence = _confluence_to_confidence(confluence)
            legs = self._build_legs("BEAR_CALL_SPREAD", chain, confidence,
                                    oi_resistance=signals.oi_velocity_resistance)
            if legs:
                return self._build_setup("BEAR_CALL_SPREAD", index, chain, legs,
                                         signals, regime, confidence)

        # ── Rule 5: LONG STRADDLE (event day) ──
        if (is_event_day and ivp < 50 and vrp < 0 and dte >= 1):
            confidence = _confluence_to_confidence(confluence)
            legs = self._build_legs("LONG_STRADDLE", chain, confidence)
            if legs:
                return self._build_setup("LONG_STRADDLE", index, chain, legs,
                                         signals, regime, confidence)

        # ── Rule 6: NO TRADE (default) ──
        return None

    def _build_legs(
        self,
        strategy_type: str,
        chain: OptionChainSnapshot,
        confidence: int,
        oi_support: list[dict] | None = None,
        oi_resistance: list[dict] | None = None,
    ) -> list[StrategyLeg]:
        """Build strategy legs with deterministic strike selection.

        Returns empty list if required strikes not found in chain.
        """
        index = chain.index
        atm = chain.atm_strike
        interval = STRIKE_INTERVALS.get(index, 50)
        lot_size = LOT_SIZES.get(index, 25)
        expiry = chain.expiry_date

        if strategy_type == "IRON_CONDOR":
            ce_sell_strike = atm + 3 * interval
            ce_buy_strike = atm + 4 * interval
            pe_sell_strike = atm - 3 * interval
            pe_buy_strike = atm - 4 * interval

            ce_sell_price = _lookup_ltp(chain, ce_sell_strike, "CE")
            ce_buy_price = _lookup_ltp(chain, ce_buy_strike, "CE")
            pe_sell_price = _lookup_ltp(chain, pe_sell_strike, "PE")
            pe_buy_price = _lookup_ltp(chain, pe_buy_strike, "PE")

            if any(p is None for p in [ce_sell_price, ce_buy_price, pe_sell_price, pe_buy_price]):
                logger.warning("IRON_CONDOR: missing strike LTP for %s — skip", index)
                return []

            return [
                StrategyLeg(index=index, strike_price=ce_sell_strike, expiry_date=expiry,
                            option_type="CE", transaction_type="SELL", lot_size=lot_size,
                            num_lots=1, entry_price=ce_sell_price),
                StrategyLeg(index=index, strike_price=ce_buy_strike, expiry_date=expiry,
                            option_type="CE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=ce_buy_price),
                StrategyLeg(index=index, strike_price=pe_sell_strike, expiry_date=expiry,
                            option_type="PE", transaction_type="SELL", lot_size=lot_size,
                            num_lots=1, entry_price=pe_sell_price),
                StrategyLeg(index=index, strike_price=pe_buy_strike, expiry_date=expiry,
                            option_type="PE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=pe_buy_price),
            ]

        elif strategy_type == "BULL_PUT_SPREAD":
            if oi_support and len(oi_support) > 0:
                pe_sell_strike = float(oi_support[0].get("strike", atm - 2 * interval))
            else:
                pe_sell_strike = atm - 2 * interval
            pe_buy_strike = pe_sell_strike - interval

            pe_sell_price = _lookup_ltp(chain, pe_sell_strike, "PE")
            pe_buy_price = _lookup_ltp(chain, pe_buy_strike, "PE")

            if any(p is None for p in [pe_sell_price, pe_buy_price]):
                return []

            return [
                StrategyLeg(index=index, strike_price=pe_sell_strike, expiry_date=expiry,
                            option_type="PE", transaction_type="SELL", lot_size=lot_size,
                            num_lots=1, entry_price=pe_sell_price),
                StrategyLeg(index=index, strike_price=pe_buy_strike, expiry_date=expiry,
                            option_type="PE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=pe_buy_price),
            ]

        elif strategy_type == "BEAR_CALL_SPREAD":
            if oi_resistance and len(oi_resistance) > 0:
                ce_sell_strike = float(oi_resistance[0].get("strike", atm + 2 * interval))
            else:
                ce_sell_strike = atm + 2 * interval
            ce_buy_strike = ce_sell_strike + interval

            ce_sell_price = _lookup_ltp(chain, ce_sell_strike, "CE")
            ce_buy_price = _lookup_ltp(chain, ce_buy_strike, "CE")

            if any(p is None for p in [ce_sell_price, ce_buy_price]):
                return []

            return [
                StrategyLeg(index=index, strike_price=ce_sell_strike, expiry_date=expiry,
                            option_type="CE", transaction_type="SELL", lot_size=lot_size,
                            num_lots=1, entry_price=ce_sell_price),
                StrategyLeg(index=index, strike_price=ce_buy_strike, expiry_date=expiry,
                            option_type="CE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=ce_buy_price),
            ]

        elif strategy_type == "LONG_STRADDLE":
            ce_price = _lookup_ltp(chain, atm, "CE")
            pe_price = _lookup_ltp(chain, atm, "PE")

            if any(p is None for p in [ce_price, pe_price]):
                return []

            return [
                StrategyLeg(index=index, strike_price=atm, expiry_date=expiry,
                            option_type="CE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=ce_price),
                StrategyLeg(index=index, strike_price=atm, expiry_date=expiry,
                            option_type="PE", transaction_type="BUY", lot_size=lot_size,
                            num_lots=1, entry_price=pe_price),
            ]

        return []

    def _build_setup(
        self,
        strategy_type: str,
        index: str,
        chain: OptionChainSnapshot,
        legs: list[StrategyLeg],
        signals: QuantSignals,
        regime: MarketRegime,
        confidence: int,
    ) -> FnOStrategySetup:
        """Build complete FnOStrategySetup from legs."""
        # Net premium: sum of SELL premiums - sum of BUY premiums
        sell_premium = sum(l.entry_price * l.quantity for l in legs if l.is_sell)
        buy_premium = sum(l.entry_price * l.quantity for l in legs if not l.is_sell)
        net_premium = sell_premium - buy_premium

        # Max profit/loss (simplified)
        max_profit = net_premium if net_premium > 0 else abs(net_premium) * 2
        interval = STRIKE_INTERVALS.get(index, 50)
        lot_size = LOT_SIZES.get(index, 25)
        if strategy_type == "IRON_CONDOR":
            max_loss = (interval * lot_size) - net_premium
        elif strategy_type in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            max_loss = (interval * lot_size) - net_premium
        else:
            max_loss = buy_premium  # debit strategies

        # Greeks (simplified — use greeks_calc if available)
        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0

        rationale = (
            f"Rule-based {strategy_type}: regime={regime.value}, "
            f"IVP={signals.iv_percentile:.0f}, VRP={signals.vrp:.1f}, "
            f"GEX={signals.gex_regime}, confluence={signals.confluence_score:.0f}"
        )

        return FnOStrategySetup(
            strategy_type=strategy_type,
            index=index,
            legs=legs,
            net_premium=round(net_premium, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            confidence_score=confidence,
            rationale=rationale,
            market_regime=regime.value,
            confluence_score=signals.confluence_score,
            expiry_date=chain.expiry_date,
        )


# ═══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def _confluence_to_confidence(confluence: float) -> int:
    """Convert confluence score to confidence (deterministic).

    confluence >= 80: confidence 9
    confluence >= 70: confidence 8
    confluence >= 60: confidence 7
    confluence >= 50: confidence 6
    """
    if confluence >= 80:
        return 9
    elif confluence >= 70:
        return 8
    elif confluence >= 60:
        return 7
    elif confluence >= 50:
        return 6
    return 5


def _lookup_ltp(chain: OptionChainSnapshot, strike: float, option_type: str) -> float | None:
    """Look up LTP for a specific strike in the option chain.

    Returns None if strike not found or LTP is 0.
    """
    for s in chain.strikes:
        if s.strike_price == strike and s.option_type == option_type:
            if s.ltp > 0:
                return s.ltp
            return None
    return None


# ═══════════════════════════════════════════════════════════
# VALIDATION TEST
# ═══════════════════════════════════════════════════════════

def validate_rules_strategy_engine():
    """Self-test: verify rule table produces expected outputs for known inputs."""

    # Mock option chain
    def _mock_chain(index="NIFTY", spot=24000, expiry="2026-05-29"):
        interval = STRIKE_INTERVALS[index]
        strikes = []
        for i in range(-5, 6):
            strike = spot + i * interval
            for otype in ("CE", "PE"):
                ltp = max(5.0, 100 - abs(i) * 15)  # decreasing away from ATM
                strikes.append(OptionStrike(
                    strike_price=strike, expiry_date=expiry, option_type=otype,
                    ltp=ltp, bid_price=ltp - 1, ask_price=ltp + 1,
                    open_interest=50000, oi_change=1000, volume=10000,
                    iv=18.0, bid_ask_spread=2.0,
                ))
        return OptionChainSnapshot(
            index=index, spot_price=spot, timestamp="2026-05-26T10:00:00+05:30",
            expiry_date=expiry, lot_size=LOT_SIZES[index], strikes=strikes,
            atm_strike=spot, pcr=1.0, max_pain=spot,
            highest_call_oi_strike=spot + 3 * interval,
            highest_put_oi_strike=spot - 3 * interval,
        )

    # Mock quant signals
    def _mock_signals(ivp=75, vrp=3.0, gex="PINNED", confluence=65,
                      skew=1.5, skew_signal="NEUTRAL",
                      oi_support=None, oi_resistance=None):
        return QuantSignals(
            iv_percentile=ivp,
            iv_percentile_signal="SELL_PREMIUM" if ivp > 60 else "BUY_PREMIUM",
            oi_velocity_support=oi_support or [],
            oi_velocity_resistance=oi_resistance or [],
            iv_skew=skew,
            iv_skew_signal=skew_signal,
            gex_map=[],
            gex_gravity_center=24000,
            gex_regime=gex,
            vrp=vrp,
            vrp_signal="STRONG_SELL" if vrp > 2 else "WEAK_EDGE",
            confluence_score=confluence,
            confluence_breakdown={},
        )

    # Scenario 1: IRON_CONDOR (sideways + high IVP + VRP + pinned)
    chain = _mock_chain()
    signals = _mock_signals(ivp=75, vrp=3.0, gex="PINNED", confluence=65)
    engine = FnO_Rules_Strategy_Engine(config=None, db=None, greeks_calc=None)
    result = engine._apply_rule_table(chain, signals, MarketRegime.SIDEWAYS, vix=15, now=datetime(2026, 5, 26), is_event_day=False)
    assert result is not None, "Scenario 1: expected IRON_CONDOR"
    assert result.strategy_type == "IRON_CONDOR", f"Scenario 1: got {result.strategy_type}"
    assert len(result.legs) == 4, "Iron Condor must have 4 legs"

    # Scenario 2: BULL_PUT_SPREAD (trending up)
    signals2 = _mock_signals(ivp=60, vrp=1.5, confluence=55, skew=0.8, skew_signal="BULLISH",
                             oi_support=[{"strike": 23800}])
    result2 = engine._apply_rule_table(chain, signals2, MarketRegime.TRENDING_UP, vix=15, now=datetime(2026, 5, 26), is_event_day=False)
    assert result2 is not None, "Scenario 2: expected BULL_PUT_SPREAD"
    assert result2.strategy_type == "BULL_PUT_SPREAD", f"Scenario 2: got {result2.strategy_type}"
    assert len(result2.legs) == 2

    # Scenario 3: BEAR_CALL_SPREAD (trending down)
    signals3 = _mock_signals(ivp=60, vrp=1.5, confluence=55, skew=3.5, skew_signal="BEARISH",
                             oi_resistance=[{"strike": 24200}])
    result3 = engine._apply_rule_table(chain, signals3, MarketRegime.TRENDING_DOWN, vix=15, now=datetime(2026, 5, 26), is_event_day=False)
    assert result3 is not None, "Scenario 3: expected BEAR_CALL_SPREAD"
    assert result3.strategy_type == "BEAR_CALL_SPREAD", f"Scenario 3: got {result3.strategy_type}"

    # Scenario 4: LONG_STRADDLE (event day + low IVP)
    signals4 = _mock_signals(ivp=40, vrp=-1.0, confluence=45)
    result4 = engine._apply_rule_table(chain, signals4, MarketRegime.SIDEWAYS, vix=15, now=datetime(2026, 5, 26), is_event_day=True)
    assert result4 is not None, "Scenario 4: expected LONG_STRADDLE"
    assert result4.strategy_type == "LONG_STRADDLE", f"Scenario 4: got {result4.strategy_type}"

    # Scenario 5: NO TRADE (VIX > 20)
    result5 = engine._apply_rule_table(chain, signals, MarketRegime.SIDEWAYS, vix=22, now=datetime(2026, 5, 26), is_event_day=False)
    assert result5 is None, "Scenario 5: VIX>20 should return None"

    # Scenario 6: NO TRADE (low confluence)
    signals6 = _mock_signals(ivp=30, vrp=0.5, confluence=35)
    result6 = engine._apply_rule_table(chain, signals6, MarketRegime.SIDEWAYS, vix=15, now=datetime(2026, 5, 26), is_event_day=False)
    assert result6 is None, "Scenario 6: low confluence should return None"

    print("✅ All 6 F&O validation scenarios PASSED")


if __name__ == "__main__":
    validate_rules_strategy_engine()
