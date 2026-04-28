"""Performance tracker and EOD report generator for the intraday auto-trader.

Generates JSON reports, calculates metrics (win rate, expectancy, drawdown),
and prints a beautiful console summary.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
REPORTS_DIR = "output/reports"


# ------------------------------------------------------------------
# Pure metric calculators (used by property tests)
# ------------------------------------------------------------------

def calc_performance_metrics(pnl_values: list[float]) -> dict:
    """Calculate performance metrics from a list of trade P&L values.

    Returns dict with: total_pnl, winning_trades, losing_trades,
    win_rate, avg_profit, avg_loss, expectancy, profit_factor.
    """
    if not pnl_values:
        return {
            "total_pnl": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "avg_profit": 0, "avg_loss": 0,
            "expectancy": 0, "profit_factor": 0,
        }

    total = len(pnl_values)
    winners = [p for p in pnl_values if p > 0]
    losers = [p for p in pnl_values if p < 0]

    win_count = len(winners)
    loss_count = len(losers)
    win_rate = (win_count / total * 100) if total > 0 else 0

    avg_profit = (sum(winners) / win_count) if win_count > 0 else 0
    avg_loss = (sum(losers) / loss_count) if loss_count > 0 else 0

    # Expectancy = avg_profit × win_rate/100 − |avg_loss| × (1 − win_rate/100)
    expectancy = avg_profit * (win_rate / 100) - abs(avg_loss) * (1 - win_rate / 100)

    # Profit factor = gross profits / |gross losses|
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    return {
        "total_pnl": round(sum(pnl_values), 2),
        "total_trades": total,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate": round(win_rate, 2),
        "avg_profit": round(avg_profit, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
    }


def calc_max_drawdown(daily_pnl: list[float]) -> float:
    """Calculate maximum peak-to-trough drawdown from daily P&L series.

    Returns 0 for empty or monotonically increasing series.
    """
    if not daily_pnl:
        return 0.0

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0

    for pnl in daily_pnl:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return round(max_dd, 2)


# ------------------------------------------------------------------
# Performance Tracker
# ------------------------------------------------------------------

class Performance_Tracker:
    """Generates EOD reports and tracks cumulative performance."""

    def __init__(self, db: Any = None, broker_name: str = "dhan", mode: str = "DRY_RUN") -> None:
        self.db = db
        self.broker_name = broker_name
        self.mode = mode

    def generate_eod_report(self, trades: list[dict], trade_date: str = "", report_prefix: str = "intraday") -> dict:
        """Generate end-of-day report and save to JSON file.

        Returns the report dict.
        """
        if not trade_date:
            trade_date = datetime.now(IST).strftime("%Y-%m-%d")

        pnl_values = [t.get("pnl", 0) or 0 for t in trades]
        metrics = calc_performance_metrics(pnl_values)

        # Strategy breakdown
        strategy_stats: dict[str, list[float]] = {}
        for t in trades:
            st = t.get("strategy_type", "UNKNOWN")
            strategy_stats.setdefault(st, []).append(t.get("pnl", 0) or 0)

        strategy_breakdown = {}
        for st, pnls in strategy_stats.items():
            strategy_breakdown[st] = calc_performance_metrics(pnls)

        # Cumulative stats from DB
        cumulative_pnl = 0.0
        overall_win_rate = metrics["win_rate"]
        max_drawdown = 0.0
        daily_pnl_history: list[dict] = []

        if self.db:
            try:
                cumulative_pnl = self.db.get_cumulative_pnl() + metrics["total_pnl"]
                # Get historical daily summaries for drawdown
                all_trades = self.db.get_trades_for_date("")  # empty = all
            except Exception:
                cumulative_pnl = metrics["total_pnl"]

        report = {
            "trade_date": trade_date,
            "mode": self.mode,
            "broker_name": self.broker_name,
            "generated_at": datetime.now(IST).isoformat(),
            "trades": [self._trade_to_report(t) for t in trades],
            "metrics": metrics,
            "strategy_breakdown": strategy_breakdown,
            "cumulative": {
                "total_pnl": round(cumulative_pnl, 2),
                "overall_win_rate": round(overall_win_rate, 2),
                "max_drawdown": round(max_drawdown, 2),
            },
        }

        # Save to file
        self._save_report(report, trade_date, report_prefix)

        # Update DB summary
        if self.db:
            self.db.upsert_daily_summary(
                trade_date=trade_date,
                total_trades=metrics["total_trades"],
                winning_trades=metrics["winning_trades"],
                losing_trades=metrics["losing_trades"],
                total_pnl=metrics["total_pnl"],
                total_realized_loss=abs(sum(p for p in pnl_values if p < 0)),
                max_drawdown=max_drawdown,
                broker_name=self.broker_name,
                mode=self.mode,
            )

        return report

    def print_summary(self, report: dict) -> None:
        """Print a beautiful console summary."""
        m = report["metrics"]
        total_pnl = m["total_pnl"]
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
        reset = "\033[0m"

        print()
        print("=" * 60)
        print(f"  📊 INTRADAY TRADING REPORT — {report['trade_date']}")
        mode_label = {"DRY_RUN": "🧪 DRY-RUN", "LIVE": "🔴 LIVE", "DEMO": "🎬 DEMO"}.get(report["mode"], report["mode"])
        print(f"  Mode: {mode_label}")
        print("=" * 60)
        print()

        # Trade details
        for t in report["trades"]:
            status_emoji = {
                "CLOSED": "🎯", "STOPPED_OUT": "🛑",
                "FORCE_EXITED": "⏰", "PARTIAL_BOOKED": "📊",
            }.get(t["status"], "⏳")
            t_pnl = t.get("pnl", 0) or 0
            pnl_str = f"\033[92m+₹{t_pnl:.0f}\033[0m" if t_pnl >= 0 else f"\033[91m-₹{abs(t_pnl):.0f}\033[0m"
            print(f"  {status_emoji} {t['tradingsymbol']:<12} "
                  f"Entry ₹{t['entry_price']:.2f} → Exit ₹{t.get('exit_price', 0):.2f}  "
                  f"Qty {t['quantity']}  P&L {pnl_str}  [{t['strategy_type']}]")

        print()
        print(f"  {pnl_emoji} Total P&L: {pnl_color}₹{total_pnl:+,.2f}{reset}")
        print(f"  📈 Win Rate: {m['win_rate']:.1f}% ({m['winning_trades']}W / {m['losing_trades']}L)")
        print(f"  💰 Avg Win: ₹{m['avg_profit']:.2f} | Avg Loss: ₹{m['avg_loss']:.2f}")
        print(f"  🎯 Expectancy: ₹{m['expectancy']:.2f}/trade")
        pf = m['profit_factor']
        pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else str(pf)
        print(f"  📊 Profit Factor: {pf_str}")
        print()

        # Strategy breakdown
        if report.get("strategy_breakdown"):
            print("  Strategy Breakdown:")
            for st, sm in report["strategy_breakdown"].items():
                print(f"    {st}: {sm['win_rate']:.0f}% WR, ₹{sm['total_pnl']:+,.0f} P&L")
            print()

        print("=" * 60)
        print()

    def _trade_to_report(self, trade: dict) -> dict:
        return {
            "tradingsymbol": trade.get("tradingsymbol", ""),
            "symbol": trade.get("symbol", ""),
            "entry_price": trade.get("entry_price", 0),
            "exit_price": trade.get("exit_price", 0),
            "target_price": trade.get("target_price", 0),
            "stop_loss_price": trade.get("stop_loss_price", 0),
            "quantity": trade.get("quantity", 0),
            "pnl": trade.get("pnl", 0),
            "status": trade.get("status", ""),
            "confidence_score": trade.get("confidence_score", 0),
            "strategy_type": trade.get("strategy_type", ""),
            "rationale": trade.get("rationale", ""),
        }

    def _save_report(self, report: dict, trade_date: str, report_prefix: str = "intraday") -> None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        path = os.path.join(REPORTS_DIR, f"{report_prefix}_{trade_date}.json")
        try:
            with open(path, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("EOD report saved to %s", path)
        except Exception:
            logger.error("Failed to save EOD report", exc_info=True)
