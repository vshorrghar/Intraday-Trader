"""V3 Strategy Wrapper — V6 ORB Momentum (Gap + ORB breakout).

Thin wrapper around backtest/rule_engine.py::generate_orb_signals.
Active only in TRENDING_UP regime.
"""
import logging

from backtest.rule_engine import generate_orb_signals

logger = logging.getLogger(__name__)


def detect_v6_signals(
    historical_data: dict,
    universe: dict,
    config: dict,
    target_date: str,
    nifty_data: dict = None,
) -> list:
    """Generate V6 ORB Momentum signals.

    V6 requires: gap > 1.5% + ORB breakout + VWAP above + volume 1.5x + Nifty up.
    Should only be called in TRENDING_UP regime.

    Args:
        historical_data: {symbol: {open: [...], high: [...], ...}} OHLC data
        universe: {symbol: security_id} mapping (symbols to scan)
        config: strategy config dict (per_trade_max_capital, etc.)
        target_date: YYYY-MM-DD string
        nifty_data: Nifty OHLC data for market direction

    Returns:
        List of signal dicts from rule_engine (compatible with trade_simulator)
    """
    logger.info("V6 ORB Momentum: scanning %d stocks for %s", len(universe), target_date)

    signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant="V6",
        nifty_data=nifty_data,
    )

    logger.info("V6 signals: %d found", len(signals))
    return signals
