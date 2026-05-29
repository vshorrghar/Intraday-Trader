"""Tests for F&O Paper Validation Tracker (Phase 6).

Tests metric computation, decision gate logic, and report generation.
Uses in-memory SQLite with synthetic trade data.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.fno_paper_validation_tracker import (
    compute_metrics,
    evaluate_gate,
    generate_report,
    VALIDATION_START_DATE,
    GATE_TRADES_MIN,
    GATE_WIN_RATE_MIN,
    GATE_PROFIT_FACTOR_MIN,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _create_test_db(tmp_path, trades: list[dict]) -> str:
    """Create a test DB with fno_strategies table and synthetic trades."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE fno_strategies (
        id INTEGER PRIMARY KEY,
        trade_date TEXT,
        strategy_type TEXT,
        index_name TEXT,
        net_premium REAL,
        max_profit REAL,
        max_loss REAL,
        realized_pnl REAL,
        corrected_pnl REAL,
        status TEXT,
        confidence_score INTEGER,
        confluence_score REAL
    )""")
    conn.execute("""CREATE TABLE fno_adjustments (
        id INTEGER PRIMARY KEY,
        strategy_id INTEGER,
        adjustment_time TEXT,
        trigger_reason TEXT,
        legs_closed TEXT,
        legs_opened TEXT,
        net_pnl_impact REAL
    )""")

    for i, t in enumerate(trades, 1):
        conn.execute(
            """INSERT INTO fno_strategies
               (id, trade_date, strategy_type, index_name, net_premium,
                max_profit, max_loss, realized_pnl, status, confidence_score, confluence_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, t.get("date", "2026-06-01"), t.get("type", "IRON_CONDOR"),
             t.get("index", "NIFTY"), t.get("premium", 500),
             t.get("max_profit", 500), t.get("max_loss", -5000),
             t.get("pnl"), t.get("status", "CLOSED"), 8, 60),
        )
    conn.commit()
    conn.close()
    return db_path


class TestTrackerMetrics:
    """Test metric computation."""

    def test_tracker_runs_with_no_trades(self, tmp_path):
        """Tracker should handle empty DB gracefully."""
        db_path = _create_test_db(tmp_path, [])
        metrics = compute_metrics(db_path, start_date="2026-05-29")

        assert metrics["trades_placed"] == 0
        assert metrics["trades_closed"] == 0
        assert metrics["win_rate"] is None
        assert metrics["profit_factor"] is None

    def test_tracker_computes_metrics_correctly(self, tmp_path):
        """Tracker should compute WR, PF, avg P&L correctly."""
        trades = [
            {"date": "2026-06-01", "pnl": 250, "status": "CLOSED"},
            {"date": "2026-06-02", "pnl": 300, "status": "CLOSED"},
            {"date": "2026-06-03", "pnl": -150, "status": "STOPPED_OUT"},
            {"date": "2026-06-04", "pnl": 200, "status": "CLOSED"},
            {"date": "2026-06-05", "pnl": -100, "status": "FORCE_EXITED"},
        ]
        db_path = _create_test_db(tmp_path, trades)
        metrics = compute_metrics(db_path, start_date="2026-05-29")

        assert metrics["trades_placed"] == 5
        assert metrics["trades_closed"] == 5
        assert metrics["win_rate"] == 60.0  # 3/5
        # PF = gross_profit / gross_loss = 750 / 250 = 3.0
        assert metrics["profit_factor"] == 3.0
        # Avg = (250+300-150+200-100) / 5 = 500/5 = 100
        assert metrics["avg_pnl"] == 100.0
        assert metrics["total_pnl"] == 500.0

    def test_strategy_breakdown(self, tmp_path):
        """Tracker should break down by strategy type."""
        trades = [
            {"date": "2026-06-01", "type": "IRON_CONDOR", "pnl": 250, "status": "CLOSED"},
            {"date": "2026-06-02", "type": "IRON_CONDOR", "pnl": -100, "status": "STOPPED_OUT"},
            {"date": "2026-06-03", "type": "BULL_PUT_SPREAD", "pnl": 300, "status": "CLOSED"},
        ]
        db_path = _create_test_db(tmp_path, trades)
        metrics = compute_metrics(db_path, start_date="2026-05-29")

        breakdown = metrics["strategy_breakdown"]
        assert "IRON_CONDOR" in breakdown
        assert breakdown["IRON_CONDOR"]["count"] == 2
        assert breakdown["IRON_CONDOR"]["winners"] == 1
        assert "BULL_PUT_SPREAD" in breakdown
        assert breakdown["BULL_PUT_SPREAD"]["count"] == 1


class TestDecisionGate:
    """Test the live-deployment decision gate."""

    def test_decision_gate_insufficient_data(self):
        """< 20 trades → INSUFFICIENT_DATA."""
        metrics = {"trades_closed": 10, "win_rate": 70, "profit_factor": 2.0, "exceeded_max_loss": False}
        gate = evaluate_gate(metrics)
        assert gate["status"] == "INSUFFICIENT_DATA"

    def test_decision_gate_approved_for_live(self):
        """≥ 30 trades + WR ≥ 60% + PF ≥ 1.4 + no breach → APPROVED."""
        metrics = {"trades_closed": 35, "win_rate": 65, "profit_factor": 1.8, "exceeded_max_loss": False}
        gate = evaluate_gate(metrics)
        assert gate["status"] == "APPROVED_FOR_LIVE"

    def test_decision_gate_continue_paper(self):
        """20-29 trades + WR ≥ 50% → CONTINUE_PAPER."""
        metrics = {"trades_closed": 25, "win_rate": 55, "profit_factor": 1.2, "exceeded_max_loss": False}
        gate = evaluate_gate(metrics)
        assert gate["status"] == "CONTINUE_PAPER"

    def test_decision_gate_major_rework(self):
        """≥ 30 trades but WR < 60% → MAJOR_REWORK."""
        metrics = {"trades_closed": 35, "win_rate": 45, "profit_factor": 0.8, "exceeded_max_loss": False}
        gate = evaluate_gate(metrics)
        assert gate["status"] == "MAJOR_REWORK_NEEDED"

    def test_decision_gate_max_loss_breach(self):
        """Even with good WR, max_loss breach → MAJOR_REWORK."""
        metrics = {"trades_closed": 35, "win_rate": 70, "profit_factor": 2.0, "exceeded_max_loss": True}
        gate = evaluate_gate(metrics)
        assert gate["status"] == "MAJOR_REWORK_NEEDED"
