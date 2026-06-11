"""Real-Time Portfolio Analyzer with Crisis-Aware Recommendations.

Provides actionable BUY/SELL/HOLD/AVERAGE recommendations for existing holdings
considering current market conditions, fundamentals, and crisis opportunities.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, FIIDIIFlow, StockFundamentals
    from llm.bedrock_client import BedrockClient
    from parsers.models import ScripSummary, StockHolding

logger = logging.getLogger(__name__)


@dataclass
class PortfolioAction:
    """Real-time action recommendation for a portfolio holding."""

    name: str
    isin: str
    current_price: float
    avg_cost: float
    current_pnl_pct: float
    action: str  # "BUY_MORE", "AVERAGE_DOWN", "HOLD_TIGHT", "BOOK_PARTIAL", "EXIT", "SWITCH"
    target_price: float
    stop_loss: float
    quantity_suggestion: int  # For averaging
    rationale: str
    priority: str  # "HIGH", "MEDIUM", "LOW"
    crisis_opportunity: bool  # Flag if this is a crisis buy


SYSTEM_PROMPT = """You are a portfolio management expert with deep experience in crisis investing and cost averaging strategies.

CRISIS CONTEXT: Iran-USA war causing market crash. This creates BUYING opportunities in quality stocks.

Analyze each portfolio holding and provide ACTIONABLE recommendations:

ACTION TYPES:
1. BUY_MORE - Quality stock, strong fundamentals, crisis creating buy opportunity
   - Use when: Good stock getting cheaper, fundamentals intact, defensive sector
   - Recommend quantity based on position size and conviction

2. AVERAGE_DOWN - Currently in loss but worth accumulating at lower price
   - Use when: Stock down 10-30%, fundamentals still good, market overreacted
   - Calculate safe quantity to average (don't suggest averaging if fundamentals weak)

3. HOLD_TIGHT - Don't sell in panic, ride it out
   - Use when: Stock down but selling now is bad timing, wait for recovery
   - Defensive stocks, quality names temporarily beaten down

4. BOOK_PARTIAL - Take some profits/cut position
   - Use when: Stock at reasonable level, reduce exposure, better opportunities elsewhere
   - Suggest 25-50% reduction

5. EXIT - Get out completely
   - Use when: Fundamentals deteriorating, better to cut losses
   - High debt, promoter issues, structural problems

6. SWITCH - Exit this, buy something better
   - Use when: Opportunity cost too high, better stocks available
   - Suggest specific alternative in rationale

For each holding, provide:
- name: stock name
- isin: ISIN code
- current_price: latest price
- avg_cost: user's average cost
- current_pnl_pct: current P&L percentage
- action: one of the 6 actions above
- target_price: where you expect it to go (12-month view)
- stop_loss: price to exit if it goes wrong
- quantity_suggestion: if BUY_MORE or AVERAGE_DOWN, suggest quantity (0 otherwise)
- rationale: 2-3 sentences explaining:
  * Why this action now
  * What data supports it (fundamentals, FII/DII activity, crisis opportunity)
  * Specific price levels or metrics
- priority: "HIGH" (act today/tomorrow), "MEDIUM" (this week), "LOW" (monitor)
- crisis_opportunity: true if this is a crisis buying opportunity (quality stock on sale)

CRISIS INVESTING MINDSET:
- Quality defensive stocks down >15% = BUY_MORE opportunity
- FII/DII buying during crash = smart money signal, follow them
- Don't average down on weak stocks (high debt, poor management, structural issues)
- Prefer large caps and defensive sectors for averaging
- This is ACCUMULATION time for 3-5 year horizon

QUANTITY SUGGESTIONS:
- Based on existing position size
- Don't suggest doubling down recklessly
- For ₹1L position at -20%, suggest ₹25-40K additional (bring avg down 5-7%)
- Be specific with logic

Use ONLY provided data. No fabrication.

Respond with ONLY a JSON array. No markdown."""


def analyze_realtime_portfolio(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    fii_dii: FIIDIIFlow,
    pnl_data: list[ScripSummary],
    indices_change: dict[str, float],
    client: BedrockClient,
) -> list[PortfolioAction]:
    """Generate real-time actionable recommendations for portfolio.

    Args:
        holdings: Current stock holdings
        bhavcopy: Live prices
        fundamentals: Stock fundamentals
        fii_dii: Institutional flow data
        pnl_data: P&L history for tax context
        indices_change: Market indices % change
        client: Bedrock client

    Returns:
        List of PortfolioAction objects with specific recommendations
    """
    if not holdings:
        return []

    # Batch processing (25 at a time)
    BATCH_SIZE = 25
    all_actions: list[PortfolioAction] = []

    for i in range(0, len(holdings), BATCH_SIZE):
        batch = holdings[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(holdings) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Analyzing portfolio batch %d/%d", batch_num, total_batches)

        user_prompt = _build_portfolio_prompt(
            batch, bhavcopy, fundamentals, fii_dii, pnl_data, indices_change
        )

        try:
            response = client.invoke(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.error("Portfolio analysis batch %d failed: %s", batch_num, e)
            continue

        if not response:
            logger.error("Empty response for batch %d", batch_num)
            continue

        batch_actions = _parse_portfolio_actions(response)
        all_actions.extend(batch_actions)

    # Sort by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_actions.sort(key=lambda x: priority_order.get(x.priority, 3))

    logger.info("Generated %d portfolio actions", len(all_actions))
    return all_actions


def _build_portfolio_prompt(
    holdings: list[StockHolding],
    bhavcopy: dict[str, BhavcopyRecord],
    fundamentals: dict[str, StockFundamentals],
    fii_dii: FIIDIIFlow,
    pnl_data: list[ScripSummary],
    indices_change: dict[str, float],
) -> str:
    """Build prompt with full portfolio context."""

    # Market context
    market_ctx = {
        "indices_change": indices_change,
        "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
        "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
        "market_phase": "CRASH" if any(v < -2 for v in indices_change.values()) else "CORRECTION"
    }

    # P&L lookup
    pnl_by_isin: dict[str, ScripSummary] = {p.isin: p for p in pnl_data}

    # Portfolio holdings with all context
    portfolio_items = []
    for h in holdings:
        # Current price
        bhav = bhavcopy.get(h.isin)
        current_price = bhav.close_price if bhav else h.groww_closing_price

        # Calculate real-time P&L
        current_value = h.quantity * current_price
        current_pnl_pct = ((current_value / h.buy_value - 1) * 100) if h.buy_value > 0 else 0

        item = {
            "name": h.name,
            "isin": h.isin,
            "quantity": h.quantity,
            "avg_cost": h.avg_buy_price,
            "invested": h.buy_value,
            "current_price": current_price,
            "current_value": current_value,
            "current_pnl_pct": round(current_pnl_pct, 2),
            "holding_type": h.holding_type,
        }

        # Fundamentals
        symbol = h.nse_symbol or h.name
        fund = fundamentals.get(symbol)
        if fund:
            item["fundamentals"] = {
                "pe": fund.pe_ratio,
                "market_cap_cr": fund.market_cap,
                "roce": fund.roce,
                "promoter_holding": fund.promoter_holding,
                "debt_to_equity": getattr(fund, 'debt_to_equity', None),
            }

        # Holding period from P&L
        pnl = pnl_by_isin.get(h.isin)
        if pnl:
            item["holding_period_days"] = pnl.holding_period_days
            item["tax_classification"] = pnl.tax_classification

        portfolio_items.append(item)

    return f"""REAL-TIME PORTFOLIO ANALYSIS - Crisis Opportunity Mode

Market Context:
{json.dumps(market_ctx, indent=2)}

Your Holdings (with live P&L):
{json.dumps(portfolio_items, indent=2)}

Provide actionable recommendations for each holding. Focus on:
- Crisis buying opportunities (quality stocks on sale)
- Averaging strategies for good stocks in red
- Exit signals for weak stocks
- Priority for each action

Be specific with quantities and price targets."""


def _parse_portfolio_actions(response: dict) -> list[PortfolioAction]:
    """Parse response into PortfolioAction objects."""
    items = response.get("items", []) if "items" in response else []
    if not items and isinstance(response, dict):
        for value in response.values():
            if isinstance(value, list):
                items = value
                break

    valid_actions = {
        "BUY_MORE", "AVERAGE_DOWN", "HOLD_TIGHT",
        "BOOK_PARTIAL", "EXIT", "SWITCH"
    }
    valid_priority = {"HIGH", "MEDIUM", "LOW"}

    actions: list[PortfolioAction] = []

    for item in items:
        try:
            name = str(item.get("name", ""))
            isin = str(item.get("isin", ""))
            current_price = float(item.get("current_price", 0))
            avg_cost = float(item.get("avg_cost", 0))
            current_pnl_pct = float(item.get("current_pnl_pct", 0))
            action = str(item.get("action", "HOLD_TIGHT")).upper()
            target_price = float(item.get("target_price", 0))
            stop_loss = float(item.get("stop_loss", 0))
            quantity_suggestion = int(item.get("quantity_suggestion", 0))
            rationale = str(item.get("rationale", ""))
            priority = str(item.get("priority", "MEDIUM")).upper()
            crisis_opportunity = bool(item.get("crisis_opportunity", False))

            # Validation
            if not name or not rationale:
                logger.warning("Skipping action: missing name or rationale")
                continue

            if action not in valid_actions:
                action = "HOLD_TIGHT"

            if priority not in valid_priority:
                priority = "MEDIUM"

            if current_price <= 0 or target_price <= 0 or stop_loss <= 0:
                logger.warning("Skipping %s: invalid prices", name)
                continue

            actions.append(PortfolioAction(
                name=name,
                isin=isin,
                current_price=current_price,
                avg_cost=avg_cost,
                current_pnl_pct=current_pnl_pct,
                action=action,
                target_price=target_price,
                stop_loss=stop_loss,
                quantity_suggestion=quantity_suggestion,
                rationale=rationale,
                priority=priority,
                crisis_opportunity=crisis_opportunity,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed action: %s", e)
            continue

    return actions
