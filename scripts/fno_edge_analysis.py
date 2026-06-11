#!/usr/bin/env python3
"""F&O Edge Analysis: Exit sweep + data inconsistency investigation."""
import sqlite3, json, statistics
from pathlib import Path

def load_all_trades():
    all_trades = []
    for db_path in ["database/portfolio.db", "database/vishal.db", "database/neha.db"]:
        if not Path(db_path).exists():
            continue
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cols = [r[1] for r in conn.execute("PRAGMA table_info(fno_strategies)").fetchall()]
        has_c = "corrected_pnl" in cols
        pnl_col = "COALESCE(corrected_pnl, realized_pnl)" if has_c else "realized_pnl"
        rows = conn.execute(f"""
            SELECT id, trade_date, strategy_type, index_name, net_premium,
                   max_profit, max_loss, {pnl_col} as pnl, status, legs_json
            FROM fno_strategies WHERE {pnl_col} IS NOT NULL ORDER BY id
        """).fetchall()
        for r in rows:
            lots = 1
            try:
                legs = json.loads(r["legs_json"] or "[]")
                if legs:
                    lots = int(legs[0].get("num_lots", 1))
            except Exception:
                pass
            pnl = float(r["pnl"])
            all_trades.append({
                "db": db_path, "id": r["id"], "date": r["trade_date"],
                "type": r["strategy_type"], "index": r["index_name"],
                "premium": abs(float(r["net_premium"] or 0)),
                "max_profit": abs(float(r["max_profit"] or 0)),
                "pnl": pnl, "pnl_per_lot": pnl / max(lots, 1),
                "lots": lots, "status": r["status"]
            })
        conn.close()
    return all_trades

def main():
    all_trades = load_all_trades()

    # ═══ FINDING 2: DATA INCONSISTENCY ═══
    print("=" * 70)
    print("FINDING 2: DATA INCONSISTENCY INVESTIGATION")
    print("=" * 70)

    for db_path in ["database/portfolio.db", "database/vishal.db", "database/neha.db"]:
        db_trades = [t for t in all_trades if t["db"] == db_path]
        if not db_trades:
            continue
        pnls = [t["pnl_per_lot"] for t in db_trades]
        print(f"\n  {db_path} ({len(db_trades)} trades):")
        print(f"    Mean P&L/lot: Rs.{statistics.mean(pnls):.2f}")
        print(f"    Median P&L/lot: Rs.{statistics.median(pnls):.2f}")
        print(f"    Lots used: {sorted(set(t['lots'] for t in db_trades))}")
        print(f"    Date range: {db_trades[0]['date']} to {db_trades[-1]['date']}")

    # Portfolio.db top 5
    port = sorted([t for t in all_trades if t["db"] == "database/portfolio.db"],
                  key=lambda x: x["pnl_per_lot"], reverse=True)
    print("\n  portfolio.db TOP 5 by P&L/lot:")
    print(f"    {'ID':<4} {'Date':<12} {'Lots':<5} {'P&L/lot':<10} {'Premium':<10} {'Status'}")
    for t in port[:5]:
        print(f"    {t['id']:<4} {t['date']:<12} {t['lots']:<5} Rs.{t['pnl_per_lot']:>7.2f} Rs.{t['premium']:>7.0f} {t['status']}")

    print("\n  ROOT CAUSE OF 50x SPREAD:")
    print("  - portfolio.db id=35: corrected_pnl=23226 / 3 lots = Rs.7742/lot (OUTLIER)")
    print("  - portfolio.db has 2-3 lot trades with higher premiums (older period)")
    print("  - vishal.db/neha.db: 1 lot, smaller premiums (Rs.44-488), newer period")
    print("  - The avg Rs.1727 in portfolio.db is SKEWED by id=35 outlier")

    # Deduplicate + clean
    seen = set()
    clean = []
    for t in all_trades:
        key = (t["date"], t["type"], t["index"], round(t["pnl_per_lot"], 0))
        if key not in seen:
            seen.add(key)
            clean.append(t)

    # Remove outliers: |P&L/lot| > Rs.5000 (impossible for defined-risk IC)
    MAX_OK = 5000
    truly_clean = [t for t in clean if abs(t["pnl_per_lot"]) <= MAX_OK]
    outliers = [t for t in clean if abs(t["pnl_per_lot"]) > MAX_OK]

    print(f"\n  CLEANING: {len(all_trades)} raw -> {len(clean)} dedup -> {len(truly_clean)} clean")
    if outliers:
        print(f"  OUTLIERS REMOVED ({len(outliers)}):")
        for o in outliers:
            print(f"    {o['db']} id={o['id']} P&L/lot=Rs.{o['pnl_per_lot']:.0f} ({o['date']})")

    # THE ONE HONEST NUMBER
    pnls = [t["pnl_per_lot"] for t in truly_clean]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]

    print(f"\n{'='*70}")
    print("THE ONE HONEST NUMBER")
    print(f"{'='*70}")
    print(f"  Clean trades: {len(truly_clean)}")
    print(f"  Winners: {len(winners)} ({len(winners)/len(truly_clean)*100:.1f}%)")
    print(f"  Losers: {len(losers)} ({len(losers)/len(truly_clean)*100:.1f}%)")
    print(f"  MEAN P&L/lot:   Rs.{statistics.mean(pnls):.2f}")
    print(f"  MEDIAN P&L/lot: Rs.{statistics.median(pnls):.2f}")
    print(f"  Std dev:        Rs.{statistics.stdev(pnls):.2f}")
    print(f"  Avg winner:     Rs.{statistics.mean(winners):.2f}" if winners else "")
    print(f"  Avg loser:      Rs.{statistics.mean(losers):.2f}" if losers else "")
    print(f"  Worst trade:    Rs.{min(pnls):.2f}")
    print(f"  Best trade:     Rs.{max(pnls):.2f}")

    # ═══ FINDING 1: EXIT SWEEP GRID ═══
    print(f"\n{'='*70}")
    print("FINDING 1: EXIT SWEEP GRID")
    print(f"{'='*70}")
    print("  profit_target: % of premium at which to exit winner")
    print("  stop_loss: multiplier of premium at which to exit loser")
    print()

    results = []
    for profit_pct in [50, 60, 70, 80, 90, 100]:
        for sl_mult in [1.5, 2.0, 2.5, 3.0]:
            simulated = []
            for t in truly_clean:
                prem_per_lot = t["premium"] / max(t["lots"], 1)
                if prem_per_lot <= 0:
                    simulated.append(t["pnl_per_lot"])
                    continue
                profit_cap = prem_per_lot * (profit_pct / 100) if profit_pct < 100 else 99999
                loss_cap = -prem_per_lot * sl_mult
                pnl = t["pnl_per_lot"]
                if pnl > 0:
                    simulated.append(min(pnl, profit_cap))
                else:
                    simulated.append(max(pnl, loss_cap))
            avg = statistics.mean(simulated)
            worst = min(simulated)
            results.append({"tp": profit_pct, "sl": sl_mult, "avg": avg, "worst": worst})

    results.sort(key=lambda x: x["avg"], reverse=True)
    print(f"  {'Target':<8} {'SL':<6} {'Avg/lot':<12} {'Worst/lot'}")
    print(f"  {'-'*8} {'-'*6} {'-'*12} {'-'*12}")
    for r in results[:15]:
        tp = "HOLD" if r["tp"] == 100 else f"{r['tp']}%"
        print(f"  {tp:<8} {r['sl']:.1f}x  Rs.{r['avg']:>8.2f}  Rs.{r['worst']:>8.2f}")

    best = results[0]
    tp_label = "HOLD-TO-EXPIRY" if best["tp"] == 100 else f"{best['tp']}%"
    print(f"\n  EMPIRICALLY BEST: profit={tp_label}, stop={best['sl']:.1f}x credit")
    print(f"  -> Avg Rs.{best['avg']:.2f}/lot, worst Rs.{best['worst']:.2f}/lot")

if __name__ == "__main__":
    main()
