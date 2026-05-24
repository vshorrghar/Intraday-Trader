"""
Swing rules-based selector — deterministic replacement for LLM selector.

Picks swing trades from scanner candidates using pure mathematical rules.
No LLM calls. No Bedrock. No boto3. Same input = same output always.

Entry logic: 20-DMA pullback with RSI(2) oversold confirmation.
Position sizing: 1% risk per trade, SL at max(4%, 1.5×ATR), target at 2.5×SL.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from swing.models import SwingTradeSetup, SwingConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def select_swing_trades(
    candidates: list,
    config: SwingConfig,
    live_mode: bool = False,
) -> list[SwingTradeSetup]:
    """Select swing trades from scored candidates using deterministic rules.

    Pipeline:
        1. Filter by minimum score
        2. Filter by 20-DMA proximity (delta between -2% and +1%)
        3. Filter by RSI(2) < 30 (oversold)
        4. Filter by last_5d_return > -8% (not falling knife)
        5. Filter by avg_turnover >= 5 Cr (liquidity)
        6. Rank by score descending
        7. Take top N
        8. Compute entry/target/SL prices
        9. Filter by R:R >= 2.0
        10. Return SwingTradeSetup objects

    Args:
        candidates: list of dicts from scanner.scan_universe()
        config: SwingConfig with thresholds
        live_mode: if True, use swing_min_confidence_live threshold

    Returns:
        list of SwingTradeSetup objects ready for execution
    """
    min_score = config.swing_min_score
    min_confidence = config.swing_min_confidence_live if live_mode else config.swing_min_confidence
    max_positions = config.swing_max_open_positions
    per_trade_max = config.swing_per_trade_max

    if not candidates:
        logger.info("rules_selector: 0 candidates received — nothing to select")
        return []

    # Step 1: Filter by minimum score
    filtered = [c for c in candidates if c.get("score", 0) >= min_score]
    logger.info("rules_selector: %d/%d pass min_score=%d", len(filtered), len(candidates), min_score)

    # Step 2: Filter by 20-DMA proximity (-2% to +1%)
    filtered = [c for c in filtered if -2.0 <= c.get("delta_from_20dma", 99) <= 1.0]
    logger.info("rules_selector: %d pass delta_from_20dma filter [-2%%, +1%%]", len(filtered))

    # Step 3: Filter by RSI(2) < 30
    filtered = [c for c in filtered if c.get("rsi2", 100) < 30]
    logger.info("rules_selector: %d pass rsi2 < 30", len(filtered))

    # Step 4: Filter by last_5d_return > -8% (not falling knife)
    filtered = [c for c in filtered if c.get("last_5d_return", -99) > -8.0]
    logger.info("rules_selector: %d pass last_5d_return > -8%%", len(filtered))

    # Step 5: Filter by avg_turnover >= 5 Cr
    filtered = [c for c in filtered if c.get("avg_turnover_cr", 0) >= 5.0]
    logger.info("rules_selector: %d pass avg_turnover >= 5 Cr", len(filtered))

    # Step 6: Rank by score descending
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Step 7: Take top N
    top_candidates = filtered[:max_positions]
    logger.info("rules_selector: taking top %d of %d", len(top_candidates), len(filtered))

    # Step 8-9: Compute prices and filter by R:R
    trades = []
    for c in top_candidates:
        setup = _build_trade_setup(c, config, per_trade_max)
        if setup is None:
            continue
        # Check confidence threshold
        if setup.confidence_score < min_confidence:
            logger.debug("rules_selector: %s conf %d < min %d — skip",
                         c["symbol"], setup.confidence_score, min_confidence)
            continue
        trades.append(setup)

    logger.info("rules_selector: %d final trades selected", len(trades))
    return trades


def _build_trade_setup(candidate: dict, config: SwingConfig, per_trade_max: float) -> SwingTradeSetup | None:
    """Build a SwingTradeSetup from a scored candidate.

    Computes entry, SL, target prices deterministically.
    Returns None if R:R < 2.0.
    """
    symbol = candidate["symbol"]
    entry_price = candidate["latest_close"]
    atr_pct = candidate.get("atr_pct", 3.0)
    score = candidate.get("score", 0)
    delta = candidate.get("delta_from_20dma", 0)
    rsi2 = candidate.get("rsi2", 50)

    # SL calculation: max(4%, 1.5×ATR%), capped at 8%
    sl_pct = max(0.04, (atr_pct / 100) * 1.5)
    sl_pct = min(sl_pct, 0.08)
    stop_loss = round(entry_price * (1 - sl_pct), 2)

    # Target calculation: 2.5× SL distance, capped at 15%
    target_pct = sl_pct * 2.5
    target_pct = min(target_pct, 0.15)
    target_price = round(entry_price * (1 + target_pct), 2)

    # R:R check
    risk = entry_price - stop_loss
    reward = target_price - entry_price
    if risk <= 0:
        return None
    rr = round(reward / risk, 2)
    if rr < config.swing_min_rr:
        logger.debug("rules_selector: %s rr=%.2f < min %.1f — skip", symbol, rr, config.swing_min_rr)
        return None

    # Position sizing: risk 1% of capital
    risk_amount = config.swing_capital_limit * 0.01
    quantity = int(risk_amount / risk) if risk > 0 else 0
    # Cap by per_trade_max
    max_qty_by_capital = int(per_trade_max / entry_price) if entry_price > 0 else 0
    quantity = min(quantity, max_qty_by_capital)
    if quantity <= 0:
        return None

    # Confidence score (deterministic from score)
    confidence = _score_to_confidence(score)

    # Strategy type (deterministic)
    strategy_type = _determine_strategy_type(delta, rsi2, candidate.get("signals", {}))

    # Holding days estimate based on target distance
    holding_estimate = min(15, max(3, int(target_pct * 100)))

    # Rationale (deterministic string from signal values)
    rationale = (
        f"{symbol}: score={score}, delta_20dma={delta:.1f}%, RSI2={rsi2:.0f}, "
        f"ATR={atr_pct:.1f}%, sector={candidate.get('sector', 'UNKNOWN')}, "
        f"5d_ret={candidate.get('last_5d_return', 0):.1f}%, "
        f"SL={sl_pct*100:.1f}%, target={target_pct*100:.1f}%, RR={rr:.1f}"
    )

    # Thesis invalidation (deterministic)
    thesis_invalidation = f"Exit if price closes below Rs.{stop_loss:.2f} (SL) or 20-DMA slope turns negative"

    return SwingTradeSetup(
        stock_name=symbol,
        tradingsymbol=symbol,
        nse_symbol=symbol,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss,
        quantity=quantity,
        confidence_score=confidence,
        rationale=rationale,
        holding_days_estimate=holding_estimate,
        thesis_invalidation=thesis_invalidation,
        sector=candidate.get("sector", ""),
        transaction_type="BUY",
        strategy_type=strategy_type,
    )


def _score_to_confidence(score: int) -> int:
    """Convert scanner score to confidence (deterministic mapping).

    score >= 14: confidence 9
    score >= 12: confidence 8
    score >= 10: confidence 7
    score >= 8:  confidence 6
    """
    if score >= 14:
        return 9
    elif score >= 12:
        return 8
    elif score >= 10:
        return 7
    elif score >= 8:
        return 6
    return 5  # should not reach here due to min_score filter


def _determine_strategy_type(delta: float, rsi2: float, signals: dict) -> str:
    """Determine strategy type from signal values (deterministic).

    PULLBACK: price at or below 20-DMA (textbook pullback)
    REVERSAL: extremely oversold with reversal candle
    """
    reversal_signal = signals.get("reversal_candle", 0)

    if rsi2 < 5 and reversal_signal >= 2:
        return "REVERSAL"
    if delta <= 0:
        return "PULLBACK"
    if delta <= 1.0 and rsi2 < 15:
        return "PULLBACK"
    return "PULLBACK"


# ═══════════════════════════════════════════════════════════
# VALIDATION TEST
# ═══════════════════════════════════════════════════════════

def validate_rules_selector():
    """Self-test: verify rules_selector works correctly with mock data."""

    config = SwingConfig(
        swing_capital_limit=100000,
        swing_per_trade_max=10000,
        swing_max_open_positions=3,
        swing_min_score=8,
        swing_min_confidence=6,
        swing_min_confidence_live=8,
        swing_min_rr=2.0,
    )

    # Mock candidates (output format from scanner.score_swing_candidate)
    candidates = [
        {"symbol": "HDFCBANK", "tradingsymbol": "HDFCBANK", "score": 12,
         "latest_close": 1600, "dma_20": 1610, "rsi2": 8, "atr_pct": 2.5,
         "avg_turnover_cr": 50, "sector": "BANKING", "delta_from_20dma": -0.6,
         "last_5d_return": -3.0, "signals": {"reversal_candle": 1}},
        {"symbol": "INFY", "tradingsymbol": "INFY", "score": 10,
         "latest_close": 1400, "dma_20": 1410, "rsi2": 12, "atr_pct": 2.0,
         "avg_turnover_cr": 80, "sector": "IT", "delta_from_20dma": -0.7,
         "last_5d_return": -2.0, "signals": {"reversal_candle": 0}},
        {"symbol": "RELIANCE", "tradingsymbol": "RELIANCE", "score": 14,
         "latest_close": 2800, "dma_20": 2810, "rsi2": 5, "atr_pct": 1.8,
         "avg_turnover_cr": 200, "sector": "OIL_GAS", "delta_from_20dma": -0.4,
         "last_5d_return": -1.5, "signals": {"reversal_candle": 3}},
        # Should be filtered: score too low
        {"symbol": "LOWSCORE", "tradingsymbol": "LOWSCORE", "score": 5,
         "latest_close": 100, "dma_20": 102, "rsi2": 8, "atr_pct": 3.0,
         "avg_turnover_cr": 10, "sector": "MISC", "delta_from_20dma": -2.0,
         "last_5d_return": -1.0, "signals": {}},
        # Should be filtered: falling knife
        {"symbol": "KNIFE", "tradingsymbol": "KNIFE", "score": 11,
         "latest_close": 500, "dma_20": 510, "rsi2": 4, "atr_pct": 4.0,
         "avg_turnover_cr": 15, "sector": "METALS", "delta_from_20dma": -0.5,
         "last_5d_return": -12.0, "signals": {}},
    ]

    # Test 1: Normal selection
    trades = select_swing_trades(candidates, config, live_mode=False)
    assert isinstance(trades, list), "Must return list"
    assert len(trades) <= 3, f"Max 3 trades, got {len(trades)}"
    assert all(isinstance(t, SwingTradeSetup) for t in trades), "Must be SwingTradeSetup"

    # Test 2: All trades have R:R >= 2.0
    for t in trades:
        risk = t.entry_price - t.stop_loss_price
        reward = t.target_price - t.entry_price
        rr = reward / risk if risk > 0 else 0
        assert rr >= 2.0, f"{t.nse_symbol} rr={rr:.2f} < 2.0"

    # Test 3: All trades have score >= 8
    # (verified by the fact they passed the filter)
    assert "LOWSCORE" not in [t.nse_symbol for t in trades], "Low score should be filtered"
    assert "KNIFE" not in [t.nse_symbol for t in trades], "Falling knife should be filtered"

    # Test 4: Confidence mapping
    for t in trades:
        if t.nse_symbol == "RELIANCE":
            assert t.confidence_score == 9, f"Score 14 → conf 9, got {t.confidence_score}"
        elif t.nse_symbol == "HDFCBANK":
            assert t.confidence_score == 8, f"Score 12 → conf 8, got {t.confidence_score}"
        elif t.nse_symbol == "INFY":
            assert t.confidence_score == 7, f"Score 10 → conf 7, got {t.confidence_score}"

    # Test 5: Empty candidates
    empty_result = select_swing_trades([], config)
    assert empty_result == [], "Empty input must return empty list"

    # Test 6: All below min_score
    low_candidates = [{"symbol": "X", "score": 3, "latest_close": 100,
                       "dma_20": 101, "rsi2": 5, "atr_pct": 2, "avg_turnover_cr": 10,
                       "sector": "X", "delta_from_20dma": -0.5, "last_5d_return": -1,
                       "signals": {}}]
    low_result = select_swing_trades(low_candidates, config)
    assert low_result == [], "All below min_score must return empty"

    print("✅ All 6 validation tests PASSED")


if __name__ == "__main__":
    validate_rules_selector()
