"""AI-driven portfolio analysis using AWS Bedrock Claude.

Analyzes stock holdings against live market data and fundamentals to generate
buy/hold/sell/exit verdicts with target prices, stop losses, and tax loss
harvesting identification.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import StockVerdict

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, StockFundamentals
    from llm.bedrock_client import BedrockClient
    from parsers.models import ScripSummary, StockHolding

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior Indian equity research analyst with 20+ years of experience in NSE/BSE markets.
Analyze the provided stock portfolio and generate actionable verdicts.

For each stock, provide:
- verdict: exactly one of "buy", "hold", "sell", or "exit"
- target_price: a realistic target price based on fundamentals and technicals
- stop_loss: a protective stop loss price below current levels
- rationale: a concise 1-2 sentence explanation

Rules:
- Use ONLY the data provided. Do NOT fabricate any prices, volumes, or metrics.
- stop_loss must be less than target_price
- Both target_price and stop_loss must be positive numbers
- Consider tax loss harvesting: if unrealised P&L is negative and holding is short-term, flag it

Respond with ONLY a JSON array of objects. No markdown, no explanation outside the JSON.
Each object must have: name, isin, verdict, target_price, stop_loss, rationale, tax_harvest_flag (boolean)"""


def analyze_portfolio(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    pnl_data: list[ScripSummary],
    client: BedrockClient,
) -> list[StockVerdict]:
    """Generate AI verdicts for each stock holding.

    Batches holdings into groups of 25 to stay within Bedrock's context limit.
    """
    if not holdings:
        return []

    BATCH_SIZE = 25
    all_verdicts: list[StockVerdict] = []

    for i in range(0, len(holdings), BATCH_SIZE):
        batch = holdings[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(holdings) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Analyzing batch %d/%d (%d stocks)", batch_num, total_batches, len(batch))

        user_prompt = _build_user_prompt(batch, bhavcopy, fundamentals, pnl_data)

        try:
            response = client.invoke(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error("Portfolio analysis batch %d failed: %s", batch_num, e)
            continue

        if not response:
            logger.error("Empty response from Bedrock for batch %d", batch_num)
            continue

        batch_verdicts = _parse_verdicts(response, batch, pnl_data)
        all_verdicts.extend(batch_verdicts)
        logger.info("Batch %d: %d verdicts parsed", batch_num, len(batch_verdicts))

    logger.info("Total verdicts: %d out of %d holdings", len(all_verdicts), len(holdings))
    return all_verdicts


def _build_user_prompt(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    pnl_data: list[ScripSummary],
) -> str:
    """Build the user prompt with portfolio data and market context."""
    # Build P&L lookup by ISIN
    pnl_by_isin: dict[str, ScripSummary] = {}
    for scrip in pnl_data:
        pnl_by_isin[scrip.isin] = scrip

    portfolio_items = []
    for h in holdings:
        item: dict = {
            "name": h.name,
            "isin": h.isin,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "buy_value": h.buy_value,
            "closing_price": h.groww_closing_price,
            "closing_value": h.groww_closing_value,
            "unrealised_pnl": h.unrealised_pnl,
            "pnl_percent": h.pnl_percent,
            "holding_type": h.holding_type,
        }

        # Add live price from Bhavcopy
        bhav = bhavcopy.get(h.isin)
        if bhav:
            item["live_price"] = bhav.close_price

        # Add fundamentals
        symbol = h.nse_symbol or h.name
        fund = fundamentals.get(symbol)
        if fund:
            item["fundamentals"] = {
                "pe_ratio": fund.pe_ratio,
                "market_cap": fund.market_cap,
                "book_value": fund.book_value,
                "dividend_yield": fund.dividend_yield,
                "roce": fund.roce,
                "promoter_holding": fund.promoter_holding,
            }

        # Add P&L data
        pnl = pnl_by_isin.get(h.isin)
        if pnl:
            item["buy_date"] = pnl.buy_date.isoformat()
            item["holding_period_days"] = pnl.holding_period_days
            item["tax_classification"] = pnl.tax_classification

        portfolio_items.append(item)

    return (
        "Analyze the following Indian stock portfolio and provide verdicts.\n\n"
        f"Portfolio Holdings:\n{json.dumps(portfolio_items, indent=2)}"
    )


def _parse_verdicts(
    response: dict,
    holdings: list[StockHolding],
    pnl_data: list[ScripSummary],
) -> list[StockVerdict]:
    """Parse Bedrock response into StockVerdict objects.

    Falls back to tax harvest flag computation if the LLM doesn't set it correctly.
    """
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        # Try to find a list in any top-level key
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    # Build P&L lookup for tax harvest flag validation
    pnl_by_isin: dict[str, ScripSummary] = {}
    for scrip in pnl_data:
        pnl_by_isin[scrip.isin] = scrip

    holdings_by_isin: dict[str, StockHolding] = {}
    for h in holdings:
        holdings_by_isin[h.isin] = h

    verdicts: list[StockVerdict] = []
    for item in items:
        try:
            isin = str(item.get("isin", ""))
            name = str(item.get("name", ""))
            verdict = str(item.get("verdict", "hold")).lower()
            if verdict not in ("buy", "hold", "sell", "exit"):
                verdict = "hold"

            target_price = float(item.get("target_price", 0))
            stop_loss = float(item.get("stop_loss", 0))
            rationale = str(item.get("rationale", ""))

            if target_price <= 0 or stop_loss <= 0:
                logger.warning("Skipping verdict for %s: invalid prices", name)
                continue

            # Determine tax harvest flag
            tax_harvest_flag = bool(item.get("tax_harvest_flag", False))
            # Override with computed value if we have the data
            holding = holdings_by_isin.get(isin)
            pnl = pnl_by_isin.get(isin)
            if holding and pnl:
                tax_harvest_flag = (
                    holding.unrealised_pnl < 0
                    and pnl.tax_classification == "short_term"
                )

            verdicts.append(StockVerdict(
                name=name,
                isin=isin,
                verdict=verdict,
                target_price=target_price,
                stop_loss=stop_loss,
                rationale=rationale,
                tax_harvest_flag=tax_harvest_flag,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed verdict item: %s", e)
            continue

    return verdicts
