#!/usr/bin/env python3
"""F&O Paper Validation Tracker — daily progress toward live deployment gate.

Reads fno_strategies since validation_start_date, computes metrics,
evaluates decision gate, outputs vishal-docs/FNO_VALIDATION_PROGRESS.md.

Run daily at 4:00 PM IST via cron. Observation-only — does not modify trades.

Usage:
    python scripts/fno_paper_validation_tracker.py
    python scripts/fno_paper_validation_tracker.py --profile vishal
    python scripts/fno_paper_validation_tracker.py --all
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

VALIDATION_START_DATE = "2026-05-29"  # Phase 5 deployment date
OUTPUT_PATH = "vishal-docs/FNO_VALIDATION_PROGRESS.md"

# Decision gate thresholds
GATE_TRADES_MIN = 30
GATE_WIN_RATE_MIN = 60.0
GATE_PROFIT_FACTOR_MIN = 1.4
GATE_MAX_LOSS_MULTIPLIER = 2.0  # No trade should exceed 2× max_loss

CLOSED_STATUSES = {"CLOSED", "FORCE_EXITED", "STOPPED_OUT", "EXPIRED"}


# ═══════════════════════════════════════════════════════════════
# METRICS COMPUTATION
# ═══════════════════════════════════════════════════════════════


def compute_metrics(db_path: str, start_date: str = VALIDATION_START_DATE) -> dict:
    """Compute validation metrics from a single DB."""
    if not Path(db_path).exists():
        return {"error": f"DB not found: {db_path}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check tables exist
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    if "fno_strategies" not in tables:
        conn.close()
        return {"error": "No fno_strategies table"}

    # Get all strategies since validation start
    has_corrected = "corrected_pnl" in [
        r[1] for r in conn.execute("PRAGMA table_info(fno_strategies)").fetchall()
    ]
    pnl_col = "COALESCE(corrected_pnl, realized_pnl)" if has_corrected else "realized_pnl"

    strategies = conn.execute(
        f"""SELECT id, trade_date, strategy_type, index_name, net_premium,
                   max_profit, max_loss, {pnl_col} as pnl, status,
                   confidence_score, confluence_score
            FROM fno_strategies
            WHERE trade_date >= ?
            ORDER BY trade_date, id""",
        (start_date,),
    ).fetchall()

    # Count adjustments
    has_adjustments = "fno_adjustments" in tables
    adjustment_count = 0
    if has_adjustments:
        row = conn.execute(
            "SELECT COUNT(*) FROM fno_adjustments WHERE adjustment_time >= ?",
            (start_date,),
        ).fetchone()
        adjustment_count = int(row[0]) if row else 0

    conn.close()

    # Compute metrics
    total_placed = len(strategies)
    closed = [dict(s) for s in strategies if s["status"] in CLOSED_STATUSES]
    total_closed = len(closed)

    if total_closed == 0:
        return {
            "db_path": db_path,
            "start_date": start_date,
            "trades_placed": total_placed,
            "trades_closed": 0,
            "win_rate": None,
            "profit_factor": None,
            "avg_pnl": None,
            "total_pnl": 0,
            "max_single_day_drawdown": 0,
            "max_trade_loss_vs_theoretical": None,
            "adjustments_triggered": adjustment_count,
            "force_exits": sum(1 for s in strategies if s["status"] == "FORCE_EXITED"),
            "strategy_breakdown": {},
            "exceeded_max_loss": False,
        }

    # Win/loss
    winners = [s for s in closed if (s["pnl"] or 0) > 0]
    losers = [s for s in closed if (s["pnl"] or 0) < 0]
    flat = [s for s in closed if (s["pnl"] or 0) == 0]

    win_rate = len(winners) / total_closed * 100 if total_closed > 0 else 0

    # Profit factor
    gross_profit = sum(float(s["pnl"]) for s in winners) if winners else 0
    gross_loss = abs(sum(float(s["pnl"]) for s in losers)) if losers else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Avg P&L
    total_pnl = sum(float(s["pnl"] or 0) for s in closed)
    avg_pnl = total_pnl / total_closed if total_closed > 0 else 0

    # Max single-day drawdown
    daily_pnl = {}
    for s in closed:
        date = s["trade_date"]
        daily_pnl[date] = daily_pnl.get(date, 0) + float(s["pnl"] or 0)
    max_drawdown = min(daily_pnl.values()) if daily_pnl else 0

    # Max trade loss vs theoretical max_loss
    exceeded_max_loss = False
    max_loss_ratio = 0
    for s in losers:
        pnl = abs(float(s["pnl"]))
        theoretical = abs(float(s["max_loss"] or pnl))
        if theoretical > 0:
            ratio = pnl / theoretical
            max_loss_ratio = max(max_loss_ratio, ratio)
            if ratio > GATE_MAX_LOSS_MULTIPLIER:
                exceeded_max_loss = True

    # Strategy breakdown
    breakdown = {}
    for s in closed:
        stype = s["strategy_type"]
        if stype not in breakdown:
            breakdown[stype] = {"count": 0, "winners": 0, "pnl": 0}
        breakdown[stype]["count"] += 1
        breakdown[stype]["pnl"] += float(s["pnl"] or 0)
        if (s["pnl"] or 0) > 0:
            breakdown[stype]["winners"] += 1

    for stype in breakdown:
        cnt = breakdown[stype]["count"]
        breakdown[stype]["win_rate"] = round(
            breakdown[stype]["winners"] / cnt * 100, 1
        ) if cnt > 0 else 0

    return {
        "db_path": db_path,
        "start_date": start_date,
        "trades_placed": total_placed,
        "trades_closed": total_closed,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        "avg_pnl": round(avg_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "max_single_day_drawdown": round(max_drawdown, 2),
        "max_trade_loss_vs_theoretical": round(max_loss_ratio, 2),
        "adjustments_triggered": adjustment_count,
        "force_exits": sum(1 for s in strategies if s["status"] == "FORCE_EXITED"),
        "strategy_breakdown": breakdown,
        "exceeded_max_loss": exceeded_max_loss,
    }


# ═══════════════════════════════════════════════════════════════
# DECISION GATE
# ═══════════════════════════════════════════════════════════════


def evaluate_gate(metrics: dict) -> dict:
    """Evaluate the live-deployment decision gate.

    Returns dict with {status, action, reason}.
    """
    trades_closed = metrics.get("trades_closed", 0)
    win_rate = metrics.get("win_rate")
    profit_factor = metrics.get("profit_factor")
    exceeded = metrics.get("exceeded_max_loss", False)

    if trades_closed < 20:
        return {
            "status": "INSUFFICIENT_DATA",
            "action": "Continue accumulating trades",
            "reason": f"Only {trades_closed} trades closed (need 30 minimum)",
        }

    if trades_closed >= GATE_TRADES_MIN:
        pf_ok = (isinstance(profit_factor, (int, float)) and profit_factor >= GATE_PROFIT_FACTOR_MIN) or profit_factor == "∞"
        if (win_rate or 0) >= GATE_WIN_RATE_MIN and pf_ok and not exceeded:
            return {
                "status": "APPROVED_FOR_LIVE",
                "action": "Enable cron for vishal-live with 1 lot, ₹50K margin",
                "reason": f"WR={win_rate}%, PF={profit_factor}, no max_loss breach",
            }
        else:
            reasons = []
            if (win_rate or 0) < GATE_WIN_RATE_MIN:
                reasons.append(f"WR {win_rate}% < {GATE_WIN_RATE_MIN}%")
            if isinstance(profit_factor, (int, float)) and profit_factor < GATE_PROFIT_FACTOR_MIN:
                reasons.append(f"PF {profit_factor} < {GATE_PROFIT_FACTOR_MIN}")
            if exceeded:
                reasons.append("Trade exceeded 2× max_loss")
            return {
                "status": "MAJOR_REWORK_NEEDED",
                "action": "Halt paper, investigate failures",
                "reason": "; ".join(reasons) if reasons else "Gate criteria not met",
            }

    # 20-29 trades
    if (win_rate or 0) >= 50:
        return {
            "status": "CONTINUE_PAPER",
            "action": "Run 10 more trades, re-evaluate",
            "reason": f"WR={win_rate}% (≥50%), need {GATE_TRADES_MIN - trades_closed} more trades",
        }

    return {
        "status": "MAJOR_REWORK_NEEDED",
        "action": "Halt paper, investigate failures",
        "reason": f"WR={win_rate}% below 50% at {trades_closed} trades",
    }


# ═══════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════


def generate_report(all_metrics: list) -> str:
    """Generate markdown validation progress report."""
    now = datetime.now(IST)
    start = datetime.strptime(VALIDATION_START_DATE, "%Y-%m-%d")
    days_elapsed = (now.date() - start.date()).days

    lines = [
        "# F&O Validation Progress",
        f"**Last Updated:** {now.strftime('%Y-%m-%d %H:%M IST')}",
        f"**Validation Started:** {VALIDATION_START_DATE}",
        f"**Days Elapsed:** {days_elapsed}",
        "",
        "---",
        "",
    ]

    # Combined metrics
    combined_placed = sum(m.get("trades_placed", 0) for m in all_metrics if "error" not in m)
    combined_closed = sum(m.get("trades_closed", 0) for m in all_metrics if "error" not in m)
    combined_pnl = sum(m.get("total_pnl", 0) for m in all_metrics if "error" not in m)

    lines.append("## Combined Metrics (All Profiles)")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Trades placed | {combined_placed} |")
    lines.append(f"| Trades closed | {combined_closed} |")
    lines.append(f"| Total P&L | ₹{combined_pnl:,.2f} |")
    lines.append("")

    # Per-profile
    for m in all_metrics:
        if "error" in m:
            lines.append(f"### {m.get('db_path', 'Unknown')}")
            lines.append(f"**Error:** {m['error']}")
            lines.append("")
            continue

        profile = Path(m["db_path"]).stem
        lines.append(f"### Profile: {profile}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Trades placed | {m['trades_placed']} |")
        lines.append(f"| Trades closed | {m['trades_closed']} |")
        lines.append(f"| Win rate | {m['win_rate']}% |" if m["win_rate"] is not None else "| Win rate | N/A |")
        lines.append(f"| Profit factor | {m['profit_factor']} |" if m["profit_factor"] is not None else "| Profit factor | N/A |")
        lines.append(f"| Avg P&L/trade | ₹{m['avg_pnl']:,.2f} |" if m["avg_pnl"] is not None else "| Avg P&L/trade | N/A |")
        lines.append(f"| Total P&L | ₹{m['total_pnl']:,.2f} |")
        lines.append(f"| Max daily drawdown | ₹{m['max_single_day_drawdown']:,.2f} |")
        lines.append(f"| Adjustments triggered | {m['adjustments_triggered']} |")
        lines.append(f"| Force exits | {m['force_exits']} |")
        lines.append(f"| Exceeded max_loss | {'⚠️ YES' if m['exceeded_max_loss'] else '✅ No'} |")
        lines.append("")

        # Strategy breakdown
        if m["strategy_breakdown"]:
            lines.append("**Strategy Breakdown:**")
            lines.append("")
            lines.append("| Strategy | Count | Win Rate | P&L |")
            lines.append("|----------|-------|----------|-----|")
            for stype, data in m["strategy_breakdown"].items():
                lines.append(
                    f"| {stype} | {data['count']} | {data['win_rate']}% | ₹{data['pnl']:,.2f} |"
                )
            lines.append("")

    # Decision gate (use combined metrics for gate evaluation)
    lines.append("---")
    lines.append("")
    lines.append("## Decision Gate")
    lines.append("")

    # Evaluate gate on combined
    combined_for_gate = {
        "trades_closed": combined_closed,
        "win_rate": None,
        "profit_factor": None,
        "exceeded_max_loss": any(m.get("exceeded_max_loss", False) for m in all_metrics if "error" not in m),
    }
    if combined_closed > 0:
        all_closed_pnl = []
        for m in all_metrics:
            if "error" not in m and m.get("total_pnl") is not None:
                # Approximate from total
                if m["trades_closed"] > 0:
                    all_closed_pnl.extend([m["total_pnl"] / m["trades_closed"]] * m["trades_closed"])
        winners_count = sum(m.get("win_rate", 0) / 100 * m.get("trades_closed", 0) for m in all_metrics if "error" not in m)
        combined_for_gate["win_rate"] = round(winners_count / combined_closed * 100, 1) if combined_closed > 0 else 0
        gross_profit = sum(m.get("total_pnl", 0) for m in all_metrics if "error" not in m and m.get("total_pnl", 0) > 0)
        gross_loss = abs(sum(m.get("total_pnl", 0) for m in all_metrics if "error" not in m and m.get("total_pnl", 0) < 0))
        combined_for_gate["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else "∞"

    gate = evaluate_gate(combined_for_gate)
    status_emoji = {
        "APPROVED_FOR_LIVE": "🟢",
        "CONTINUE_PAPER": "🟡",
        "INSUFFICIENT_DATA": "⏳",
        "MAJOR_REWORK_NEEDED": "🔴",
    }
    lines.append(f"**Status:** {status_emoji.get(gate['status'], '❓')} {gate['status']}")
    lines.append(f"**Action:** {gate['action']}")
    lines.append(f"**Reason:** {gate['reason']}")
    lines.append("")

    # Gate criteria
    lines.append("### Gate Criteria")
    lines.append("")
    lines.append(f"| Criterion | Required | Current | Status |")
    lines.append(f"|-----------|----------|---------|--------|")
    lines.append(f"| Trades closed | ≥ {GATE_TRADES_MIN} | {combined_closed} | {'✅' if combined_closed >= GATE_TRADES_MIN else '⏳'} |")
    wr = combined_for_gate.get("win_rate")
    lines.append(f"| Win rate | ≥ {GATE_WIN_RATE_MIN}% | {wr}% | {'✅' if wr and wr >= GATE_WIN_RATE_MIN else '⏳'} |")
    pf = combined_for_gate.get("profit_factor")
    pf_ok = (isinstance(pf, (int, float)) and pf >= GATE_PROFIT_FACTOR_MIN) or pf == "∞"
    lines.append(f"| Profit factor | ≥ {GATE_PROFIT_FACTOR_MIN} | {pf} | {'✅' if pf_ok else '⏳'} |")
    lines.append(f"| No 2× max_loss breach | True | {'✅' if not combined_for_gate['exceeded_max_loss'] else '⚠️'} | {'✅' if not combined_for_gate['exceeded_max_loss'] else '❌'} |")
    lines.append("")

    # Notes
    lines.append("---")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- All Phase 1-5 fixes deployed")
    lines.append("- P&L bug fixed (lot-multiplication + MTM bounds)")
    lines.append("- Real Dhan chain pricing active (no simulation)")
    lines.append("- 50% profit targets active (IC), 70% (spreads)")
    lines.append("- Adjustment engine active (0.5σ trigger)")
    lines.append("- Rules-based strategy selection (no LLM)")
    lines.append(f"- Regime allowlist: SIDEWAYS + HIGH_VOLATILITY")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="F&O Paper Validation Tracker")
    parser.add_argument("--profile", default=None, help="Single profile to track")
    parser.add_argument("--all", action="store_true", help="Track all profiles")
    args = parser.parse_args()

    if args.profile:
        db_paths = [f"database/{args.profile}.db"]
    elif args.all:
        db_paths = []
        for name in ["vishal.db", "neha.db"]:
            if Path(f"database/{name}").exists():
                db_paths.append(f"database/{name}")
    else:
        # Default: track vishal and neha paper profiles
        db_paths = [p for p in ["database/vishal.db", "database/neha.db"] if Path(p).exists()]
        if not db_paths and Path("database/portfolio.db").exists():
            db_paths = ["database/portfolio.db"]

    all_metrics = []
    for db_path in db_paths:
        print(f"Tracking: {db_path}")
        metrics = compute_metrics(db_path)
        all_metrics.append(metrics)

        if "error" not in metrics:
            print(f"  Placed: {metrics['trades_placed']}, Closed: {metrics['trades_closed']}")
            if metrics["win_rate"] is not None:
                print(f"  WR: {metrics['win_rate']}%, PF: {metrics['profit_factor']}, Avg: ₹{metrics['avg_pnl']:.2f}")
            gate = evaluate_gate(metrics)
            print(f"  Gate: {gate['status']} — {gate['reason']}")
        else:
            print(f"  Error: {metrics['error']}")
        print()

    # Generate report
    report = generate_report(all_metrics)
    output_path = Path(OUTPUT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"Report saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
