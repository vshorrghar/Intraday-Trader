"""Dashboard JSON API writer for the intraday auto-trader.

Writes ``dashboard/api/intraday_latest.json`` with today's trades,
P&L, and historical performance data for the dashboard frontend.

MERGE BEHAVIOR: If the dashboard file already exists for today, new trades
are merged with existing ones (deduped by tradingsymbol) so that morning
and midday runs combine correctly instead of overwriting each other.
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
    api_dir: str | None = None,
) -> None:
    """Write the intraday dashboard JSON file.

    If the file already exists and was updated today, new trades are MERGED
    with existing trades (deduped by tradingsymbol, newer status wins).
    This ensures morning + midday runs combine correctly.

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
    api_dir:
        Override dashboard API directory (for multi-profile support).
    """
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")

    # Use profile-specific directory if provided
    output_dir = api_dir or DASHBOARD_API_DIR
    output_file = os.path.join(output_dir, "intraday_latest.json")

    # ── Merge with existing trades from earlier runs today ──
    existing_trades = _load_existing_trades(today, output_file)
    merged_trades = _merge_trades(existing_trades, trades)

    # Today's data (computed from merged trades)
    total_pnl = sum(t.get("pnl", 0) or 0 for t in merged_trades)
    realized_loss = sum(abs(t.get("pnl", 0)) for t in merged_trades if (t.get("pnl", 0) or 0) < 0)
    daily_loss_cap = config.daily_loss_limit if config else 2500
    loss_cap_pct = (realized_loss / daily_loss_cap * 100) if daily_loss_cap > 0 else 0

    trade_list = []
    for t in merged_trades:
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

    os.makedirs(output_dir, exist_ok=True)
    try:
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(
            "Dashboard JSON updated: %s (%d trades, ₹%.2f P&L)",
            output_file, len(trade_list), total_pnl,
        )
    except Exception:
        logger.error("Failed to write dashboard JSON", exc_info=True)

    # Write separate history.json for dashboard JS
    try:
        history_file = os.path.join(output_dir, "history.json")
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2, default=str)
    except Exception:
        logger.error("Failed to write history JSON", exc_info=True)


def _load_existing_trades(today: str, dashboard_file: str = DASHBOARD_FILE) -> list[dict]:
    """Load existing trades from today's dashboard file (if any).

    Returns an empty list if the file doesn't exist, is from a different
    day, or can't be parsed.
    """
    if not os.path.exists(dashboard_file):
        return []
    try:
        with open(dashboard_file) as f:
            data = json.load(f)
        # Only merge if the file is from today
        updated_at = data.get("updated_at", "")
        if today not in updated_at:
            logger.info("Dashboard file is from a previous day — starting fresh")
            return []
        return data.get("today", {}).get("trades", [])
    except Exception:
        logger.warning("Could not load existing dashboard trades", exc_info=True)
        return []


def _merge_trades(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge existing and new trades, deduplicating by tradingsymbol.

    If the same tradingsymbol appears in both lists, the newer entry wins
    (it has updated status/pnl from monitoring). New trades not in existing
    are appended.
    """
    if not existing:
        return new
    if not new:
        return existing

    # Index existing trades by symbol
    merged: dict[str, dict] = {}
    for t in existing:
        sym = t.get("tradingsymbol", "")
        if sym:
            merged[sym] = t

    # New trades overwrite existing (newer status) or add new ones
    for t in new:
        sym = t.get("tradingsymbol", "")
        if sym:
            merged[sym] = t  # newer data wins

    result = list(merged.values())
    if len(result) > len(new):
        logger.info(
            "Merged %d existing + %d new trades → %d combined",
            len(existing), len(new), len(result),
        )
    return result


def _build_history(db: Any) -> dict:
    """Build historical performance data from DB."""
    if db is None:
        return {"days": [], "cumulative_pnl": 0, "win_rate": 0, "total_days": 0}

    try:
        cumulative_pnl = db.get_cumulative_pnl()

        # Pull daily P&L history for chart
        daily_pnl = []
        try:
            cursor = db.conn.cursor()
            cursor.execute(
                """SELECT trade_date,
                          COALESCE(total_pnl, 0) as pnl,
                          COALESCE(total_trades, 0) as trades,
                          COALESCE(winning_trades, 0) as winners,
                          COALESCE(losing_trades, 0) as losers
                   FROM intraday_daily_summary
                   WHERE total_trades > 0
                   ORDER BY trade_date ASC"""
            )
            rows = cursor.fetchall()
            total_winners = 0
            total_losers = 0
            for row in rows:
                daily_pnl.append({
                    "date": row["trade_date"],
                    "pnl": round(float(row["pnl"]), 2),
                    "trades": int(row["trades"]),
                    "winners": int(row["winners"]),
                    "losers": int(row["losers"]),
                })
                total_winners += int(row["winners"])
                total_losers += int(row["losers"])

            total_trades = total_winners + total_losers
            win_rate = round(total_winners / total_trades * 100, 1) if total_trades > 0 else 0
        except Exception:
            win_rate = 0
            total_trades = 0

        return {
            "days": daily_pnl,
            "cumulative_pnl": round(cumulative_pnl, 2),
            "win_rate": win_rate,
            "total_days": len(daily_pnl),
        }
    except Exception:
        return {"days": [], "cumulative_pnl": 0, "win_rate": 0, "total_days": 0}
