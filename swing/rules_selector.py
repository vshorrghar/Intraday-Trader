"""
Swing selector — deterministic entry/SL/target + LLM-scored confidence (Hybrid).

PRINCIPLE: Python owns the risk math; the LLM only *scores* confidence.

Rules (deterministic, UNCHANGED — these decide prices and R:R):
  1. Stock near 20-DMA (within -5% to +2%) — buying the dip
  2. RSI(2) < 40 — oversold (bounce likely)
  3. Avg turnover >= 2 Cr — liquid enough to exit
  4. SL: 4% below entry (broker-held via Super Order)
  5. Target: 8% above entry (2:1 R:R)
  6. Max 8 entries per scan cycle
  7. Max 8 positions total

Confidence (NEW — Hybrid):
  After the deterministic filters select the survivors and compute their
  prices, a single Bedrock call scores each survivor's confidence 1-10 with a
  one-line reason. The LLM NEVER sets entry/SL/target — those stay fully
  deterministic, so the 2:1 R:R guarantee and broker-SL safety are untouched.
  If Bedrock is unavailable, confidence falls back to a scanner-score mapping
  so a Bedrock outage never zeroes out swing.
"""

import logging

from swing.models import SwingTradeSetup, SwingConfig

logger = logging.getLogger(__name__)

# Bedrock model proven working on the intraday path (keeps `temperature`-free
# BedrockClient contract). us.anthropic.claude-sonnet-4-6.
_LLM_REGION = "us-east-1"
_LLM_MODEL = "us.anthropic.claude-sonnet-4-6"


def _fallback_confidence(score: int) -> int:
    """Deterministic confidence from scanner score (used if LLM unavailable)."""
    if score >= 14:
        return 9
    if score >= 12:
        return 8
    if score >= 10:
        return 7
    if score >= 8:
        return 6
    return 5


def _llm_confidence_scores(survivors: list) -> dict:
    """Score survivor confidence 1-10 via one Bedrock call.

    Returns {symbol: {"confidence": int, "reason": str}}.
    On ANY failure returns {} so caller falls back to score-based confidence.
    The LLM sees read-only facts and only judges conviction — it does not pick
    prices, stops, or targets.
    """
    if not survivors:
        return {}
    try:
        from llm.bedrock_client import BedrockClient
    except Exception as e:  # noqa: BLE001
        logger.warning("confidence LLM: BedrockClient import failed (%s) — fallback", e)
        return {}

    lines = []
    for c in survivors:
        lines.append(
            f"- {c['symbol']}: score={c.get('score',0)}, "
            f"delta_from_20DMA={c.get('delta_from_20dma',0):.1f}%, "
            f"RSI2={c.get('rsi2',0):.0f}, ATR={c.get('atr_pct',0):.1f}%, "
            f"5d_return={c.get('last_5d_return',0):.1f}%, "
            f"turnover={c.get('avg_turnover_cr',0):.0f}Cr, "
            f"sector={c.get('sector','UNKNOWN')}"
        )
    facts = "\n".join(lines)

    system_prompt = (
        "You are a swing-trading analyst for Indian NSE equities. The strategy is a "
        "20-DMA pullback in uptrending stocks, held 5-15 days, LONG only. Entry, "
        "stop-loss and target are already fixed by rules — do NOT propose prices. "
        "Your ONLY job is to rate conviction 1-10 for each candidate based on the "
        "pullback quality (closeness to 20-DMA, oversold RSI, healthy ATR, not a "
        "falling knife, liquid, defensive sector preferred). Respond ONLY as JSON."
    )
    user_prompt = (
        "Rate each candidate's swing-entry conviction 1-10 (10=best pullback setup).\n"
        f"Candidates:\n{facts}\n\n"
        'Respond as JSON: {"scores": [{"symbol": "X", "confidence": 7, '
        '"reason": "one short sentence"}, ...]}'
    )

    try:
        client = BedrockClient(region=_LLM_REGION, model_id=_LLM_MODEL)
        resp = client.invoke(system_prompt, user_prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("confidence LLM: invoke failed (%s) — fallback", e)
        return {}

    out = {}
    for row in (resp.get("scores") or []):
        sym = str(row.get("symbol", "")).upper()
        try:
            conf = int(round(float(row.get("confidence", 0))))
        except (TypeError, ValueError):
            continue
        if sym and 1 <= conf <= 10:
            out[sym] = {"confidence": conf, "reason": str(row.get("reason", ""))[:120]}
    if out:
        logger.info("confidence LLM: scored %d/%d survivors", len(out), len(survivors))
    else:
        logger.warning("confidence LLM: empty/invalid response — fallback to score-based")
    return out


def select_swing_trades(
    candidates: list,
    config: SwingConfig,
    live_mode: bool = False,
) -> list[SwingTradeSetup]:
    """Deterministic pick + prices; LLM-scored confidence; min-confidence gate."""
    per_trade_max = config.swing_per_trade_max
    capital = config.swing_capital_limit
    max_entries_per_scan = 8  # raised 2->8 for diversification (2026-10-14)
    min_confidence = (
        config.swing_min_confidence_live if live_mode else config.swing_min_confidence
    )

    if not candidates:
        logger.info("selector: 0 candidates received")
        return []

    # ── Deterministic filters (UNCHANGED) ──
    filtered = [c for c in candidates if -5.0 <= c.get("delta_from_20dma", 99) <= 2.0]
    logger.info("selector: %d/%d pass 20-DMA [-5%%, +2%%]", len(filtered), len(candidates))

    filtered = [c for c in filtered if c.get("rsi2", 100) < 40]
    logger.info("selector: %d pass rsi2 < 40", len(filtered))

    filtered = [c for c in filtered if c.get("avg_turnover_cr", 0) >= 2.0]
    logger.info("selector: %d pass turnover >= 2 Cr", len(filtered))

    # Sort by RSI (most oversold first), take top N
    filtered.sort(key=lambda x: x.get("rsi2", 100))
    top = filtered[:max_entries_per_scan]
    logger.info("selector: taking top %d", len(top))

    # ── LLM confidence scoring on the shortlisted survivors (one call) ──
    llm_scores = _llm_confidence_scores(top)

    # ── Build trade setups (prices fully deterministic) ──
    trades = []
    for c in top:
        entry_price = c["latest_close"]
        sl_pct = 0.04  # 4% SL — FIXED (deterministic)
        target_pct = 0.08  # 8% target — 2:1 R:R (deterministic)

        stop_loss = round(entry_price * (1 - sl_pct), 2)
        target_price = round(entry_price * (1 + target_pct), 2)

        risk_per_share = entry_price - stop_loss
        if risk_per_share <= 0:
            continue

        risk_amount = capital * 0.01
        quantity = int(risk_amount / risk_per_share)
        max_qty = int(per_trade_max / entry_price) if entry_price > 0 else 0
        quantity = min(quantity, max_qty)
        if quantity <= 0:
            continue

        # Confidence: real LLM score if available, else score-based fallback
        sym = c["symbol"].upper()
        llm = llm_scores.get(sym)
        if llm:
            confidence = llm["confidence"]
            conf_src = "LLM"
            conf_reason = llm["reason"]
        else:
            confidence = _fallback_confidence(c.get("score", 0))
            conf_src = "fallback"
            conf_reason = ""

        # Confidence gate (now meaningful — real scores vary)
        if confidence < min_confidence:
            logger.info("selector: %s conf %d (%s) < min %d — skip",
                        sym, confidence, conf_src, min_confidence)
            continue

        rationale = (
            f"{c['symbol']}: RSI2={c.get('rsi2',0):.0f}, "
            f"delta={c.get('delta_from_20dma',0):.1f}%, "
            f"turnover={c.get('avg_turnover_cr',0):.0f}Cr, conf={confidence}({conf_src})"
        )
        if conf_reason:
            rationale += f" — {conf_reason}"

        trades.append(SwingTradeSetup(
            stock_name=c["symbol"],
            tradingsymbol=c["symbol"],
            nse_symbol=c["symbol"],
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss,
            quantity=quantity,
            confidence_score=confidence,
            rationale=rationale,
            holding_days_estimate=7,
            thesis_invalidation=f"Exit if below Rs.{stop_loss:.2f}",
            sector=c.get("sector", ""),
            strategy_type="PULLBACK_SIMPLE",
        ))

    logger.info("selector: %d final trades", len(trades))
    return trades
