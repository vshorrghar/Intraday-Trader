"""
Rule Engine — deterministic ORB + VWAP + ATR signal generation.
Replaces LLM-based trade selection entirely.
No API calls. Pure math. Same input = same output always.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================
# CANDLE UTILITIES
# ============================================================

def get_candles_for_date(ohlc: dict, date_str: str) -> list:
    """Extract candles for a specific date from OHLC data."""
    candles = []
    opens = ohlc.get("open", [])
    highs = ohlc.get("high", [])
    lows = ohlc.get("low", [])
    closes = ohlc.get("close", [])
    volumes = ohlc.get("volume", [])
    timestamps = ohlc.get("timestamp", [])

    for i in range(len(timestamps)):
        dt = datetime.fromtimestamp(timestamps[i], tz=IST)
        if dt.strftime("%Y-%m-%d") == date_str:
            candles.append({
                "time": dt,
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i],
            })

    return sorted(candles, key=lambda x: x["time"])


def get_prev_close(ohlc: dict, date_str: str) -> float:
    """Get previous trading day's closing price."""
    closes = ohlc.get("close", [])
    timestamps = ohlc.get("timestamp", [])
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    prev_close = 0.0
    for i in range(len(timestamps)):
        dt = datetime.fromtimestamp(timestamps[i], tz=IST)
        if dt.date() < target_date:
            prev_close = closes[i]

    return prev_close


# ============================================================
# INDICATOR CALCULATIONS
# ============================================================

def calculate_vwap(candles: list) -> list:
    """
    Calculate VWAP from market open for each candle.
    VWAP = cumulative(typical_price × volume) / cumulative(volume)
    Typical price = (high + low + close) / 3
    """
    vwap_values = []
    cum_tp_vol = 0.0
    cum_vol = 0.0

    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3
        vol = c["volume"] if c["volume"] > 0 else 1
        cum_tp_vol += typical_price * vol
        cum_vol += vol
        vwap_values.append(round(cum_tp_vol / cum_vol, 2))

    return vwap_values


def calculate_atr(candles: list, period: int = 14) -> list:
    """
    Calculate ATR (Average True Range) using Wilder's smoothing.
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    """
    if len(candles) < 2:
        return [0.0] * len(candles)

    true_ranges = []
    atr_values = []

    for i in range(len(candles)):
        if i == 0:
            tr = candles[i]["high"] - candles[i]["low"]
        else:
            prev_close = candles[i-1]["close"]
            tr = max(
                candles[i]["high"] - candles[i]["low"],
                abs(candles[i]["high"] - prev_close),
                abs(candles[i]["low"] - prev_close),
            )
        true_ranges.append(tr)

        if i < period:
            # Initial ATR = simple average
            atr_values.append(round(sum(true_ranges) / len(true_ranges), 4))
        else:
            # Wilder's smoothing
            prev_atr = atr_values[-1]
            atr = (prev_atr * (period - 1) + tr) / period
            atr_values.append(round(atr, 4))

    return atr_values


def calculate_relative_volume(
    candles_today: list,
    ohlc_all: dict,
    date_str: str,
    lookback_days: int = 20,
) -> float:
    """
    Calculate relative volume at 9:30 AM.
    Compares today's volume in first 15 candles to
    average volume in same window over last 20 trading days.
    """
    # Today's volume in first 15 candles (9:15-9:30)
    opening_candles = [c for c in candles_today
                       if c["time"].hour == 9 and c["time"].minute < 31]
    today_vol = sum(c["volume"] for c in opening_candles)

    if today_vol == 0:
        return 1.0

    # Historical average for same window
    timestamps = ohlc_all.get("timestamp", [])
    volumes = ohlc_all.get("volume", [])
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    # Group by date, get opening window volume
    daily_opening_vols = {}
    for i in range(len(timestamps)):
        dt = datetime.fromtimestamp(timestamps[i], tz=IST)
        d = dt.date()
        if d >= target_date:
            continue
        if dt.hour == 9 and dt.minute < 31:
            if d not in daily_opening_vols:
                daily_opening_vols[d] = 0
            daily_opening_vols[d] += volumes[i]

    recent_dates = sorted(daily_opening_vols.keys())[-lookback_days:]
    if not recent_dates:
        return 1.0

    avg_opening_vol = sum(daily_opening_vols[d] for d in recent_dates) / len(recent_dates)
    if avg_opening_vol == 0:
        return 1.0

    return round(today_vol / avg_opening_vol, 2)


# ============================================================
# OPENING RANGE CALCULATION
# ============================================================

def get_opening_range(candles: list) -> Optional[dict]:
    """
    Calculate the opening range from first 15-min candles (9:15-9:30 IST).
    Returns: high, low, width, width_pct
    """
    opening = [c for c in candles
               if c["time"].hour == 9 and c["time"].minute < 31]

    if len(opening) < 2:
        return None

    or_high = max(c["high"] for c in opening)
    or_low = min(c["low"] for c in opening)
    or_open = opening[0]["open"]
    or_width = or_high - or_low
    or_width_pct = (or_width / or_open * 100) if or_open > 0 else 0

    return {
        "high": round(or_high, 2),
        "low": round(or_low, 2),
        "width": round(or_width, 2),
        "width_pct": round(or_width_pct, 3),
        "open": round(or_open, 2),
        "candle_count": len(opening),
    }


# ============================================================
# MARKET DIRECTION
# ============================================================

def get_market_direction(
    nifty_ohlc: dict,
    date_str: str,
) -> dict:
    """
    Determine Nifty's direction by 9:30 AM on a given date.
    Returns: direction (BULL/BEAR/FLAT), change_pct, strength
    """
    candles = get_candles_for_date(nifty_ohlc, date_str)
    prev_close = get_prev_close(nifty_ohlc, date_str)

    if not candles or prev_close == 0:
        return {"direction": "FLAT", "change_pct": 0, "strength": "UNKNOWN"}

    # Price at 9:30 AM (after opening range forms)
    price_at_930 = None
    for c in candles:
        if c["time"].hour == 9 and c["time"].minute >= 30:
            price_at_930 = c["close"]
            break

    if price_at_930 is None:
        price_at_930 = candles[0]["open"]

    change_pct = (price_at_930 - prev_close) / prev_close * 100

    if change_pct > 1.5:
        direction, strength = "BULL", "STRONG"
    elif change_pct > 0.5:
        direction, strength = "BULL", "MODERATE"
    elif change_pct > 0.0:
        direction, strength = "BULL", "WEAK"
    elif change_pct > -0.5:
        direction, strength = "BEAR", "WEAK"
    elif change_pct > -1.5:
        direction, strength = "BEAR", "MODERATE"
    else:
        direction, strength = "BEAR", "STRONG"

    if abs(change_pct) <= 0.3:
        direction = "FLAT"
        strength = "SIDEWAYS"

    return {
        "direction": direction,
        "change_pct": round(change_pct, 3),
        "strength": strength,
    }


# ============================================================
# SIGNAL GENERATION — THE CORE ENGINE
# ============================================================

def generate_orb_signals(
    target_date: str,
    historical_data: dict,
    universe: dict,
    config: dict,
    strategy_variant: str = "V4",
    nifty_data: dict = None,
) -> list:
    """
    Generate ORB-based trade signals for a given date.
    Pure math. No LLM. Deterministic.

    Strategy variants:
      V1: Pure ORB only
      V2: ORB + VWAP filter
      V3: ORB + VWAP + ATR sizing
      V4: ORB + VWAP + ATR + Market direction (RECOMMENDED)
      V5: VWAP reclaim only
      V6: Gap + ORB (catalyst stocks only)

    Returns list of picks in format compatible with trade_simulator.
    """
    signals = []

    # Get market direction if available (for V4, V6)
    market = {"direction": "BULL", "change_pct": 0, "strength": "MODERATE"}
    if nifty_data and strategy_variant in ("V4", "V6"):
        market = get_market_direction(nifty_data, target_date)

    # V4: Skip if market is strongly bearish
    if strategy_variant == "V4" and market["direction"] == "BEAR" and market["strength"] == "STRONG":
        return []

    # V4: Only long on BULL days, only short on BEAR days
    allowed_directions = ["LONG"]
    if strategy_variant in ("V4", "V6"):
        if market["direction"] == "BEAR":
            allowed_directions = ["SHORT"]
        elif market["direction"] == "FLAT":
            return []  # Skip flat/sideways days

    per_trade_cap = config.get("per_trade_max_capital", 15000)
    min_rel_volume = 1.5  # Minimum relative volume
    atr_multiplier = 1.5  # Stop = entry - (1.5 × ATR)

    for symbol in universe:
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if len(candles) < 20:
            continue

        prev_close = get_prev_close(ohlc, target_date)
        if prev_close == 0:
            continue

        # Opening range
        opening_range = get_opening_range(candles)
        if not opening_range:
            continue

        # Skip if opening range too wide (news event, manipulation risk)
        if opening_range["width_pct"] > 3.0:
            continue

        # Skip if opening range too narrow (not enough movement expected)
        if opening_range["width_pct"] < 0.3:
            continue

        # Calculate gap at open
        gap_pct = (opening_range["open"] - prev_close) / prev_close * 100

        # V6: Catalyst stocks only — must have gap > 1.5%
        if strategy_variant == "V6" and abs(gap_pct) < 1.5:
            continue

        # Calculate indicators
        vwap_values = calculate_vwap(candles)
        atr_values = calculate_atr(candles)
        rel_volume = calculate_relative_volume(candles, ohlc, target_date)

        # Find breakout candle (after 9:30 AM)
        breakout_candle = None
        breakout_idx = None
        direction = None

        for i, c in enumerate(candles):
            if c["time"].hour == 9 and c["time"].minute < 31:
                continue  # Still in opening range window
            if c["time"].hour >= 11:
                break  # Only look for ORB breakout in first 90 min

            # Check LONG breakout
            if "LONG" in allowed_directions:
                if c["high"] > opening_range["high"]:
                    # V2, V3, V4: VWAP confirmation
                    if strategy_variant in ("V2", "V3", "V4", "V6"):
                        if c["close"] < vwap_values[i]:
                            continue  # Price below VWAP — skip

                    # Volume confirmation
                    if rel_volume >= min_rel_volume:
                        breakout_candle = c
                        breakout_idx = i
                        direction = "LONG"
                        break

            # Check SHORT breakout
            if "SHORT" in allowed_directions:
                if c["low"] < opening_range["low"]:
                    # VWAP confirmation for shorts
                    if strategy_variant in ("V2", "V3", "V4", "V6"):
                        if c["close"] > vwap_values[i]:
                            continue  # Price above VWAP — skip

                    if rel_volume >= min_rel_volume:
                        breakout_candle = c
                        breakout_idx = i
                        direction = "SHORT"
                        break

        if not breakout_candle or not direction:
            continue

        # Entry price = close of breakout candle
        entry_price = breakout_candle["close"]
        if entry_price <= 0:
            continue

        # ATR at breakout point
        atr = atr_values[breakout_idx] if breakout_idx < len(atr_values) else 0
        if atr == 0:
            # Fallback: use opening range width as ATR proxy
            atr = opening_range["width"]

        # Stop loss and target
        if direction == "LONG":
            stop_loss = round(entry_price - (atr_multiplier * atr), 2)
            target = round(entry_price + (atr_multiplier * 2 * atr), 2)
        else:
            stop_loss = round(entry_price + (atr_multiplier * atr), 2)
            target = round(entry_price - (atr_multiplier * 2 * atr), 2)

        # Validate R:R
        if direction == "LONG":
            risk = entry_price - stop_loss
        else:
            risk = stop_loss - entry_price

        if risk <= 0:
            continue

        reward = abs(target - entry_price)
        rr = reward / risk
        if rr < 1.99:
            continue

        # Position sizing
        qty = max(1, int(per_trade_cap / entry_price))

        # Score this signal (0-10)
        score = 0
        # Price movement score
        if abs(gap_pct) > 2.0:
            score += 2
        elif abs(gap_pct) > 1.0:
            score += 1
        # Volume score
        if rel_volume > 4.0:
            score += 3
        elif rel_volume > 2.5:
            score += 2
        elif rel_volume > 1.5:
            score += 1
        # Market alignment score
        if market["strength"] in ("STRONG", "MODERATE"):
            score += 2
        elif market["strength"] == "WEAK":
            score += 1
        # ATR quality (not too wide, not too narrow)
        atr_pct = atr / entry_price * 100
        if 0.3 <= atr_pct <= 1.5:
            score += 2
        elif atr_pct < 0.3 or atr_pct > 3.0:
            score -= 1

        if score < 4:  # Minimum quality threshold
            continue

        signals.append({
            "symbol": symbol,
            "direction": direction,
            "entry_price": round(entry_price, 2),
            "target_price": round(target, 2),
            "stop_loss_price": round(stop_loss, 2),
            "qty": qty,
            "confidence_score": min(9, max(5, score)),
            "strategy_type": f"ORB_{strategy_variant}",
            "gap_pct": round(gap_pct, 3),
            "rel_volume": rel_volume,
            "atr": round(atr, 4),
            "rr": round(rr, 2),
            "market_direction": market["direction"],
            "market_strength": market["strength"],
            "breakout_time": breakout_candle["time"].strftime("%H:%M"),
            "score": score,
        })

    # Sort by score descending — best signals first
    signals.sort(key=lambda x: x["score"], reverse=True)

    # Return top signals (respect max_trades limit)
    max_trades = config.get("max_trades_per_day", 3)
    return signals[:max_trades]


def generate_vwap_reclaim_signals(
    target_date: str,
    historical_data: dict,
    universe: dict,
    config: dict,
    nifty_data: dict = None,
) -> list:
    """
    Strategy 2: VWAP Reclaim (11:00-13:00 IST window)

    Logic: Stock gapped up in morning, pulled back to VWAP, now bouncing back above it.
    This is institutional buying — they buy the dip to VWAP on strong stocks.

    Rules:
      - Stock up > 1% from prev close (morning strength confirmed)
      - Price touched VWAP (within 0.5%) at some point after 11:00
      - Price now ABOVE VWAP (reclaim confirmed on current candle)
      - Volume on reclaim candle > 0.7x avg (not dead volume)
      - Nifty BULL day (direction = BULL)
      - RSI(14) between 35-70 (healthy range, not extreme)
      - Only fires between 11:00-13:00 IST

    Returns list of signal dicts compatible with select_trades_v2()
    """
    import logging
    from datetime import datetime, timezone, timedelta

    logger = logging.getLogger(__name__)
    IST = timezone(timedelta(hours=5, minutes=30))
    per_trade_cap = config.get("per_trade_max_capital", 10000)

    # Market direction check
    if nifty_data:
        market = get_market_direction(nifty_data, target_date)
        direction = market.get("direction", "FLAT")
        if direction not in ("BULL", "BULL MODERATE", "BULL STRONG"):
            logger.info("VWAP_RECLAIM: Skipping — market direction %s", direction)
            return []

    signals = []

    for symbol, sec_id in universe.items():
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if len(candles) < 8:
            continue

        prev_close = get_prev_close(ohlc, target_date)
        if not prev_close or prev_close <= 0:
            continue

        vwap_values = calculate_vwap(candles)
        atr_values = calculate_atr(candles)
        rel_volume = calculate_relative_volume(candles, ohlc, target_date)

        # Check morning strength — stock must be up > 1% from prev close
        # Use first candle close as proxy for morning open
        if not candles:
            continue
        first_close = candles[0]["close"]
        gap_pct = ((first_close - prev_close) / prev_close) * 100
        if gap_pct < 1.0:
            continue  # No morning strength — skip

        # Look for VWAP reclaim candle between 11:00-13:00 IST
        reclaim_candle = None
        reclaim_idx = None

        for i, c in enumerate(candles):
            hour = c["time"].hour
            minute = c["time"].minute

            # Only look in 11:00-13:00 window
            if hour < 11:
                continue
            if hour >= 13:
                break

            if i >= len(vwap_values):
                continue

            vwap = vwap_values[i]
            if vwap <= 0:
                continue

            price = c["close"]

            # Price must be above VWAP now (reclaim)
            if price <= vwap:
                continue

            # Price must be within 1.5% above VWAP (fresh reclaim, not already ran)
            if price > vwap * 1.015:
                continue

            # Previous candle must have touched VWAP (touched from above or below)
            if i > 0 and i - 1 < len(vwap_values):
                prev_vwap = vwap_values[i - 1]
                prev_low = candles[i - 1]["low"]
                # Previous candle low must have been near or below VWAP
                if prev_low > prev_vwap * 1.01:
                    continue  # Did not touch VWAP — not a reclaim

            # Volume check — candle volume vs avg
            avg_vol = sum(x["volume"] for x in candles[:i]) / max(i, 1)
            if avg_vol > 0 and c["volume"] < avg_vol * 0.7:
                continue  # Too low volume on reclaim

            reclaim_candle = c
            reclaim_idx = i
            break

        if not reclaim_candle:
            continue

        entry_price = reclaim_candle["close"]
        if entry_price <= 0:
            continue

        atr = atr_values[reclaim_idx] if reclaim_idx < len(atr_values) else 0
        if atr == 0:
            atr = entry_price * 0.005  # 0.5% fallback

        # SL just below VWAP at entry
        vwap_at_entry = vwap_values[reclaim_idx]
        stop_loss = round(min(entry_price - atr, vwap_at_entry * 0.997), 2)
        target = round(entry_price + (1.5 * atr), 2)

        risk = entry_price - stop_loss
        if risk <= 0:
            continue
        reward = target - entry_price
        rr = reward / risk
        if rr < 1.4:
            continue

        qty = max(1, int(per_trade_cap / entry_price))

        # Score
        score = 5  # Base score for VWAP reclaim
        if gap_pct > 2.0:
            score += 2
        elif gap_pct > 1.5:
            score += 1
        if rel_volume > 1.2:
            score += 1
        if rr > 2.0:
            score += 1

        signals.append({
            "symbol": symbol,
            "security_id": sec_id,
            "direction": "LONG",
            "strategy_type": "VWAP_RECLAIM",
            "entry_price": entry_price,
            "stop_loss_price": stop_loss,
            "target_price": target,
            "quantity": qty,
            "gap_pct": gap_pct,
            "rel_volume": rel_volume,
            "score": score,
            "market_direction": market.get("direction", "") if nifty_data else "",
            "market_strength": market.get("strength", "") if nifty_data else "",
            "vwap_at_entry": vwap_at_entry,
            "rr": round(rr, 2),
        })
        logger.info(
            "VWAP_RECLAIM SIGNAL: %s @ %.2f SL %.2f T %.2f gap=%.1f%% RR=%.1f score=%d",
            symbol, entry_price, stop_loss, target, gap_pct, rr, score
        )

    # Sort by score descending
    signals.sort(key=lambda x: x["score"], reverse=True)
    return signals


def generate_trend_continuation_signals(
    target_date: str,
    historical_data: dict,
    universe: dict,
    config: dict,
    nifty_data: dict = None,
) -> list:
    """
    Strategy 3: Trend Continuation (13:00-14:30 IST window)

    Logic: Stock that gapped AND held above VWAP all day.
    These are the strongest stocks — institutions accumulating all day.
    Late afternoon push as weak hands exit and strong hands add.

    Rules:
      - Stock up > 2% from prev close (strong gap — not marginal)
      - Price ABOVE VWAP at 13:00 (held the morning move)
      - Price within 2% of day high (not fading, near highs)
      - Current candle volume > 0.6x avg (sustained)
      - Nifty up > 0.3% (confirmed bull day)
      - Only fires between 13:00-14:30 IST
      - Tighter SL — less time to recover in afternoon

    Returns list of signal dicts compatible with select_trades_v2()
    """
    import logging
    from datetime import datetime, timezone, timedelta

    logger = logging.getLogger(__name__)
    IST = timezone(timedelta(hours=5, minutes=30))
    per_trade_cap = config.get("per_trade_max_capital", 10000)

    # Strong bull day required for trend continuation
    if nifty_data:
        market = get_market_direction(nifty_data, target_date)
        direction = market.get("direction", "FLAT")
        strength = market.get("strength", "")
        # Need confirmed bull — not just marginal
        if direction not in ("BULL", "BULL MODERATE", "BULL STRONG"):
            logger.info("TREND_CONT: Skipping — market %s %s", direction, strength)
            return []
        # Also check Nifty is actually up on the day
        nifty_change = market.get("change_pct", 0)
        if nifty_change < 0.3:
            logger.info("TREND_CONT: Skipping — Nifty only up %.2f%%", nifty_change)
            return []
    else:
        market = {"direction": "UNKNOWN", "strength": "", "change_pct": 0}

    signals = []

    for symbol, sec_id in universe.items():
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if len(candles) < 12:  # Need enough candles for 13:00 check
            continue

        prev_close = get_prev_close(ohlc, target_date)
        if not prev_close or prev_close <= 0:
            continue

        vwap_values = calculate_vwap(candles)
        atr_values = calculate_atr(candles)

        # Morning gap must be > 2%
        first_close = candles[0]["close"]
        gap_pct = ((first_close - prev_close) / prev_close) * 100
        if gap_pct < 2.0:
            continue

        # Find the 13:00 candle and check conditions
        trigger_candle = None
        trigger_idx = None
        day_high = max(c["high"] for c in candles)

        for i, c in enumerate(candles):
            hour = c["time"].hour
            minute = c["time"].minute

            # Only look in 13:00-14:30 window
            if hour < 13:
                continue
            if hour > 14 or (hour == 14 and minute > 30):
                break

            if i >= len(vwap_values):
                continue

            vwap = vwap_values[i]
            if vwap <= 0:
                continue

            price = c["close"]

            # Must be above VWAP (held the trend)
            if price <= vwap:
                continue

            # Must be within 2% of day high (near highs, not fading)
            if price < day_high * 0.98:
                continue

            # Volume check
            avg_vol = sum(x["volume"] for x in candles[:i]) / max(i, 1)
            if avg_vol > 0 and c["volume"] < avg_vol * 0.6:
                continue

            trigger_candle = c
            trigger_idx = i
            break

        if not trigger_candle:
            continue

        entry_price = trigger_candle["close"]
        if entry_price <= 0:
            continue

        atr = atr_values[trigger_idx] if trigger_idx < len(atr_values) else 0
        if atr == 0:
            atr = entry_price * 0.005

        # Tighter SL for afternoon — less time to recover
        vwap_at_entry = vwap_values[trigger_idx]
        stop_loss = round(entry_price - (0.7 * atr), 2)
        target = round(entry_price + (1.2 * atr), 2)

        risk = entry_price - stop_loss
        if risk <= 0:
            continue
        reward = target - entry_price
        rr = reward / risk
        if rr < 1.4:
            continue

        qty = max(1, int(per_trade_cap / entry_price))

        # Score
        score = 5
        if gap_pct > 3.0:
            score += 2
        elif gap_pct > 2.5:
            score += 1
        if price >= day_high * 0.99:  # Within 1% of high
            score += 2
        if rr > 2.0:
            score += 1

        signals.append({
            "symbol": symbol,
            "security_id": sec_id,
            "direction": "LONG",
            "strategy_type": "TREND_CONT",
            "entry_price": entry_price,
            "stop_loss_price": stop_loss,
            "target_price": target,
            "quantity": qty,
            "gap_pct": gap_pct,
            "rel_volume": 1.0,
            "score": score,
            "market_direction": market.get("direction", ""),
            "market_strength": market.get("strength", ""),
            "vwap_at_entry": vwap_at_entry,
            "day_high": day_high,
            "rr": round(rr, 2),
        })
        logger.info(
            "TREND_CONT SIGNAL: %s @ %.2f SL %.2f T %.2f gap=%.1f%% near_high=%.1f%% RR=%.1f score=%d",
            symbol, entry_price, stop_loss, target, gap_pct,
            (price / day_high) * 100, rr, score
        )

    signals.sort(key=lambda x: x["score"], reverse=True)
    return signals
