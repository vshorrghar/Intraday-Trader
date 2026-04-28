"""Brutal Portfolio Analyzer - Honest assessment with no sugar coating.

Tells you straight up what's junk in your portfolio. Flags weak stocks
but respects penny stock positions (small amounts kept for lottery tickets).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, StockFundamentals
    from llm.bedrock_client import BedrockClient
    from parsers.models import StockHolding

logger = logging.getLogger(__name__)

# Penny stock threshold - positions worth less than this are flagged but not sell recommendations
PENNY_POSITION_THRESHOLD = 5000  # ₹5,000


@dataclass
class BrutalAssessment:
    """Brutally honest assessment of a portfolio holding."""

    name: str
    isin: str
    current_price: float
    position_value: float
    verdict: str  # "QUALITY", "DECENT", "MEDIOCRE", "WEAK", "JUNK"
    quality_score: int  # 1-10 (10 = best)
    is_penny_position: bool  # True if position < ₹5,000
    red_flags: list[str]  # List of problems
    strengths: list[str]  # List of positives (even junk stocks may have 1-2)
    action_recommendation: str  # What to do
    brutal_truth: str  # No-nonsense honest assessment


SYSTEM_PROMPT = """You are a brutally honest portfolio analyst with 25 years of experience. Your job is to tell the TRUTH about stock quality without sugar coating.

DO NOT be polite or diplomatic. If a stock is junk, say it's junk. If fundamentals are weak, call them weak. If it's a gamble, say it's a gamble.

For each holding, assess:

**QUALITY INDICATORS** (Good Signs):
- Low debt (D/E < 0.5)
- High ROCE (>15%)
- Consistent profits (not erratic)
- Growing revenue (>10% CAGR)
- Stable promoter holding (50-75%)
- Good corporate governance
- Strong moat/competitive advantage

**RED FLAGS** (Bad Signs):
- High debt (D/E > 1.0)
- Negative/low ROCE (< 10%)
- Declining revenue
- Erratic profits or losses
- Promoter pledging/selling
- Corporate governance issues
- Commoditized business (no moat)
- Penny stock (price < ₹10)
- Low liquidity

VERDICT CATEGORIES:
1. **QUALITY** (8-10 score) - Blue chip or solid mid cap, hold for years
2. **DECENT** (6-7 score) - Okay business, not great but not terrible
3. **MEDIOCRE** (4-5 score) - Average stock, no edge, many better options exist
4. **WEAK** (2-3 score) - Fundamentals deteriorating, high risk
5. **JUNK** (1 score) - Bad business, poor management, or penny stock speculation

For each stock, provide:
- name: stock name
- isin: ISIN code
- current_price: latest price
- position_value: current holding value
- verdict: one of the 5 categories above
- quality_score: 1-10 rating
- is_penny_position: true if position value < ₹5,000 (penny stock gamble)
- red_flags: List of 2-4 specific problems (be harsh)
- strengths: List of 1-2 positives (even junk has some)
- action_recommendation: specific action
  * QUALITY/DECENT: "HOLD" or "ADD ON DIPS"
  * MEDIOCRE: "HOLD BUT DON'T ADD" or "SWITCH TO BETTER STOCK"
  * WEAK: "EXIT ON BOUNCE" or "CUT LOSSES"
  * JUNK penny position: "KEEP AS LOTTERY TICKET" (if < ₹5K)
  * JUNK large position: "EXIT IMMEDIATELY"
- brutal_truth: 2-3 sentences of harsh reality about this stock

IMPORTANT RULES:
1. Be BRUTALLY HONEST - if it's crap, say it's crap
2. Don't recommend selling penny positions (< ₹5,000) - let them ride as lottery tickets
3. DO recommend exiting junk stocks if position is > ₹5,000
4. Call out specific red flags with data (declining revenue, high debt, etc.)
5. Even junk stocks have 1-2 strengths - find them for balanced view

Use ONLY provided data. No fabrication.

Respond with ONLY a JSON array. No markdown."""


def analyze_portfolio_brutally(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    client: BedrockClient,
) -> list[BrutalAssessment]:
    """Generate brutally honest assessments for portfolio holdings.

    Args:
        holdings: Current stock holdings
        bhavcopy: Live prices
        fundamentals: Stock fundamentals
        client: Bedrock client

    Returns:
        List of BrutalAssessment objects with harsh reality checks
    """
    if not holdings:
        return []

    # Batch processing (25 at a time)
    BATCH_SIZE = 25
    all_assessments: list[BrutalAssessment] = []

    for i in range(0, len(holdings), BATCH_SIZE):
        batch = holdings[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(holdings) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Brutally analyzing batch %d/%d", batch_num, total_batches)

        user_prompt = _build_brutal_prompt(batch, bhavcopy, fundamentals)

        try:
            response = client.invoke(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error("Brutal analysis batch %d failed: %s", batch_num, e)
            continue

        if not response:
            logger.error("Empty response for batch %d", batch_num)
            continue

        batch_assessments = _parse_brutal_assessments(response)
        all_assessments.extend(batch_assessments)

    # Sort by quality_score (worst first - show the junk at the top!)
    all_assessments.sort(key=lambda x: x.quality_score)

    logger.info("Brutal assessment complete: %d stocks analyzed", len(all_assessments))
    return all_assessments


def _build_brutal_prompt(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
) -> str:
    """Build prompt with portfolio holdings and their fundamentals."""

    portfolio_items = []
    for h in holdings:
        # Current price
        bhav = bhavcopy.get(h.isin)
        current_price = bhav.close_price if bhav else h.groww_closing_price

        # Position value
        position_value = h.quantity * current_price

        # Is this a penny position?
        is_penny_position = position_value < PENNY_POSITION_THRESHOLD

        item = {
            "name": h.name,
            "isin": h.isin,
            "quantity": h.quantity,
            "current_price": current_price,
            "position_value": position_value,
            "avg_cost": h.avg_buy_price,
            "pnl_pct": round(((current_price / h.avg_buy_price - 1) * 100), 2) if h.avg_buy_price > 0 else 0,
            "is_penny_position": is_penny_position,
            "holding_type": h.holding_type,
        }

        # Add fundamentals if available
        symbol = h.nse_symbol or h.name
        fund = fundamentals.get(symbol)
        if fund:
            item["fundamentals"] = {
                "pe": fund.pe_ratio,
                "market_cap_cr": fund.market_cap,
                "roce": fund.roce,
                "promoter_holding": fund.promoter_holding,
                "debt_to_equity": getattr(fund, 'debt_to_equity', None),
                "book_value": fund.book_value,
            }
        else:
            item["fundamentals"] = "Data not available - likely penny stock or illiquid"

        portfolio_items.append(item)

    return f"""BRUTAL PORTFOLIO ANALYSIS - No Sugar Coating

Your Holdings ({len(portfolio_items)} stocks):
{json.dumps(portfolio_items, indent=2)}

Analyze each stock with BRUTAL HONESTY:
- Call out junk stocks directly
- Flag red flags (debt, declining revenue, poor management)
- Rate quality 1-10 (most will be 3-6, be realistic)
- For penny positions (< ₹5K), say "KEEP AS LOTTERY TICKET"
- For junk positions > ₹5K, recommend EXIT

Be harsh but fair. Even bad stocks have 1-2 strengths."""


def _parse_brutal_assessments(response: dict) -> list[BrutalAssessment]:
    """Parse response into BrutalAssessment objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    valid_verdicts = {"QUALITY", "DECENT", "MEDIOCRE", "WEAK", "JUNK"}
    assessments: list[BrutalAssessment] = []

    for item in items:
        try:
            name = str(item.get("name", ""))
            isin = str(item.get("isin", ""))
            current_price = float(item.get("current_price", 0))
            position_value = float(item.get("position_value", 0))
            verdict = str(item.get("verdict", "MEDIOCRE")).upper()
            quality_score = int(item.get("quality_score", 5))
            is_penny_position = bool(item.get("is_penny_position", False))
            red_flags = item.get("red_flags", [])
            strengths = item.get("strengths", [])
            action_recommendation = str(item.get("action_recommendation", "HOLD"))
            brutal_truth = str(item.get("brutal_truth", ""))

            # Validation
            if not name or not brutal_truth:
                logger.warning("Skipping assessment: missing name or truth")
                continue

            if verdict not in valid_verdicts:
                verdict = "MEDIOCRE"

            # Ensure score is 1-10
            quality_score = max(1, min(10, quality_score))

            # Ensure lists
            if not isinstance(red_flags, list):
                red_flags = [str(red_flags)] if red_flags else []
            if not isinstance(strengths, list):
                strengths = [str(strengths)] if strengths else []

            assessments.append(BrutalAssessment(
                name=name,
                isin=isin,
                current_price=current_price,
                position_value=position_value,
                verdict=verdict,
                quality_score=quality_score,
                is_penny_position=is_penny_position,
                red_flags=red_flags,
                strengths=strengths,
                action_recommendation=action_recommendation,
                brutal_truth=brutal_truth,
            ))

        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed assessment: %s", e)
            continue

    return assessments
