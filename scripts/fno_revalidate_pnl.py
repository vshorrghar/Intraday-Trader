#!/usr/bin/env python3
"""F&O P&L Revalidation Script.

Iterates all fno_strategies in a given DB, checks for the lot-multiplication
bug (f77de67), and produces a revalidation report.

Usage:
    python scripts/fno_revalidate_pnl.py                    # portfolio.db
    python scripts/fno_revalidate_pnl.py --db database/vishal.db
    python scripts/fno_revalidate_pnl.py --fix              # Apply corrections
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_num_lots(legs_json_str: str) -> int:
    """Extract num_lots from first leg of legs_json."""
    try:
        legs = json.loads(legs_json_str) if legs_json_str else []
        if legs:
            return int(legs[0].get("num_lots", 1))
    except (json.JSONDecodeError, TypeError, IndexError):
        pass
    return 1


def validate_strategy(row: dict) -> dict:
    """Validate a single strategy's P&L.

    Returns dict with:
        - id, strategy_type, net_premium, realized_pnl
        - status: 'CLEAN', 'CORRUPTED', 'SUSPICIOUS', 'NULL_PNL'
        - reason: explanation
        - corrected_pnl: what it should be (if corrupted)
        - num_lots: from legs_json
    """
    sid = row["id"]
    net_premium = abs(float(row["net_premium"] or 0))
    realized_pnl = row["realized_pnl"]
    max_profit = float(row["max_profit"] or net_premium)
    max_loss = float(row["max_loss"] or 0)
    strategy_type = row["strategy_type"]
    legs_json = row.get("legs_json", "[]")
    status_db = row["status"]
    num_lots = get_num_lots(legs_json)

    result = {
        "id": sid,
        "trade_date": row["trade_date"],
        "strategy_type": strategy_type,
        "index_name": row.get("index_name", ""),
        "net_premium": net_premium,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "realized_pnl": realized_pnl,
        "db_status": status_db,
        "num_lots": num_lots,
        "status": "CLEAN",
        "reason": "",
        "corrected_pnl": None,
    }

    # NULL P&L
    if realized_pnl is None:
        result["status"] = "NULL_PNL"
        result["reason"] = "No realized_pnl recorded"
        return result

    realized_pnl = float(realized_pnl)

    # Check for lot-multiplication bug: realized_pnl == net_premium × num_lots
    if num_lots > 1 and net_premium > 0:
        expected_buggy = round(net_premium * num_lots, 2)
        if abs(realized_pnl - expected_buggy) < 0.01:
            result["status"] = "CORRUPTED"
            result["reason"] = (
                f"Bug f77de67: realized_pnl={realized_pnl:.2f} == "
                f"net_premium({net_premium:.2f}) × num_lots({num_lots}) = {expected_buggy:.2f}. "
                f"Double-counted lot size."
            )
            result["corrected_pnl"] = round(realized_pnl / num_lots, 2)
            return result

    # Check bounds: for selling strategies, max profit = net_premium
    is_selling = strategy_type in (
        "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
        "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
    )

    if is_selling and net_premium > 0:
        # Profit should not exceed net_premium (max theoretical profit for credit strategies)
        if realized_pnl > net_premium * 1.05:  # 5% tolerance
            result["status"] = "CORRUPTED"
            result["reason"] = (
                f"MTM bug: profit {realized_pnl:.2f} exceeds max theoretical profit "
                f"(net_premium {net_premium:.2f}) by {(realized_pnl/net_premium - 1)*100:.0f}%"
            )
            # Correct to max_profit (= net_premium for credit strategies)
            result["corrected_pnl"] = round(min(realized_pnl, net_premium), 2)
            return result
        # Loss should not exceed max_loss (absolute value)
        abs_max_loss = abs(max_loss) if max_loss != 0 else net_premium * 3
        if realized_pnl < 0 and abs(realized_pnl) > abs_max_loss * 1.05:
            result["status"] = "CORRUPTED"
            result["reason"] = (
                f"MTM bug: loss {realized_pnl:.2f} exceeds max theoretical loss "
                f"(max_loss {-abs_max_loss:.2f}) by {(abs(realized_pnl)/abs_max_loss - 1)*100:.0f}%"
            )
            # Correct to -max_loss
            result["corrected_pnl"] = round(-abs_max_loss, 2)
            return result

    return result


def run_revalidation(db_path: str, apply_fix: bool = False) -> dict:
    """Run revalidation against a DB. Returns summary dict."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check if table exists
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fno_strategies'"
    ).fetchone()
    if not tables:
        conn.close()
        return {"error": f"No fno_strategies table in {db_path}"}

    strategies = conn.execute(
        "SELECT * FROM fno_strategies ORDER BY id"
    ).fetchall()

    results = []
    for row in strategies:
        result = validate_strategy(dict(row))
        results.append(result)

    # Categorize
    corrupted = [r for r in results if r["status"] == "CORRUPTED"]
    suspicious = [r for r in results if r["status"] == "SUSPICIOUS"]
    null_pnl = [r for r in results if r["status"] == "NULL_PNL"]
    clean = [r for r in results if r["status"] == "CLEAN"]

    # Compute cumulative P&L
    pnl_before = sum(float(r["realized_pnl"] or 0) for r in results)
    pnl_after = sum(
        float(r["corrected_pnl"]) if r["corrected_pnl"] is not None
        else float(r["realized_pnl"] or 0)
        for r in results
    )

    summary = {
        "db_path": db_path,
        "total_strategies": len(results),
        "corrupted": len(corrupted),
        "suspicious": len(suspicious),
        "null_pnl": len(null_pnl),
        "clean": len(clean),
        "corrupted_ids": [r["id"] for r in corrupted],
        "suspicious_ids": [r["id"] for r in suspicious],
        "cumulative_pnl_before": round(pnl_before, 2),
        "cumulative_pnl_after": round(pnl_after, 2),
        "discrepancy": round(pnl_before - pnl_after, 2),
        "details": results,
    }

    # Apply fix if requested
    if apply_fix and corrupted:
        # Add corrected_pnl column if not exists
        try:
            conn.execute("ALTER TABLE fno_strategies ADD COLUMN corrected_pnl REAL")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE fno_strategies ADD COLUMN correction_reason TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        for r in corrupted:
            conn.execute(
                "UPDATE fno_strategies SET corrected_pnl=?, correction_reason=? WHERE id=?",
                (
                    r["corrected_pnl"],
                    f"Bug f77de67: lot-mult double-count, divided by num_lots={r['num_lots']}",
                    r["id"],
                ),
            )
        conn.commit()
        summary["fix_applied"] = True
        summary["rows_corrected"] = len(corrupted)

    conn.close()
    return summary


def generate_report(summaries: list) -> str:
    """Generate markdown report from revalidation summaries."""
    lines = [
        "# F&O P&L Revalidation Report",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]

    for s in summaries:
        if "error" in s:
            lines.append(f"## {s['db_path']}")
            lines.append(f"**Error:** {s['error']}")
            lines.append("")
            continue

        lines.append(f"## Database: `{s['db_path']}`")
        lines.append("")
        lines.append("### Summary")
        lines.append(f"- Total strategies audited: **{s['total_strategies']}**")
        lines.append(f"- Corrupted (lot-mult bug): **{s['corrupted']}** (IDs: {s['corrupted_ids']})")
        lines.append(f"- Suspicious (bounds violation): **{s['suspicious']}** (IDs: {s['suspicious_ids']})")
        lines.append(f"- NULL P&L (no exit recorded): **{s['null_pnl']}**")
        lines.append(f"- Clean: **{s['clean']}**")
        lines.append("")
        lines.append("### Cumulative P&L")
        lines.append(f"- **BEFORE correction:** ₹{s['cumulative_pnl_before']:,.2f}")
        lines.append(f"- **AFTER correction:** ₹{s['cumulative_pnl_after']:,.2f}")
        lines.append(f"- **Discrepancy (inflated profit):** ₹{s['discrepancy']:,.2f}")
        lines.append("")

        if s.get("fix_applied"):
            lines.append(f"### Fix Applied")
            lines.append(f"- Rows corrected: {s['rows_corrected']}")
            lines.append(f"- Column `corrected_pnl` populated")
            lines.append(f"- Original `realized_pnl` preserved (audit trail)")
            lines.append("")

        # Detail corrupted
        corrupted = [r for r in s["details"] if r["status"] == "CORRUPTED"]
        if corrupted:
            lines.append("### Corrupted Strategies (lot-multiplication bug)")
            lines.append("")
            lines.append("| ID | Date | Type | Index | net_premium | Stored P&L | Corrected P&L | num_lots |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for r in corrupted:
                lines.append(
                    f"| {r['id']} | {r['trade_date']} | {r['strategy_type']} | "
                    f"{r['index_name']} | ₹{r['net_premium']:,.2f} | "
                    f"₹{r['realized_pnl']:,.2f} | ₹{r['corrected_pnl']:,.2f} | "
                    f"{r['num_lots']} |"
                )
            lines.append("")

        # Detail suspicious
        suspicious = [r for r in s["details"] if r["status"] == "SUSPICIOUS"]
        if suspicious:
            lines.append("### Suspicious Strategies (bounds violation)")
            lines.append("")
            for r in suspicious:
                lines.append(f"- **ID {r['id']}** ({r['strategy_type']} {r['index_name']}): {r['reason']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="F&O P&L Revalidation")
    parser.add_argument("--db", default="database/portfolio.db", help="Path to DB file")
    parser.add_argument("--fix", action="store_true", help="Apply corrections to DB")
    parser.add_argument("--all", action="store_true", help="Run against all known DBs")
    args = parser.parse_args()

    db_paths = []
    if args.all:
        for name in ["portfolio.db", "vishal.db", "vishal-live.db", "neha.db", "neha-live.db"]:
            path = f"database/{name}"
            if Path(path).exists():
                db_paths.append(path)
    else:
        db_paths = [args.db]

    summaries = []
    for db_path in db_paths:
        if not Path(db_path).exists():
            summaries.append({"db_path": db_path, "error": "File not found"})
            continue
        print(f"Validating: {db_path}")
        summary = run_revalidation(db_path, apply_fix=args.fix)
        summaries.append(summary)

        # Print quick summary
        if "error" not in summary:
            print(f"  Strategies: {summary['total_strategies']}")
            print(f"  Corrupted: {summary['corrupted']} (IDs: {summary['corrupted_ids']})")
            print(f"  Suspicious: {summary['suspicious']}")
            print(f"  P&L before: ₹{summary['cumulative_pnl_before']:,.2f}")
            print(f"  P&L after:  ₹{summary['cumulative_pnl_after']:,.2f}")
            print(f"  Discrepancy: ₹{summary['discrepancy']:,.2f}")
            if summary.get("fix_applied"):
                print(f"  ✅ Fix applied: {summary['rows_corrected']} rows corrected")
        print()

    # Generate report
    report = generate_report(summaries)
    report_path = "vishal-docs/FNO_PNL_REVALIDATION_REPORT.md"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(report)
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
