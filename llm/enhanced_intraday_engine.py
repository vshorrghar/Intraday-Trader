"""Enhanced Intraday Engine with Smart Money Flow Analysis.

Generates superior intraday setups by combining:
- FII/DII institutional flow patterns
- Volume spike detection
- Defensive sector filtering during crisis
- Technical + fundamental screening
- Real-time market sentiment analysis
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from llm.models import IntradaySetup

if TYPE_CHECKING:
    from fetchers.models import BhavcopyRecord, DealRecord, FIIDIIFlow, StockFundamentals
    from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an elite NSE intraday trader with 15+ years of scalping experience and deep understanding of institutional flow patterns.

MARKET CONTEXT: Iran-USA war causing volatility. Oil prices up, markets choppy. Smart money hunting opportunities.

Generate EXACTLY 10 intraday trading setups for TODAY's session based on:

SCREENING CRITERIA (use ALL of these):
1. SMART MONEY SIGNALS
   - FII/DII net buying OR recent bulk deal accumulation
   - Institutional activity in last 24-48 hours
   - Large orders absorbed without price crash = strong hands

2. VOLUME + MOMENTUM
   - Volume spike >50% above average
   - Price holding above VWAP/key support despite market weakness
   - Relative strength vs Nifty (stock green when market red = winner)

3. DEFENSIVE PREFERENCE (crisis context)
   - Prioritize: Pharma, IT, FMCG, Healthcare, Defense
   - Avoid: Real estate, NBFCs, high-beta cyclicals
   - Exception: Crisis beneficiaries (oil & gas, defense stocks)

4. FUNDAMENTALS CHECK
   - PE reasonable (<30 for quality stocks, <20 for value)
   - Promoter holding stable or increasing
   - Not penny stocks - prefer liquid large/midcaps

5. TECHNICAL SETUP
   - Clear entry trigger (breakout, support bounce, pullback)
   - Tight stop loss (<3% for intraday)
   - Minimum 1:2 risk-reward ratio

For each setup, provide:
- stock_name: company name
- symbol: NSE symbol
- entry_price: specific entry level (current price or trigger)
- target_price: realistic intraday target (1.5-3% move)
- stop_loss: tight stop (<3% below entry)
- rationale: 2-3 sentences citing SPECIFIC data points:
  * What institutional signal (FII buying / bulk deal / volume spike)
  * Why it's strong today (technical setup, sector strength, relative performance)
  * Risk-reward justification

QUALITY OVER QUANTITY - If you find only 7 solid setups, that's better than 10 mediocre ones.
But aim for exactly 10 if possible.

Rules:
- ONLY use provided data - no fabrication
- target_price > entry_price
- stop_loss < entry_price (typically 2-3% below)
- Cite specific evidence (FII net, deal size, volume %, PE ratio)
- Prefer stocks with multiple positive signals

Respond with ONLY a JSON array of 10 objects. No markdown."""


def generate_enhanced_intraday_setups(
    bhavcopy: dict[str, BhavcopyRecord],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
    indices: dict[str, float],  # Current index levels/changes
    client: BedrockClient,
) -> list[IntradaySetup]:
    """Generate smart-money-aware intraday setups.

    Args:
        bhavcopy: Live NSE prices by ISIN
        deals: Recent bulk/block deals
        fii_dii: FII/DII flow data
        fundamentals: Stock fundamentals by symbol
        indices: Market indices data
        client: Bedrock client

    Returns:
        List of 10 IntradaySetup objects (or fewer if quality is low)
    """
    user_prompt = _build_enhanced_prompt(
        bhavcopy, deals, fii_dii, fundamentals, indices
    )

    try:
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error("Enhanced intraday setup generation failed: %s", e)
        return []

    if not response:
        logger.error("Empty response from Bedrock for enhanced intraday")
        return []

    setups = _parse_setups(response)
    logger.info("Generated %d enhanced intraday setups", len(setups))
    return setups


def _build_enhanced_prompt(
    bhavcopy: dict[str, BhavcopyRecord],
    deals: list[DealRecord],
    fii_dii: FIIDIIFlow,
    fundamentals: dict[str, StockFundamentals],
    indices: dict[str, float],
) -> str:
    """Build comprehensive prompt with all relevant data."""

    # FII/DII Summary
    fii_dii_summary = {
        "date": fii_dii.date,
        "fii_net_crores": round(fii_dii.fii_net / 10000000, 2),
        "dii_net_crores": round(fii_dii.dii_net / 10000000, 2),
        "net_institutional_flow": round((fii_dii.fii_net + fii_dii.dii_net) / 10000000, 2),
        "sentiment": "BUYING" if (fii_dii.fii_net + fii_dii.dii_net) > 0 else "SELLING"
    }

    # Recent deals with institutional signals
    deal_signals = []
    for d in deals[:30]:  # Focus on recent 30
        deal_signals.append({
            "stock": d.security_name,
            "symbol": getattr(d, 'symbol', ''),
            "deal_type": d.deal_type,
            "client": d.client_name,
            "quantity": d.quantity,
            "price": d.price,
        })

    # Top movers from bhavcopy (volume + price action)
    movers = []
    for isin, record in bhavcopy.items():
        if record.prev_close > 0 and record.volume > 0:
            change_pct = ((record.close_price / record.prev_close - 1) * 100)
            movers.append({
                "symbol": record.symbol,
                "isin": isin,
                "close": record.close_price,
                "change_pct": round(change_pct, 2),
                "volume": record.volume,
                "prev_volume": getattr(record, 'avg_volume', record.volume),  # If available
            })

    # Sort by absolute change and volume - top 50 candidates
    movers.sort(key=lambda x: abs(x["change_pct"]) + (x["volume"] / 1000000), reverse=True)
    movers = movers[:50]

    # Fundamentals for candidate stocks
    fund_data = {}
    for symbol, f in fundamentals.items():
        if symbol in [m["symbol"] for m in movers[:30]]:  # Only for top movers
            fund_data[symbol] = {
                "pe": f.pe_ratio,
                "market_cap_cr": f.market_cap,
                "roce": f.roce,
                "promoter_holding": f.promoter_holding,
                "sector": getattr(f, 'sector', 'Unknown'),
            }

    # Market indices context
    indices_summary = {
        "nifty_50": indices.get("NIFTY 50", 0),
        "nifty_bank": indices.get("NIFTY BANK", 0),
        "nifty_it": indices.get("NIFTY IT", 0),
        "nifty_pharma": indices.get("NIFTY PHARMA", 0),
    }

    return f"""ENHANCED INTRADAY SCAN - Smart Money Analysis

Institutional Flows (Today):
{json.dumps(fii_dii_summary, indent=2)}

Recent Bulk/Block Deals (Institutional Activity):
{json.dumps(deal_signals, indent=2)}

Top Volume Movers (Sorted by Volume + Price Action):
{json.dumps(movers, indent=2)}

Fundamentals (Top Candidates):
{json.dumps(fund_data, indent=2)}

Market Indices:
{json.dumps(indices_summary, indent=2)}

Generate 10 intraday setups using this data. Prioritize stocks with:
- FII/DII buying OR bulk deal accumulation
- Strong volume + relative strength
- Defensive sectors (pharma, IT, FMCG) during crisis
- Clear technical setup with tight stop loss"""


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
            symbol = str(item.get("symbol", stock_name))  # Fallback to stock_name
            entry_price = float(item.get("entry_price", 0))
            target_price = float(item.get("target_price", 0))
            stop_loss = float(item.get("stop_loss", 0))
            rationale = str(item.get("rationale", ""))

            # Validation
            if entry_price <= 0 or target_price <= 0 or stop_loss <= 0:
                logger.warning("Skipping setup for %s: non-positive prices", stock_name)
                continue

            if target_price <= entry_price:
                logger.warning("Skipping %s: target not above entry", stock_name)
                continue

            if stop_loss >= entry_price:
                logger.warning("Skipping %s: stop loss not below entry", stock_name)
                continue

            if not stock_name or not rationale:
                logger.warning("Skipping setup: missing name or rationale")
                continue

            # Risk-reward check (optional but good)
            risk = entry_price - stop_loss
            reward = target_price - entry_price
            if risk > 0 and (reward / risk) < 1.2:
                logger.warning("Skipping %s: poor risk-reward ratio", stock_name)
                continue

            setups.append(IntradaySetup(
                stock_name=f"{stock_name} ({symbol})" if symbol and symbol != stock_name else stock_name,
                entry_price=entry_price,
                target_price=target_price,
                stop_loss=stop_loss,
                rationale=rationale,
            ))
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed setup: %s", e)
            continue

    return setups
