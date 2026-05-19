"""
Swing selector — LLM-based final pick from scanner candidates.
Uses Claude Sonnet 4.5 via AWS Bedrock.
LONG ONLY for v0.1.

# TODO Week 3: Add half-Kelly position sizing alongside fixed 1%
# TODO Week 3: Add slippage modeling per stock liquidity tier
"""

import json
import logging
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config as BotoConfig

from swing.models import SwingTradeSetup, SwingConfig
from swing.sector_map import SECTOR_MAP

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def build_swing_prompt(candidates: list, config: SwingConfig, regime_info: dict = None) -> str:
    """Build LLM prompt for swing stock selection."""
    now = datetime.now(IST)
    regime_str = ""
    if regime_info:
        regime_str = f"""
Market Regime:
- VIX: {regime_info.get('vix', 'N/A')}
- Nifty vs 50-DMA: {regime_info.get('nifty_vs_50dma', 'N/A')}
- Nifty vs 200-DMA: {regime_info.get('nifty_vs_200dma', 'N/A')}
- Regime: {regime_info.get('regime_status', 'NORMAL')}
"""

    candidates_str = "\n".join([
        f"  {i+1}. {c['symbol']} | Score {c['score']} | Rs.{c['latest_close']:.2f} | "
        f"20-DMA Rs.{c['dma_20']:.2f} (delta {c['delta_from_20dma']:.1f}%) | "
        f"RSI(2) {c['rsi2']:.0f} | ATR {c['atr_pct']:.1f}% | "
        f"Sector: {c['sector']} | Turnover: Rs.{c['avg_turnover_cr']:.0f} Cr | "
        f"5d return: {c['last_5d_return']:.1f}%"
        for i, c in enumerate(candidates[:20])
    ])

    prompt = f"""You are a swing trading analyst for Indian NSE equities.
Strategy: 20-DMA pullback in uptrending stocks. LONG ONLY.
Hold period: 5-15 trading days.
Date: {now.strftime('%Y-%m-%d')}
{regime_str}
CANDIDATES (pre-scored by scanner, sorted by score):
{candidates_str}

YOUR TASK:
Select 1-3 best swing entries from the candidates above.

For EACH pick, provide:
1. symbol: NSE symbol
2. entry_price: suggested entry (at or near current close)
3. target_price: 5-10% above entry (realistic swing target)
4. stop_loss_price: 4-6% below entry (below recent swing low or 20-DMA)
5. confidence_score: 1-10 (7+ required for paper, 8+ for live)
6. holding_days_estimate: 5-15 expected days
7. strategy_type: "PULLBACK" (primary) or "BREAKOUT" or "REVERSAL"
8. rationale: 2-3 sentences explaining why this is a good swing entry
9. thesis_invalidation: what would prove this trade wrong (1 sentence)

RULES:
- LONG ONLY. No short selling.
- Target must be 5-15% above entry.
- Stop loss must be 4-8% below entry.
- R:R must be >= 2.0
- Prefer stocks near 20-DMA (pullback signal strongest)
- Prefer defensive sectors in uncertain regime
- Skip if no good setups exist (return empty picks array)
- Maximum 3 picks per day

RESPOND IN VALID JSON:
{{
  "picks": [
    {{
      "symbol": "SYMBOL",
      "entry_price": 0.0,
      "target_price": 0.0,
      "stop_loss_price": 0.0,
      "confidence_score": 7,
      "holding_days_estimate": 10,
      "strategy_type": "PULLBACK",
      "rationale": "...",
      "thesis_invalidation": "..."
    }}
  ],
  "market_view": "Brief 1-line market assessment",
  "skip_reason": null
}}

If no good setups, return: {{"picks": [], "market_view": "...", "skip_reason": "reason"}}
"""
    return prompt


def call_bedrock(prompt: str, region: str = "us-east-1") -> dict | None:
    """Call Claude Sonnet 4.5 via Bedrock."""
    try:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=BotoConfig(read_timeout=60, connect_timeout=10, retries={"max_attempts": 1})
        )
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        })
        response = client.invoke_model(
            modelId="us.anthropic.claude-sonnet-4-5-20250514",
            body=body,
            contentType="application/json",
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]

        # Parse JSON from response
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        return json.loads(text.strip())
    except Exception as e:
        logger.error("Bedrock call failed: %s", e)
        return None


def validate_swing_pick(pick: dict, config: SwingConfig, live_mode: bool = False) -> bool:
    """Validate a single LLM pick against swing rules."""
    entry = pick.get("entry_price", 0)
    target = pick.get("target_price", 0)
    sl = pick.get("stop_loss_price", 0)
    conf = pick.get("confidence_score", 0)
    hold = pick.get("holding_days_estimate", 0)
    thesis = pick.get("thesis_invalidation", "")

    if entry <= 0 or target <= 0 or sl <= 0:
        logger.warning("Invalid prices for %s", pick.get("symbol"))
        return False

    # Target must be 5-15% above entry
    target_pct = (target - entry) / entry * 100
    if target_pct < 5 or target_pct > 15:
        logger.warning("%s target %.1f%% outside 5-15%% range", pick.get("symbol"), target_pct)
        return False

    # SL must be 4-8% below entry
    sl_pct = (entry - sl) / entry * 100
    if sl_pct < 4 or sl_pct > 8:
        logger.warning("%s SL %.1f%% outside 4-8%% range", pick.get("symbol"), sl_pct)
        return False

    # R:R >= 2.0
    risk = entry - sl
    reward = target - entry
    rr = reward / risk if risk > 0 else 0
    if rr < config.swing_min_rr:
        logger.warning("%s R:R %.1f < min %.1f", pick.get("symbol"), rr, config.swing_min_rr)
        return False

    # Confidence threshold
    min_conf = config.swing_min_confidence_live if live_mode else config.swing_min_confidence
    if conf < min_conf:
        logger.warning("%s confidence %d < min %d", pick.get("symbol"), conf, min_conf)
        return False

    # Holding days 5-15
    if hold < 5 or hold > 15:
        logger.warning("%s holding_days %d outside 5-15", pick.get("symbol"), hold)
        return False

    # Thesis invalidation must be non-empty
    if not thesis or len(thesis) < 10:
        logger.warning("%s thesis_invalidation too short", pick.get("symbol"))
        return False

    # Direction: LONG only (target > entry > SL)
    if not (target > entry > sl):
        logger.warning("%s direction invalid: target=%.2f entry=%.2f sl=%.2f",
                       pick.get("symbol"), target, entry, sl)
        return False

    return True


def select_swing_trades(candidates: list, config: SwingConfig,
                        regime_info: dict = None, live_mode: bool = False) -> list:
    """
    Run LLM selection on scanner candidates.
    Returns list of validated SwingTradeSetup objects.
    """
    if not candidates:
        logger.info("No candidates for LLM selection")
        return []

    prompt = build_swing_prompt(candidates, config, regime_info)
    logger.info("Calling Bedrock for swing selection (%d candidates)", len(candidates))

    result = call_bedrock(prompt)
    if not result:
        logger.error("Bedrock returned no result")
        return []

    picks = result.get("picks", [])
    market_view = result.get("market_view", "")
    skip_reason = result.get("skip_reason")

    if skip_reason:
        logger.info("LLM skipped: %s", skip_reason)
        return []

    if market_view:
        logger.info("LLM market view: %s", market_view)

    validated = []
    for pick in picks:
        if not validate_swing_pick(pick, config, live_mode):
            continue

        symbol = pick["symbol"]
        sector = SECTOR_MAP.get(symbol, "UNKNOWN")

        setup = SwingTradeSetup(
            stock_name=symbol,
            tradingsymbol=symbol,
            nse_symbol=symbol,
            entry_price=pick["entry_price"],
            target_price=pick["target_price"],
            stop_loss_price=pick["stop_loss_price"],
            quantity=0,  # sized by risk_manager later
            confidence_score=pick["confidence_score"],
            rationale=pick["rationale"],
            holding_days_estimate=pick["holding_days_estimate"],
            thesis_invalidation=pick["thesis_invalidation"],
            sector=sector,
            strategy_type=pick.get("strategy_type", "PULLBACK"),
        )
        validated.append(setup)
        logger.info("Pick VALID: %s @ Rs.%.2f -> Rs.%.2f (SL Rs.%.2f, R:R %.1f, conf %d) [%s]",
                    symbol, setup.entry_price, setup.target_price, setup.stop_loss_price,
                    (setup.target_price - setup.entry_price) / (setup.entry_price - setup.stop_loss_price),
                    setup.confidence_score, setup.strategy_type)

    logger.info("LLM selection complete: %d valid trade(s)", len(validated))
    return validated
