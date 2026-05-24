"""
Intraday Selector V2 — deterministic rules-based replacement for LLM selection.

Replaces select_trades_llm() in run_intraday.py Phase 7.
Uses rule_engine.generate_orb_signals() V6+V4 strategy.
No LLM. No Bedrock. No boto3. Same input = same output always.

V2 changes from V1 (LLM-based):
  - No LLM confidence score gate
  - No price ceiling (price_range_max used only as hard upper bound)
  - LONG only (no SHORT trades — SHORT WR proven 10-20%)
  - V6 primary: gap > 1.5% + ORB breakout + volume
  - V4 fill: ORB + VWAP + market direction on non-gap days
  - Market direction filter: skip flat/bearish days for longs

Data from 2026-05-24 audit:
  LLM conf 7 live WR: 31%  (losing)
  LLM conf 8 live WR: 25%  (losing)
  V6 backtest WR:     61%  PF 3.61 (proven edge)
  V4 backtest WR:     47%  PF 1.37 (proven edge)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from backtest.rule_engine import generate_orb_signals, get_market_direction
from intraday.models import TradeSetup

if TYPE_CHECKING:
    from intraday.models import IntraConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

# DYNAMIC SUSPENSION LIST — reviewed every 2 weeks
# Rule: stock suspended if WR < 30% over last 14 days with >= 3 trades
# Rule: stock reinstated when WR improves above 45%
# NOT permanent — market regimes change, stocks recover
#
# Only permanent exclusion: structural impossibility
# (e.g. MRF at Rs.1.4L — mathematically untradeable at Rs.10K/trade)
#
# Last reviewed: 2026-05-24
# Next review:   2026-06-07
#
# To update: run scripts/review_blacklist.py (TODO — build this)

INTRADAY_V2_BLACKLIST = {
    # STRUCTURAL: mathematically untradeable at current capital
    "MRF",          # Rs.1.4L/share — need Rs.1.4L just for 1 share

    # SUSPENDED 2026-05-24: consistent losers from Nifty500 backtest
    # Review 2026-06-07 — remove if live WR improves above 45%
    "SAIL",         # 0-33% WR, -Rs.5,260 across all configs
    "LAURUSLABS",   # 0% WR, -Rs.4,851
    "IPCALAB",      # 0% WR, -Rs.4,209
    "CONCOR",       # 33% WR, -Rs.4,145
    "PRESTIGE",     # 0% WR, -Rs.4,098
    "GNFC",         # 0-50% WR, -Rs.3,309
    "BSE",          # 0% WR, -Rs.3,539
    "SONACOMS",     # 0% WR, -Rs.3,568
    "ANGELONE",     # 0% WR, -Rs.3,054
    "PVRINOX",      # 0% WR, -Rs.2,804
    "PIIND",        # 0% WR, -Rs.2,865
    "MCDOWELL-N",   # 0% WR, -Rs.2,152
    "GODREJCP",     # 0% WR, -Rs.2,739
    "UBL",          # 0% WR, -Rs.3,150

    # SUSPENDED from previous backtest 2026-05-23
    # Review 2026-06-07
    "TATASTEEL", "BPCL", "ASIANPAINT", "HINDUNILVR",
    "TATACONSUM", "HDFCLIFE", "ADANIPOWER", "BEL", "COFORGE",
    "IREDA", "NAUKRI", "BDL", "CANBK", "MAZDOCK",
    "ASTRAL", "FEDERALBNK", "OFSS",
    "BAJAJFINSV", "BAJFINANCE", "HEROMOTOCO", "BAJAJ-AUTO",
    "JSWSTEEL", "INDIGO", "COCHINSHIP",

    # REINSTATED (removed from suspension):
    # None yet — add here when live data shows improvement
}

# PRIORITY WHITELIST — give these priority when they appear as signals
# Consistent winners from Nifty500 backtest 2026-05-24
# These stocks have proven they move cleanly on catalyst days
INTRADAY_V2_WHITELIST = {
    "HINDZINC", "NESTLEIND", "PNBHOUSING", "BHEL",
    "ADANIENSOL", "NTPC", "SHRIRAMFIN", "GRANULES",
    "ULTRACEMCO", "GRASIM", "GAIL", "BOSCHLTD",
    "DRREDDY", "MOTHERSON", "PFC", "LICI",
    "POWERGRID", "CHOLAFIN", "TATACHEM", "GRASIM",
    "IIFLSEC", "TIINDIA", "IRCON", "MARUTI",
}


def select_trades_v2(
    candidates: list[dict],
    historical_data: dict,
    nifty_data: dict,
    config: "IntraConfig",
    target_date: str | None = None,
) -> list[TradeSetup]:
    """
    Rules-based trade selection using V6+V4 ORB strategy.

    Replaces select_trades_llm() entirely.
    No API calls. No LLM. Deterministic.

    Algorithm:
      1. Get Nifty market direction for today
      2. Skip if market is FLAT (no edge)
      3. Generate V6 signals (gap > 1.5% + ORB breakout) — best quality
      4. Fill remaining slots with V4 signals (ORB + VWAP + direction)
      5. Filter: LONG only, not in blacklist
      6. Return top N by signal score (N = config.max_trades_per_day)

    Parameters
    ----------
    candidates : list[dict]
        Pre-filtered candidates from pre_filter_candidates().
        Used to restrict universe to what scanner already approved.
    historical_data : dict
        {symbol: ohlc_dict} with 15-min candles.
        Must be fetched before calling this function.
    nifty_data : dict
        Nifty index 15-min OHLC for market direction.
    config : IntraConfig
        Profile configuration (capital, max_trades, etc.)
    target_date : str | None
        Date to run signals for (YYYY-MM-DD). Defaults to today IST.

    Returns
    -------
    list[TradeSetup]
        Validated trade setups ready for execution.
        Empty list = no trades today (flat market or no signals).
    """
    now = datetime.now(IST)
    if target_date is None:
        target_date = now.strftime("%Y-%m-%d")

    # Build universe from candidates (already pre-filtered by scanner)
    # Map symbol → security_id for rule engine
    candidate_symbols = {c.get("nse_symbol") or c.get("symbol"): c
                         for c in candidates if c.get("nse_symbol") or c.get("symbol")}

    # Filter: remove blacklisted stocks
    candidate_symbols = {
        sym: c for sym, c in candidate_symbols.items()
        if sym not in INTRADAY_V2_BLACKLIST
    }

    if not candidate_symbols:
        logger.warning("V2: No candidates after blacklist filter")
        return []

    # Build universe dict for rule engine (symbol → security_id)
    universe = {}
    for sym, candidate in candidate_symbols.items():
        sec_id = candidate.get("security_id") or candidate.get("securityId", "")
        universe[sym] = str(sec_id)

    orb_config = {
        "per_trade_max_capital": config.per_trade_max_capital,
        "max_trades_per_day": config.max_trades_per_day,
        "daily_loss_limit": getattr(config, "daily_loss_limit", 500),
    }

    # Step 1: V6 signals (gap catalyst — best quality, 61% WR)
    v6_signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=orb_config,
        strategy_variant="V6",
        nifty_data=nifty_data,
    )
    # LONG only, positive gap only
    v6_signals = [
        s for s in v6_signals
        if s.get("direction") == "LONG" and s.get("gap_pct", 0) > 0
    ]

    # Step 2: V4 fills remaining slots (47% WR, PF 1.37)
    remaining = config.max_trades_per_day - len(v6_signals)
    v4_signals = []
    if remaining > 0:
        v6_symbols = {s["symbol"] for s in v6_signals}
        v4_config = {**orb_config, "max_trades_per_day": remaining + 3}
        all_v4 = generate_orb_signals(
            target_date=target_date,
            historical_data=historical_data,
            universe=universe,
            config=v4_config,
            strategy_variant="V4",
            nifty_data=nifty_data,
        )
        v4_signals = [
            s for s in all_v4
            if s.get("direction") == "LONG"
            and s["symbol"] not in v6_symbols
        ][:remaining]

    all_signals = (v6_signals + v4_signals)[:config.max_trades_per_day]

    if not all_signals:
        market = get_market_direction(nifty_data, target_date) if nifty_data else {}
        logger.info(
            "V2: No signals for %s (market: %s %s)",
            target_date,
            market.get("direction", "UNKNOWN"),
            market.get("strength", ""),
        )
        return []

    # Convert signals to TradeSetup objects
    trades = []
    for signal in all_signals:
        symbol = signal["symbol"]
        entry = signal["entry_price"]
        target_price = signal["target_price"]
        sl = signal["stop_loss_price"]
        qty = max(1, int(config.per_trade_max_capital / entry))
        strategy = signal.get("strategy_type", "ORB_V6")

        # Build rationale from signal data — deterministic, not LLM
        rationale = (
            f"{strategy}: gap={signal.get('gap_pct', 0):.1f}%, "
            f"rel_vol={signal.get('rel_volume', 0):.1f}x, "
            f"score={signal.get('score', 0)}, "
            f"market={signal.get('market_direction', '')} "
            f"{signal.get('market_strength', '')}, "
            f"entry={entry}, target={target_price}, sl={sl}"
        )

        try:
            trade = TradeSetup(
                stock_name=symbol,
                nse_symbol=symbol,
                tradingsymbol=symbol,
                action="BUY",
                entry_price=entry,
                target_price=target_price,
                stop_loss_price=sl,
                quantity=qty,
                confidence_score=signal.get("score", 6),
                rationale=rationale,
                strategy_type=strategy,
            )
            trades.append(trade)
            logger.info(
                "V2 SIGNAL: %s @ ₹%.2f → ₹%.2f (SL ₹%.2f) | "
                "gap=%.1f%% vol=%.1fx score=%d [%s]",
                symbol, entry, target_price, sl,
                signal.get("gap_pct", 0),
                signal.get("rel_volume", 0),
                signal.get("score", 0),
                strategy,
            )
        except Exception as exc:
            logger.warning("V2: Failed to build TradeSetup for %s: %s", symbol, exc)
            continue

    logger.info("V2 selection: %d trades (V6=%d, V4=%d)",
                len(trades), len(v6_signals), len(v4_signals))
    return trades
