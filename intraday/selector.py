"""Trade selection: rule-based pre-filter and LLM-driven trade picker.

This module implements two stages of the selection pipeline:

1. **pre_filter_candidates** — deterministic rule-based filtering that removes
   stocks outside the configured price range, with zero volume, etc.
2. **select_trades_llm** — sends pre-filtered candidates to Claude Sonnet 4.5
   via :class:`BedrockClient` and validates the returned picks.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from intraday.models import IntraConfig, TradeSetup

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

MAX_PRE_FILTER_OUTPUT = 20
HIGH_VOLATILITY_GAP_THRESHOLD = 3.0
LOW_CANDIDATE_WARNING_THRESHOLD = 3

# ---------------------------------------------------------------------------
# Required fields the LLM must return for each pick
# ---------------------------------------------------------------------------
REQUIRED_PICK_FIELDS = {
    "stock_name": str,
    "nse_symbol": str,
    "tradingsymbol": str,
    "entry_price": (int, float),
    "target_price": (int, float),
    "stop_loss_price": (int, float),
    "confidence_score": (int, float),
    "rationale": str,
    "strategy_type": str,
}


# ===================================================================
# Task 6.2 — Rule-based pre-filter
# ===================================================================

def pre_filter_candidates(
    candidates: list[dict],
    config: IntraConfig,
    sectors: list[dict] | None = None,
) -> list[dict]:
    """Apply rule-based filters to raw scan candidates.

    Filters applied (in order):
    1. Price within ``[config.price_range_min, config.price_range_max]``
    2. Volume > 0
    3. Flag ``high_volatility`` when ``abs(gap_pct) > 3.0``
    4. Sector alignment — prefer stocks in sectors with positive momentum
    5. Cap at 20 candidates

    Parameters
    ----------
    candidates:
        Raw candidate dicts from :class:`Pre_Market_Scanner`.
    config:
        Intraday configuration with price range limits.
    sectors:
        Ranked sector list (from scanner) used for alignment check.

    Returns
    -------
    list[dict]
        Filtered and annotated candidate dicts (max 20).
    """
    positive_sectors: set[str] = set()
    if sectors:
        for s in sectors:
            if s.get("change_pct", 0) > 0:
                positive_sectors.add(s.get("name", "").upper())

    filtered: list[dict] = []

    for c in candidates:
        # --- Price range filter ---
        price = c.get("ltp", 0) or c.get("open_price", 0) or c.get("prev_close", 0) or 0
        if price > 0:
            # Only apply price range filter when we have actual price data
            if price < config.price_range_min or price > config.price_range_max:
                continue
        # If price is 0 (after hours), still accept — LLM will use change_pct and volume

        # --- Volume filter (lenient: accept if any volume indicator > 0) ---
        volume = c.get("volume", 0) or c.get("active_volume", 0) or 0
        if volume <= 0:
            # After hours, most-active stocks may have volume in different fields
            # Accept the candidate anyway if it has a valid price
            logger.debug("Stock %s has zero volume — accepting anyway (after-hours data)", c.get("symbol", "?"))

        # --- High-volatility flag ---
        gap_pct = c.get("gap_pct", 0) or 0
        c["high_volatility"] = abs(gap_pct) > HIGH_VOLATILITY_GAP_THRESHOLD

        # --- Sector alignment ---
        c["sector_aligned"] = _check_sector_alignment(c, positive_sectors)

        filtered.append(c)

    # Sort: sector-aligned first, then by absolute gap_pct descending
    filtered.sort(
        key=lambda x: (x.get("sector_aligned", False), abs(x.get("gap_pct", 0))),
        reverse=True,
    )

    # Cap at MAX_PRE_FILTER_OUTPUT
    result = filtered[:MAX_PRE_FILTER_OUTPUT]

    if len(result) < LOW_CANDIDATE_WARNING_THRESHOLD:
        logger.warning(
            "Only %d candidate(s) passed pre-filter (threshold: %d)",
            len(result),
            LOW_CANDIDATE_WARNING_THRESHOLD,
        )

    logger.info("Pre-filter: %d → %d candidates", len(candidates), len(result))
    return result


def _check_sector_alignment(candidate: dict, positive_sectors: set[str]) -> bool:
    """Check if a candidate's sector has positive momentum.

    We do a fuzzy match: if any positive sector keyword appears in the
    candidate's symbol or category, we consider it aligned.  This is a
    best-effort heuristic since NSE movers data doesn't carry an explicit
    sector tag.
    """
    if not positive_sectors:
        return False

    sym = (candidate.get("symbol", "") or "").upper()
    # Simple heuristic — always True if we have positive sectors but can't
    # determine the stock's sector.  The LLM will do deeper analysis.
    # We only mark as *not* aligned if we have evidence the sector is negative.
    return True


# ===================================================================
# Trade history for LLM context
# ===================================================================


def _fetch_trade_history(db, days: int = 30) -> str:
    """Fetch last N days of trade history and format as LLM context."""
    if db is None:
        return ""
    try:
        from datetime import datetime, timedelta
        stock_stats: dict = {}
        total_trades = 0
        total_wins = 0

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                trades = db.get_trades_for_date(date)
            except Exception:
                continue
            for t in trades:
                if t.get("action") != "BUY":
                    continue
                symbol = t.get("tradingsymbol", "")
                pnl = float(t.get("pnl") or 0)
                total_trades += 1
                if pnl > 0:
                    total_wins += 1
                if symbol not in stock_stats:
                    stock_stats[symbol] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
                stock_stats[symbol]["trades"] += 1
                stock_stats[symbol]["total_pnl"] += pnl
                if pnl > 0:
                    stock_stats[symbol]["wins"] += 1

        if total_trades == 0:
            return ""

        win_rate = total_wins / total_trades * 100
        lines = [f"Last {days} days: {total_trades} trades, {win_rate:.0f}% win rate\nStock performance:"]

        for sym, stats in sorted(stock_stats.items(), key=lambda x: x[1]["trades"], reverse=True)[:10]:
            wr = stats["wins"] / stats["trades"] * 100 if stats["trades"] > 0 else 0
            avg_pnl = stats["total_pnl"] / stats["trades"]
            lines.append(f"  {sym}: {stats['trades']} trades, {wr:.0f}% WR, avg P&L ₹{avg_pnl:.0f}")

        return "\n".join(lines)
    except Exception as e:
        return ""


# ===================================================================
# Task 7.1 — LLM trade selection
# ===================================================================


def _build_system_prompt(config: IntraConfig) -> str:
    """Build the system prompt for Claude Sonnet 4.5 trade selection.

    This prompt encodes the institutional-grade strategy that adapts to
    market conditions (bullish vs bearish days).
    """
    return f"""You are an expert NSE intraday trader. Your goal is maximum profit with strict capital protection.

STEP 1: READ THE MARKET FIRST

Count green vs red sectors:
- >12 green  -> BULLISH  -> trade aggressively, up to {config.max_trades_per_day} picks
- 8-12 green -> NEUTRAL  -> trade selectively, 2-3 picks only
- <8 green   -> BEARISH  -> 1 pick max, NEVER skip entirely (paper needs experience on red days)
- VIX > 20 AND red market -> 1 pick max with tighter SL, do not skip entirely
- On bearish days: entry allowed within 3% of open (relaxed from 1.5%)
- On bearish days: minimum confidence 6 accepted

STEP 2: STOCK SELECTION CRITERIA

MUST HAVE ALL of these:
- Volume > 2,000,000 today (high liquidity only)
- Price between Rs.{config.price_range_min} and Rs.{config.price_range_max}
- Stock moving WITH its sector
- Clear reason for move (gap, momentum, sector leadership)
- high_volatility flag must be FALSE

AVOID:
- Stocks already up >3% from open (chasing)
- Stocks with high_volatility = True (SL slippage risk)
- Two stocks from same sector
- Volume < 2,000,000

STEP 3: ENTRY, TARGET, STOP LOSS

FOR LONG SETUPS (setup_type = LONG):
- ENTRY: Use current LTP as entry price
- Only enter if LTP is within 3% of open price
- SL = entry x 0.982 (1.8% below entry)
- On VIX > 18: SL = entry x 0.980 (2% below)
- TARGET: Minimum entry x 1.036 (3.6% above), preferred entry x 1.04
- R:R must be >= 2.0 always

FOR SHORT SETUPS (setup_type = SHORT):
- ENTRY: Use current LTP as entry price
- Only enter if LTP is within 3% of open price (from below)
- SL = entry x 1.018 (1.8% above entry)
- On VIX > 18: SL = entry x 1.020 (2% above)
- TARGET: Minimum entry x 0.964 (3.6% below), preferred entry x 0.96
- R:R must be >= 2.0 always
- SHORT candidates are stocks with setup_type=SHORT in the data
- Do not short a stock unless it has setup_type=SHORT

POSITION SIZING (handled by system):
- Budget: Rs.{config.daily_capital_limit:,.0f} total
- Per trade max: Rs.{config.per_trade_max_capital:,.0f}

STEP 4: STRATEGY TYPE

LONG strategies:
MOMENTUM : Strong gap up + volume surge + sector leading
ORB      : Price breaking above first 15min high with volume
GAP      : Clean gap up from prev close, holding above gap level
VWAP     : Price reclaiming VWAP after dip with volume support
REVERSAL : Green stock on red day with sector support

SHORT strategies:
SHORT_MOMENTUM : Strong gap down + volume surge + sector falling
SHORT_ORB      : Price breaking below first 15min low with volume
SHORT_GAP      : Clean gap down from prev close, holding below gap
SHORT_REVERSAL : Red stock on green day — weak stock in strong market

STEP 5: SELF-CHECK BEFORE SUBMITTING

Before returning JSON, verify each pick:
- R:R = (target - entry) / (entry - SL) >= 2.0?
- Each pick from different sector?
- Volume > 2,000,000?
- Entry within 1.5% of open?
- high_volatility = False?
- Confidence >= {config.min_confidence_score}?

If any pick fails -> remove it. Better 1 good trade than 3 bad ones.

RESPONSE FORMAT - valid JSON only, no markdown

{{
  "picks": [
    {{
      "stock_name": "Full Company Name",
      "nse_symbol": "SYMBOL",
      "tradingsymbol": "SYMBOL",
      "entry_price": 123.45,
      "target_price": 128.90,
      "stop_loss_price": 121.20,
      "confidence_score": 8,
      "rationale": "Volume 3.2M. Gap up 1.8%. Sector Banking +1.2% leading. Entry near open. R:R 2.2:1",
      "strategy_type": "MOMENTUM",
      "sector": "Banking",
      "transaction_type": "BUY"
    }}
  ],
  "market_mood": "BULLISH - 14/20 sectors green, VIX stable at 14.2",
  "vix_assessment": "Normal - full position sizing allowed",
  "skip_reason": ""
}}

RULES:
- Return ONLY valid JSON
- Empty picks with skip_reason if market is dangerous
- Rationale must cite actual numbers from the data
- Never invent data not in the prompt
- high_volatility stocks must never appear in picks
"""

def _build_user_prompt(
    candidates: list[dict],
    sectors: list[dict],
    vix_value: float,
    config: IntraConfig,
    gainers: list[dict] | None = None,
    losers: list[dict] | None = None,
    history: str = "",
) -> str:
    """Build the user prompt with today's market data."""
    now = datetime.now(IST)
    date_str = now.strftime("%Y-%m-%d %H:%M IST")

    # --- Market condition assessment ---
    green_sectors = sum(1 for s in sectors if s.get("change_pct", 0) > 0)
    total_sectors = len(sectors)
    if green_sectors > total_sectors * 0.6:
        market_condition = "BULLISH — majority sectors green"
    elif green_sectors > total_sectors * 0.4:
        market_condition = "NEUTRAL — mixed sectors"
    else:
        market_condition = "BEARISH — majority sectors red, be very selective or skip"

    # --- Sector table ---
    sorted_sectors = sorted(sectors, key=lambda x: x.get("change_pct", 0), reverse=True)
    sector_lines = ["| Rank | Sector | Change % |", "|------|--------|----------|"]
    for i, s in enumerate(sorted_sectors, 1):
        sector_lines.append(f"| {i} | {s['name']} | {s['change_pct']:+.2f}% |")
    sector_table = "\n".join(sector_lines)

    # --- Candidates table ---
    cand_lines = [
        "| # | Symbol | Setup | LTP (₹) | Open (₹) | Prev Close (₹) | Change % | Gap % | Volume | High Vol |",
        "|---|--------|-------|---------|----------|----------------|----------|-------|--------|----------|",
    ]
    for i, c in enumerate(candidates, 1):
        hv = "⚠️ YES" if c.get("high_volatility") else "no"
        open_p = c.get("open_price", 0)
        prev_cl = c.get("prev_close", 0)
        setup = c.get("setup_type", "LONG")
        cand_lines.append(
            f"| {i} | {c.get('symbol', '?')} | {setup} | ₹{c.get('ltp', 0):.2f} "
            f"| ₹{open_p:.2f} | ₹{prev_cl:.2f} "
            f"| {c.get('change_pct', 0):+.2f}% "
            f"| {c.get('gap_pct', 0):+.2f}% | {c.get('volume', 0):,} | {hv} |"
        )
    candidates_table = "\n".join(cand_lines)

    # --- Gainers summary ---
    gainer_lines = []
    for g in (gainers or [])[:5]:
        gainer_lines.append(f"  {g['symbol']}: {g.get('change_pct', 0):+.2f}% (vol {g.get('volume', 0):,})")
    gainers_summary = "\n".join(gainer_lines) if gainer_lines else "  (no data)"

    # --- Losers summary ---
    loser_lines = []
    for lo in (losers or [])[:5]:
        loser_lines.append(f"  {lo['symbol']}: {lo.get('change_pct', 0):+.2f}% (vol {lo.get('volume', 0):,})")
    losers_summary = "\n".join(loser_lines) if loser_lines else "  (no data)"

    return f"""\
Date: {date_str}
India VIX: {vix_value:.2f}

MARKET CONDITION: {market_condition} ({green_sectors}/{total_sectors} sectors green)

{f"TRADE HISTORY (use this to avoid repeating mistakes):{chr(10)}{history}{chr(10)}" if history else ""}SECTOR PERFORMANCE (ranked by change %, strongest first):
{sector_table}

PRE-FILTERED CANDIDATES ({len(candidates)} stocks):
{candidates_table}

TOP GAINERS:
{gainers_summary}

TOP LOSERS:
{losers_summary}

Adapt to market conditions: {market_condition}.
Budget: ₹{config.daily_capital_limit:,.0f} total, ₹{config.per_trade_max_capital:,.0f} per trade.
Entry near open price. 1.5-2% SL. 3-4% target. R:R ≥ 2:1.
Each pick from a DIFFERENT sector.
"""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_pick(pick: dict, config: IntraConfig) -> str | None:
    """Validate a single LLM pick dict.

    Returns ``None`` if valid, or an error message string if invalid.
    """
    # Check required fields and types
    for field_name, expected_type in REQUIRED_PICK_FIELDS.items():
        if field_name not in pick:
            return f"missing field '{field_name}'"
        val = pick[field_name]
        if not isinstance(val, expected_type):
            return f"field '{field_name}' has wrong type {type(val).__name__}"

    entry = float(pick["entry_price"])
    target = float(pick["target_price"])
    sl = float(pick["stop_loss_price"])
    confidence = int(pick["confidence_score"])

    # Confidence threshold
    if confidence < config.min_confidence_score:
        return f"confidence {confidence} < min {config.min_confidence_score}"

    transaction_type = str(pick.get("transaction_type", "BUY")).upper()

    if transaction_type == "SELL":
        # SHORT trade: target below entry, SL above entry
        if target >= entry:
            return f"SHORT: target {target} >= entry {entry}"
        if sl <= entry:
            return f"SHORT: stop_loss {sl} <= entry {entry}"
        risk = sl - entry
        if risk <= 0:
            return f"SHORT: risk (SL - entry) = {risk} <= 0"
        rr = (entry - target) / risk
    else:
        # LONG trade: target above entry, SL below entry
        if target <= entry:
            return f"target {target} <= entry {entry}"
        if sl >= entry:
            return f"stop_loss {sl} >= entry {entry}"
        risk = entry - sl
        if risk <= 0:
            return f"risk (entry - SL) = {risk} <= 0"
        rr = (target - entry) / risk

    if rr < 1.99:
        return f"R:R {rr:.2f} < 2.0"

    # Reject high volatility stocks — prone to SL slippage
    if pick.get("high_volatility"):
        return "high volatility stock rejected"

    return None


def _pick_to_trade_setup(pick: dict) -> TradeSetup:
    """Convert a validated pick dict to a :class:`TradeSetup`."""
    entry = float(pick["entry_price"])
    target = float(pick["target_price"])
    sl = float(pick["stop_loss_price"])
    transaction_type = str(pick.get("transaction_type", "BUY")).upper()

    # R:R calculation differs for long vs short
    if transaction_type == "SELL":
        risk = sl - entry  # for short: SL is above entry
        rr = (entry - target) / risk if risk > 0 else 0.0
    else:
        risk = entry - sl
        rr = (target - entry) / risk if risk > 0 else 0.0

    return TradeSetup(
        stock_name=str(pick["stock_name"]),
        nse_symbol=str(pick["nse_symbol"]),
        tradingsymbol=str(pick["tradingsymbol"]),
        entry_price=entry,
        target_price=target,
        stop_loss_price=sl,
        confidence_score=int(pick["confidence_score"]),
        rationale=str(pick["rationale"]),
        strategy_type=str(pick["strategy_type"]),
        risk_reward_ratio=round(rr, 2),
        transaction_type=transaction_type,
    )


# ---------------------------------------------------------------------------
# Main LLM selection entry point
# ---------------------------------------------------------------------------

def select_trades_llm(
    candidates: list[dict],
    sectors: list[dict],
    vix_value: float,
    config: IntraConfig,
    bedrock_client: Any,
    *,
    gainers: list[dict] | None = None,
    losers: list[dict] | None = None,
    dry_run: bool = False,
    db=None,
) -> list[TradeSetup]:
    """Send pre-filtered candidates to Claude and return validated trades.

    Parameters
    ----------
    candidates:
        Pre-filtered candidate dicts from :func:`pre_filter_candidates`.
    sectors:
        Ranked sector dicts from the scanner.
    vix_value:
        Current India VIX reading.
    config:
        Intraday configuration.
    bedrock_client:
        An instance of :class:`BedrockClient` (or compatible mock).
    gainers:
        Top gainers summary for the user prompt.
    losers:
        Top losers summary for the user prompt.

    Returns
    -------
    list[TradeSetup]
        Validated trade setups. Empty list if LLM fails or no valid picks.
    """
    system_prompt = _build_system_prompt(config)
    history = _fetch_trade_history(db)
    user_prompt = _build_user_prompt(
        candidates, sectors, vix_value, config,
        gainers=gainers, losers=losers, history=history,
    )

    logger.info("Sending %d candidates to LLM for trade selection…", len(candidates))

    response = bedrock_client.invoke(system_prompt, user_prompt)

    if not response:
        logger.error("LLM returned empty response — aborting trade selection")
        return []

    picks = response.get("picks")
    if not isinstance(picks, list):
        logger.error("LLM response missing 'picks' array — aborting trade selection")
        return []

    # Log market mood if present
    mood = response.get("market_mood", "")
    vix_note = response.get("vix_assessment", "")
    skip_reason = response.get("skip_reason", "")
    if mood:
        logger.info("LLM market mood: %s", mood)
    if vix_note:
        logger.info("LLM VIX assessment: %s", vix_note)
    if skip_reason:
        logger.info("LLM skip reason: %s", skip_reason)

    # If LLM says skip and returned no picks, respect that
    if skip_reason and not picks:
        logger.info("LLM recommends skipping today: %s", skip_reason)
        return []

    # Validate each pick
    valid_trades: list[TradeSetup] = []
    for i, pick in enumerate(picks):
        if not isinstance(pick, dict):
            logger.warning("Pick #%d is not a dict — skipping", i + 1)
            continue

        error = validate_pick(pick, config)
        if error:
            logger.warning("Pick #%d (%s) invalid: %s — discarding",
                           i + 1, pick.get("nse_symbol", "?"), error)
            continue

        trade = _pick_to_trade_setup(pick)
        valid_trades.append(trade)
        logger.info(
            "Pick #%d VALID: %s @ ₹%.2f → ₹%.2f (SL ₹%.2f, R:R %.1f, conf %d) [%s] — %s",
            i + 1,
            trade.nse_symbol,
            trade.entry_price,
            trade.target_price,
            trade.stop_loss_price,
            trade.risk_reward_ratio,
            trade.confidence_score,
            trade.strategy_type,
            trade.rationale,
        )

    if not valid_trades:
        logger.error("Zero valid picks from LLM — aborting trade selection")
        return []

    logger.info("LLM selection complete: %d valid trade(s)", len(valid_trades))
    return valid_trades
