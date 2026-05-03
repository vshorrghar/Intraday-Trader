"""Positional trade selector — LLM picks multi-week/month positions.

Evaluates candidates on:
- Fundamental strength (PE, sector, market cap)
- Technical momentum (near 52w high, volume)
- Sector rotation (FII/DII flows)
- Risk:Reward (minimum 2.5:1 for positional)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from positional.models import PositionalConfig, PositionalSetup

logger = logging.getLogger(__name__)

POSITIONAL_PROMPT = """You are an expert Indian stock market positional trader. Select up to {max_positions} stocks for positional trades (hold 4-12 weeks).

MARKET CONTEXT:
- Sectors: {sectors}
- FII Net: ₹{fii_net:.0f} Cr | DII Net: ₹{dii_net:.0f} Cr

CANDIDATES:
{candidates}

SELECTION CRITERIA (POSITIONAL — longer term):
1. Strong fundamentals: reasonable PE, good sector, institutional interest
2. Technical momentum: within 10% of 52-week high, or bouncing from support
3. Sector tailwind: FII buying + sector outperforming
4. Market cap preference: LARGE and MID cap for safety
5. Target: 15-25% upside over 4-12 weeks
6. Stop loss: 6-10% below entry
7. Risk:Reward minimum 2.5:1

For each pick:
- entry_price: current LTP or slight pullback level
- target_price: 15-25% above entry
- stop_loss_price: 6-10% below entry
- expected_hold_weeks: 4-12
- strategy_type: GROWTH / VALUE / MOMENTUM / SECTOR_ROTATION / EARNINGS
- confidence_score: 1-10
- rationale: fundamental + technical thesis

Respond in JSON:
{{
  "market_outlook": "brief multi-week outlook",
  "skip_reason": null or "reason",
  "picks": [
    {{
      "nse_symbol": "SYMBOL",
      "stock_name": "Name",
      "entry_price": 1000.0,
      "target_price": 1200.0,
      "stop_loss_price": 920.0,
      "confidence_score": 8,
      "strategy_type": "MOMENTUM",
      "rationale": "...",
      "expected_hold_weeks": 8,
      "sector": "IT",
      "market_cap": "LARGE"
    }}
  ]
}}"""


def select_positional_trades(
    candidates: list[dict],
    sectors: list[dict],
    fii_dii: dict,
    config: PositionalConfig,
    bedrock_client: Any,
) -> list[PositionalSetup]:
    """Use LLM to select positional trade setups."""

    if not candidates:
        logger.warning("No candidates for positional selection")
        return []

    sectors_str = ", ".join(f"{s['name']} ({s['change_pct']:+.2f}%)" for s in sectors[:8])
    candidates_str = json.dumps(candidates[:20], indent=2, default=str)

    prompt = POSITIONAL_PROMPT.format(
        max_positions=config.max_positions,
        sectors=sectors_str,
        fii_net=fii_dii.get("fii_net", 0) / 10_000_000,
        dii_net=fii_dii.get("dii_net", 0) / 10_000_000,
        candidates=candidates_str,
    )

    logger.info("Sending %d candidates to LLM for positional selection…", len(candidates))

    try:
        response = bedrock_client.invoke(
            "You are an expert Indian stock market positional trader. Respond only in valid JSON.",
            prompt,
        )
        result = response if isinstance(response, dict) else json.loads(response)
    except Exception as exc:
        logger.error("LLM positional selection failed: %s", exc)
        return []

    if result.get("skip_reason"):
        logger.info("LLM skipping positional: %s", result["skip_reason"])
        return []

    logger.info("LLM outlook: %s", result.get("market_outlook", ""))

    setups: list[PositionalSetup] = []
    for pick in result.get("picks", []):
        try:
            entry = float(pick["entry_price"])
            target = float(pick["target_price"])
            sl = float(pick["stop_loss_price"])
            conf = int(pick["confidence_score"])

            if entry <= 0 or target <= entry or sl >= entry:
                continue
            if conf < config.min_confidence_score:
                continue

            risk = entry - sl
            reward = target - entry
            rr = reward / risk if risk > 0 else 0
            if rr < 2.0:
                continue

            setups.append(PositionalSetup(
                nse_symbol=str(pick["nse_symbol"]),
                stock_name=str(pick.get("stock_name", pick["nse_symbol"])),
                entry_price=entry,
                target_price=target,
                stop_loss_price=sl,
                confidence_score=conf,
                strategy_type=str(pick.get("strategy_type", "MOMENTUM")),
                rationale=str(pick.get("rationale", "")),
                expected_hold_weeks=int(pick.get("expected_hold_weeks", 8)),
                risk_reward_ratio=round(rr, 2),
                sector=str(pick.get("sector", "")),
                market_cap=str(pick.get("market_cap", "")),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    logger.info("Positional selection: %d valid setups", len(setups))
    return setups
