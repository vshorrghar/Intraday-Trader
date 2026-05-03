"""Swing trade selector — uses LLM to pick multi-day setups.

Sends enriched candidates to Claude for analysis. LLM evaluates:
- Technical setup quality (breakout, pullback, reversal)
- Sector strength alignment
- Risk:Reward ratio (minimum 2:1)
- Volume confirmation
- Proximity to 52-week high/low
"""

from __future__ import annotations

import json
import logging
from typing import Any

from swing.models import SwingConfig, SwingSetup

logger = logging.getLogger(__name__)

SWING_PROMPT = """You are an expert Indian stock market swing trader. Analyze these candidates and select up to {max_positions} stocks for swing trades (hold 2-15 days).

MARKET CONTEXT:
- Sectors (strongest first): {sectors}

CANDIDATES (with OHLCV data):
{candidates}

SELECTION CRITERIA:
1. Strong sector tailwind (stock's sector is in top 5 performing)
2. Clear technical setup: breakout above resistance, pullback to support, or reversal pattern
3. Volume confirmation (above average)
4. Near 52-week high = momentum play, near 52-week low = reversal play
5. Risk:Reward minimum 2:1 (target 8%, stop loss 4%)
6. Price between ₹{price_min} and ₹{price_max}

For each pick, provide:
- entry_price: realistic entry (near current LTP or on pullback)
- target_price: 5-10% above entry (based on resistance levels)
- stop_loss_price: 3-5% below entry (based on support levels)
- expected_hold_days: 2-15 days
- strategy_type: BREAKOUT / PULLBACK / REVERSAL / MOMENTUM
- confidence_score: 1-10
- rationale: why this stock, what's the setup

If market conditions are unfavorable for swing trades, return empty picks with skip_reason.

Respond in JSON:
{{
  "market_mood": "brief assessment",
  "skip_reason": null or "reason to skip all",
  "picks": [
    {{
      "nse_symbol": "SYMBOL",
      "stock_name": "Name",
      "entry_price": 100.0,
      "target_price": 108.0,
      "stop_loss_price": 96.0,
      "confidence_score": 8,
      "strategy_type": "BREAKOUT",
      "rationale": "...",
      "expected_hold_days": 5,
      "sector": "IT"
    }}
  ]
}}"""


def select_swing_trades(
    candidates: list[dict],
    sectors: list[dict],
    config: SwingConfig,
    bedrock_client: Any,
) -> list[SwingSetup]:
    """Use LLM to select swing trade setups from candidates."""

    if not candidates:
        logger.warning("No candidates for swing selection")
        return []

    # Format sectors
    sectors_str = ", ".join(
        f"{s['name']} ({s['change_pct']:+.2f}%)" for s in sectors[:10]
    )

    # Format candidates
    candidates_str = json.dumps(candidates[:25], indent=2, default=str)

    prompt = SWING_PROMPT.format(
        max_positions=config.max_open_positions,
        sectors=sectors_str,
        candidates=candidates_str,
        price_min=config.price_range_min,
        price_max=config.price_range_max,
    )

    logger.info("Sending %d candidates to LLM for swing selection…", len(candidates))

    try:
        response = bedrock_client.invoke(
            "You are an expert Indian stock market swing trader. Respond only in valid JSON.",
            prompt,
        )
        result = response if isinstance(response, dict) else json.loads(response)
    except Exception as exc:
        logger.error("LLM swing selection failed: %s", exc)
        return []

    # Check skip
    if result.get("skip_reason"):
        logger.info("LLM recommends skipping swing trades: %s", result["skip_reason"])
        return []

    logger.info("LLM market mood: %s", result.get("market_mood", ""))

    # Validate picks
    setups: list[SwingSetup] = []
    for pick in result.get("picks", []):
        try:
            entry = float(pick["entry_price"])
            target = float(pick["target_price"])
            sl = float(pick["stop_loss_price"])
            conf = int(pick["confidence_score"])

            # Validation
            if entry <= 0 or target <= entry or sl >= entry:
                continue
            if conf < config.min_confidence_score:
                continue

            risk = entry - sl
            reward = target - entry
            rr = reward / risk if risk > 0 else 0
            if rr < 1.5:
                continue

            setups.append(SwingSetup(
                nse_symbol=str(pick["nse_symbol"]),
                stock_name=str(pick.get("stock_name", pick["nse_symbol"])),
                entry_price=entry,
                target_price=target,
                stop_loss_price=sl,
                confidence_score=conf,
                strategy_type=str(pick.get("strategy_type", "MOMENTUM")),
                rationale=str(pick.get("rationale", "")),
                expected_hold_days=int(pick.get("expected_hold_days", 5)),
                risk_reward_ratio=round(rr, 2),
                sector=str(pick.get("sector", "")),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    logger.info("Swing selection: %d valid setups", len(setups))
    return setups
