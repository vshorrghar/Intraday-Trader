"""
Swing scanner — 20-DMA pullback scoring.
Strategy: Investors Way Strategy 3 (pullback in uptrending stocks).

Signals:
  1. 20-DMA pullback proximity (0-5 pts) — KEY SIGNAL
  2. RSI(2) oversold (0-3 pts)
  3. Bullish reversal candle (0-3 pts)
  4. Defensive sector bonus (0-3 pts)
  5. Liquidity confirmation (0-2 pts)

Penalties:
  1. Falling knife (-3 pts)
  2. Weakening trend (-2 pts)

# TODO Week 3: Replace flat sector bonus with full correlation matrix
# TODO Week 3: Add 8-signal regime detector (currently 0 signals here)
# TODO Week 4: Add news sentiment signal
# TODO Week 4: Add FII/DII flow integration
"""

import logging
import math
from datetime import datetime
from pathlib import Path

from swing.sector_map import SECTOR_MAP, DEFENSIVE_SECTORS
from fetchers.swing_earnings_list import get_earnings_within_days

logger = logging.getLogger(__name__)

# F&O ban list (updated manually — automate Week 3)
FNO_BAN_LIST = set()  # Empty for now; populated from NSE daily


def compute_sma(closes: list, period: int) -> float:
    """Simple moving average of last N closes."""
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period


def compute_ema(closes: list, period: int) -> float:
    """Exponential moving average."""
    if len(closes) < period:
        return 0.0
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def compute_rsi(closes: list, period: int = 2) -> float:
    """RSI calculation. Default period=2 for swing oversold detection."""
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Average True Range."""
    if len(highs) < period + 1:
        return 0.0
    trs = []
    for i in range(-period, 0):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    return sum(trs) / period


def _detect_reversal_candle(opens: list, highs: list, lows: list, closes: list) -> int:
    """Detect bullish reversal candle patterns. Returns score 0-3."""
    if len(opens) < 2:
        return 0

    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    prev_o, prev_c = opens[-2], closes[-2]
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    total_range = h - l

    if total_range == 0:
        return 0

    # Hammer: lower wick > 2x body, small upper wick
    if lower_wick > 2 * body and upper_wick < body * 0.5 and c > o:
        return 3

    # Bullish engulfing: today's body engulfs yesterday's
    if c > o and prev_c < prev_o:  # today green, yesterday red
        if c > prev_o and o < prev_c:  # engulfs
            return 3

    # Inside day near support (small range inside previous range)
    prev_range = highs[-2] - lows[-2]
    if prev_range > 0 and total_range < prev_range * 0.6:
        return 2

    # Bullish doji (small body, long wicks)
    if body < total_range * 0.1 and c >= o:
        return 1

    return 0


def score_swing_candidate(symbol: str, daily_data: dict, sector: str = "") -> dict | None:
    """
    Score a stock for swing entry using 20-DMA pullback strategy.

    Args:
        symbol: NSE symbol
        daily_data: dict with keys 'open', 'high', 'low', 'close', 'volume'
                    each a list of floats (oldest first, newest last)
                    Minimum 200 data points required.
        sector: sector classification from SECTOR_MAP

    Returns:
        dict with score and details, or None if gated out.
    """
    closes = daily_data.get("close", [])
    highs = daily_data.get("high", [])
    lows = daily_data.get("low", [])
    opens = daily_data.get("open", [])
    volumes = daily_data.get("volume", [])

    if len(closes) < 200:
        return None

    latest_close = closes[-1]
    latest_low = lows[-1]
    latest_high = highs[-1]

    # ─── GATE 1: Pass/Fail filters ───
    # Price range
    if latest_close < 50 or latest_close > 5000:
        return None

    # 20-day avg turnover >= Rs.3 Cr
    # RELAXED 2026-05-28 — matches rules_selector turnover threshold.
    # Original 5 Cr was a silent gatekeeper that defeated the rules_selector
    # relaxation in Phase 3.5. Now consistent across scanner + selector.
    if len(volumes) >= 20:
        avg_volume_20 = sum(volumes[-20:]) / 20
        avg_turnover = avg_volume_20 * latest_close
        if avg_turnover < 3_00_00_000:  # Rs.3 Cr
            return None
    else:
        return None

    # 200-DMA and 50-DMA
    dma_200 = compute_sma(closes, 200)
    dma_50 = compute_sma(closes, 50)
    dma_20 = compute_sma(closes, 20)

    if dma_200 <= 0 or dma_50 <= 0 or dma_20 <= 0:
        return None

    # Must be above 200-DMA (uptrend)
    if latest_close < dma_200:
        return None

    # Must be above 50-DMA
    if latest_close < dma_50:
        return None

    # ATR(14) % between 1.5 and 5
    atr = compute_atr(highs, lows, closes, 14)
    atr_pct = (atr / latest_close) * 100 if latest_close > 0 else 0
    if atr_pct < 1.5 or atr_pct > 5:
        return None

    # F&O ban list
    if symbol in FNO_BAN_LIST:
        return None

    # ─── GATE 2: Earnings filter ───
    if get_earnings_within_days(symbol, days=5):
        return None

    # ─── SIGNAL 1: 20-DMA pullback (0-5 pts) — KEY SIGNAL ───
    delta = (latest_low - dma_20) / dma_20 * 100
    if delta <= 0:
        signal_1 = 5  # precise touch or below
    elif delta <= 0.5:
        signal_1 = 4
    elif delta <= 1.0:
        signal_1 = 3
    elif delta <= 2.0:
        signal_1 = 1
    else:
        signal_1 = 0

    # ─── SIGNAL 2: RSI(2) oversold (0-3 pts) ───
    rsi2 = compute_rsi(closes, 2)
    if rsi2 < 5:
        signal_2 = 3
    elif rsi2 < 10:
        signal_2 = 2
    elif rsi2 < 15:
        signal_2 = 1
    else:
        signal_2 = 0

    # ─── SIGNAL 3: Bullish reversal candle (0-3 pts) ───
    signal_3 = _detect_reversal_candle(opens, highs, lows, closes)

    # ─── SIGNAL 4: Defensive sector bonus (0-3 pts) ───
    stock_sector = sector or SECTOR_MAP.get(symbol, "UNKNOWN")
    if stock_sector in DEFENSIVE_SECTORS:
        signal_4 = 3
    elif stock_sector in ("PHARMA", "FMCG", "HEALTHCARE"):
        signal_4 = 3
    elif stock_sector in ("CONSUMER_DURABLE",):
        signal_4 = 1
    else:
        signal_4 = 0

    # ─── SIGNAL 5: Liquidity confirmation (0-2 pts) ───
    if avg_turnover > 20_00_00_000:  # Rs.20 Cr
        signal_5 = 2
    elif avg_turnover > 5_00_00_000:  # Rs.5 Cr (already gated)
        signal_5 = 1
    else:
        signal_5 = 0

    # ─── PENALTY 1: Falling knife (-3 pts) ───
    if len(closes) >= 5:
        last_5d_return = (closes[-1] - closes[-6]) / closes[-6] * 100
    else:
        last_5d_return = 0
    penalty_1 = -3 if last_5d_return < -8 else 0

    # ─── PENALTY 2: Weakening trend (-2 pts) ───
    # Close > 200-DMA but close < 50-DMA
    penalty_2 = -2 if (latest_close > dma_200 and latest_close < dma_50) else 0

    # ─── TOTAL SCORE ───
    total_score = signal_1 + signal_2 + signal_3 + signal_4 + signal_5 + penalty_1 + penalty_2
    total_score = max(0, total_score)

    return {
        "symbol": symbol,
        "tradingsymbol": symbol,
        "score": total_score,
        "latest_close": latest_close,
        "dma_20": round(dma_20, 2),
        "dma_50": round(dma_50, 2),
        "dma_200": round(dma_200, 2),
        "rsi2": round(rsi2, 1),
        "atr_pct": round(atr_pct, 2),
        "avg_turnover_cr": round(avg_turnover / 1_00_00_000, 1),
        "sector": stock_sector,
        "delta_from_20dma": round(delta, 2),
        "last_5d_return": round(last_5d_return, 1),
        "signals": {
            "pullback": signal_1,
            "rsi2_oversold": signal_2,
            "reversal_candle": signal_3,
            "defensive_sector": signal_4,
            "liquidity": signal_5,
        },
        "penalties": {
            "falling_knife": penalty_1,
            "weakening_trend": penalty_2,
        },
    }


def scan_universe(universe_data: dict, min_score: int = 8, top_n: int = 30) -> list:
    """
    Score all stocks in universe, return top N by score.

    Args:
        universe_data: dict of {symbol: daily_ohlc_dict}
        min_score: minimum score to qualify
        top_n: max candidates to return

    Returns:
        list of scored candidates, sorted by score descending
    """
    candidates = []
    for symbol, daily_data in universe_data.items():
        sector = SECTOR_MAP.get(symbol, "")
        result = score_swing_candidate(symbol, daily_data, sector)
        if result and result["score"] >= min_score:
            candidates.append(result)

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_n]
