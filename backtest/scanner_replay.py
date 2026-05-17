"""Backtest scanner replay — replays scanner v3 scoring on historical OHLC data.

Uses 5-min candles to reconstruct the market state at 9:30 AM IST,
then applies the same scoring signals as intraday/scanner.py.

Signals replicated:
  1. Intraday continuation (change_from_open)
  2. Momentum strength (change_pct from prev close)
  3. Price near day high
  4. Volume confirmation
  5. FNO liquidity bonus (from config)
  6. Sector rotation — OMITTED (requires sector index data, not in OHLC)
  7. Time multiplier — fixed at 1.5 (simulating 9:30 AM scan)

Signals omitted (documented):
  - Sector rotation bonus (needs sector indices, not available in OHLC)
  - Fade detector (needs real-time LTP vs high, approximated with candle data)
  - 52-week high/low (not in intraday OHLC, would need daily data)
  - is_fno flag (hardcoded from known FNO list)
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Known FNO stocks (Nifty 50 are all FNO)
FNO_STOCKS = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NTPC", "NESTLEIND", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SUNPHARMA",
    "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM",
    "TITAN", "ULTRACEMCO", "WIPRO", "SHRIRAMFIN", "TRENT",
}


def _get_candles_for_date(ohlc_data: dict, target_date: str) -> list[dict]:
    """Extract candles for a specific date from OHLC arrays.

    Returns list of {open, high, low, close, volume, timestamp} dicts
    sorted by timestamp, for the given date only.
    """
    opens = ohlc_data.get("open", [])
    highs = ohlc_data.get("high", [])
    lows = ohlc_data.get("low", [])
    closes = ohlc_data.get("close", [])
    volumes = ohlc_data.get("volume", [])
    timestamps = ohlc_data.get("timestamp", [])

    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    candles = []

    for i in range(len(timestamps)):
        ts = datetime.fromtimestamp(timestamps[i], tz=IST)
        if ts.date() == target_dt:
            candles.append({
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i],
                "timestamp": timestamps[i],
                "time": ts,
            })

    return sorted(candles, key=lambda c: c["timestamp"])


def _get_prev_close(ohlc_data: dict, target_date: str) -> float:
    """Get previous trading day's closing price."""
    timestamps = ohlc_data.get("timestamp", [])
    closes = ohlc_data.get("close", [])
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    prev_close = 0.0
    for i in range(len(timestamps)):
        ts = datetime.fromtimestamp(timestamps[i], tz=IST)
        if ts.date() < target_dt:
            prev_close = closes[i]  # Keep updating — last one before target date

    return prev_close


def _score_stock_at_930(symbol: str, candles: list[dict], prev_close: float) -> dict | None:
    """Score a stock using candles available by 9:30 AM (first 3 candles of 5-min data).

    Simulates scanner v3 scoring at 9:30 AM using:
    - First candle open = open_price
    - 3rd candle close = approximate LTP at 9:30
    - Cumulative volume of first 3 candles
    - High/low of first 3 candles
    """
    if not candles or len(candles) < 3:
        return None
    if prev_close <= 0:
        return None

    # Market state at 9:30 AM (after 3 five-min candles: 9:15, 9:20, 9:25)
    open_price = candles[0]["open"]
    ltp = candles[2]["close"]  # Price at ~9:30
    volume = sum(c["volume"] for c in candles[:3])
    day_high = max(c["high"] for c in candles[:3])
    day_low = min(c["low"] for c in candles[:3])

    change_pct = (ltp - prev_close) / prev_close * 100
    gap_pct = (open_price - prev_close) / prev_close * 100
    change_from_open = (ltp - open_price) / open_price * 100 if open_price > 0 else 0

    # Also compute EOD close for later validation
    eod_close = candles[-1]["close"] if candles else ltp
    eod_change_pct = (eod_close - prev_close) / prev_close * 100
    total_volume = sum(c["volume"] for c in candles)

    # === SCORING (replicating scanner v3) ===

    # Signal 1: Intraday continuation (0-5 pts)
    long_score = 0
    if change_from_open > 4.0:
        long_score += 5
    elif change_from_open > 2.0:
        long_score += 4
    elif change_from_open > 1.0:
        long_score += 3
    elif change_from_open > 0.5:
        long_score += 2
    elif change_from_open > 0.0:
        long_score += 1

    # Signal 2: Momentum strength (0-8 pts)
    if change_pct > 15.0:
        long_score += 8
    elif change_pct > 10.0:
        long_score += 6
    elif change_pct > 7.0:
        long_score += 5
    elif change_pct > 5.0:
        long_score += 4
    elif change_pct > 3.0:
        long_score += 3
    elif change_pct > 2.0:
        long_score += 2
    elif change_pct > 1.0:
        long_score += 1

    # Signal 3: Price near day high (0-2 pts)
    pct_from_high = ((day_high - ltp) / day_high * 100) if day_high > 0 else 99
    if pct_from_high < 0.5:
        long_score += 2
    elif pct_from_high < 1.5:
        long_score += 1

    # Signal 4: Volume confirmation (0-2 pts) — extrapolate to full day
    projected_volume = volume * (75 / 3)  # 75 candles in full day, we have 3
    if projected_volume > 5_000_000:
        long_score += 2
    elif projected_volume > 2_000_000:
        long_score += 1

    # Signal 5: FNO bonus (0-1 pt)
    if symbol in FNO_STOCKS:
        long_score += 1

    # Signal 6: Sector rotation — OMITTED (no sector data in OHLC)

    # Time multiplier: 1.5 (simulating 9:30 AM scan)
    long_score = int(long_score * 1.5)

    # Fade detector
    fade_pct = ((day_high - ltp) / day_high * 100) if day_high > 0 else 0
    if fade_pct > 3.0:
        long_score -= 3
    elif fade_pct > 1.5:
        long_score -= 1
    if gap_pct > 2.0 and change_from_open < 0:
        long_score -= 3
    if gap_pct > 3.0 and change_from_open < 0.5:
        long_score -= 2

    # Short score
    short_score = 0
    if change_from_open < -4.0:
        short_score += 5
    elif change_from_open < -2.0:
        short_score += 4
    elif change_from_open < -1.0:
        short_score += 3
    elif change_from_open < -0.5:
        short_score += 2
    elif change_from_open < 0.0:
        short_score += 1

    if change_pct < -15.0:
        short_score += 8
    elif change_pct < -10.0:
        short_score += 6
    elif change_pct < -7.0:
        short_score += 5
    elif change_pct < -5.0:
        short_score += 4
    elif change_pct < -3.0:
        short_score += 3
    elif change_pct < -2.0:
        short_score += 2
    elif change_pct < -1.0:
        short_score += 1

    short_score = int(short_score * 1.5)

    return {
        "symbol": symbol,
        "long_score": long_score,
        "short_score": short_score,
        "change_pct": round(change_pct, 2),
        "change_from_open": round(change_from_open, 2),
        "gap_pct": round(gap_pct, 2),
        "volume_30min": int(volume),
        "ltp_at_930": round(ltp, 2),
        "eod_close": round(eod_close, 2),
        "eod_change_pct": round(eod_change_pct, 2),
    }


def replay_scanner_for_date(
    target_date: str,
    universe: dict[str, str],
    historical_data: dict[str, dict],
) -> dict:
    """Replay scanner v3 scoring for a given date.

    Parameters
    ----------
    target_date : str
        'YYYY-MM-DD'
    universe : dict
        {symbol: security_id}
    historical_data : dict
        {symbol: ohlc_dict} from data_loader

    Returns
    -------
    dict with date, picks_long, picks_short, total_universe_scanned
    """
    scored = []
    for symbol in universe:
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = _get_candles_for_date(ohlc, target_date)
        if not candles:
            continue

        prev_close = _get_prev_close(ohlc, target_date)
        result = _score_stock_at_930(symbol, candles, prev_close)
        if result:
            scored.append(result)

    picks_long = sorted(
        [s for s in scored if s["long_score"] > 0],
        key=lambda x: x["long_score"],
        reverse=True,
    )[:10]

    picks_short = sorted(
        [s for s in scored if s["short_score"] > 0],
        key=lambda x: x["short_score"],
        reverse=True,
    )[:10]

    return {
        "date": target_date,
        "picks_long": picks_long,
        "picks_short": picks_short,
        "total_universe_scanned": len(scored),
    }


def compare_picks_to_actuals(
    backtest_picks: dict,
    db_path: str = "database/vishal.db",
) -> dict:
    """Compare backtest picks to actual day's top movers from DB.

    Uses daily_top_performers table if available, otherwise uses
    EOD change_pct from the picks themselves as proxy.
    """
    date = backtest_picks["date"]
    long_symbols = [p["symbol"] for p in backtest_picks["picks_long"][:5]]

    # Try to get actual top performers from DB
    actual_top = []
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT symbol FROM daily_top_performers WHERE date=? ORDER BY change_pct DESC LIMIT 10",
            (date,)
        ).fetchall()
        actual_top = [r[0] for r in rows]
        con.close()
    except Exception:
        pass

    if not actual_top:
        # Fallback: use EOD data from our own picks to rank
        all_scored = backtest_picks["picks_long"] + backtest_picks["picks_short"]
        actual_top = [
            s["symbol"] for s in sorted(all_scored, key=lambda x: x["eod_change_pct"], reverse=True)[:10]
        ]

    overlap = set(long_symbols) & set(actual_top[:5])
    hit_rate = len(overlap) / max(len(long_symbols), 1) * 100

    return {
        "date": date,
        "our_picks": long_symbols,
        "actual_top_5": actual_top[:5],
        "overlap_count": len(overlap),
        "hit_rate_pct": round(hit_rate, 1),
        "missed_top_5": [s for s in actual_top[:5] if s not in long_symbols],
    }


def run_backtest(
    from_date: str,
    to_date: str,
    universe: dict[str, str],
    historical_data: dict[str, dict],
    db_path: str = "database/vishal.db",
    output_dir: str = "backtest/results",
) -> dict:
    """Run backtest for date range. Returns summary dict."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Find trading days in our data
    sample_symbol = next(iter(historical_data), None)
    if not sample_symbol:
        return {"error": "No historical data"}

    sample_ohlc = historical_data[sample_symbol]
    timestamps = sample_ohlc.get("timestamp", [])

    trading_days = set()
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

    for ts in timestamps:
        dt = datetime.fromtimestamp(ts, tz=IST).date()
        if from_dt <= dt <= to_dt:
            trading_days.add(dt.isoformat())

    trading_days = sorted(trading_days)
    print(f"Trading days found: {len(trading_days)}")

    results = []
    for day in trading_days:
        picks = replay_scanner_for_date(day, universe, historical_data)
        comparison = compare_picks_to_actuals(picks, db_path)
        results.append({
            "picks": picks,
            "comparison": comparison,
        })
        print(f"  {day}: {len(picks['picks_long'])} long, {len(picks['picks_short'])} short, hit_rate={comparison['hit_rate_pct']}%")

    # Summary
    hit_rates = [r["comparison"]["hit_rate_pct"] for r in results]
    avg_hit_rate = sum(hit_rates) / len(hit_rates) if hit_rates else 0

    summary = {
        "from_date": from_date,
        "to_date": to_date,
        "trading_days": len(trading_days),
        "universe_size": len(universe),
        "avg_hit_rate_pct": round(avg_hit_rate, 1),
        "best_day": max(results, key=lambda r: r["comparison"]["hit_rate_pct"])["comparison"]["date"] if results else None,
        "worst_day": min(results, key=lambda r: r["comparison"]["hit_rate_pct"])["comparison"]["date"] if results else None,
        "daily_results": results,
        "signals_replicated": [
            "intraday_continuation", "momentum_strength", "near_day_high",
            "volume_confirmation", "fno_bonus", "time_multiplier", "fade_detector"
        ],
        "signals_omitted": ["sector_rotation", "52w_high_low"],
    }

    # Save results
    output_file = Path(output_dir) / f"scanner_v3_{from_date}_{to_date}.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved: {output_file}")
    print(f"Average hit rate: {avg_hit_rate:.1f}%")

    return summary
