#!/usr/bin/env python3
"""S3 Prod-Grade Scorecard — decides if S3 earns the right to go live.

Reads from vishal-s3.db (or backtest results if no live paper data yet).
Prints 3-PF breakdown + hard VERDICT.

Usage: cd ~/dev-sandbox && .venv/bin/python scripts/s3_prod_grade_scorecard.py
"""
import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent

# Thresholds for live graduation
MIN_TRADES = 50
MIN_PF = 1.5
MAX_DD_PCT = 15  # % of capital
MAX_WORST_DAY = 5000  # Rs

CAPITAL = 30000


def load_trades_from_db(db_path: str) -> list:
    """Load S3 trades from SQLite."""
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM intraday_trades WHERE status NOT IN ('REJECTED','CANCELLED','PENDING') ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def load_trades_from_backtest() -> list:
    """Fallback: load from clean V6 baseline (per-trade, V4 excluded)."""
    baseline_path = ROOT / "backtest" / "results" / "v6_baseline_clean.json"
    if baseline_path.exists():
        data = json.loads(baseline_path.read_text())
        return data.get("trades", [])
    # Last resort: suite results
    results_dir = ROOT / "backtest" / "results"
    suite_files = sorted(results_dir.glob("v3_suite_*.json"), reverse=True)
    if not suite_files:
        return []
    data = json.loads(suite_files[0].read_text())
    s2 = data.get("scenario_2_pnl", {})
    daily = s2.get("daily_pnl", {})
    trades = []
    for date, pnl in daily.items():
        if pnl != 0:
            trades.append({"trade_date": date, "pnl": pnl, "strategy_type": "GAP_ORB"})
    return trades


def compute_metrics(trades: list) -> dict:
    if not trades:
        return {"trades": 0, "wr": 0, "pf": 0, "cum_pnl": 0, "max_dd": 0, "worst_day": 0}

    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    total = len(trades)
    wr = wins / total * 100 if total else 0

    gross_w = sum(t.get("pnl", 0) for t in trades if (t.get("pnl") or 0) > 0)
    gross_l = abs(sum(t.get("pnl", 0) for t in trades if (t.get("pnl") or 0) <= 0))
    pf = gross_w / gross_l if gross_l > 0 else 0

    cum_pnl = sum(t.get("pnl", 0) for t in trades)

    # Max drawdown
    running, peak, max_dd = 0, 0, 0
    for t in trades:
        running += t.get("pnl", 0)
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)

    # Worst day
    by_date = defaultdict(float)
    for t in trades:
        by_date[t.get("trade_date", "?")] += t.get("pnl", 0)
    worst_day = abs(min(by_date.values())) if by_date else 0

    return {
        "trades": total, "wins": wins, "wr": round(wr, 1),
        "pf": round(pf, 2), "cum_pnl": round(cum_pnl, 0),
        "max_dd": round(max_dd, 0), "max_dd_pct": round(max_dd / CAPITAL * 100, 1),
        "worst_day": round(worst_day, 0),
    }


def main():
    print("=" * 60)
    print("S3 PROD-GRADE SCORECARD")
    print("=" * 60)

    # Try DB first, fallback to backtest
    db_path = str(ROOT / "database" / "vishal-s3.db")
    trades = load_trades_from_db(db_path)
    source = "vishal-s3.db (live paper)"

    if not trades:
        trades = load_trades_from_backtest()
        source = "backtest results (no paper data yet)"

    print(f"  Source: {source}")
    print(f"  Capital: Rs{CAPITAL:,}")
    print()

    if not trades:
        print("  ⚠️  NO DATA — run S3 paper first to collect trades")
        print("  VERDICT: NOT READY (0 trades, need 50)")
        return

    # Overall metrics
    m = compute_metrics(trades)

    # Per-signal breakdown (if strategy_type available)
    gap_orb = [t for t in trades if "GAP" in (t.get("strategy_type") or "GAP_ORB").upper() or "V6" in (t.get("strategy_type") or "").upper()]
    vwap = [t for t in trades if "VWAP" in (t.get("strategy_type") or "").upper() or "REVERT" in (t.get("strategy_type") or "").upper()]
    claude = [t for t in trades if "CLAUDE" in (t.get("strategy_type") or "").upper() or "FALLBACK" in (t.get("strategy_type") or "").upper()]

    # If no strategy_type tagging, all are GAP_ORB (backtest default)
    if not gap_orb and not vwap and not claude:
        gap_orb = trades

    m_gap = compute_metrics(gap_orb)
    m_vwap = compute_metrics(vwap)
    m_claude = compute_metrics(claude)

    # Print 3-PF breakdown
    print("  ┌─────────────────────────────────────────────────┐")
    print(f"  │ GAP_ORB only:      PF {m_gap['pf']:.2f}  ({m_gap['trades']} trades, {m_gap['wr']:.0f}% WR)")
    print(f"  │ + VWAP_REVERT:     PF {m_vwap['pf']:.2f}  ({m_vwap['trades']} trades, {m_vwap['wr']:.0f}% WR)")
    print(f"  │ + Claude fallback: PF {m_claude['pf']:.2f}  ({m_claude['trades']} trades, {m_claude['wr']:.0f}% WR)")
    print(f"  │ BLENDED (all):     PF {m['pf']:.2f}  ({m['trades']} trades, {m['wr']:.0f}% WR)")
    print("  └─────────────────────────────────────────────────┘")
    print()
    print(f"  Cumulative P&L:  Rs{m['cum_pnl']:>+,}")
    print(f"  Max Drawdown:    Rs{m['max_dd']:,} ({m['max_dd_pct']:.1f}% of capital)")
    print(f"  Worst Single Day: Rs{m['worst_day']:,}")
    print()

    # VERDICT
    print("  " + "─" * 50)
    if m["trades"] < MIN_TRADES:
        verdict = f"NOT READY (only {m['trades']} trades, need {MIN_TRADES})"
    elif m["pf"] < MIN_PF:
        verdict = f"KILL INTRADAY (blended PF {m['pf']:.2f} < {MIN_PF} after {m['trades']} trades)"
    elif m["max_dd_pct"] > MAX_DD_PCT:
        verdict = f"NOT READY (maxDD {m['max_dd_pct']:.1f}% > {MAX_DD_PCT}% limit)"
    elif m["worst_day"] > MAX_WORST_DAY:
        verdict = f"NOT READY (worst day Rs{m['worst_day']:,} > Rs{MAX_WORST_DAY:,} limit)"
    else:
        verdict = f"READY FOR LIVE (blended PF {m['pf']:.2f} >= {MIN_PF}, {m['trades']}+ trades, maxDD {m['max_dd_pct']:.1f}% < {MAX_DD_PCT}%)"

    print(f"  VERDICT: {verdict}")
    print("  " + "─" * 50)


if __name__ == "__main__":
    main()
