#!/usr/bin/env python3
"""F&O 2L Capital Replay — scales recorded paper trades to Rs2L capital.

CRITICAL HONESTY CAVEAT:
This is a REPLAY of real recorded paper trades scaled to 2L, NOT a fresh backtest.
Dhan does NOT provide historical option-chain data. We CANNOT simulate new F&O trades
on arbitrary past days. We can only replay the trades that were actually placed.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

PAPER_CAPITAL = 50_000
TARGET_CAPITAL = 200_000
MARGIN_PER_IC = 50_000
MAX_CONCURRENT_AT_2L = int(TARGET_CAPITAL / MARGIN_PER_IC)  # = 4
REGIME_THRESHOLD = 0.4


def load_trades_from_db(db_path):
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cols = [r[1] for r in conn.execute("PRAGMA table_info(fno_strategies)").fetchall()]
    has_corrected = "corrected_pnl" in cols
    pnl_col = "COALESCE(corrected_pnl, realized_pnl)" if has_corrected else "realized_pnl"
    rows = conn.execute(f"""
        SELECT id, trade_date, strategy_type, index_name, net_premium,
               max_profit, max_loss, {pnl_col} as pnl, status, legs_json
        FROM fno_strategies WHERE {pnl_col} IS NOT NULL ORDER BY trade_date, id
    """).fetchall()
    trades = []
    for r in rows:
        lots = 1
        try:
            legs = json.loads(r["legs_json"] or "[]")
            if legs:
                lots = int(legs[0].get("num_lots", 1))
        except Exception:
            pass
        trades.append({
            "db": db_path, "id": r["id"], "date": r["trade_date"],
            "strategy_type": r["strategy_type"], "index": r["index_name"],
            "net_premium": float(r["net_premium"] or 0),
            "max_profit": float(r["max_profit"] or 0),
            "max_loss": float(r["max_loss"] or 0),
            "pnl": float(r["pnl"]),
            "pnl_per_lot": float(r["pnl"]) / max(lots, 1),
            "status": r["status"], "lots": lots,
        })
    conn.close()
    return trades


def deduplicate_trades(all_trades):
    seen = set()
    unique = []
    for t in all_trades:
        key = (t["date"], t["strategy_type"], t["index"], round(t["pnl"], 0))
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def classify_regime(date_str):
    try:
        conn = sqlite3.connect("database/vishal.db")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT log_return FROM fno_spot_history WHERE index_name='NIFTY' AND date=?",
            (date_str,)).fetchall()
        conn.close()
        if rows:
            pct = float(rows[0]["log_return"]) * 100
            if pct > REGIME_THRESHOLD:
                return "UP"
            elif pct < -REGIME_THRESHOLD:
                return "DOWN"
            else:
                return "SIDEWAYS"
    except Exception:
        pass
    return "UNKNOWN"


def scale_to_2L(trade):
    return trade["pnl_per_lot"] * MAX_CONCURRENT_AT_2L


def run_replay():
    all_trades = []
    for db in ["database/portfolio.db", "database/vishal.db", "database/neha.db"]:
        trades = load_trades_from_db(db)
        all_trades.extend(trades)
        if trades:
            print(f"  {db}: {len(trades)} trades")

    trades = deduplicate_trades(all_trades)
    print(f"\nTotal unique trades: {len(trades)} (from {len(all_trades)} raw)")

    for t in trades:
        t["scaled_pnl"] = scale_to_2L(t)
        t["regime"] = classify_regime(t["date"])

    winners = [t for t in trades if t["scaled_pnl"] > 0]
    losers = [t for t in trades if t["scaled_pnl"] < 0]
    total_pnl = sum(t["scaled_pnl"] for t in trades)
    gross_profit = sum(t["scaled_pnl"] for t in winners)
    gross_loss = abs(sum(t["scaled_pnl"] for t in losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    wr = len(winners) / len(trades) * 100 if trades else 0
    avg = total_pnl / len(trades) if trades else 0

    cumulative = 0
    peak = 0
    max_dd = 0
    for t in sorted(trades, key=lambda x: x["date"]):
        cumulative += t["scaled_pnl"]
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    best = max(trades, key=lambda x: x["scaled_pnl"]) if trades else None
    worst = min(trades, key=lambda x: x["scaled_pnl"]) if trades else None

    regime_stats = {}
    for regime in ["UP", "DOWN", "SIDEWAYS", "UNKNOWN"]:
        rt = [t for t in trades if t["regime"] == regime]
        if not rt:
            regime_stats[regime] = {"trades": 0, "wr": 0, "pnl": 0, "avg": 0}
            continue
        rw = sum(1 for t in rt if t["scaled_pnl"] > 0)
        rp = sum(t["scaled_pnl"] for t in rt)
        regime_stats[regime] = {"trades": len(rt), "wr": round(rw/len(rt)*100, 1), "pnl": round(rp, 2), "avg": round(rp/len(rt), 2)}

    type_stats = {}
    for stype in set(t["strategy_type"] for t in trades):
        st = [t for t in trades if t["strategy_type"] == stype]
        sw = sum(1 for t in st if t["scaled_pnl"] > 0)
        sp = sum(t["scaled_pnl"] for t in st)
        type_stats[stype] = {"trades": len(st), "wr": round(sw/len(st)*100, 1), "pnl": round(sp, 2), "avg": round(sp/len(st), 2)}

    print("\n" + "=" * 70)
    print("F&O 2L CAPITAL REPLAY - RECORDED PAPER TRADES")
    print("=" * 70)
    print("\nCRITICAL HONESTY CAVEAT:")
    print("This is a REPLAY of real recorded paper trades scaled to Rs2L,")
    print("NOT a fresh backtest. Dhan does NOT provide historical option-chain data.")
    print(f"\nScaling: Rs{PAPER_CAPITAL:,} (1 lot) -> Rs{TARGET_CAPITAL:,} ({MAX_CONCURRENT_AT_2L} lots)")
    print(f"Assumption: Linear scaling - same per-lot P&L x {MAX_CONCURRENT_AT_2L} lots")
    print("\n--- OVERALL ---")
    print(f"  Total strategies:    {len(trades)}")
    print(f"  Winners:             {len(winners)}")
    print(f"  Losers:              {len(losers)}")
    print(f"  Win rate:            {wr:.1f}%")
    print(f"  Profit factor:       {pf:.2f}")
    print(f"  Cumulative P&L @2L:  Rs.{total_pnl:,.2f} ({total_pnl/TARGET_CAPITAL*100:.1f}% of capital)")
    print(f"  Avg P&L per trade:   Rs.{avg:,.2f}")
    if best:
        print(f"  Best single trade:   Rs.{best['scaled_pnl']:,.2f} ({best['strategy_type']} {best['index']} {best['date']})")
    if worst:
        print(f"  Worst single trade:  Rs.{worst['scaled_pnl']:,.2f} ({worst['strategy_type']} {worst['index']} {worst['date']})")
    print(f"  Max drawdown:        Rs.{max_dd:,.2f}")
    print("\n--- BY DAY TYPE ---")
    print(f"  {'Regime':<10} {'Trades':<8} {'WR%':<8} {'P&L@2L (Rs)':<15} {'Avg/trade'}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*15} {'-'*10}")
    for regime in ["UP", "DOWN", "SIDEWAYS", "UNKNOWN"]:
        s = regime_stats[regime]
        print(f"  {regime:<10} {s['trades']:<8} {s['wr']:<8} {s['pnl']:>12,.2f}   {s['avg']:>8,.2f}")
    print("\n--- BY STRATEGY TYPE ---")
    print(f"  {'Type':<20} {'Trades':<8} {'WR%':<8} {'P&L@2L (Rs)':<15} {'Avg/trade'}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*15} {'-'*10}")
    for stype in sorted(type_stats, key=lambda x: type_stats[x]["pnl"], reverse=True):
        s = type_stats[stype]
        print(f"  {stype:<20} {s['trades']:<8} {s['wr']:<8} {s['pnl']:>12,.2f}   {s['avg']:>8,.2f}")
    print(f"\n--- THE Rs155/TRADE PROBLEM ---")
    orig_avg = sum(t["pnl"] for t in trades) / len(trades) if trades else 0
    print(f"  Original avg (1 lot, Rs50K): Rs.{orig_avg:,.2f}/trade")
    print(f"  Scaled avg (4 lots, Rs2L):   Rs.{avg:,.2f}/trade")
    print(f"  Scaling multiplier:          {MAX_CONCURRENT_AT_2L}x")
    if avg > 0:
        print(f"  Does more size fix it?       YES - edge scales linearly")
    else:
        print(f"  Does more size fix it?       NO - scaling a losing strategy loses more")
    print(f"  Monthly projection (20 trades): Rs.{avg * 20:,.2f}")

    Path("backtest/results").mkdir(parents=True, exist_ok=True)
    output = {
        "generated": datetime.now(IST).isoformat(),
        "caveat": "REPLAY of recorded trades, NOT fresh simulation",
        "scaling": {"from": PAPER_CAPITAL, "to": TARGET_CAPITAL, "lots_multiplier": MAX_CONCURRENT_AT_2L},
        "overall": {"total_trades": len(trades), "winners": len(winners), "losers": len(losers),
                    "win_rate": round(wr, 1), "profit_factor": round(pf, 2) if pf != float("inf") else "inf",
                    "cumulative_pnl": round(total_pnl, 2), "avg_pnl": round(avg, 2),
                    "best_trade": round(best["scaled_pnl"], 2) if best else 0,
                    "worst_trade": round(worst["scaled_pnl"], 2) if worst else 0,
                    "max_drawdown": round(max_dd, 2)},
        "by_regime": regime_stats, "by_strategy_type": type_stats,
        "trades": [{"date": t["date"], "type": t["strategy_type"], "index": t["index"],
                    "pnl_1lot": round(t["pnl"], 2), "pnl_2L": round(t["scaled_pnl"], 2),
                    "regime": t["regime"]} for t in trades],
    }
    with open("backtest/results/fno_2L_3mo.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nResults saved: backtest/results/fno_2L_3mo.json")


if __name__ == "__main__":
    print("F&O 2L Capital Replay")
    print("Loading trades from all available DBs...")
    run_replay()
