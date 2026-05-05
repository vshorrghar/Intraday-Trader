"""Crisis Opportunity Analyzer - Finds gems during market crashes.

Identifies high-quality stocks that are oversold during market panics,
focusing on defensive sectors, smart money accumulation, and value opportunities.
Specifically designed for geopolitical crisis scenarios (war, oil shocks, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import CrisisOpportunity

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, DealRecord, FIIDIIFlow, StockFundamentals
    from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a crisis-investing expert with 30+ years of experience buying during market crashes.
Your specialty is finding quality companies that panic-sellers are dumping irrationally.

CONTEXT: Markets are crashing due to Iran-USA war tensions. Oil prices spiking, safe-haven demand rising.

Analyze the provided data and identify crisis opportunities across these categories:

1. DEFENSIVE_QUALITY - Defensive sectors (pharma, FMCG, healthcare, IT services) with strong fundamentals
   - Low debt, consistent profits, stable cash flows
   - Essential products/services that don't depend on economic cycles

2. SMART_MONEY_BUY - Stocks where FII/DII are BUYING despite the crash
   - Positive FII/DII net buying in deals data
   - Institutional accumulation while retail panics

3. OVERSOLD_GEM - Quality stocks down >15% but fundamentals intact
   - PE < industry average, high ROCE (>20%), growing promoter holding
   - Panic selling created value opportunity

4. CRISIS_BENEFICIARY - Companies that benefit from war/oil shock
   - Defense stocks, oil & gas, logistics, gold/metals
   - Revenue/profits likely to increase during crisis

For each opportunity, provide:
- stock_name: company name
- symbol: NSE symbol
- crisis_category: one of the 4 categories above
- current_price: latest price from bhavcopy
- estimated_value: your estimate of fair value (20-40% above current in a crisis)
- risk_reward: "high", "medium", or "low" - be selective
- rationale: 2-3 sentences explaining why this is a crisis buy, citing specific data
- action: "BUY_NOW" or "ACCUMULATE_ON_DIP" or "WATCH"

Rules:
- ONLY use provided data - no fabrication
- Be HIGHLY selective - quality over quantity
- Focus on stocks with EVIDENCE of strength (buying activity, strong fundamentals)
- risk_reward "high" only for defensive+strong fundamentals+institutional buying
- Prefer large/mid caps over small caps during crisis
- Return empty array if no quality opportunities found

Respond with ONLY a JSON array. No markdown, no preamble."""


def analyze_crisis_opportunities(
    bhavcopy: dict[str, BhavcopyRecord],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
    indices_change: dict[str, float],  # Nifty, Bank Nifty etc. % change
    client: BedrockClient,
) -> list[CrisisOpportunity]:
    """Find crisis buying opportunities during market crash.

    Args:
        bhavcopy: Live NSE prices by ISIN
        deals: Recent bulk/block deals
        fii_dii: FII/DII flow data
        fundamentals: Stock fundamentals by symbol
        indices_change: Market indices % change (negative during crash)
        client: Bedrock client

    Returns:
        List of CrisisOpportunity objects, sorted by risk_reward
    """
    user_prompt = _build_crisis_prompt(
        bhavcopy, deals, fii_dii, fundamentals, indices_change
    )

    try:
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error("Crisis opportunity analysis failed: %s", e)
        return []

    if not response:
        logger.error("Empty response from Bedrock for crisis analysis")
        return []

    opportunities = _parse_crisis_opportunities(response)

    # Sort by risk_reward (high first) then by estimated upside
    risk_priority = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(
        key=lambda x: (
            risk_priority.get(x.risk_reward, 3),
            -(x.estimated_value / x.current_price - 1) if x.current_price > 0 else 0
        )
    )

    logger.info("Found %d crisis opportunities", len(opportunities))
    return opportunities


def _build_crisis_prompt(
    bhavcopy: dict[str, BhavcopyRecord],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
    indices_change: dict[str, float],
) -> str:
    """Build comprehensive crisis analysis prompt."""

    # Market context
    market_status = {
        "indices_change": indices_change,
        "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
        "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
        "market_sentiment": "PANIC" if any(v < -2 for v in indices_change.values()) else "CAUTIOUS"
    }

    # Recent deals with institutional buying signals
    deal_items = []
    for d in deals[:50]:  # Top 50 recent deals
        deal_items.append({
            "deal_type": d.deal_type,
            "stock": d.security_name,
            "isin": d.isin,
            "client": d.client_name,
            "quantity": d.quantity,
            "price": d.price,
        })

    # Fundamentals for analysis
    fund_items = {}
    for symbol, f in fundamentals.items():
        if f.pe_ratio and f.market_cap:  # Only include if we have data
            fund_items[symbol] = {
                "pe": f.pe_ratio,
                "market_cap_cr": f.market_cap,
                "book_value": f.book_value,
                "roce": f.roce,
                "promoter_holding": f.promoter_holding,
                "dividend_yield": f.dividend_yield,
            }

    # Sample bhavcopy for price context (top liquid stocks)
    price_sample = {}
    for isin, record in list(bhavcopy.items())[:100]:
        price_sample[record.symbol] = {
            "isin": isin,
            "close": record.close_price,
            "prev_close": record.prev_close,
            "change_pct": round(((record.close_price / record.prev_close - 1) * 100), 2) if record.prev_close > 0 else 0,
            "volume": record.volume,
        }

    return f"""MARKET CRASH ANALYSIS - Iran-USA War Impact

Market Status:
{json.dumps(market_status, indent=2)}

Recent Bulk/Block Deals (Institutional Activity):
{json.dumps(deal_items, indent=2)}

Stock Fundamentals:
{json.dumps(fund_items, indent=2)}

Live Prices (Sample of Liquid Stocks):
{json.dumps(price_sample, indent=2)}

Find crisis buying opportunities. Focus on:
- Defensive sectors holding up well
- Stocks with FII/DII buying despite crash
- Quality names oversold >15% with strong fundamentals
- Crisis beneficiaries (defense, oil & gas, pharma)

Be highly selective - only flag TRUE opportunities with evidence."""


def _parse_crisis_opportunities(response: dict) -> list[CrisisOpportunity]:
    """Parse Bedrock response into CrisisOpportunity objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    valid_categories = {
        "DEFENSIVE_QUALITY", "SMART_MONEY_BUY",
        "OVERSOLD_GEM", "CRISIS_BENEFICIARY"
    }
    valid_actions = {"BUY_NOW", "ACCUMULATE_ON_DIP", "WATCH"}
    valid_risk = {"high", "medium", "low"}

    opportunities: list[CrisisOpportunity] = []

    for item in items:
        try:
            stock_name = str(item.get("stock_name", ""))
            symbol = str(item.get("symbol", ""))
            crisis_category = str(item.get("crisis_category", "")).upper()
            current_price = float(item.get("current_price", 0))
            estimated_value = float(item.get("estimated_value", 0))
            risk_reward = str(item.get("risk_reward", "medium")).lower()
            rationale = str(item.get("rationale", ""))
            action = str(item.get("action", "WATCH")).upper()

            # Validation
            if not stock_name or not rationale:
                logger.warning("Skipping opportunity: missing name or rationale")
                continue

            if crisis_category not in valid_categories:
                logger.warning("Invalid crisis category: %s", crisis_category)
                continue

            if current_price <= 0 or estimated_value <= 0:
                logger.warning("Skipping %s: invalid prices", stock_name)
                continue

            if estimated_value <= current_price:
                logger.warning("Skipping %s: estimated value not above current", stock_name)
                continue

            if risk_reward not in valid_risk:
                risk_reward = "medium"

            if action not in valid_actions:
                action = "WATCH"

            upside_pct = round(((estimated_value / current_price - 1) * 100), 1)

            opportunities.append(CrisisOpportunity(
                stock_name=stock_name,
                symbol=symbol,
                crisis_category=crisis_category,
                current_price=current_price,
                estimated_value=estimated_value,
                upside_potential_pct=upside_pct,
                risk_reward=risk_reward,
                rationale=rationale,
                action=action,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed crisis opportunity: %s", e)
            continue

    return opportunities
