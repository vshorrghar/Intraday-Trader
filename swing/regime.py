"""
Market regime detector for swing module.

Determines whether to trade (BULL), reduce size (HALF), or sit in cash (CASH).
Uses Nifty 50 proxy (average of top 10 large-caps from cache).

Regime rules:
  BULL: Nifty proxy > 50-DMA AND 50-DMA > 200-DMA (confirmed uptrend)
  HALF: Nifty proxy > 200-DMA but < 50-DMA (caution, reduce size)
  CASH: Nifty proxy < 200-DMA OR VIX > 22 (no new entries)
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache" / "swing_daily"

# Top 10 liquid large-caps as Nifty proxy
NIFTY_PROXY = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "ITC", "LT", "KOTAKBANK", "HINDUNILVR",
]


def _compute_sma(values: list, period: int) -> float:
    if len(values) < period:
        return 0
    return sum(values[-period:]) / period


def get_nifty_proxy_closes() -> list[float]:
    """Build Nifty proxy from average of top large-caps in cache."""
    # Load all proxy stocks
    stock_closes = {}
    stock_dates = {}
    for sym in NIFTY_PROXY:
        cache_file = CACHE_DIR / f"{sym}.json"
        if not cache_file.exists():
            continue
        try:
            with open(cache_file) as f:
                data = json.load(f)
            candles = data.get("candles", [])
            stock_closes[sym] = {c["date"]: c["close"] for c in candles}
            if not stock_dates:
                stock_dates = [c["date"] for c in candles]
        except Exception:
            continue

    if len(stock_closes) < 5:
        logger.warning("Regime: only %d proxy stocks available (need 5+)", len(stock_closes))
        return []

    # Use dates from first available stock
    if not stock_dates:
        return []

    # Compute average close per date
    proxy_closes = []
    for date in stock_dates:
        day_vals = []
        for sym, closes_dict in stock_closes.items():
            if date in closes_dict:
                day_vals.append(closes_dict[date])
        if day_vals:
            proxy_closes.append(sum(day_vals) / len(day_vals))

    return proxy_closes


def detect_regime(vix: float = 15.0) -> tuple[str, str]:
    """Detect current market regime.

    Returns:
        (regime, reason) where regime is "BULL", "HALF", or "CASH"
    """
    if vix > 22:
        return "CASH", f"VIX {vix:.1f} > 22 — extreme volatility, no entries"

    proxy_closes = get_nifty_proxy_closes()
    if len(proxy_closes) < 200:
        return "HALF", "Insufficient proxy data for regime detection — defaulting to HALF"

    price = proxy_closes[-1]
    sma50 = _compute_sma(proxy_closes, 50)
    sma200 = _compute_sma(proxy_closes, 200)

    if sma50 <= 0 or sma200 <= 0:
        return "HALF", "Invalid SMAs — defaulting to HALF"

    if price > sma50 and sma50 > sma200:
        return "BULL", f"Nifty proxy {price:.0f} > 50-DMA {sma50:.0f} > 200-DMA {sma200:.0f}"

    if price > sma200:
        return "HALF", f"Nifty proxy above 200-DMA but below 50-DMA — caution"

    return "CASH", f"Nifty proxy {price:.0f} < 200-DMA {sma200:.0f} — bear regime, no entries"


def get_max_positions(regime: str, config_max: int = 10) -> int:
    """Get max positions allowed for current regime."""
    if regime == "BULL":
        return config_max
    elif regime == "HALF":
        return max(1, config_max // 2)
    return 0  # CASH = no new entries
