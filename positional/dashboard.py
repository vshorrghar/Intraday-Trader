"""Positional trading dashboard JSON writer."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


def write_positional_dashboard(db, config=None, dashboard_dir: str = "dashboard") -> None:
    """Write positional positions to dashboard JSON for the web UI."""
    os.makedirs(os.path.join(dashboard_dir, "api"), exist_ok=True)
    output_path = os.path.join(dashboard_dir, "api", "positional_latest.json")

    all_positions = db.get_positional_positions()
    open_pos = [p for p in all_positions if p.status == "OPEN"]
    closed_pos = [p for p in all_positions if p.status != "OPEN"]

    total_realized = sum(p.pnl for p in closed_pos)
    total_unrealized = sum(
        (p.current_price - p.entry_price) * p.quantity
        for p in open_pos if p.current_price > 0
    )

    # For positions without live prices yet, show entry value as placeholder
    for p in open_pos:
        if p.current_price <= 0:
            p.current_price = p.entry_price

    data = {
        "updated_at": datetime.now(IST).isoformat(),
        "mode": "DRY_RUN",
        "capital": 25000,
        "open_positions": [
            {
                "symbol": p.nse_symbol,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "target_price": p.target_price,
                "stop_loss_price": p.stop_loss_price,
                "quantity": p.quantity,
                "status": p.status,
                "strategy_type": p.strategy_type,
                "confidence_score": p.confidence_score,
                "entry_date": p.entry_date,
                "weeks_held": p.weeks_held,
                "sector": p.sector,
                "market_cap": p.market_cap,
                "unrealized_pnl": round((p.current_price - p.entry_price) * p.quantity, 2) if p.current_price > 0 else 0,
                "change_pct": round((p.current_price - p.entry_price) / p.entry_price * 100, 2) if p.current_price > 0 and p.entry_price > 0 else 0,
            }
            for p in open_pos
        ],
        "closed_positions": [
            {
                "symbol": p.nse_symbol,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "quantity": p.quantity,
                "pnl": p.pnl,
                "status": p.status,
                "strategy_type": p.strategy_type,
                "entry_date": p.entry_date,
                "exit_date": p.exit_date,
                "weeks_held": p.weeks_held,
                "sector": p.sector,
            }
            for p in closed_pos
        ],
        "summary": {
            "total_open": len(open_pos),
            "total_closed": len(closed_pos),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(total_realized + total_unrealized, 2),
            "win_rate": round(
                sum(1 for p in closed_pos if p.pnl > 0) / len(closed_pos) * 100, 1
            ) if closed_pos else 0,
        },
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    logger.info("Positional dashboard updated: %s", output_path)
