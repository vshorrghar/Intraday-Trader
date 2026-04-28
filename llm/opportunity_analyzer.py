"""AI-driven market opportunity analyzer.

Uses real-time NSE data + Screener fundamentals + Bedrock Claude to identify
stocks and ETFs worth buying during market crashes/corrections.

Thinks like a 30-year veteran SEBI-registered research analyst.
"""
from __future__ import annotations
import json, logging
from dataclasses import dataclass
from llm.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)


@dataclass
class OpportunityPick:
    symbol: str
    name: str
    pick_type: str  # "stock" or "etf"
    action: str  # "strong_buy", "buy", "accumulate", "watch"
    current_price: float
    target_price: float
    stop_loss: float
    time_horizon: str  # "intraday", "swing", "positional", "long_term"
    conviction: str  # "high", "medium", "low"
    rationale: str
    risk_factors: str
    sector: str
    score: int  # 0-100 analyst score


SYSTEM_PROMPT = """You are a SEBI-registered research analyst with 30 years of experience in Indian equity markets (NSE/BSE). You have deep expertise in:

FUNDAMENTAL ANALYSIS:
- Valuation: P/E vs industry PE, P/B, EV/EBITDA, PEG ratio, DCF intrinsic value
- Profitability: ROCE (>15% is good, >20% excellent), ROE, operating margins, net margins
- Growth: Revenue CAGR (3Y/5Y), profit CAGR, EPS growth trajectory
- Balance sheet: Debt/Equity (<0.5 ideal), interest coverage (>3x), current ratio
- Cash flow: Free cash flow yield, operating cash flow vs net profit consistency
- Ownership: Promoter holding (>50% preferred), pledge % (<10%), FII/DII trends

TECHNICAL ANALYSIS:
- Price action: Support/resistance levels, 52-week high/low proximity
- Moving averages: 50 DMA, 200 DMA crossovers (golden cross/death cross)
- Momentum: RSI (oversold <30, overbought >70), MACD signal line crossovers
- Volume: Volume spike analysis, delivery % (>50% = genuine buying)
- Patterns: Cup & handle, double bottom, falling wedge (reversal patterns in crashes)
- Fibonacci: Retracement levels (38.2%, 50%, 61.8%) from recent highs

CRISIS/WAR ANALYSIS:
- Defensive sectors: Pharma, FMCG, IT (USD earners), Gold ETFs
- Beneficiaries: Defense stocks, oil & gas (if India benefits), import substitution
- Avoid: High-beta, leveraged companies, companies with forex exposure to conflict zones
- Historical patterns: Markets recover 6-12 months post-crisis, quality stocks bounce first

ETF STRATEGY DURING CRASHES:
- Nifty 50 ETF: Core allocation, buy on every 5% dip
- Nifty Next 50 ETF: Growth allocation, higher beta but higher returns
- Nifty Midcap 150 ETF: Aggressive allocation, buy in SIP mode during crash
- Sectoral ETFs: Pharma, IT, Bank — based on sector rotation signals
- Gold ETF/Sovereign Gold Bond: Hedge allocation during geopolitical uncertainty
- International ETFs: NASDAQ 100, S&P 500 — if rupee depreciation expected

RULES:
1. Use ONLY the real market data provided. Never fabricate prices or metrics.
2. Every pick must have a clear entry price, target, and stop loss.
3. Risk-reward ratio must be at least 1:2 (potential gain > 2x potential loss).
4. Diversify across sectors — don't recommend >2 stocks from same sector.
5. Include at least 3 ETF recommendations for diversified crash-buying.
6. Flag conviction level honestly — "high" only when multiple factors align.
7. Consider tax implications — short-term vs long-term holding period.

Respond with ONLY valid JSON:
{
  "market_regime": "crash/correction/consolidation/recovery/bull",
  "vix_assessment": "...",
  "sector_rotation": "which sectors money is flowing into/out of",
  "stock_picks": [
    {
      "symbol": "SYMBOL",
      "name": "Full Name",
      "pick_type": "stock",
      "action": "strong_buy/buy/accumulate/watch",
      "current_price": 0.0,
      "target_price": 0.0,
      "stop_loss": 0.0,
      "time_horizon": "positional/long_term",
      "conviction": "high/medium/low",
      "rationale": "Detailed 2-3 sentence analysis using technical + fundamental reasoning",
      "risk_factors": "Key risks to watch",
      "sector": "Sector name",
      "score": 85
    }
  ],
  "etf_picks": [
    {
      "symbol": "ETF_SYMBOL",
      "name": "ETF Full Name",
      "pick_type": "etf",
      "action": "strong_buy/buy/accumulate",
      "current_price": 0.0,
      "target_price": 0.0,
      "stop_loss": 0.0,
      "time_horizon": "long_term",
      "conviction": "high/medium",
      "rationale": "Why this ETF now",
      "risk_factors": "Risks",
      "sector": "Broad Market/Sectoral",
      "score": 80
    }
  ],
  "avoid_list": ["SYMBOL1 - reason", "SYMBOL2 - reason"],
  "portfolio_allocation_advice": "How to allocate fresh capital across these picks"
}"""


def analyze_opportunities(market_data: dict, fii_dii: dict | None, existing_holdings: list[str], client: BedrockClient) -> dict:
    """Run comprehensive opportunity analysis using real market data + Claude.

    Args:
        market_data: From fetch_all_market_data() — gainers, losers, active, sectors
        fii_dii: FII/DII flow data if available
        existing_holdings: List of symbols already in portfolio (to exclude)
        client: BedrockClient instance

    Returns:
        Parsed JSON response with stock_picks, etf_picks, avoid_list, etc.
    """
    user_prompt = _build_opportunity_prompt(market_data, fii_dii, existing_holdings)

    try:
        logger.info("Running opportunity analysis via Bedrock Claude...")
        response = client.invoke(SYSTEM_PROMPT, user_prompt)
        if not response:
            logger.error("Empty response from Bedrock for opportunity analysis")
            return {}
        logger.info("Opportunity analysis complete: %d stock picks, %d ETF picks",
                     len(response.get("stock_picks", [])), len(response.get("etf_picks", [])))
        return response
    except Exception as e:
        logger.error("Opportunity analysis failed: %s", e)
        return {}


def _build_opportunity_prompt(market_data: dict, fii_dii: dict | None, existing_holdings: list[str]) -> str:
    """Build detailed prompt with all real market data."""
    parts = []

    parts.append("CURRENT MARKET DATA (REAL-TIME FROM NSE):\n")

    # Sector indices — shows where money is flowing
    sectors = market_data.get("sectors", [])
    if sectors:
        parts.append("SECTOR PERFORMANCE (sorted worst to best):")
        for s in sectors:
            emoji = "🟢" if s.get("change_pct", 0) > 0 else "🔴"
            parts.append(f"  {emoji} {s['name']}: {s.get('last_price',0):,.0f} ({s.get('change_pct',0):+.2f}%)")
        parts.append("")

    # Top gainers — momentum stocks
    gainers = market_data.get("gainers", [])
    if gainers:
        parts.append(f"TOP GAINERS TODAY ({len(gainers)} stocks):")
        for g in gainers[:15]:
            parts.append(f"  {g['symbol']}: ₹{g.get('ltp',0):,.1f} ({g.get('change_pct',0):+.2f}%) Vol:{g.get('volume',0):,}")
        parts.append("")

    # Top losers — potential crash-buying candidates
    losers = market_data.get("losers", [])
    if losers:
        parts.append(f"TOP LOSERS TODAY ({len(losers)} stocks — potential crash buys):")
        for l in losers[:15]:
            parts.append(f"  {l['symbol']}: ₹{l.get('ltp',0):,.1f} ({l.get('change_pct',0):+.2f}%) Vol:{l.get('volume',0):,}")
        parts.append("")

    # Most active — institutional interest
    active = market_data.get("most_active", [])
    if active:
        parts.append(f"MOST ACTIVE BY VOLUME ({len(active)} stocks — institutional interest):")
        for a in active[:10]:
            parts.append(f"  {a['symbol']}: ₹{a.get('ltp',0):,.1f} ({a.get('change_pct',0):+.2f}%) Vol:{a.get('volume',0):,}")
        parts.append("")

    # FII/DII flows
    if fii_dii:
        parts.append("FII/DII FLOWS:")
        parts.append(f"  FII: Buy ₹{fii_dii.get('fii_buy',0):,.0f}Cr | Sell ₹{fii_dii.get('fii_sell',0):,.0f}Cr | Net ₹{fii_dii.get('fii_net',0):,.0f}Cr")
        parts.append(f"  DII: Buy ₹{fii_dii.get('dii_buy',0):,.0f}Cr | Sell ₹{fii_dii.get('dii_sell',0):,.0f}Cr | Net ₹{fii_dii.get('dii_net',0):,.0f}Cr")
        parts.append("")

    # Existing holdings to exclude
    if existing_holdings:
        parts.append(f"INVESTOR ALREADY HOLDS THESE ({len(existing_holdings)} stocks) — suggest NEW picks not in this list:")
        parts.append(f"  {', '.join(existing_holdings[:50])}")
        if len(existing_holdings) > 50:
            parts.append(f"  ... and {len(existing_holdings)-50} more")
        parts.append("")

    parts.append("""INSTRUCTIONS:
1. Recommend 20-25 STOCK picks across ALL market caps and ALL sectors:
   - 4-5 large-cap (Nifty 50/Next 50) — but NOT obvious names like Reliance, HDFC Bank, TCS, Infosys, DMart
   - 6-8 mid-cap (₹5,000-50,000 Cr market cap) — this is where real gems hide
   - 6-8 small-cap (₹500-5,000 Cr market cap) — high-growth undiscovered companies
   - 2-3 micro-cap (₹100-500 Cr) — speculative but high-reward picks
   - Cover at least 8 different sectors: IT, Pharma, Auto, BFSI, Chemicals, Defense, Infra, Consumer, Energy, Metals
2. IMPORTANT PRICE PREFERENCE: The investor strongly prefers stocks priced BELOW ₹1,000 per share.
   - At least 15 out of 25 picks should be under ₹1,000 per share
   - Stocks above ₹2,000 should only be included if they are exceptional quality
   - Avoid recommending stocks above ₹5,000 per share unless truly outstanding
3. Recommend 5-7 ETF picks (index + sectoral + gold/international + thematic)
4. IMPORTANT: Focus on HIDDEN GEMS — companies with strong fundamentals that most retail investors don't know about
   - Look for: ROCE >18%, ROE >15%, low debt, consistent growth, promoter buying
   - Avoid recommending well-known blue-chips everyone already owns
   - Find companies in niche sectors: specialty chemicals, defense ancillaries, API pharma, EMS, capital goods
5. For EACH pick, provide DETAILED rationale explaining:
   - WHY this stock specifically (not generic reasons)
   - Fundamental case: PE vs industry, ROCE, debt, growth numbers
   - Technical setup: support/resistance, 52W position, chart pattern
   - Catalyst: what will drive the stock up in next 3-12 months
6. Mark if the stock is ALREADY in investor's portfolio (check against the holdings list)
7. Provide realistic target prices and stop losses
8. Include an avoid list (5-8 stocks) with specific reasons
9. Give portfolio allocation advice for ₹5 lakh AND ₹10 lakh fresh capital""")

    return "\n".join(parts)
