"""Backtest trade simulator — simulates intraday trade execution on 1-min candles.

Core engine for backtest v1. Replays scanner v3 scoring, picks top 5 stocks,
simulates entry/exit on 1-min OHLC data with realistic charges.

Assumption: LLM picks approximated by scanner v3 top-5 scores.
Real LLM integration in v1.1.
"""

import json
import logging
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtest.scanner_replay import _score_stock_at_930, _get_candles_for_date, _get_prev_close
from intraday.charges import calculate_intraday_charges

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def build_market_context_for_date(
    target_date: str,
    historical_data: dict[str, dict],
    universe: dict[str, str],
) -> dict:
    """Reconstruct what scanner would see at 9:30 AM for a given date.

    Parameters
    ----------
    target_date : str
        'YYYY-MM-DD'
    historical_data : dict
        {symbol: ohlc_dict}
    universe : dict
        {symbol: security_id}

    Returns
    -------
    dict with scored_stocks (list), nifty_range_pct (float), date
    """
    scored = []
    for symbol in universe:
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = _get_candles_for_date(ohlc, target_date)
        if not candles or len(candles) < 3:
            continue

        prev_close = _get_prev_close(ohlc, target_date)
        result = _score_stock_at_930(symbol, candles, prev_close)
        if result:
            scored.append(result)

    # Estimate NIFTY day range from available data (proxy for VIX gate)
    # Use average range of top stocks as proxy
    nifty_range_pct = 0.0
    if scored:
        ranges = [abs(s["change_pct"]) for s in scored[:20]]
        nifty_range_pct = sum(ranges) / len(ranges) if ranges else 0.0

    return {
        "date": target_date,
        "scored_stocks": scored,
        "nifty_range_pct": round(nifty_range_pct, 2),
        "universe_scanned": len(scored),
    }


def simulate_trade_execution(
    pick: dict,
    symbol_data: dict,
    target_date: str,
    profile_config: dict,
) -> dict:
    """Simulate one trade with 1-min candles.

    Entry at 9:30 AM candle open * 1.003 (LONG) or * 0.997 (SHORT).
    Walk 1-min candles from 9:31 onward.
    Force exit at 15:15 IST close.

    Parameters
    ----------
    pick : dict
        Scored stock dict from scanner_replay (has symbol, long_score, short_score, ltp_at_930)
    symbol_data : dict
        Full OHLC data for this symbol
    target_date : str
        'YYYY-MM-DD'
    profile_config : dict
        Profile intraday config (per_trade_max_capital, etc.)

    Returns
    -------
    dict with trade details: symbol, direction, entry, exit, pnl, charges, net_pnl, exit_reason, exit_time
    """
    candles = _get_candles_for_date(symbol_data, target_date)
    if not candles or len(candles) < 10:
        return None

    # Determine direction
    direction = "LONG" if pick["long_score"] >= pick["short_score"] else "SHORT"

    # Find 9:30 AM candle (approximately candle index 15 for 1-min from 9:15)
    # 9:15 = candle 0, 9:30 = candle 15
    entry_candle_idx = None
    for i, c in enumerate(candles):
        ct = c["time"] if "time" in c else datetime.fromtimestamp(c["timestamp"], tz=IST)
        if ct.hour == 9 and ct.minute >= 30:
            entry_candle_idx = i
            break

    if entry_candle_idx is None or entry_candle_idx >= len(candles) - 5:
        return None

    # Entry price with buffer
    entry_candle = candles[entry_candle_idx]
    raw_entry = entry_candle["open"]

    if direction == "LONG":
        entry_price = round(raw_entry * 1.003, 2)
        sl_price = round(entry_price * 0.982, 2)
        target_price = round(entry_price * 1.036, 2)
    else:
        entry_price = round(raw_entry * 0.997, 2)
        sl_price = round(entry_price * 1.018, 2)
        target_price = round(entry_price * 0.964, 2)

    # Position sizing
    per_trade_cap = profile_config.get("per_trade_max_capital", 50000)
    qty = max(1, int(per_trade_cap / entry_price))

    # Walk candles from entry+1 onward
    exit_price = None
    exit_reason = None
    exit_time = None

    for i in range(entry_candle_idx + 1, len(candles)):
        c = candles[i]
        ct = c["time"] if "time" in c else datetime.fromtimestamp(c["timestamp"], tz=IST)

        # Force exit at 15:15 IST
        if ct.hour > 15 or (ct.hour == 15 and ct.minute >= 15):
            exit_price = c["close"]
            exit_reason = "FORCE_EXIT_1515"
            exit_time = ct.strftime("%H:%M")
            break

        if direction == "LONG":
            # Check SL hit first (conservative: if both in same candle, SL first)
            if c["low"] <= sl_price:
                exit_price = sl_price
                exit_reason = "STOPPED_OUT"
                exit_time = ct.strftime("%H:%M")
                break
            # Check target hit
            if c["high"] >= target_price:
                exit_price = target_price
                exit_reason = "TARGET_HIT"
                exit_time = ct.strftime("%H:%M")
                break
        else:  # SHORT
            # SL hit (price goes UP to SL)
            if c["high"] >= sl_price:
                exit_price = sl_price
                exit_reason = "STOPPED_OUT"
                exit_time = ct.strftime("%H:%M")
                break
            # Target hit (price goes DOWN to target)
            if c["low"] <= target_price:
                exit_price = target_price
                exit_reason = "TARGET_HIT"
                exit_time = ct.strftime("%H:%M")
                break

    # If no exit triggered (shouldn't happen with force exit, but safety)
    if exit_price is None:
        exit_price = candles[-1]["close"]
        exit_reason = "EOD_CLOSE"
        exit_time = "15:30"

    # Compute P&L
    if direction == "LONG":
        gross_pnl = (exit_price - entry_price) * qty
        charges = calculate_intraday_charges(entry_price, exit_price, qty)
    else:
        gross_pnl = (entry_price - exit_price) * qty
        charges = calculate_intraday_charges(exit_price, entry_price, qty)

    net_pnl = round(gross_pnl - charges, 2)

    return {
        "symbol": pick["symbol"],
        "direction": direction,
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "sl_price": round(sl_price, 2),
        "target_price": round(target_price, 2),
        "qty": qty,
        "gross_pnl": round(gross_pnl, 2),
        "charges": round(charges, 2),
        "net_pnl": net_pnl,
        "exit_reason": exit_reason,
        "exit_time": exit_time,
        "long_score": pick["long_score"],
        "short_score": pick["short_score"],
        "change_pct_at_930": pick["change_pct"],
    }


def simulate_day(
    target_date: str,
    profile: str,
    universe: dict[str, str],
    historical_data: dict[str, dict],
) -> dict:
    """Full day simulation for one profile.

    Reads profile config, applies VIX gate, scores stocks,
    picks top 5 by long_score, simulates trades with daily_loss_limit.

    Assumption: LLM picks approximated by scanner v3 top-5 scores.
    Real LLM integration in v1.1.

    Parameters
    ----------
    target_date : str
        'YYYY-MM-DD'
    profile : str
        Profile name (e.g., 'vishal', 'vishal-live')
    universe : dict
        {symbol: security_id}
    historical_data : dict
        {symbol: ohlc_dict}

    Returns
    -------
    dict with day summary: date, profile, trades, total_pnl, etc.
    """
    # Load profile config
    profile_path = Path(f"config/profiles/{profile}.yaml")
    if not profile_path.exists():
        return {"date": target_date, "profile": profile, "error": f"Profile not found: {profile_path}"}

    with open(profile_path) as f:
        config = yaml.safe_load(f)

    intraday_cfg = config.get("intraday", {})
    max_trades = intraday_cfg.get("max_trades_per_day", 5)
    daily_loss_limit = intraday_cfg.get("daily_loss_limit", 9000)
    vix_threshold = intraday_cfg.get("vix_threshold", 18)

    # Build market context
    context = build_market_context_for_date(target_date, historical_data, universe)

    # VIX gate: estimate VIX from NIFTY day range
    # If average stock range > 2%, assume VIX > 22 (skip or reduce)
    estimated_vix_high = context["nifty_range_pct"] > 2.0
    vix_skip = context["nifty_range_pct"] > 3.0  # Extreme — skip entirely

    if vix_skip:
        return {
            "date": target_date,
            "profile": profile,
            "trades": [],
            "total_gross_pnl": 0,
            "total_charges": 0,
            "total_net_pnl": 0,
            "trades_placed": 0,
            "winners": 0,
            "losers": 0,
            "skipped_reason": "VIX_SKIP (estimated range > 3%)",
            "universe_scanned": context["universe_scanned"],
        }

    # Reduce max trades if high volatility
    if estimated_vix_high:
        max_trades = min(max_trades, 2)

    # Score and pick top 5 by long_score (approximating LLM picks)
    scored = context["scored_stocks"]
    top_picks = sorted(
        [s for s in scored if s["long_score"] >= 3],
        key=lambda x: x["long_score"],
        reverse=True,
    )[:5]

    # Simulate trades with daily loss limit
    trades = []
    cumulative_loss = 0.0

    for pick in top_picks:
        # Check max trades
        if len(trades) >= max_trades:
            break

        # Check daily loss limit
        if abs(cumulative_loss) >= daily_loss_limit:
            break

        symbol_data = historical_data.get(pick["symbol"])
        if not symbol_data:
            continue

        result = simulate_trade_execution(pick, symbol_data, target_date, intraday_cfg)
        if result:
            trades.append(result)
            if result["net_pnl"] < 0:
                cumulative_loss += abs(result["net_pnl"])

    # Aggregate
    total_gross = sum(t["gross_pnl"] for t in trades)
    total_charges = sum(t["charges"] for t in trades)
    total_net = sum(t["net_pnl"] for t in trades)
    winners = sum(1 for t in trades if t["net_pnl"] > 0)
    losers = sum(1 for t in trades if t["net_pnl"] <= 0)

    return {
        "date": target_date,
        "profile": profile,
        "trades": trades,
        "total_gross_pnl": round(total_gross, 2),
        "total_charges": round(total_charges, 2),
        "total_net_pnl": round(total_net, 2),
        "trades_placed": len(trades),
        "winners": winners,
        "losers": losers,
        "win_rate_pct": round(winners / len(trades) * 100, 1) if trades else 0,
        "universe_scanned": context["universe_scanned"],
        "max_trades_allowed": max_trades,
        "vix_reduced": estimated_vix_high,
        "assumption": "LLM picks approximated by scanner v3 top-5 scores. Real LLM integration in v1.1.",
    }
