"""Backtest trade simulator — simulates intraday trade execution on 1-min candles.

Core engine for backtest v1.1. Uses REAL LLM calls via Bedrock (cached).
Entry/exit simulated on 1-min OHLC data with realistic charges.

Documented limitations:
- sectors=[] (historical sector index data not available)
- VIX estimated from NIFTY 60-min day_range for target_date
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

    # Determine direction — use LLM-provided direction if available, else score-based
    if "direction" in pick:
        direction = pick["direction"]
    else:
        direction = "LONG" if pick.get("long_score", 0) >= pick.get("short_score", 0) else "SHORT"

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

    # Entry/SL/Target: use LLM-provided prices if available, else compute from candle
    entry_candle = candles[entry_candle_idx]
    if pick.get("entry_price") and pick.get("target_price") and pick.get("stop_loss_price"):
        entry_price = pick["entry_price"]
        target_price = pick["target_price"]
        sl_price = pick["stop_loss_price"]
    else:
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
        "long_score": pick.get("long_score", 0),
        "short_score": pick.get("short_score", 0),
        "change_pct_at_930": pick.get("change_pct", 0),
        "confidence_score": pick.get("confidence_score", 0),
    }


def simulate_day(
    target_date: str,
    profile: str,
    universe: dict[str, str],
    historical_data: dict[str, dict],
    bedrock_client=None,
) -> dict:
    """Full day simulation for one profile using REAL LLM picks.

    Uses backtest/llm_replay.py for real Bedrock calls (cached).
    Applies VIX gate, confidence threshold, R:R check, max_trades, daily_loss_limit.

    Documented limitations:
    - sectors=[] (historical sector index data not available)
    - VIX estimated from NIFTY day_range
    """
    from backtest.llm_replay import load_profile_config, build_market_context_for_date as build_llm_context, call_llm_for_picks

    # Load profile config using same loader as run_intraday.py
    intra_config, app_config = load_profile_config(profile)

    max_trades = intra_config.max_trades_per_day
    daily_loss_limit = intra_config.daily_loss_limit
    vix_threshold = intra_config.vix_threshold
    min_confidence = intra_config.min_confidence_score
    per_trade_max = intra_config.per_trade_max_capital

    # Build market context from historical data
    context = build_llm_context(target_date, historical_data)
    vix_value = context["vix_value"]

    # VIX gate
    if vix_value > vix_threshold:
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
            "win_rate_pct": 0,
            "skipped_reason": f"VIX_GATE_SKIP (VIX={vix_value} > threshold={vix_threshold})",
            "vix_value": vix_value,
            "candidates_count": len(context["candidates"]),
        }

    # Get LLM picks (real Bedrock call, cached)
    if not bedrock_client:
        from llm.bedrock_client import BedrockClient
        bedrock_client = BedrockClient(
            region=app_config.bedrock_region,
            model_id=app_config.bedrock_model_id,
        )

    picks = call_llm_for_picks(
        target_date=target_date,
        profile=profile,
        market_context=context,
        config=intra_config,
        bedrock_client=bedrock_client,
    )

    # Filter picks by confidence and R:R
    valid_picks = []
    filtered_reasons = []
    for p in picks:
        conf = p.get("confidence_score", 0)
        if conf < min_confidence:
            filtered_reasons.append(f"{p['symbol']}: conf={conf} < {min_confidence}")
            continue

        entry = p.get("entry_price", 0)
        target = p.get("target_price", 0)
        sl = p.get("stop_loss_price", 0)
        direction = p.get("direction", "LONG")

        if direction == "LONG" and entry > 0 and sl > 0:
            rr = (target - entry) / (entry - sl) if entry > sl else 0
        elif direction == "SHORT" and entry > 0 and sl > 0:
            rr = (entry - target) / (sl - entry) if sl > entry else 0
        else:
            rr = 0

        if rr < 1.99:  # Accept R:R >= 2.0 (floating point safe)
            filtered_reasons.append(f"{p['symbol']}: R:R={rr:.1f} < 2.0")
            continue

        valid_picks.append(p)

    # Simulate trades with max_trades and daily_loss_limit
    trades = []
    cumulative_loss = 0.0
    intraday_cfg = {
        "per_trade_max_capital": per_trade_max,
        "daily_loss_limit": daily_loss_limit,
    }

    for pick in valid_picks:
        if len(trades) >= max_trades:
            break
        if abs(cumulative_loss) >= daily_loss_limit:
            break

        symbol = pick["symbol"]
        symbol_data = historical_data.get(symbol)
        if not symbol_data:
            continue

        # Build pick dict compatible with simulate_trade_execution
        sim_pick = {
            "symbol": symbol,
            "direction": pick.get("direction", "LONG"),
            "entry_price": pick.get("entry_price", 0),
            "target_price": pick.get("target_price", 0),
            "stop_loss_price": pick.get("stop_loss_price", 0),
            "confidence_score": pick.get("confidence_score", 0),
        }

        result = simulate_trade_execution(sim_pick, symbol_data, target_date, intraday_cfg)
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
        "vix_value": vix_value,
        "candidates_count": len(context["candidates"]),
        "llm_picks_count": len(picks),
        "filtered_picks": filtered_reasons,
        "max_trades_allowed": max_trades,
    }

