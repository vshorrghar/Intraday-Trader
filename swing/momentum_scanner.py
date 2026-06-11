"""
Momentum breakout scanner — Minervini/O'Neil style adapted for NSE.

Finds stocks breaking out of tight bases in confirmed Stage 2 uptrends.
Entry: new 10-day high + volume surge + MA stack aligned.
This is the PRIMARY swing strategy (replaces pullback as default).

Evidence: 20 years of Indian momentum data shows strength continues.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _sma(values: list, period: int) -> float:
    if len(values) < period:
        return 0
    return sum(values[-period:]) / period


def _ema(values: list, period: int) -> float:
    if len(values) < period:
        return 0
    mult = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for p in values[period:]:
        ema = (p - ema) * mult + ema
    return ema


def is_stage2(closes: list) -> bool:
    """Minervini Stage 2 trend template.

    All must be true:
    1. Price > 50-DMA > 150-DMA > 200-DMA (MA stack)
    2. 200-DMA trending up for 1+ month
    3. Price within 25% of 52-week high
    4. Price at least 30% above 52-week low
    """
    if len(closes) < 250:
        return False

    price = closes[-1]
    sma50 = _sma(closes, 50)
    sma150 = _sma(closes, 150)
    sma200 = _sma(closes, 200)

    # MA stack
    if not (price > sma50 > sma150 > sma200):
        return False

    # 200-DMA trending up
    sma200_month_ago = _sma(closes[:-20], 200) if len(closes) >= 220 else sma200
    if sma200 <= sma200_month_ago:
        return False

    # Within 25% of 52-week high
    high_52w = max(closes[-250:])
    if price < high_52w * 0.75:
        return False

    # At least 30% above 52-week low
    low_52w = min(closes[-250:])
    if price < low_52w * 1.30:
        return False

    return True


def is_breakout(closes: list, highs: list, volumes: list) -> bool:
    """Detect breakout: new 10-day high with volume surge."""
    if len(closes) < 50:
        return False

    price = closes[-1]

    # New 10-day high
    prior_highs = highs[-11:-1]
    if price <= max(prior_highs):
        return False

    # Volume > 1.2x 50-day average
    avg_vol = sum(volumes[-50:]) / 50
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * 1.2:
        return False

    return True


def has_volatility_contraction(highs: list, lows: list) -> bool:
    """Relaxed VCP: recent range < 85% of prior range (base tightening)."""
    if len(highs) < 25:
        return False

    recent = [highs[i] - lows[i] for i in range(-5, 0)]
    prior = [highs[i] - lows[i] for i in range(-25, -5)]

    avg_recent = sum(recent) / len(recent)
    avg_prior = sum(prior) / len(prior)

    if avg_prior <= 0:
        return False

    return avg_recent < avg_prior * 0.85


def compute_relative_strength(closes: list, nifty_closes: list, lookback: int = 60) -> float:
    """Stock return vs Nifty return over lookback period."""
    if len(closes) < lookback or len(nifty_closes) < lookback:
        return 0
    stock_ret = (closes[-1] - closes[-lookback]) / closes[-lookback]
    nifty_ret = (nifty_closes[-1] - nifty_closes[-lookback]) / nifty_closes[-lookback]
    return stock_ret - nifty_ret


def scan_momentum_breakouts(universe_data: dict, nifty_proxy_closes: list = None,
                            min_turnover_cr: float = 5.0) -> list[dict]:
    """Scan universe for momentum breakout candidates.

    Args:
        universe_data: {symbol: {open, high, low, close, volume}} (flat lists)
        nifty_proxy_closes: Nifty proxy close prices for RS calculation
        min_turnover_cr: Minimum 20-day average turnover in crores

    Returns:
        List of candidate dicts sorted by relative strength descending.
    """
    candidates = []

    for symbol, data in universe_data.items():
        closes = data.get("close", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        volumes = data.get("volume", [])

        if len(closes) < 250:
            continue

        # Turnover filter
        avg_vol = sum(volumes[-20:]) / 20
        avg_turnover = avg_vol * closes[-1]
        if avg_turnover < min_turnover_cr * 1_00_00_000:
            continue

        # Stage 2 (the most important filter)
        if not is_stage2(closes):
            continue

        # Breakout detection
        if not is_breakout(closes, highs, volumes):
            continue

        # Relative strength
        rs = 0
        if nifty_proxy_closes and len(nifty_proxy_closes) >= 60:
            rs = compute_relative_strength(closes, nifty_proxy_closes)

        # Compute entry/SL/target
        entry_price = closes[-1]
        base_low = min(lows[-10:])
        sl_price = max(base_low * 0.99, entry_price * 0.93)  # 7% max SL
        risk_per_share = entry_price - sl_price

        if risk_per_share <= 0:
            continue

        # ATR for position info
        atr_vals = []
        for i in range(-14, 0):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            atr_vals.append(tr)
        atr = sum(atr_vals) / len(atr_vals) if atr_vals else 0
        atr_pct = (atr / entry_price * 100) if entry_price > 0 else 0

        candidates.append({
            "symbol": symbol,
            "entry_price": round(entry_price, 2),
            "sl_price": round(sl_price, 2),
            "risk_per_share": round(risk_per_share, 2),
            "risk_pct": round(risk_per_share / entry_price * 100, 1),
            "relative_strength": round(rs, 4),
            "avg_turnover_cr": round(avg_turnover / 1_00_00_000, 1),
            "atr_pct": round(atr_pct, 2),
            "sma50": round(_sma(closes, 50), 2),
            "sma200": round(_sma(closes, 200), 2),
            "strategy_type": "MOMENTUM_BREAKOUT",
        })

    # Sort by relative strength (strongest first)
    candidates.sort(key=lambda x: x["relative_strength"], reverse=True)
    return candidates
