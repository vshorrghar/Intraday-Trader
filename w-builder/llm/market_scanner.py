"""AI-driven market opportunity scanner using AWS Bedrock Claude.

Scans bulk/block deal data, FII/DII flows, and stock fundamentals to identify
promoter buying signals, multibagger candidates, and FII accumulation plays.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import MarketOpportunity

if TYPE_CHECKING:
    from fetchers.models import DealRecord, FIIDIIFlow, StockFundamentals
    from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior Indian equity market analyst specializing in institutional flow analysis and deal pattern recognition.
Analyze the provided bulk/block deal data, FII/DII flows, and stock fundamentals to identify market opportunities.

Identify three types of signals:
1. "promoter_buying" — Stocks where promoters or insiders are accumulating via bulk/block deals
2. "multibagger" — Stocks with strong fundamentals (low PE, high ROCE, growing promoter holding) and institutional interest
3. "fii_accumulation" — Stocks where FII activity suggests accumulation based on deal data and flow patterns

For each opportunity, provide:
- stock_name: the company name
- signal_type: exactly one of "promoter_buying", "multibagger", "fii_accumulation"
- rationale: a concise 1-2 sentence explanation based on the data provided

Rules:
- Use ONLY the data provided. Do NOT fabricate any signals, prices, or metrics.
- Only flag genuine signals supported by the data.
- If no opportunities are found, return an empty array.

Respond with ONLY a JSON array of objects. No markdown, no explanation outside the JSON."""


def scan_opportunities(
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
    client: BedrockClient,
) -> list[MarketOpportunity]:
    """Identify market opportunities from deal data and institutional flows.

    Args:
        deals: Latest bulk and block deal records from NSE.
        fii_dii: Latest FII/DII flow data.
        fundamentals: Stock fundamentals keyed by symbol.
        client: Initialized BedrockClient instance.

    Returns:
        List of MarketOpportunity objects, or empty list on failure.
    """
    user_prompt = _build_user_prompt(deals, fii_dii, fundamentals)

    try:
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error("Market scan failed: %s", e)
        return []

    if not response:
        logger.error("Empty response from Bedrock for market scan")
        return []

    return _parse_opportunities(response)


def _build_user_prompt(
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
) -> str:
    """Build user prompt with deal data, FII/DII flows, and fundamentals."""
    deal_items = []
    for d in deals:
        deal_items.append({
            "deal_type": d.deal_type,
            "security_name": d.security_name,
            "isin": d.isin,
            "client_name": d.client_name,
            "quantity": d.quantity,
            "price": d.price,
        })

    fii_dii_data = {
        "date": fii_dii.date,
        "fii_buy": fii_dii.fii_buy,
        "fii_sell": fii_dii.fii_sell,
        "fii_net": fii_dii.fii_net,
        "dii_buy": fii_dii.dii_buy,
        "dii_sell": fii_dii.dii_sell,
        "dii_net": fii_dii.dii_net,
    }

    fund_items = {}
    for symbol, f in fundamentals.items():
        fund_items[symbol] = {
            "pe_ratio": f.pe_ratio,
            "market_cap": f.market_cap,
            "book_value": f.book_value,
            "dividend_yield": f.dividend_yield,
            "roce": f.roce,
            "promoter_holding": f.promoter_holding,
        }

    return (
        "Analyze the following market data and identify opportunities.\n\n"
        f"Bulk/Block Deals:\n{json.dumps(deal_items, indent=2)}\n\n"
        f"FII/DII Flows:\n{json.dumps(fii_dii_data, indent=2)}\n\n"
        f"Stock Fundamentals:\n{json.dumps(fund_items, indent=2)}"
    )


def _parse_opportunities(response: dict) -> list[MarketOpportunity]:
    """Parse Bedrock response into MarketOpportunity objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    valid_signals = {"promoter_buying", "multibagger", "fii_accumulation"}
    opportunities: list[MarketOpportunity] = []

    for item in items:
        try:
            stock_name = str(item.get("stock_name", ""))
            signal_type = str(item.get("signal_type", "")).lower()
            rationale = str(item.get("rationale", ""))

            if not stock_name or signal_type not in valid_signals:
                logger.warning("Skipping invalid opportunity: %s", item)
                continue

            opportunities.append(MarketOpportunity(
                stock_name=stock_name,
                signal_type=signal_type,
                rationale=rationale,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed opportunity item: %s", e)
            continue

    return opportunities
