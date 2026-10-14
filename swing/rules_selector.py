"""
Swing rules selector — SIMPLE version. Trades every day.

PRINCIPLE: Trade first, optimize later. A system with 0 trades has 0 edge.

Rules (and ONLY these rules):
  1. Stock near 20-DMA (within -5% to +2%) — buying the dip
  2. RSI(2) < 40 — oversold (bounce likely)
  3. Avg turnover >= 2 Cr — liquid enough to exit
  4. SL: 4% below entry (broker-held via Super Order)
  5. Target: 8% above entry (2:1 R:R)
  6. Max 2 entries per scan cycle
  7. Max 8 positions total

NO regime filter. NO Stage 2. NO VCP. NO relative strength.
NO confluence. NO IVP. NO breadth gates.

Those are for LATER once we have 30+ trades of DATA.
"""

import logging
from swing.models import SwingTradeSetup, SwingConfig

logger = logging.getLogger(__name__)


def select_swing_trades(
    candidates: list,
    config: SwingConfig,
    live_mode: bool = False,
) -> list[SwingTradeSetup]:
    """Select swing trades. SIMPLE: near 20-DMA + RSI oversold = BUY."""
    per_trade_max = config.swing_per_trade_max
    capital = config.swing_capital_limit
    max_entries_per_scan = 2  # Max 2 new entries per scan cycle

    if not candidates:
        logger.info("selector: 0 candidates received")
        return []

    # ONLY 3 FILTERS:
    # 1. Near 20-DMA (-5% to +2%)
    filtered = [c for c in candidates if -5.0 <= c.get("delta_from_20dma", 99) <= 2.0]
    logger.info("selector: %d/%d pass 20-DMA [-5%%, +2%%]", len(filtered), len(candidates))

    # 2. RSI(2) < 40 (oversold)
    filtered = [c for c in filtered if c.get("rsi2", 100) < 40]
    logger.info("selector: %d pass rsi2 < 40", len(filtered))

    # 3. Turnover >= 2 Cr
    filtered = [c for c in filtered if c.get("avg_turnover_cr", 0) >= 2.0]
    logger.info("selector: %d pass turnover >= 2 Cr", len(filtered))

    # Sort by RSI (most oversold first)
    filtered.sort(key=lambda x: x.get("rsi2", 100))

    # Take top N
    top = filtered[:max_entries_per_scan]
    logger.info("selector: taking top %d", len(top))

    # Build trade setups
    trades = []
    for c in top:
        entry_price = c["latest_close"]
        sl_pct = 0.04  # 4% SL — FIXED
        target_pct = 0.08  # 8% target — 2:1 R:R

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

        trades.append(SwingTradeSetup(
            stock_name=c["symbol"],
            tradingsymbol=c["symbol"],
            nse_symbol=c["symbol"],
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss,
            quantity=quantity,
            confidence_score=7,
            rationale=f"{c['symbol']}: RSI2={c.get('rsi2',0):.0f}, delta={c.get('delta_from_20dma',0):.1f}%, turnover={c.get('avg_turnover_cr',0):.0f}Cr",
            holding_days_estimate=7,
            thesis_invalidation=f"Exit if below Rs.{stop_loss:.2f}",
            sector=c.get("sector", ""),
            strategy_type="PULLBACK_SIMPLE",
        ))

    logger.info("selector: %d final trades", len(trades))
    return trades
