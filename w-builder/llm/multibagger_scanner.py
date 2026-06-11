"""Multibagger Scanner - Find hidden gems, NOT top 50 companies.

Identifies high-growth potential stocks outside Nifty 50 and top large caps.
Focuses on small/mid cap companies with strong fundamentals and growth catalysts.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import MultibaggerOpportunity

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, DealRecord, FIIDIIFlow, StockFundamentals
    from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

# Nifty 50 companies to EXCLUDE (updated list as of 2024)
NIFTY_50_SYMBOLS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR", "ICICIBANK", "SBIN", "BHARTIARTL",
    "ITC", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "BAJFINANCE", "HCLTECH",
    "TITAN", "WIPRO", "SUNPHARMA", "ULTRACEMCO", "ONGC", "NTPC", "TATAMOTORS", "NESTLEIND",
    "M&M", "POWERGRID", "BAJAJFINSV", "TECHM", "ADANIENT", "JSWSTEEL", "HINDALCO", "INDUSINDBK",
    "COALINDIA", "TATASTEEL", "GRASIM", "CIPLA", "EICHERMOT", "TATACONSUM", "HDFCLIFE",
    "SBILIFE", "BPCL", "DRREDDY", "ADANIPORTS", "APOLLOHOSP", "DIVISLAB", "BRITANNIA",
    "BAJAJ-AUTO", "HEROMOTOCO", "SHRIRAMFIN", "TRENT"
}

# Additional top 150 large caps to exclude (focus on mid/small caps)
TOP_LARGECAPS_EXCLUDE = {
    "VEDL", "UPL", "DLF", "GODREJCP", "PIDILITIND", "HAVELLS", "COLPAL", "DABUR",
    "MARICO", "MCDOWELL-N", "AMBUJACEM", "ACC", "GAIL", "IOC", "PNB", "BANKBARODA",
    "BOSCHLTD", "SIEMENS", "ABB", "MRF", "TORNTPHARM", "LUPIN", "BIOCON",
    "BERGEPAINT", "CANBK", "IDEA", "ZOMATO", "NYKAA", "PAYTM", "POLICYBZR"
}

EXCLUDE_SYMBOLS = NIFTY_50_SYMBOLS | TOP_LARGECAPS_EXCLUDE

# Market cap thresholds (in crores)
SMALL_CAP_MAX = 10000  # < 10,000 Cr
MID_CAP_MAX = 50000    # 10,000 - 50,000 Cr


SYSTEM_PROMPT = """You are a small-cap and mid-cap stock analyst specializing in identifying future multibaggers BEFORE they become mainstream.

IMPORTANT: Do NOT recommend any Nifty 50 stocks or mega-cap companies. Focus on HIDDEN GEMS in small/mid cap space.

CONTEXT: Market crash creating opportunity to buy quality small caps at discount. Look for 3-5 year multibagger potential.

Identify stocks with these characteristics:

1. **STRONG GROWTH TRAJECTORY**
   - Revenue CAGR >20% over last 3 years
   - Expanding margins (EBITDA margin improving)
   - Consistent profit growth
   - NOT one-time spike - sustainable business

2. **REASONABLE VALUATION**
   - PE < 30 (not overvalued despite growth)
   - PEG ratio < 1.5 (growth vs valuation)
   - Market cap < ₹50,000 Cr (room to grow)

3. **QUALITY BUSINESS**
   - ROCE > 15% (capital efficient)
   - Debt/Equity < 0.5 (manageable debt)
   - Promoter holding 50-75% (aligned interests, not too much)
   - No governance red flags

4. **GROWTH CATALYSTS**
   - New product launches
   - Capacity expansion
   - Export opportunities
   - Sector tailwinds
   - Margin expansion levers

5. **MARKET POSITIONING**
   - Niche player or #2/#3 in segment (not commoditized)
   - High entry barriers
   - Recurring revenue model preferred

For each multibagger candidate, provide:
- stock_name: company name
- symbol: NSE symbol
- market_cap_cr: market cap in crores
- category: "small_cap" (<₹10,000 Cr) or "mid_cap" (₹10,000-50,000 Cr)
- current_price: latest price
- estimated_target_3yr: realistic 3-year price target
- upside_potential_pct: % upside to 3-year target
- multibagger_score: 1-10 (10 = highest conviction)
- growth_drivers: List of 2-3 specific catalysts
- risks: 1-2 key risks to watch
- rationale: 3-4 sentences explaining the multibagger thesis with specific metrics

QUALITY OVER QUANTITY:
- Only flag TRUE multibagger potential
- Be selective - 5-10 stocks max
- Must have ALL: growth + value + quality + catalyst
- No penny stocks (price < ₹10) or loss-making companies
- No one-hit wonders - need sustainable business model

Use ONLY provided data. No fabrication.

Respond with ONLY a JSON array. No markdown."""


def scan_multibaggers(
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    client: BedrockClient,
) -> list[MultibaggerOpportunity]:
    """Scan for multibagger opportunities outside Nifty 50.

    Args:
        bhavcopy: Live NSE prices
        fundamentals: Stock fundamentals by symbol
        deals: Recent bulk/block deals
        fii_dii: FII/DII flow data
        client: Bedrock client

    Returns:
        List of MultibaggerOpportunity objects, sorted by conviction score
    """
    # Filter out top companies from fundamentals
    filtered_fundamentals = {
        symbol: data
        for symbol, data in fundamentals.items()
        if symbol not in EXCLUDE_SYMBOLS and _is_small_or_mid_cap(data)
    }

    if not filtered_fundamentals:
        logger.warning("No small/mid cap stocks after filtering")
        return []

    logger.info("Scanning %d small/mid cap stocks for multibagger potential", len(filtered_fundamentals))

    user_prompt = _build_multibagger_prompt(
        bhavcopy, filtered_fundamentals, deals, fii_dii
    )

    try:
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error("Multibagger scan failed: %s", e)
        return []

    if not response:
        logger.error("Empty response from Bedrock for multibagger scan")
        return []

    opportunities = _parse_multibagger_opportunities(response)

    # Sort by multibagger_score (highest first)
    opportunities.sort(key=lambda x: x.multibagger_score, reverse=True)

    logger.info("Found %d multibagger candidates", len(opportunities))
    return opportunities


def _is_small_or_mid_cap(fundamentals: StockFundamentals) -> bool:
    """Check if stock is small or mid cap (< 50,000 Cr market cap)."""
    if not fundamentals.market_cap:
        return False

    return fundamentals.market_cap < MID_CAP_MAX


def _build_multibagger_prompt(
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
) -> str:
    """Build prompt with filtered small/mid cap data."""

    # Market context
    market_context = {
        "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
        "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
        "note": "Market crash = opportunity to buy quality small caps at discount"
    }

    # Fundamentals for small/mid caps only
    fund_items = {}
    for symbol, f in fundamentals.items():
        # Only include if we have enough data
        if f.pe_ratio and f.market_cap and f.roce:
            fund_items[symbol] = {
                "market_cap_cr": f.market_cap,
                "pe": f.pe_ratio,
                "roce": f.roce,
                "promoter_holding": f.promoter_holding,
                "book_value": f.book_value,
                "dividend_yield": f.dividend_yield,
            }

    # Recent deals on small/mid caps
    deal_signals = []
    for d in deals:
        # Check if deal is on a small/mid cap
        symbol = getattr(d, 'symbol', d.security_name.upper().replace(" ", ""))
        if symbol in fundamentals:
            deal_signals.append({
                "stock": d.security_name,
                "symbol": symbol,
                "deal_type": d.deal_type,
                "client": d.client_name,
                "quantity": d.quantity,
                "price": d.price,
            })

    # Price data for candidates
    price_data = {}
    for isin, record in bhavcopy.items():
        if record.symbol in fundamentals:
            price_data[record.symbol] = {
                "current_price": record.close_price,
                "change_pct": round(((record.close_price / record.prev_close - 1) * 100), 2) if record.prev_close > 0 else 0,
            }

    return f"""MULTIBAGGER SCAN - Hidden Gems (NO Nifty 50 / Top Large Caps)

Market Context:
{json.dumps(market_context, indent=2)}

Small/Mid Cap Fundamentals ({len(fund_items)} stocks):
{json.dumps(fund_items, indent=2)}

Recent Deals on Small/Mid Caps:
{json.dumps(deal_signals[:20], indent=2)}

Current Prices:
{json.dumps(price_data, indent=2)}

Find 5-10 multibagger candidates with:
- Market cap < ₹50,000 Cr (small/mid cap)
- Strong growth (revenue CAGR >20%)
- Quality business (ROCE >15%, low debt)
- Reasonable valuation (PE < 30)
- Clear growth catalysts

EXCLUDE: Nifty 50, mega caps, penny stocks, loss-making companies.

Focus on 3-5 year wealth creation potential."""


def _parse_multibagger_opportunities(response: dict) -> list[MultibaggerOpportunity]:
    """Parse Bedrock response into MultibaggerOpportunity objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    opportunities: list[MultibaggerOpportunity] = []

    for item in items:
        try:
            stock_name = str(item.get("stock_name", ""))
            symbol = str(item.get("symbol", "")).upper()
            market_cap_cr = float(item.get("market_cap_cr", 0))
            category = str(item.get("category", "small_cap")).lower()
            current_price = float(item.get("current_price", 0))
            estimated_target_3yr = float(item.get("estimated_target_3yr", 0))
            upside_potential_pct = float(item.get("upside_potential_pct", 0))
            multibagger_score = int(item.get("multibagger_score", 5))
            growth_drivers = item.get("growth_drivers", [])
            risks = item.get("risks", [])
            rationale = str(item.get("rationale", ""))

            # Validation
            if not stock_name or not rationale:
                logger.warning("Skipping opportunity: missing name or rationale")
                continue

            # Check if it's actually in excluded list (safety check)
            if symbol in EXCLUDE_SYMBOLS:
                logger.warning("Filtered out excluded symbol: %s", symbol)
                continue

            if current_price <= 0 or estimated_target_3yr <= 0:
                logger.warning("Skipping %s: invalid prices", stock_name)
                continue

            if estimated_target_3yr <= current_price:
                logger.warning("Skipping %s: target not above current", stock_name)
                continue

            # Ensure penny stocks filtered out
            if current_price < 10:
                logger.warning("Filtering out penny stock: %s at ₹%.2f", stock_name, current_price)
                continue

            # Validate category
            if category not in ("small_cap", "mid_cap"):
                category = "small_cap" if market_cap_cr < SMALL_CAP_MAX else "mid_cap"

            # Ensure score is 1-10
            multibagger_score = max(1, min(10, multibagger_score))

            # Ensure growth_drivers and risks are lists
            if not isinstance(growth_drivers, list):
                growth_drivers = [str(growth_drivers)] if growth_drivers else []
            if not isinstance(risks, list):
                risks = [str(risks)] if risks else []

            opportunities.append(MultibaggerOpportunity(
                stock_name=stock_name,
                symbol=symbol,
                market_cap_cr=market_cap_cr,
                category=category,
                current_price=current_price,
                estimated_target_3yr=estimated_target_3yr,
                upside_potential_pct=upside_potential_pct,
                multibagger_score=multibagger_score,
                growth_drivers=growth_drivers,
                risks=risks,
                rationale=rationale,
            ))

        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed multibagger item: %s", e)
            continue

    return opportunities
