"""F&O Reporter — EOD performance reports and strategy analytics.

Generates JSON reports at output/reports/fno_YYYY-MM-DD.json with
strategy-level metrics, cumulative P&L, max drawdown, expectancy,
and theta decay tracking.  Upserts fno_daily_summary in DB and
updates dashboard JSON.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
REPORTS_DIR = "output/reports"


class FnO_Reporter:
    """Generates EOD F&O performance reports."""

    def __init__(self, config: FnO_Config, db: DBManager) -> None:
        self.config = config
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_eod_report(
        self,
        trade_date: str | None = None,
    ) -> dict:
        """Generate the end-of-day JSON report.

        Parameters
        ----------
        trade_date : str | None
            Date in YYYY-MM-DD format. Defaults to today.

        Returns
        -------
        dict
            The complete report data.
        """
        today = trade_date or datetime.now(IST).strftime("%Y-%m-%d")

        # Fetch data
        strategies = self.db.get_fno_strategies_for_date(today)
        trades = self.db.get_fno_trades_for_date(today)

        # Compute metrics
        total_pnl = sum(float(s.get("realized_pnl", 0) or 0) for s in strategies)
        winning = [s for s in strategies if (s.get("realized_pnl") or 0) > 0]
        losing = [s for s in strategies if (s.get("realized_pnl") or 0) < 0]
        total_count = len(strategies)
        win_count = len(winning)
        loss_count = len(losing)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0

        # Strategy-level metrics by type
        strategy_metrics = self._compute_strategy_metrics(strategies)

        # Cumulative P&L
        cumulative_pnl = self.db.get_fno_cumulative_pnl()

        # Max drawdown
        max_drawdown = self._compute_max_drawdown()

        # Expectancy
        avg_profit = (
            sum(float(s.get("realized_pnl", 0)) for s in winning) / win_count
            if win_count > 0 else 0
        )
        avg_loss = (
            sum(float(s.get("realized_pnl", 0)) for s in losing) / loss_count
            if loss_count > 0 else 0
        )
        expectancy = avg_profit * (win_rate / 100) - abs(avg_loss) * (1 - win_rate / 100)

        # Theta decay P&L
        theta_pnl = self._compute_theta_pnl(strategies)

        # Build report
        report = {
            "trade_date": today,
            "mode": self.config.mode.upper(),
            "broker": self.config.broker,
            "total_strategies": total_count,
            "winning_strategies": win_count,
            "losing_strategies": loss_count,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "max_drawdown": round(max_drawdown, 2),
            "expectancy": round(expectancy, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "theta_decay_pnl": round(theta_pnl, 2),
            "strategy_metrics": strategy_metrics,
            "strategies": [
                {
                    "id": s.get("id"),
                    "strategy_type": s.get("strategy_type"),
                    "index_name": s.get("index_name"),
                    "legs_json": s.get("legs_json"),
                    "net_premium": s.get("net_premium"),
                    "max_profit": s.get("max_profit"),
                    "max_loss": s.get("max_loss"),
                    "status": s.get("status"),
                    "entry_time": s.get("entry_time"),
                    "exit_time": s.get("exit_time"),
                    "realized_pnl": s.get("realized_pnl"),
                    "confidence_score": s.get("confidence_score"),
                    "confluence_score": s.get("confluence_score"),
                }
                for s in strategies
            ],
            "trades": [
                {
                    "id": t.get("id"),
                    "tradingsymbol": t.get("tradingsymbol"),
                    "action": t.get("action"),
                    "quantity": t.get("quantity"),
                    "entry_price": t.get("entry_price"),
                    "exit_price": t.get("exit_price"),
                    "pnl": t.get("pnl"),
                    "status": t.get("status"),
                }
                for t in trades
            ],
        }

        # Write report file (overwrite if exists)
        self._write_report(today, report)

        # Upsert daily summary in DB
        self.db.upsert_fno_daily_summary(
            today,
            total_strategies=total_count,
            winning_strategies=win_count,
            losing_strategies=loss_count,
            total_pnl=round(total_pnl, 2),
            total_realized_loss=round(sum(abs(float(s.get("realized_pnl", 0))) for s in losing), 2),
            max_drawdown=round(max_drawdown, 2),
            broker_name=self.config.broker,
            mode=self.config.mode.upper(),
            paper_capital_remaining=self.config.paper_capital - abs(total_pnl) if self.config.mode == "paper" else None,
        )

        # Update dashboard JSON
        self._update_dashboard(strategies, today)

        logger.info(
            "EOD report generated: %s — P&L ₹%.2f, Win rate %.1f%%",
            today, total_pnl, win_rate,
        )

        return report

    # ------------------------------------------------------------------
    # Metrics Computation
    # ------------------------------------------------------------------

    def _compute_strategy_metrics(self, strategies: list[dict]) -> dict:
        """Compute per-strategy-type metrics: win rate, avg profit/loss, profit factor."""
        by_type: dict[str, list[float]] = {}
        for s in strategies:
            stype = s.get("strategy_type", "UNKNOWN")
            pnl = float(s.get("realized_pnl", 0) or 0)
            by_type.setdefault(stype, []).append(pnl)

        metrics = {}
        for stype, pnls in by_type.items():
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            total = len(pnls)
            win_rate = (len(wins) / total * 100) if total > 0 else 0
            avg_profit = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            total_profit = sum(wins)
            total_loss = abs(sum(losses))
            profit_factor = (total_profit / total_loss) if total_loss > 0 else float("inf")

            metrics[stype] = {
                "count": total,
                "win_rate": round(win_rate, 1),
                "avg_profit": round(avg_profit, 2),
                "avg_loss": round(avg_loss, 2),
                "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
                "total_pnl": round(sum(pnls), 2),
            }

        return metrics

    def _compute_max_drawdown(self) -> float:
        """Compute maximum peak-to-trough drawdown across cumulative P&L series."""
        try:
            # Get all daily summaries
            cursor = self.db.conn.cursor()
            cursor.execute(
                "SELECT trade_date, total_pnl FROM fno_daily_summary ORDER BY trade_date"
            )
            rows = cursor.fetchall()
        except Exception:
            return 0.0

        if not rows:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for row in rows:
            cumulative += float(row["total_pnl"] or 0)
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    @staticmethod
    def _compute_theta_pnl(strategies: list[dict]) -> float:
        """Estimate theta decay P&L for premium-selling strategies.

        Approximation: for selling strategies, theta P&L ≈ net_theta × days_held.
        """
        theta_pnl = 0.0
        selling_types = {
            "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "STRANGLE", "STRADDLE",
            "NAKED_CE", "NAKED_PE",
        }
        for s in strategies:
            if s.get("strategy_type") in selling_types:
                theta = float(s.get("net_theta", 0) or 0)
                # Estimate 1 day of theta decay
                theta_pnl += abs(theta)
        return theta_pnl

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _write_report(self, date_str: str, report: dict) -> None:
        """Write report JSON to output/reports/fno_YYYY-MM-DD.json."""
        os.makedirs(REPORTS_DIR, exist_ok=True)
        filepath = os.path.join(REPORTS_DIR, f"fno_{date_str}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Report written: %s", filepath)
        except Exception:
            logger.error("Failed to write report to %s", filepath, exc_info=True)

    def _update_dashboard(self, strategies: list[dict], today: str) -> None:
        """Update dashboard JSON via fno/dashboard.py."""
        try:
            from fno.dashboard import write_fno_dashboard_json

            # Convert DB strategy dicts to dashboard format
            dash_strategies = []
            for s in strategies:
                legs_json = s.get("legs_json", "[]")
                try:
                    legs = json.loads(legs_json) if isinstance(legs_json, str) else legs_json
                except Exception:
                    legs = []

                legs_summary = " + ".join(
                    f"{l.get('transaction_type', '')} {l.get('strike', '')}{l.get('option_type', '')}"
                    for l in legs
                ) if legs else ""

                dash_strategies.append({
                    "strategy_type": s.get("strategy_type", ""),
                    "index": s.get("index_name", ""),
                    "legs_summary": legs_summary,
                    "entry_premium": float(s.get("net_premium", 0) or 0),
                    "current_premium": float(s.get("net_premium", 0) or 0),
                    "unrealized_pnl": float(s.get("realized_pnl", 0) or 0),
                    "status": s.get("status", ""),
                    "confluence_score": float(s.get("confluence_score", 0) or 0),
                    "net_greeks": {
                        "delta": float(s.get("net_delta", 0) or 0),
                        "gamma": float(s.get("net_gamma", 0) or 0),
                        "theta": float(s.get("net_theta", 0) or 0),
                        "vega": float(s.get("net_vega", 0) or 0),
                    },
                })

            write_fno_dashboard_json(
                strategies=dash_strategies,
                config=self.config,
                db=self.db,
                mode=self.config.mode.upper(),
                broker=self.config.broker,
                session_active=False,
            )
        except Exception:
            logger.error("Failed to update dashboard", exc_info=True)
