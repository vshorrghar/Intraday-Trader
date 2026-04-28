"""AI-driven intraday trading setup generator using AWS Bedrock Claude.

Generates exactly 5 intraday trading setups with entry, target, stop loss,
and rationale based on live market data.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import IntradaySetup

if TYPE_CHECKING:
    from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert Indian equity intraday trader with deep knowledge of NSE market microstructure.
Generate exactly 5 intraday trading setups based on the provided market data.

For each setup, provide:
- stock_name: the company/stock name
- entry_price: the recommended entry price (positive number)
- target_price: the exit target price (must be greater than entry_price)
- stop_loss: the protective stop loss price (must be less than entry_price)
- rationale: a concise 1-2 sentence explanation based on the data provided

Rules:
- Generate EXACTLY 5 setups. No more, no less.
- Use ONLY the data provided. Do NOT fabricate any prices, volumes, or technical patterns.
- entry_price, target_price, and stop_loss must all be positive numbers.
- target_price > entry_price (for long setups)
- stop_loss < entry_price
- Each rationale must reference actual data points from the input.

Respond with ONLY a JSON array of exactly 5 objects. No markdown, no explanation outside the JSON."""


def generate_intraday_setups(
    market_data: dict,
    client: BedrockClient,
) -> list[IntradaySetup]:
    """Generate exactly 5 intraday trading setups.

    Args:
        market_data: Dictionary containing live market data (bhavcopy, indices,
            deals, etc.) to inform setup generation.
        client: Initialized BedrockClient instance.

    Returns:
        List of IntradaySetup objects (ideally 5), or empty list on failure.
    """
    user_prompt = _build_user_prompt(market_data)

    try:
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error("Intraday setup generation failed: %s", e)
        return []

    if not response:
        logger.error("Empty response from Bedrock for intraday setups")
        return []

    return _parse_setups(response)


def _build_user_prompt(market_data: dict) -> str:
    """Build user prompt with available market data."""
    return (
        "Generate 5 intraday trading setups based on the following market data.\n\n"
        f"Market Data:\n{json.dumps(market_data, indent=2, default=str)}"
    )


def _parse_setups(response: dict) -> list[IntradaySetup]:
    """Parse Bedrock response into IntradaySetup objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    setups: list[IntradaySetup] = []

    for item in items:
        try:
            stock_name = str(item.get("stock_name", ""))
            entry_price = float(item.get("entry_price", 0))
            target_price = float(item.get("target_price", 0))
            stop_loss = float(item.get("stop_loss", 0))
            rationale = str(item.get("rationale", ""))

            if entry_price <= 0 or target_price <= 0 or stop_loss <= 0:
                logger.warning("Skipping setup for %s: non-positive prices", stock_name)
                continue

            if not stock_name or not rationale:
                logger.warning("Skipping setup: missing stock_name or rationale")
                continue

            setups.append(IntradaySetup(
                stock_name=stock_name,
                entry_price=entry_price,
                target_price=target_price,
                stop_loss=stop_loss,
                rationale=rationale,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed intraday setup: %s", e)
            continue

    return setups
