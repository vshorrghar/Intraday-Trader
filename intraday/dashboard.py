"""Dashboard JSON API writer for the intraday auto-trader.

Writes ``dashboard/api/intraday_latest.json`` with today's trades,
P&L, and historical performance data for the dashboard frontend.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
DASHBOARD_API_DIR = "dashboard/api"
DASHBOARD_FILE = os.path.join(DASHBOARD_API_DIR, "intraday_latest.json")


def write_dashboard_json(
    trades: list[dict],
    config: Any = None,
    db: Any = None,
    mode: str = "DRY_RUN",
    broker: str = "dhan",
    session_active: bool = False,
) -> None:
    """Write the intraday dashboard JSON file.

    Parameters
    ----------
    trades:
        List of trade record dicts (from executor/monitor).
    config:
        IntraConfig instance.
    db:
        DBManager instance for historical data.
    mode:
        "DRY_RUN" or "LIVE".
    broker:
        Broker name.
    session_active:
        Whether the trading session is still active.
    """
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")

    # Today's data
    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    realized_loss = sum(abs(t.get("pnl", 0)) for t in trades if (t.get("pnl", 0) or 0) < 0)
    daily_loss_cap = config.daily_loss_limit if config else 2500
    loss_cap_pct = (realized_loss / daily_loss_cap * 100) if daily_loss_cap > 0 else 0

    trade_list = []
    for t in trades:
        trade_list.append({
            "tradingsymbol": t.get("tradingsymbol", ""),
            "entry_price": t.get("entry_price", 0),
            "current_price": t.get("current_price", t.get("entry_price", 0)),
            "target_price": t.get("target_price", 0),
            "stop_loss_price": t.get("stop_loss_price", 0),
            "quantity": t.get("quantity", 0),
            "pnl": t.get("pnl", 0),
            "status": t.get("status", ""),
            "strategy_type": t.get("strategy_type", ""),
            "confidence_score": t.get("confidence_score", 0),
        })

    # Historical data
    history = _build_history(db)

    data = {
        "updated_at": now.isoformat(),
        "mode": mode,
        "broker": broker,
        "session_active": session_active,
        "today": {
            "trades": trade_list,
            "total_pnl": round(total_pnl, 2),
            "realized_loss": round(realized_loss, 2),
            "daily_loss_cap": daily_loss_cap,
            "loss_cap_pct": round(loss_cap_pct, 1),
        },
        "history": history,
    }

    os.makedirs(DASHBOARD_API_DIR, exist_ok=True)
    try:
        with open(DASHBOARD_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Dashboard JSON updated: %s", DASHBOARD_FILE)
    except Exception:
        logger.error("Failed to write dashboard JSON", exc_info=True)


def _build_history(db: Any) -> dict:
    """Build historical performance data from DB."""
    if db is None:
        return {"daily_pnl": [], "cumulative_pnl": 0, "win_rate": 0, "total_days": 0}

    try:
        cumulative_pnl = db.get_cumulative_pnl()
        return {
            "daily_pnl": [],
            "cumulative_pnl": round(cumulative_pnl, 2),
            "win_rate": 0,
            "total_days": 0,
        }
    except Exception:
        return {"daily_pnl": [], "cumulative_pnl": 0, "win_rate": 0, "total_days": 0}
