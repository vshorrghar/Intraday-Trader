"""Dashboard JSON API writer for the F&O auto-trader.

Writes ``dashboard/api/fno_latest.json`` with today's strategies,
P&L, Greeks, and historical performance data for the dashboard frontend.
Generates demo data on first run so the dashboard shows something immediately.
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
DASHBOARD_FILE = os.path.join(DASHBOARD_API_DIR, "fno_latest.json")


def write_fno_dashboard_json(
    strategies: list[dict] | None = None,
    config: Any = None,
    db: Any = None,
    mode: str = "PAPER",
    broker: str = "dhan",
    session_active: bool = False,
) -> None:
    """Write the F&O dashboard JSON file.

    Parameters
    ----------
    strategies:
        List of strategy record dicts (from executor/monitor).
        If None or empty, demo data is generated.
    config:
        FnO_Config instance.
    db:
        DBManager instance for historical data.
    mode:
        "PAPER" or "LIVE".
    broker:
        Broker name.
    session_active:
        Whether the trading session is still active.
    """
    now = datetime.now(IST)

    if not strategies:
        strategies = _generate_demo_strategies(now)

    total_pnl = sum(s.get("unrealized_pnl", 0) or 0 for s in strategies)
    realized_loss = sum(
        abs(s.get("unrealized_pnl", 0))
        for s in strategies
        if (s.get("unrealized_pnl", 0) or 0) < 0
    )
    daily_loss_cap = config.daily_loss_limit if config else 5000
    loss_cap_pct = (realized_loss / daily_loss_cap * 100) if daily_loss_cap > 0 else 0
    paper_capital = config.paper_capital if config else 500_000

    # Aggregate net Greeks
    net_greeks = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
    for s in strategies:
        ng = s.get("net_greeks", {})
        for g in net_greeks:
            net_greeks[g] += ng.get(g, 0)
    net_greeks = {k: round(v, 2) for k, v in net_greeks.items()}

    strategy_list = []
    for s in strategies:
        strategy_list.append({
            "strategy_type": s.get("strategy_type", ""),
            "index": s.get("index", ""),
            "legs_summary": s.get("legs_summary", ""),
            "entry_premium": s.get("entry_premium", 0),
            "current_premium": s.get("current_premium", 0),
            "unrealized_pnl": s.get("unrealized_pnl", 0),
            "status": s.get("status", ""),
            "confluence_score": s.get("confluence_score", 0),
            "net_greeks": s.get("net_greeks", {}),
        })

    history = _build_fno_history(db)

    data = {
        "updated_at": now.isoformat(),
        "mode": mode,
        "broker": broker,
        "session_active": session_active,
        "paper_capital_remaining": round(paper_capital - abs(total_pnl), 2),
        "today": {
            "strategies": strategy_list,
            "total_pnl": round(total_pnl, 2),
            "realized_loss": round(realized_loss, 2),
            "daily_loss_cap": daily_loss_cap,
            "loss_cap_pct": round(loss_cap_pct, 1),
            "net_greeks": net_greeks,
        },
        "history": history,
    }

    os.makedirs(DASHBOARD_API_DIR, exist_ok=True)
    try:
        with open(DASHBOARD_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("F&O Dashboard JSON updated: %s", DASHBOARD_FILE)
    except Exception:
        logger.error("Failed to write F&O dashboard JSON", exc_info=True)


def _build_fno_history(db: Any) -> dict:
    """Build historical F&O performance data from DB.

    Uses realized_pnl from closed strategies. Filters out obviously
    erroneous entries (e.g. single-day P&L > paper_capital) that may
    have been recorded during early development/testing.
    """
    if db is None:
        return _demo_history()
    try:
        # Pull daily P&L from fno_strategies table grouped by date
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT trade_date,
                      SUM(COALESCE(realized_pnl, 0)) as daily_pnl,
                      COUNT(*) as num_strategies,
                      SUM(CASE WHEN COALESCE(realized_pnl, 0) > 0 THEN 1 ELSE 0 END) as winners,
                      SUM(CASE WHEN COALESCE(realized_pnl, 0) < 0 THEN 1 ELSE 0 END) as losers
               FROM fno_strategies
               WHERE status IN ('CLOSED', 'FORCE_EXITED', 'STOPPED_OUT', 'EXPIRED', 'PARTIAL_BOOKED')
               GROUP BY trade_date
               ORDER BY trade_date ASC"""
        )
        rows = cursor.fetchall()

        daily_pnl = []
        total_winners = 0
        total_losers = 0
        cumulative_pnl = 0.0

        for row in rows:
            day_pnl = round(float(row["daily_pnl"]), 2)
            num_strats = int(row["num_strategies"])

            # Sanity check: flag days where P&L per strategy is unreasonably high
            # (> ₹25,000 per strategy suggests a data bug from early development)
            avg_pnl_per_strat = abs(day_pnl) / max(num_strats, 1)
            if avg_pnl_per_strat > 25000:
                logger.warning(
                    "FnO history: skipping %s — avg P&L ₹%.0f/strategy looks like a data bug",
                    row["trade_date"], avg_pnl_per_strat,
                )
                continue

            cumulative_pnl += day_pnl
            daily_pnl.append({
                "date": row["trade_date"],
                "pnl": day_pnl,
                "strategies": num_strats,
                "winners": int(row["winners"]),
                "losers": int(row["losers"]),
            })
            total_winners += int(row["winners"])
            total_losers += int(row["losers"])

        # Strategy type breakdown (also excluding buggy entries)
        strategy_breakdown: dict[str, dict] = {}
        cursor.execute(
            """SELECT strategy_type,
                      COUNT(*) as count,
                      SUM(CASE WHEN COALESCE(realized_pnl, 0) > 0 THEN 1 ELSE 0 END) as wins,
                      SUM(COALESCE(realized_pnl, 0)) as total_pnl
               FROM fno_strategies
               WHERE status IN ('CLOSED', 'FORCE_EXITED', 'STOPPED_OUT', 'EXPIRED', 'PARTIAL_BOOKED')
                 AND ABS(COALESCE(realized_pnl, 0)) < 50000
               GROUP BY strategy_type"""
        )
        for row in cursor.fetchall():
            cnt = int(row["count"])
            wins = int(row["wins"])
            strategy_breakdown[row["strategy_type"]] = {
                "count": cnt,
                "win_rate": round(wins / cnt * 100, 1) if cnt > 0 else 0,
                "total_pnl": round(float(row["total_pnl"]), 2),
            }

        total_trades = total_winners + total_losers
        win_rate = round(total_winners / total_trades * 100, 1) if total_trades > 0 else 0

        return {
            "daily_pnl": daily_pnl,
            "cumulative_pnl": round(cumulative_pnl, 2),
            "win_rate": win_rate,
            "total_days": len(daily_pnl),
            "total_trades": total_trades,
            "total_winners": total_winners,
            "total_losers": total_losers,
            "strategy_breakdown": strategy_breakdown,
        }
    except Exception:
        logger.error("Failed to build F&O history", exc_info=True)
        return _demo_history()


def _demo_history() -> dict:
    """Return demo historical data for first-run display."""
    now = datetime.now(IST)
    return {
        "daily_pnl": [
            {"date": (now - timedelta(days=2)).strftime("%Y-%m-%d"), "pnl": 2200},
            {"date": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "pnl": -800},
        ],
        "cumulative_pnl": 12500.0,
        "win_rate": 68.5,
        "total_days": 15,
        "strategy_breakdown": {
            "IRON_CONDOR": {"count": 8, "win_rate": 75.0, "total_pnl": 8500},
            "SHORT_STRANGLE": {"count": 5, "win_rate": 60.0, "total_pnl": 3200},
            "BULL_PUT_SPREAD": {"count": 2, "win_rate": 50.0, "total_pnl": 800},
        },
    }


def _generate_demo_strategies(now: datetime) -> list[dict]:
    """Generate 2-3 sample paper trading strategies for demo display."""
    today = now.strftime("%Y-%m-%d")
    return [
        {
            "strategy_type": "IRON_CONDOR",
            "index": "NIFTY",
            "legs_summary": "Sell 24800CE + Buy 24900CE + Sell 24200PE + Buy 24100PE",
            "entry_premium": 95.50,
            "current_premium": 72.30,
            "unrealized_pnl": 580.0,
            "status": "OPEN",
            "confluence_score": 78,
            "net_greeks": {"delta": -2.5, "gamma": -0.8, "theta": 45.2, "vega": -12.3},
        },
        {
            "strategy_type": "BULL_PUT_SPREAD",
            "index": "BANKNIFTY",
            "legs_summary": "Sell 51500PE + Buy 51300PE",
            "entry_premium": 65.00,
            "current_premium": 42.10,
            "unrealized_pnl": 1145.0,
            "status": "OPEN",
            "confluence_score": 72,
            "net_greeks": {"delta": 3.1, "gamma": -0.4, "theta": 28.5, "vega": -8.1},
        },
        {
            "strategy_type": "SHORT_STRANGLE",
            "index": "NIFTY",
            "legs_summary": "Sell 24900CE + Sell 24100PE",
            "entry_premium": 155.00,
            "current_premium": 168.20,
            "unrealized_pnl": -330.0,
            "status": "OPEN",
            "confluence_score": 81,
            "net_greeks": {"delta": -5.2, "gamma": -1.2, "theta": 62.0, "vega": -18.5},
        },
    ]
