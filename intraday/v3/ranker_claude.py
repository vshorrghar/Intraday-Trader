"""V3 Claude Ranker — ranks top 20 candidates to top 3.

Uses Claude via Bedrock as a RANKER (not screener).
Receives pre-filtered candidates with scores, returns ranked top 3.
Max 1 call per day (enforced by orchestrator).
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RANKER_SYSTEM_PROMPT = """You are an expert NSE intraday trade ranker.

You will receive 20 pre-screened stock candidates with their scores, sectors, 
entry/SL/target prices, and R:R ratios. All have already passed quantitative filters.

Your job: Rank the TOP 3 best trades by combining:
1. Risk/Reward quality (higher R:R = better)
2. Sector diversification (avoid 2 from same sector in top 3)
3. Score strength (higher score = stronger signal)
4. Capital efficiency (prefer stocks where position size is meaningful)

Current market regime: {regime}

RULES:
- Return EXACTLY 3 picks (or fewer if less than 3 candidates are acceptable)
- LONG only — no SHORT trades
- If no candidate is worth trading, return empty picks array with skip_reason
- Return valid JSON only

OUTPUT FORMAT (strict JSON):
{{
  "picks": [
    {{"symbol": "SYMBOL1", "rank": 1, "reasoning": "..."}},
    {{"symbol": "SYMBOL2", "rank": 2, "reasoning": "..."}},
    {{"symbol": "SYMBOL3", "rank": 3, "reasoning": "..."}}
  ],
  "skip_reason": null
}}
"""

RANKER_USER_PROMPT = """REGIME: {regime}

TOP 20 CANDIDATES (pre-filtered, sorted by score):

{candidates_table}

Rank the top 3 best trades. Return JSON only."""


def _format_candidates_table(candidates: list) -> str:
    """Format candidates into a readable table for Claude."""
    lines = ["#  | Symbol      | Score | Sector              | Entry   | SL      | Target  | R:R  | Mcap"]
    lines.append("-" * 95)
    for i, c in enumerate(candidates[:20], 1):
        lines.append(
            f"{i:2d} | {c.get('symbol','?'):<11s} | {c.get('score',0):5.1f} | "
            f"{c.get('sector','?'):<19s} | {c.get('entry_price',0):7.1f} | "
            f"{c.get('stop_loss',0):7.1f} | {c.get('target',0):7.1f} | "
            f"{c.get('rr',0):4.1f} | {c.get('mcap_bucket','?')}"
        )
    return "\n".join(lines)


def rank_top_3(
    candidates: list[dict],
    regime: str,
    bedrock_client,
) -> list[dict]:
    """Send top 20 candidates to Claude for ranking.

    Args:
        candidates: Pre-filtered list of signal dicts (max 20).
                    Each must have: symbol, score, sector, mcap_bucket,
                    entry_price, stop_loss, target
        regime: Current market regime string
        bedrock_client: Instance of llm.bedrock_client.BedrockClient

    Returns:
        List of up to 3 ranked picks with reasoning.
        Empty list if Claude recommends skipping.
    """
    if not candidates:
        logger.info("Claude ranker: no candidates to rank")
        return []

    # Compute R:R for each candidate
    for c in candidates:
        entry = c.get("entry_price", 0)
        sl = c.get("stop_loss", 0)
        target = c.get("target", 0)
        risk = entry - sl if entry > sl else 1
        reward = target - entry if target > entry else 0
        c["rr"] = round(reward / risk, 1) if risk > 0 else 0

    # Build prompts
    system_prompt = RANKER_SYSTEM_PROMPT.format(regime=regime)
    user_prompt = RANKER_USER_PROMPT.format(
        regime=regime,
        candidates_table=_format_candidates_table(candidates[:20]),
    )

    logger.info("Claude ranker: sending %d candidates (regime=%s)", len(candidates[:20]), regime)

    try:
        response = bedrock_client.invoke(system_prompt, user_prompt)
        if not response:
            logger.warning("Claude ranker: empty response")
            return []

        # Parse response
        content = response.get("content", "")
        if isinstance(content, list):
            content = content[0].get("text", "") if content else ""

        # Extract JSON from response
        parsed = _parse_claude_response(content)
        if not parsed:
            logger.warning("Claude ranker: failed to parse response")
            return []

        picks = parsed.get("picks", [])
        skip_reason = parsed.get("skip_reason")

        if skip_reason:
            logger.info("Claude ranker: skip recommended — %s", skip_reason)
            return []

        # Map picks back to full candidate data
        result = []
        symbol_map = {c["symbol"]: c for c in candidates}
        for pick in picks[:3]:
            sym = pick.get("symbol", "")
            if sym in symbol_map:
                enriched = {**symbol_map[sym], "claude_rank": pick.get("rank"), "claude_reasoning": pick.get("reasoning", "")}
                result.append(enriched)

        logger.info("Claude ranker: returned %d picks", len(result))
        return result

    except Exception as exc:
        logger.error("Claude ranker failed: %s", exc)
        return []


def _parse_claude_response(content: str) -> Optional[dict]:
    """Extract JSON from Claude's response text."""
    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block
    import re
    json_match = re.search(r'\{[\s\S]*"picks"[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None
