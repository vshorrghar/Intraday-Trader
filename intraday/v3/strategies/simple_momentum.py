"""S3 Simple Momentum — trades EVERY day. No regime gates. No LLM.

Logic:
1. From bulk LTP data, find stocks that gapped up > 0.5% from prev_close
2. Filter: volume > 500K, price Rs50-5000
3. Rank by gap size (strongest first)
4. Take top 3
5. Entry: current LTP
6. SL: 1.5% below entry
7. Target: 3% above entry (2:1 R:R)
8. Max 3 trades/day

That's it. No regime. No breadth. No VIX. No Claude.
Trades every day there's at least 1 stock with a gap-up.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def find_simple_momentum_trades(candidates: list, config: dict) -> list:
    """Find strongest gap-up stocks from bulk LTP data.

    Args:
        candidates: List of dicts with {symbol, ltp, open, volume, prev_close, sector, mcap_bucket}
        config: {per_trade_max_capital, max_trades_per_day}

    Returns:
        List of trade signals ready for executor.
    """
    per_trade = config.get("per_trade_max_capital", 65000)
    max_trades = config.get("max_trades_per_day", 3)

    # Filter: has data, gapped up, has volume
    eligible = []
    for c in candidates:
        ltp = c.get("ltp", 0)
        prev = c.get("prev_close", 0)
        volume = c.get("volume", 0)
        open_price = c.get("open", 0)

        if ltp <= 0 or prev <= 0:
            continue
        if ltp < 50 or ltp > 5000:
            continue
        if volume < 500000:
            continue

        # Gap: open vs prev_close
        gap_pct = (open_price - prev) / prev * 100 if prev > 0 and open_price > 0 else 0

        # Current momentum: ltp vs open
        momentum_pct = (ltp - open_price) / open_price * 100 if open_price > 0 else 0

        # Must be up from prev close (any amount — no minimum gap gate)
        change_pct = (ltp - prev) / prev * 100
        if change_pct < 0.5:  # Very loose: just needs to be up 0.5%+ from yesterday
            continue

        eligible.append({
            **c,
            "gap_pct": round(gap_pct, 2),
            "momentum_pct": round(momentum_pct, 2),
            "change_pct": round(change_pct, 2),
        })

    if not eligible:
        logger.info("SIMPLE_MOMENTUM: 0 eligible stocks (all < 0.5%% up)")
        return []

    # Rank by change_pct (strongest movers first)
    eligible.sort(key=lambda x: x["change_pct"], reverse=True)

    # Take top N
    picks = eligible[:max_trades]

    # Build trade signals
    signals = []
    for p in picks:
        entry = p["ltp"]
        sl = round(entry * 0.985, 2)  # 1.5% SL
        target = round(entry * 1.03, 2)  # 3% target (2:1 R:R)
        qty = max(1, int(per_trade / entry))

        signals.append({
            "symbol": p["symbol"],
            "direction": "LONG",
            "entry_price": entry,
            "stop_loss": sl,
            "target": target,
            "qty": qty,
            "score": p["change_pct"],
            "strategy": "SIMPLE_MOMENTUM",
            "confidence": 7,
            "gap_pct": p["gap_pct"],
            "change_pct": p["change_pct"],
            "volume": p["volume"],
        })

    logger.info("SIMPLE_MOMENTUM: %d trades from %d eligible (top by change%%)",
                len(signals), len(eligible))
    return signals
