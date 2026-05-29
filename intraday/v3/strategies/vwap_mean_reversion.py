"""V3 Strategy — VWAP Mean Reversion.

Fires only in RANGING regime. Looks for stocks that dipped below VWAP
and are reverting back. Entry on VWAP cross-above confirmation.
"""
import logging
from typing import Optional

from backtest.rule_engine import calculate_vwap, get_candles_for_date

logger = logging.getLogger(__name__)

# Strategy parameters (LOCKED — do not modify to chase backtest results)
MIN_BELOW_VWAP_PCT = 1.5   # Stock must be at least 1.5% below VWAP
MAX_BELOW_VWAP_PCT = 3.0   # But not more than 3% (too weak)
STOP_LOSS_PCT = 1.0         # 1% below entry
TARGET_ABOVE_VWAP_PCT = 0.5 # Target = VWAP + 0.5%
MIN_RR = 1.5                # Minimum risk:reward
TIME_STOP_CANDLES = 6       # 6 × 15-min = 90 minutes
POSITION_SIZE = 10000       # ₹10,000 per trade


def detect_vwap_mr_signals(
    historical_data: dict,
    universe: dict,
    config: dict,
    target_date: str,
    regime: str,
    nifty_data: dict = None,
) -> list:
    """Detect VWAP Mean Reversion signals.

    Only fires when regime == 'RANGING'. Looks for stocks that dipped
    1.5-3% below VWAP and are crossing back above.

    Args:
        historical_data: {symbol: {open: [...], high: [...], ...}} 15-min OHLC
        universe: {symbol: security_id} mapping
        config: strategy config dict
        target_date: YYYY-MM-DD string
        regime: current market regime string
        nifty_data: optional Nifty data (not used directly)

    Returns:
        List of signal dicts compatible with trade_simulator format.
    """
    if regime != "RANGING":
        logger.info("VWAP_MR: Skipping — regime is %s (need RANGING)", regime)
        return []

    signals = []
    per_trade_cap = config.get("per_trade_max_capital", POSITION_SIZE)

    for symbol in universe:
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = _get_candles_columnar(ohlc, target_date)
        if not candles or len(candles) < 12:  # Need at least 3 hours of data
            continue

        # Calculate VWAP for all candles
        vwap_values = _calculate_vwap_columnar(candles)
        if not vwap_values:
            continue

        # Look for VWAP cross-above signal after first hour (skip opening noise)
        # First hour = candles 0-3 (4 × 15min = 60min from 9:15)
        signal = _find_vwap_cross_signal(candles, vwap_values, start_idx=4)
        if not signal:
            continue

        entry_price = signal["entry_price"]
        vwap_at_entry = signal["vwap_at_entry"]

        # Stop loss: 1% below entry
        stop_loss = round(entry_price * (1 - STOP_LOSS_PCT / 100), 2)

        # Target: VWAP + 0.5% (or 1.5x risk, whichever larger)
        target_vwap = round(vwap_at_entry * (1 + TARGET_ABOVE_VWAP_PCT / 100), 2)
        risk = entry_price - stop_loss
        target_rr = round(entry_price + (MIN_RR * risk), 2)
        target = max(target_vwap, target_rr)

        # Validate R:R
        if risk <= 0:
            continue
        reward = target - entry_price
        rr = reward / risk
        if rr < MIN_RR:
            continue

        # Position sizing
        qty = max(1, int(per_trade_cap / entry_price))

        signals.append({
            "symbol": symbol,
            "direction": "LONG",
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "qty": qty,
            "score": round(rr * 10, 1),  # Higher R:R = higher score
            "strategy": "VWAP_MR",
            "entry_candle_idx": signal["entry_idx"],
            "vwap_at_entry": vwap_at_entry,
            "below_vwap_pct": signal["below_vwap_pct"],
            "time_stop_candles": TIME_STOP_CANDLES,
        })

    logger.info("VWAP_MR: %d signals found on %s (RANGING regime)", len(signals), target_date)
    return signals


def _get_candles_columnar(ohlc: dict, target_date: str) -> Optional[list]:
    """Convert columnar OHLC to list of candle dicts for a specific date.

    Handles both timestamp formats (Unix epoch and ISO string).
    """
    opens = ohlc.get("open", [])
    highs = ohlc.get("high", [])
    lows = ohlc.get("low", [])
    closes = ohlc.get("close", [])
    volumes = ohlc.get("volume", [])
    timestamps = ohlc.get("start_Time", ohlc.get("timestamp", []))

    if not opens:
        return None

    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    candles = []
    for i in range(len(opens)):
        # Parse timestamp
        ts = timestamps[i] if i < len(timestamps) else 0
        if isinstance(ts, (int, float)) and ts > 1000000000:
            dt = datetime.fromtimestamp(ts, tz=IST)
        else:
            continue

        if dt.strftime("%Y-%m-%d") != target_date:
            continue

        candles.append({
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": volumes[i] if i < len(volumes) else 0,
            "time": dt,
        })

    return candles if candles else None


def _calculate_vwap_columnar(candles: list) -> list:
    """Calculate VWAP from list of candle dicts."""
    cum_tp_vol = 0.0
    cum_vol = 0
    vwap_values = []

    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3
        vol = c["volume"]
        cum_tp_vol += typical_price * vol
        cum_vol += vol
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else c["close"]
        vwap_values.append(vwap)

    return vwap_values


def _find_vwap_cross_signal(candles: list, vwap_values: list, start_idx: int = 4) -> Optional[dict]:
    """Find first VWAP cross-above signal after start_idx.

    Looks for: previous candle close below VWAP by 1.5-3%, current candle close above VWAP.
    """
    for i in range(start_idx, len(candles)):
        if i == 0:
            continue

        prev_close = candles[i - 1]["close"]
        curr_close = candles[i]["close"]
        vwap_prev = vwap_values[i - 1]
        vwap_curr = vwap_values[i]

        # Previous candle must be below VWAP by 1.5-3%
        if vwap_prev <= 0:
            continue
        below_pct = (vwap_prev - prev_close) / vwap_prev * 100

        if below_pct < MIN_BELOW_VWAP_PCT or below_pct > MAX_BELOW_VWAP_PCT:
            continue

        # Current candle must close above VWAP (cross-above confirmed)
        if curr_close <= vwap_curr:
            continue

        # Confirmed cross-above
        return {
            "entry_price": curr_close,
            "entry_idx": i,
            "vwap_at_entry": vwap_curr,
            "below_vwap_pct": round(below_pct, 2),
        }

    return None
