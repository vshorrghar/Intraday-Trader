"""V3 Strategy Wrapper — V4 ORB + VWAP (no gap requirement).

Thin wrapper around backtest/rule_engine.py::generate_orb_signals.
Active in TRENDING_UP and RANGING regimes.
"""
import logging

from backtest.rule_engine import generate_orb_signals

logger = logging.getLogger(__name__)


def detect_v4_signals(
    historical_data: dict,
    universe: dict,
    config: dict,
    target_date: str,
    nifty_data: dict = None,
) -> list:
    """Generate V4 ORB + VWAP signals.

    V4 requires: ORB breakout + VWAP confirmation + market direction.
    No gap requirement (fires more often than V6).
    Active in TRENDING_UP and RANGING regimes.

    Args:
        historical_data: {symbol: {open: [...], high: [...], ...}} OHLC data
        universe: {symbol: security_id} mapping (symbols to scan)
        config: strategy config dict (per_trade_max_capital, etc.)
        target_date: YYYY-MM-DD string
        nifty_data: Nifty OHLC data for market direction

    Returns:
        List of signal dicts from rule_engine (compatible with trade_simulator)
    """
    logger.info("V4 ORB+VWAP: scanning %d stocks for %s", len(universe), target_date)

    signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant="V4",
        nifty_data=nifty_data,
    )

    logger.info("V4 signals: %d found", len(signals))
    return signals
