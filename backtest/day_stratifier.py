"""Day stratifier — pick 8 days covering different market conditions from past 30 trading days."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# NIFTY 50 security ID on Dhan
NIFTY50_SEC_ID = "13"


def stratify_past_days(num_days: int = 30, broker=None) -> dict:
    """Fetch NIFTY 50 daily candles for past num_days trading days.
    Categorize and pick 8 stratified days.

    Parameters
    ----------
    num_days : int
        How many trading days back to look.
    broker : DhanBrokerClient
        Authenticated broker for historical data.

    Returns
    -------
    dict with selected_days, categorized, method
    """
    if not broker:
        raise ValueError("Broker required for historical data fetch")

    # Fetch NIFTY 50 60-min candles for past num_days calendar days
    # Add buffer for weekends/holidays
    to_date = datetime.now(IST).strftime("%Y-%m-%d")
    from_date = (datetime.now(IST) - timedelta(days=num_days + 15)).strftime("%Y-%m-%d")

    data = broker.get_historical_ohlc(
        security_id=NIFTY50_SEC_ID,
        exchange_segment="IDX_I",
        instrument="INDEX",
        interval="60",
        from_date=from_date,
        to_date=to_date,
    )

    if not data or not data.get("open"):
        raise RuntimeError(f"Failed to fetch NIFTY historical data")

    # Group candles by date
    opens = data["open"]
    highs = data["high"]
    lows = data["low"]
    closes = data["close"]
    timestamps = data["timestamp"]

    daily_stats = {}
    for i in range(len(timestamps)):
        dt = datetime.fromtimestamp(timestamps[i], tz=IST)
        date_str = dt.date().isoformat()
        if date_str not in daily_stats:
            daily_stats[date_str] = {
                "first_open": opens[i],
                "day_high": highs[i],
                "day_low": lows[i],
                "last_close": closes[i],
            }
        else:
            daily_stats[date_str]["day_high"] = max(daily_stats[date_str]["day_high"], highs[i])
            daily_stats[date_str]["day_low"] = min(daily_stats[date_str]["day_low"], lows[i])
            daily_stats[date_str]["last_close"] = closes[i]

    # Compute daily metrics and categorize
    categorized = {
        "strong_up": [],
        "strong_down": [],
        "high_volatility": [],
        "sideways": [],
        "normal": [],
    }

    for date_str, stats in sorted(daily_stats.items()):
        day_open = stats["first_open"]
        day_close = stats["last_close"]
        day_high = stats["day_high"]
        day_low = stats["day_low"]

        if day_open <= 0:
            continue

        change_pct = (day_close - day_open) / day_open * 100
        day_range_pct = (day_high - day_low) / day_open * 100

        category = "normal"
        if change_pct > 1.0:
            category = "strong_up"
        elif change_pct < -1.0:
            category = "strong_down"
        elif day_range_pct > 1.5 and -0.5 <= change_pct <= 0.5:
            category = "high_volatility"
        elif -0.5 < change_pct < 0.5:
            category = "sideways"

        categorized[category].append({
            "date": date_str,
            "change_pct": round(change_pct, 2),
            "day_range_pct": round(day_range_pct, 2),
            "open": day_open,
            "close": day_close,
        })

    # Pick 8 stratified days
    selected = []
    targets = [
        ("strong_up", 2),
        ("strong_down", 2),
        ("sideways", 2),
        ("high_volatility", 1),
        ("normal", 1),
    ]

    for category, count in targets:
        pool = categorized[category]
        # Pick most recent days from each category
        picked = pool[-count:] if len(pool) >= count else pool
        for p in picked:
            selected.append(p["date"])

    # Fill remaining from normal pool if needed
    while len(selected) < 8:
        for cat in ["normal", "sideways", "strong_up"]:
            for day_info in categorized[cat]:
                if day_info["date"] not in selected:
                    selected.append(day_info["date"])
                    break
            if len(selected) >= 8:
                break

    # Limit to most recent num_days trading days
    all_dates = sorted(daily_stats.keys())
    recent_dates = all_dates[-num_days:] if len(all_dates) > num_days else all_dates
    selected = [d for d in selected if d in recent_dates][:8]

    return {
        "selected_days": sorted(selected),
        "categorized": {k: [d["date"] for d in v] for k, v in categorized.items()},
        "all_stats": {d["date"]: d for cat_days in categorized.values() for d in cat_days},
        "method": "stratified",
        "total_trading_days_found": len(daily_stats),
    }
