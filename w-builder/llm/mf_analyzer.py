"""AI-driven mutual fund analysis using AWS Bedrock Claude.

Analyzes mutual fund holdings against current NAV data to generate
continue/stop/switch SIP recommendations with alternative scheme suggestions.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import MFRecommendation

if TYPE_CHECKING:
    from fetchers.models import NAVRecord
    from llm.bedrock_client import BedrockClient
    from parsers.models import MFHolding

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior Indian mutual fund advisor with expertise in SEBI-regulated schemes and AMFI data.
Analyze the provided mutual fund portfolio and generate SIP recommendations.

For each scheme, provide:
- scheme_name: the exact scheme name as provided
- recommendation: exactly one of "continue", "stop", or "switch"
- alternative_scheme: if recommendation is "switch", suggest a specific alternative scheme in the same category. Set to null for "continue" or "stop".
- rationale: a concise 1-2 sentence explanation based on the data provided

Rules:
- Use ONLY the data provided. Do NOT fabricate any NAV values, returns, or scheme names.
- "continue" — scheme is performing well relative to category, keep SIP running
- "stop" — scheme is consistently underperforming, stop SIP
- "switch" — scheme is underperforming and a better alternative exists in the same category
- When recommending "switch", the alternative_scheme MUST be a real, specific scheme name
- For "continue" and "stop", alternative_scheme must be null

Respond with ONLY a JSON array of objects. No markdown, no explanation outside the JSON."""


def analyze_mutual_funds(
    holdings: list[MFHolding],
    nav_data: dict[str, NAVRecord],
    client: BedrockClient,
) -> list[MFRecommendation]:
    """Generate SIP recommendations for each mutual fund scheme.

    Batches holdings into groups of 20 to stay within Bedrock's context limit.
    """
    if not holdings:
        return []

    BATCH_SIZE = 20
    all_recs: list[MFRecommendation] = []

    for i in range(0, len(holdings), BATCH_SIZE):
        batch = holdings[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(holdings) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Analyzing MF batch %d/%d (%d schemes)", batch_num, total_batches, len(batch))

        user_prompt = _build_user_prompt(batch, nav_data)

        try:
            response = client.invoke(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error("MF analysis batch %d failed: %s", batch_num, e)
            continue

        if not response:
            logger.error("Empty response from Bedrock for MF batch %d", batch_num)
            continue

        batch_recs = _parse_recommendations(response)
        all_recs.extend(batch_recs)
        logger.info("MF batch %d: %d recommendations parsed", batch_num, len(batch_recs))

    logger.info("Total MF recommendations: %d out of %d schemes", len(all_recs), len(holdings))
    return all_recs


def _build_user_prompt(
    holdings: list[MFHolding],
    nav_data: dict[str, NAVRecord],
) -> str:
    """Build user prompt with MF holdings and NAV data."""
    mf_items = []
    for h in holdings:
        item: dict = {
            "scheme_name": h.scheme_name,
            "amc": h.amc,
            "category": h.category,
            "sub_category": h.sub_category,
            "units": h.units,
            "invested_value": h.invested_value,
            "current_value": h.current_value,
            "returns_absolute": h.returns_absolute,
            "xirr": h.xirr,
            "returns_percent": h.returns_percent,
        }

        # Add current NAV if available
        if h.scheme_code and h.scheme_code in nav_data:
            nav_record = nav_data[h.scheme_code]
            item["current_nav"] = nav_record.nav
            item["nav_date"] = nav_record.date

        mf_items.append(item)

    return (
        "Analyze the following mutual fund portfolio and provide SIP recommendations.\n\n"
        f"Mutual Fund Holdings:\n{json.dumps(mf_items, indent=2)}"
    )


def _parse_recommendations(response: dict) -> list[MFRecommendation]:
    """Parse Bedrock response into MFRecommendation objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    valid_recommendations = {"continue", "stop", "switch"}
    recommendations: list[MFRecommendation] = []

    for item in items:
        try:
            scheme_name = str(item.get("scheme_name", ""))
            recommendation = str(item.get("recommendation", "")).lower()
            rationale = str(item.get("rationale", ""))
            alternative_scheme = item.get("alternative_scheme")

            if not scheme_name or recommendation not in valid_recommendations:
                logger.warning("Skipping invalid MF recommendation: %s", item)
                continue

            # Enforce: alternative_scheme only for "switch"
            if recommendation == "switch":
                if not alternative_scheme:
                    logger.warning(
                        "Switch recommendation for %s missing alternative_scheme, skipping",
                        scheme_name,
                    )
                    continue
                alternative_scheme = str(alternative_scheme)
            else:
                alternative_scheme = None

            recommendations.append(MFRecommendation(
                scheme_name=scheme_name,
                recommendation=recommendation,
                alternative_scheme=alternative_scheme,
                rationale=rationale,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed MF recommendation: %s", e)
            continue

    return recommendations
