#!/usr/bin/env python3
"""Update cumulative P&L history JSON from daily reports.

Reads all daily report files and builds a history JSON that the dashboard uses
to show P&L across all trading days.

Run after each trading day (added to sync_dashboard.sh).
"""

import json
import os
import glob
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
REPORTS_DIR = "output/reports"
DASHBOARD_DIR = "dashboard/api"


def build_history():
    os.makedirs(DASHBOARD_DIR, exist_ok=True)

    history = {
        "updated_at": datetime.now(IST).isoformat(),
        "intraday": {"daily": [], "cumulative_pnl": 0, "total_trades": 0, "winners": 0, "losers": 0},
        "fno": {"daily": [], "cumulative_pnl": 0, "total_trades": 0, "winners": 0, "losers": 0},
        "swing": {"daily": [], "cumulative_pnl": 0, "total_trades": 0, "winners": 0, "losers": 0},
        "positional": {"daily": [], "cumulative_pnl": 0, "total_trades": 0, "winners": 0, "losers": 0},
        "grand_total": 0,
    }

    # Intraday reports
    for f in sorted(glob.glob(f"{REPORTS_DIR}/intraday_*.json")):
        if "demo" in f:
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            date = data.get("trade_date", os.path.basename(f).replace("intraday_", "").replace(".json", ""))
            # Sum P&L from individual trades (total_pnl not always at top level)
            trades = data.get("trades", [])
            pnl = float(data.get("total_pnl", 0))
            if pnl == 0 and trades:
                pnl = sum(float(t.get("pnl", 0)) for t in trades)
            wins = sum(1 for t in trades if float(t.get("pnl", 0)) > 0)
            losses = sum(1 for t in trades if float(t.get("pnl", 0)) < 0)
            total_trades = len(trades)
            history["intraday"]["daily"].append({"date": date, "pnl": round(pnl, 2), "trades": total_trades, "winners": wins, "losers": losses})
            history["intraday"]["cumulative_pnl"] += pnl
            history["intraday"]["total_trades"] += total_trades
            history["intraday"]["winners"] += wins
            history["intraday"]["losers"] += losses
        except Exception:
            pass

    # FnO reports
    for f in sorted(glob.glob(f"{REPORTS_DIR}/fno_*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            date = data.get("trade_date", os.path.basename(f).replace("fno_", "").replace(".json", ""))
            pnl = float(data.get("total_pnl", 0))
            strategies = int(data.get("total_strategies", 0))
            wins = int(data.get("winning_strategies", data.get("winners", 0)))
            losses = int(data.get("losing_strategies", data.get("losers", 0)))
            history["fno"]["daily"].append({"date": date, "pnl": round(pnl, 2), "strategies": strategies, "winners": wins, "losers": losses})
            history["fno"]["cumulative_pnl"] += pnl
            history["fno"]["total_trades"] += strategies
            history["fno"]["winners"] += wins
            history["fno"]["losers"] += losses
        except Exception:
            pass

    history["grand_total"] = (
        history["intraday"]["cumulative_pnl"]
        + history["fno"]["cumulative_pnl"]
        + history["swing"]["cumulative_pnl"]
        + history["positional"]["cumulative_pnl"]
    )

    # Calculate win rates
    for key in ["intraday", "fno", "swing", "positional"]:
        total = history[key]["winners"] + history[key]["losers"]
        history[key]["win_rate"] = round(history[key]["winners"] / total * 100, 1) if total > 0 else 0

    output_path = os.path.join(DASHBOARD_DIR, "history.json")
    with open(output_path, "w") as fh:
        json.dump(history, fh, indent=2, default=str)

    print(f"History updated: {output_path}")
    print(f"  Intraday: ₹{history['intraday']['cumulative_pnl']:+,.2f} ({len(history['intraday']['daily'])} days)")
    print(f"  FnO: ₹{history['fno']['cumulative_pnl']:+,.2f} ({len(history['fno']['daily'])} days)")
    print(f"  Grand Total: ₹{history['grand_total']:+,.2f}")


if __name__ == "__main__":
    build_history()
