"""LLM replay module — real Bedrock calls for backtest with caching.

Uses the SAME functions as live trading:
- intraday/selector.py: select_trades_llm, _build_system_prompt, _build_user_prompt
- llm/bedrock_client.py: BedrockClient
- config/config_loader.py: load_config, load_intraday_config
- config/profile_loader.py: load_profile

NO proxy. NO approximation. Real LLM calls, cached for reproducibility.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Known FNO stocks (for is_fno flag in candidate dicts)
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


def load_profile_config(profile: str):
    """Load IntraConfig for given profile using same loader as run_intraday.py.

    Returns (intra_config, app_config) tuple.
    """
    from config.config_loader import load_config, load_intraday_config
    from config.profile_loader import load_profile

    app_config = load_config("config/config.yaml")
    intra_config = load_intraday_config("config/config.yaml")

    profile_config = load_profile(profile)
    intra_overrides = profile_config.get("intraday", {})
    for k, v in intra_overrides.items():
        if hasattr(intra_config, k):
            setattr(intra_config, k, v)

    return intra_config, app_config


def build_market_context_for_date(target_date: str, universe_data: dict) -> dict:
    """Reconstruct candidates + VIX from historical 1-min OHLC data.

    Simulates what scanner.py would produce at 9:30 AM on target_date.

    Parameters
    ----------
    target_date : str
        'YYYY-MM-DD'
    universe_data : dict
        {symbol: ohlc_dict} where ohlc_dict has open/high/low/close/volume/timestamp arrays.

    Returns
    -------
    dict with candidates, sectors, vix_value, gainers, losers
    """
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    candidates = []

    for symbol, ohlc in universe_data.items():
        if not ohlc or not ohlc.get("open"):
            continue

        timestamps = ohlc["timestamp"]
        opens = ohlc["open"]
        highs = ohlc["high"]
        lows = ohlc["low"]
        closes = ohlc["close"]
        volumes = ohlc["volume"]

        # Get candles for target date
        day_candles = []
        for i in range(len(timestamps)):
            dt = datetime.fromtimestamp(timestamps[i], tz=IST)
            if dt.date() == target_dt:
                day_candles.append({
                    "open": opens[i], "high": highs[i], "low": lows[i],
                    "close": closes[i], "volume": volumes[i], "time": dt,
                })

        if len(day_candles) < 3:
            continue

        # Get prev day close
        prev_close = 0.0
        for i in range(len(timestamps) - 1, -1, -1):
            dt = datetime.fromtimestamp(timestamps[i], tz=IST)
            if dt.date() < target_dt:
                prev_close = closes[i]
                break

        if prev_close <= 0:
            continue

        # First 3 candles = 9:15, 9:16, 9:17 (1-min) or 9:15, 9:20, 9:25 (5-min)
        # For 1-min data, use first 15 candles (9:15-9:30)
        scan_candles = day_candles[:15]  # First 15 minutes
        if len(scan_candles) < 3:
            continue

        open_price = scan_candles[0]["open"]
        ltp = scan_candles[-1]["close"]  # Price at ~9:30
        volume = sum(c["volume"] for c in scan_candles)
        day_high = max(c["high"] for c in scan_candles)
        day_low = min(c["low"] for c in scan_candles)

        change_pct = (ltp - prev_close) / prev_close * 100
        gap_pct = (open_price - prev_close) / prev_close * 100
        change_from_open = (ltp - open_price) / open_price * 100 if open_price > 0 else 0

        # Score using scanner v3 logic
        long_score = 0
        # Signal 1: Intraday continuation
        if change_from_open > 4.0: long_score += 5
        elif change_from_open > 2.0: long_score += 4
        elif change_from_open > 1.0: long_score += 3
        elif change_from_open > 0.5: long_score += 2
        elif change_from_open > 0.0: long_score += 1

        # Signal 2: Momentum strength
        if change_pct > 15.0: long_score += 8
        elif change_pct > 10.0: long_score += 6
        elif change_pct > 7.0: long_score += 5
        elif change_pct > 5.0: long_score += 4
        elif change_pct > 3.0: long_score += 3
        elif change_pct > 2.0: long_score += 2
        elif change_pct > 1.0: long_score += 1

        # Signal 3: Near day high
        pct_from_high = ((day_high - ltp) / day_high * 100) if day_high > 0 else 99
        if pct_from_high < 0.5: long_score += 2
        elif pct_from_high < 1.5: long_score += 1

        # Signal 4: Volume (project to full day)
        projected_volume = volume * (375 / 15)  # 375 1-min candles, we have 15
        if projected_volume > 5_000_000: long_score += 2
        elif projected_volume > 2_000_000: long_score += 1

        # Signal 5: FNO bonus
        if symbol in FNO_STOCKS: long_score += 1

        # Time multiplier: 1.5 (simulating 9:30 AM)
        long_score = int(long_score * 1.5)

        # Fade detector
        fade_pct = ((day_high - ltp) / day_high * 100) if day_high > 0 else 0
        if fade_pct > 3.0: long_score -= 3
        elif fade_pct > 1.5: long_score -= 1
        if gap_pct > 2.0 and change_from_open < 0: long_score -= 3
        if gap_pct > 3.0 and change_from_open < 0.5: long_score -= 2

        # Short score
        short_score = 0
        if change_from_open < -4.0: short_score += 5
        elif change_from_open < -2.0: short_score += 4
        elif change_from_open < -1.0: short_score += 3
        elif change_from_open < -0.5: short_score += 2
        elif change_from_open < 0.0: short_score += 1

        if change_pct < -15.0: short_score += 8
        elif change_pct < -10.0: short_score += 6
        elif change_pct < -7.0: short_score += 5
        elif change_pct < -5.0: short_score += 4
        elif change_pct < -3.0: short_score += 3
        elif change_pct < -2.0: short_score += 2
        elif change_pct < -1.0: short_score += 1
        short_score = int(short_score * 1.5)

        # Build candidate dict matching scanner.py structure (line 535)
        candidates.append({
            "symbol": symbol,
            "name": symbol,
            "ltp": round(ltp, 2),
            "open_price": round(open_price, 2),
            "prev_close": round(prev_close, 2),
            "change": round(ltp - prev_close, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(volume),
            "gap_pct": round(gap_pct, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "year_high": round(day_high * 1.1, 2),  # Approximation: no 52w data in OHLC
            "year_low": round(day_low * 0.7, 2),    # Approximation: no 52w data in OHLC
            "near_52w_high_pct": 10.0,  # Placeholder — no 52w data available
            "near_52w_low_pct": 30.0,   # Placeholder — no 52w data available
            "change_from_open": round(change_from_open, 2),
            "high_volatility": abs(gap_pct) > 3.0 or ((day_high - day_low) / prev_close * 100) > 5.0,
            "is_fno": symbol in FNO_STOCKS,
            "industry": "",  # Not available in historical OHLC
            "category": "active",
            "high": round(day_high, 2),
            "low": round(day_low, 2),
            "long_score": long_score,
            "short_score": short_score,
            "setup_type": "LONG" if long_score > short_score else ("SHORT" if short_score > 0 else ""),
        })

    # Sort and pick top candidates (matching scanner output: top 15 long + 15 short)
    long_candidates = sorted(
        [c for c in candidates if c["long_score"] > 3],
        key=lambda x: x["long_score"], reverse=True,
    )[:15]
    short_candidates = sorted(
        [c for c in candidates if c["short_score"] > 3 and c["change_pct"] < 0],
        key=lambda x: x["short_score"], reverse=True,
    )[:15]

    for c in long_candidates:
        c["setup_type"] = "LONG"
    for c in short_candidates:
        c["setup_type"] = "SHORT"

    # Combine (deduplicate)
    seen = set()
    combined = []
    for c in long_candidates + short_candidates:
        if c["symbol"] not in seen:
            seen.add(c["symbol"])
            combined.append(c)

    # Estimate VIX from NIFTY day range (no historical VIX available)
    # Use all candles for the day to compute range
    nifty_ohlc = universe_data.get("NIFTY 50", universe_data.get("NIFTY", None))
    vix_estimate = 15.0  # Default moderate
    if nifty_ohlc and nifty_ohlc.get("open"):
        nifty_day_candles = []
        for i in range(len(nifty_ohlc["timestamp"])):
            dt = datetime.fromtimestamp(nifty_ohlc["timestamp"][i], tz=IST)
            if dt.date() == target_dt:
                nifty_day_candles.append({
                    "high": nifty_ohlc["high"][i],
                    "low": nifty_ohlc["low"][i],
                    "open": nifty_ohlc["open"][i],
                })
        if nifty_day_candles:
            day_high_n = max(c["high"] for c in nifty_day_candles)
            day_low_n = min(c["low"] for c in nifty_day_candles)
            day_open_n = nifty_day_candles[0]["open"]
            range_pct = (day_high_n - day_low_n) / day_open_n * 100
            # Rough VIX estimate: range% * 10 (empirical)
            vix_estimate = round(range_pct * 10, 1)
            vix_estimate = max(10.0, min(35.0, vix_estimate))

    # Gainers and losers
    gainers = sorted(combined, key=lambda x: x["change_pct"], reverse=True)[:5]
    losers = sorted(combined, key=lambda x: x["change_pct"])[:5]

    return {
        "candidates": combined,
        "sectors": [],  # Historical sector index data not available
        "vix_value": vix_estimate,
        "gainers": gainers,
        "losers": losers,
    }


def call_llm_for_picks(
    target_date: str,
    profile: str,
    market_context: dict,
    config,
    bedrock_client,
    cache_dir: str = "cache/backtest_llm",
) -> list[dict]:
    """Get LLM picks for date+profile. Cache in cache/backtest_llm/{date}_{profile}.json.

    Uses select_trades_llm from intraday/selector.py — the SAME function used live.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"{target_date}_{profile}.json"

    # Check cache
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            logger.info("LLM cache HIT: %s", cache_file.name)
            return cached
        except Exception:
            pass

    # Real LLM call
    from intraday.selector import select_trades_llm

    candidates = market_context["candidates"]
    sectors = market_context["sectors"]
    vix_value = market_context["vix_value"]
    gainers = market_context.get("gainers")
    losers = market_context.get("losers")

    logger.info("LLM call: %s %s (%d candidates, VIX=%.1f)",
                target_date, profile, len(candidates), vix_value)

    trade_setups = select_trades_llm(
        candidates=candidates,
        sectors=sectors,
        vix_value=vix_value,
        config=config,
        bedrock_client=bedrock_client,
        gainers=gainers,
        losers=losers,
        dry_run=False,
        db=None,
    )

    # Convert TradeSetup objects to dicts for caching
    picks = []
    for ts in trade_setups:
        picks.append({
            "symbol": ts.nse_symbol,
            "stock_name": ts.stock_name,
            "direction": "LONG" if ts.transaction_type == "BUY" else "SHORT",
            "entry_price": ts.entry_price,
            "target_price": ts.target_price,
            "stop_loss_price": ts.stop_loss_price,
            "confidence_score": ts.confidence_score,
            "rationale": ts.rationale,
            "strategy_type": ts.strategy_type,
            "risk_reward_ratio": ts.risk_reward_ratio,
            "transaction_type": ts.transaction_type,
        })

    # Save to cache
    with open(cache_file, "w") as f:
        json.dump(picks, f, indent=2)
    logger.info("LLM cache SAVED: %s (%d picks)", cache_file.name, len(picks))

    return picks
