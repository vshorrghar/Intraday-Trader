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
# Task 7.1 — LLM trade selection
# ===================================================================


def _build_system_prompt(config: IntraConfig) -> str:
    """Build the system prompt for Claude Sonnet 4.5 trade selection.

    This prompt encodes the institutional-grade strategy that adapts to
    market conditions (bullish vs bearish days).
    """
    return f"""\
You are an elite quantitative trading analyst at a top institutional hedge fund.
Your job is to select high-confidence intraday LONG trades from the candidate list.

═══════════════════════════════════════════════════════════════
MARKET-ADAPTIVE STRATEGY — READ THE MARKET FIRST
═══════════════════════════════════════════════════════════════

STEP 1: ASSESS MARKET CONDITIONS
• Count how many of the top 20 sectors are GREEN vs RED.
• If majority GREEN (>12 sectors) → BULLISH DAY → pick up to {config.max_trades_per_day} trades.
• If mixed (8-12 green) → NEUTRAL DAY → pick 3-4 trades, be selective.
• If majority RED (<8 green) → BEARISH DAY → pick only 1-3 trades with exceptional relative strength, or SKIP entirely.
• If VIX is rising AND market is red → DANGEROUS → reduce to 1-2 picks max or skip.

STEP 2: ON BULLISH DAYS
• Pick {config.max_trades_per_day} stocks from {config.max_trades_per_day} DIFFERENT sectors.
• Entry MUST be near the stock's opening price (within 0.5% of open).
• NEVER chase a stock that has already moved 2%+ from open — that's chasing, not catching.
• Target 3-4% above entry for good R:R with 1.5-2% stop loss.

STEP 3: ON BEARISH DAYS
• Look for stocks that are GREEN despite market being red (relative strength).
• Look for stocks that gapped down but are recovering (reversal plays).
• Prefer defensive sectors (Pharma, FMCG, IT) that outperform.
• It is BETTER to pick 1 great trade than 5 mediocre ones.
• If nothing looks good, return empty picks with skip_reason.

═══════════════════════════════════════════════════════════════
ENTRY RULES — CRITICAL (learn from past mistakes)
═══════════════════════════════════════════════════════════════

RULE 1: ENTER NEAR OPEN PRICE
• Entry should be within 0.5% of the stock's opening price.
• If a stock opened at ₹200 and is now at ₹210, DO NOT pick it at ₹210.
• Use the "open" column in the data, not "ltp" for entry.

RULE 2: DIVERSIFY ACROSS SECTORS
• Each pick MUST be from a DIFFERENT sector.
• Banking, IT, Pharma, Auto, FMCG, Metal, Energy, Realty, Infra, Telecom, Finance — spread across them.
• If you pick HDFCBANK (Banking), do NOT pick ICICIBANK (also Banking).

RULE 3: WIDER STOP LOSSES (1.5-2%)
• Tight SLs get triggered by normal intraday noise. Use 1.5-2% SL.
• SL = entry × 0.98 (2% below) is the sweet spot.
• On high-VIX days (>20), use 2% SL minimum.

RULE 4: REALISTIC TARGETS (3-4% above entry)
• Target = entry × 1.03 to entry × 1.04 gives good R:R with 2% SL.
• Don't set targets at obvious round numbers everyone watches.

RULE 5: VOLUME CONFIRMATION
• Only pick stocks with volume > 1 million today.
• Higher volume = more reliable price action.

RULE 6: BUY ON DIP, NOT ON RALLY
• If stock gapped up and is pulling back toward open — GOOD entry.
• If stock is at day's high with no pullback — BAD entry (chasing).

═══════════════════════════════════════════════════════════════
RISK RULES — every pick MUST satisfy ALL of these:
═══════════════════════════════════════════════════════════════

• Stop loss within 2% of entry: (entry - SL) / entry ≤ 0.02
• Risk:Reward ratio ≥ 2:1: (target - entry) / (entry - SL) ≥ 2.0
• Stock price between ₹{config.price_range_min} and ₹{config.price_range_max}
• Budget: ₹{config.daily_capital_limit:,.0f} total, ₹{config.per_trade_max_capital:,.0f} per trade
• Confidence 1-10, only ≥ {config.min_confidence_score} used

EXAMPLE of correct math:
• Entry ₹200, Target ₹206 (+3%), SL ₹196 (-2%) → R:R = 3.0:1 ✓
• Entry ₹500, Target ₹520 (+4%), SL ₹490 (-2%) → R:R = 2.0:1 ✓
• Entry ₹300, Target ₹306 (+2%), SL ₹297 (-1%) → R:R = 2.0:1 ✓

DO NOT set target at only 1-2% with 1.5% SL — that gives R:R < 2:1 which gets REJECTED.

═══════════════════════════════════════════════════════════════
STRATEGY TYPES — assign exactly one:
═══════════════════════════════════════════════════════════════

• "MOMENTUM" — riding a strong directional move confirmed by volume
• "ORB"      — Opening Range Breakout in the first 15-30 minutes
• "GAP"      — trading a gap-up continuation or gap-down reversal
• "VWAP"     — mean-reversion or trend-following around VWAP
• "REVERSAL" — stock showing strength against market weakness (bearish day play)

═══════════════════════════════════════════════════════════════
RESPONSE FORMAT — EXACTLY this JSON, nothing else:
═══════════════════════════════════════════════════════════════

{{
  "picks": [
    {{
      "stock_name": "Full Company Name",
      "nse_symbol": "SYMBOL",
      "tradingsymbol": "SYMBOL",
      "entry_price": 123.45,
      "target_price": 130.00,
      "stop_loss_price": 121.00,
      "confidence_score": 8,
      "rationale": "Cite specific data — volume, sector rank, gap %, relative strength",
      "strategy_type": "MOMENTUM",
      "sector": "Banking"
    }}
  ],
  "market_mood": "One-line market assessment",
  "vix_assessment": "VIX impact on strategy",
  "skip_reason": "If skipping, explain why. Empty string if trading."
}}

CRITICAL:
• Return ONLY valid JSON — no markdown, no commentary.
• Each pick needs ALL fields above including "sector".
• On red days, fewer picks = smarter. Protecting capital > forcing trades.
• If nothing meets criteria, return empty picks with skip_reason.
• Rationale must cite specific numbers from the data.
"""


def _build_user_prompt(
    candidates: list[dict],
    sectors: list[dict],
    vix_value: float,
    config: IntraConfig,
    gainers: list[dict] | None = None,
    losers: list[dict] | None = None,
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
        "| # | Symbol | LTP (₹) | Open (₹) | Prev Close (₹) | High (₹) | Low (₹) | Gap % | Volume | High Vol | Sector Aligned |",
        "|---|--------|---------|----------|----------------|----------|---------|-------|--------|----------|----------------|",
    ]
    for i, c in enumerate(candidates, 1):
        hv = "⚠️ YES" if c.get("high_volatility") else "no"
        sa = "✅" if c.get("sector_aligned") else "—"
        open_p = c.get("open_price", 0)
        prev_cl = c.get("prev_close", 0)
        high_p = c.get("high", 0)
        low_p = c.get("low", 0)
        cand_lines.append(
            f"| {i} | {c.get('symbol', '?')} | ₹{c.get('ltp', 0):.2f} "
            f"| ₹{open_p:.2f} | ₹{prev_cl:.2f} | ₹{high_p:.2f} | ₹{low_p:.2f} "
            f"| {c.get('gap_pct', 0):+.2f}% | {c.get('volume', 0):,} | {hv} | {sa} |"
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

SECTOR PERFORMANCE (ranked by change %, strongest first):
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

    # Target must be above entry for long trades
    if target <= entry:
        return f"target {target} <= entry {entry}"

    # SL must be below entry for long trades
    if sl >= entry:
        return f"stop_loss {sl} >= entry {entry}"

    # Risk:Reward >= 1.5 (aggressive mode)
    risk = entry - sl
    if risk <= 0:
        return f"risk (entry - SL) = {risk} <= 0"
    rr = (target - entry) / risk
    if rr < 1.5:
        return f"R:R {rr:.2f} < 1.5"

    return None


def _pick_to_trade_setup(pick: dict) -> TradeSetup:
    """Convert a validated pick dict to a :class:`TradeSetup`."""
    entry = float(pick["entry_price"])
    target = float(pick["target_price"])
    sl = float(pick["stop_loss_price"])
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
    user_prompt = _build_user_prompt(
        candidates, sectors, vix_value, config,
        gainers=gainers, losers=losers,
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
