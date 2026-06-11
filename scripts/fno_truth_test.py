#!/usr/bin/env python3
"""F&O Truth Test: Q1 (slippage), Q2 (outlier sensitivity), Q3 (monthly expectancy)."""
import sqlite3, json, statistics
from pathlib import Path

def load_clean_trades():
    """Load all trades, dedup, remove outliers (|P&L/lot| > 5000)."""
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
                if legs: lots = int(legs[0].get("num_lots", 1))
            except: pass
            pnl = float(r["pnl"])
            all_trades.append({
                "db": db_path, "id": r["id"], "date": r["trade_date"],
                "premium": abs(float(r["net_premium"] or 0)),
                "pnl": pnl, "pnl_per_lot": pnl / max(lots, 1), "lots": lots,
            })
        conn.close()
    # Dedup
    seen = set()
    clean = []
    for t in all_trades:
        key = (t["date"], round(t["pnl_per_lot"], 0))
        if key not in seen:
            seen.add(key)
            clean.append(t)
    # Remove outliers
    return [t for t in clean if abs(t["pnl_per_lot"]) <= 5000]

def apply_stop(trades, sl_mult=1.5):
    """Apply 1.5x credit stop to all trades. Returns adjusted P&L list."""
    adjusted = []
    for t in trades:
        prem_per_lot = t["premium"] / max(t["lots"], 1)
        if prem_per_lot <= 0:
            adjusted.append(t["pnl_per_lot"])
            continue
        loss_cap = -prem_per_lot * sl_mult
        pnl = t["pnl_per_lot"]
        if pnl < 0:
            adjusted.append(max(pnl, loss_cap))
        else:
            adjusted.append(pnl)  # HOLD winners, no cap
    return adjusted

def main():
    trades = load_clean_trades()
    print(f"Clean trades loaded: {len(trades)}")
    
    # Base case: HOLD + 1.5x stop (no slippage)
    base_pnls = apply_stop(trades, 1.5)
    base_mean = statistics.mean(base_pnls)
    base_median = statistics.median(base_pnls)
    losers_idx = [i for i, p in enumerate(base_pnls) if p < 0]
    
    print(f"\nBASELINE (HOLD + 1.5x stop, no slippage):")
    print(f"  Mean: Rs.{base_mean:.2f}/lot")
    print(f"  Median: Rs.{base_median:.2f}/lot")
    print(f"  Losers: {len(losers_idx)}")

    # ═══════════════════════════════════════════════════════════
    # Q1: DOES 1.5x STOP SURVIVE LIVE EXECUTION WITH SLIPPAGE?
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("Q1: DOES THE 1.5x STOP SURVIVE LIVE SLIPPAGE?")
    print(f"{'='*70}")
    print()
    print("Scenario: When stop triggers, we close 4 legs in a moving market.")
    print("Slippage = worse fills on exit. Applied ONLY to losing trades.")
    print()
    
    for slip_pct in [5, 10, 15, 20, 25, 30]:
        slipped = []
        for i, pnl in enumerate(base_pnls):
            if pnl < 0:
                # Slippage makes loss WORSE by slip_pct%
                slipped.append(pnl * (1 + slip_pct/100))
            else:
                slipped.append(pnl)
        mean_s = statistics.mean(slipped)
        print(f"  Slippage {slip_pct:>2}% on stops: Mean Rs.{mean_s:>7.2f}/lot  "
              f"({'POSITIVE' if mean_s > 0 else 'NEGATIVE'})")
    
    # Find breakeven slippage
    for slip in range(1, 100):
        slipped = []
        for i, pnl in enumerate(base_pnls):
            if pnl < 0:
                slipped.append(pnl * (1 + slip/100))
            else:
                slipped.append(pnl)
        if statistics.mean(slipped) <= 0:
            print(f"\n  BREAKEVEN SLIPPAGE: {slip}% — edge goes to zero")
            print(f"  If real-world stop slippage exceeds {slip}%, strategy LOSES money.")
            break
    
    # Realistic assessment
    print(f"\n  VERDICT:")
    slip_10 = [p * 1.10 if p < 0 else p for p in base_pnls]
    print(f"  At 10% slippage (realistic for liquid NIFTY options):")
    print(f"    Mean: Rs.{statistics.mean(slip_10):.2f}/lot")
    print(f"    Still positive: {'YES' if statistics.mean(slip_10) > 0 else 'NO'}")

    # ═══════════════════════════════════════════════════════════
    # Q2: IS THE MEAN REAL OR ONE-OUTLIER-AWAY-FROM-NEGATIVE?
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("Q2: OUTLIER SENSITIVITY — REMOVE TOP WINNERS")
    print(f"{'='*70}")
    print()
    
    # Sort by P&L descending
    sorted_pnls = sorted(base_pnls, reverse=True)
    
    print(f"  Top 5 winners (P&L/lot):")
    for i, p in enumerate(sorted_pnls[:5]):
        print(f"    #{i+1}: Rs.{p:.2f}")
    
    print()
    for remove_n in [1, 2, 3, 5, 10]:
        remaining = sorted_pnls[remove_n:]
        if remaining:
            mean_r = statistics.mean(remaining)
            print(f"  Remove top {remove_n:>2} winners: Mean Rs.{mean_r:>7.2f}/lot  "
                  f"({'POSITIVE' if mean_r > 0 else 'NEGATIVE — EDGE GONE'})")
    
    # Find how many winners need removing to flip negative
    for n in range(1, len(sorted_pnls)):
        if statistics.mean(sorted_pnls[n:]) <= 0:
            print(f"\n  FLIP POINT: Remove top {n} winners and mean goes NEGATIVE")
            print(f"  That's {n}/{len(sorted_pnls)} = {n/len(sorted_pnls)*100:.0f}% of trades")
            if n <= 3:
                print(f"  ⚠️  FRAGILE: Only {n} trades separate profit from loss")
            elif n <= 10:
                print(f"  ⚠️  MODERATE: {n} trades carry the strategy")
            else:
                print(f"  ✅ ROBUST: Need to remove {n} winners to break it")
            break

    # ═══════════════════════════════════════════════════════════
    # Q3: REALISTIC MONTHLY EXPECTANCY
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*70}")
    print("Q3: REALISTIC MONTHLY EXPECTANCY")
    print(f"{'='*70}")
    print()
    
    trades_per_month = 20  # Conservative estimate
    
    # Pessimistic: use median (most trades make this)
    # Optimistic: use mean (average including big winners)
    # Realistic: use mean with 10% slippage on stops
    
    realistic_pnls = [p * 1.10 if p < 0 else p for p in base_pnls]
    realistic_mean = statistics.mean(realistic_pnls)
    
    print(f"  Assumptions: {trades_per_month} trades/month, 1 lot each")
    print()
    print(f"  PESSIMISTIC (median-based, most trades look like this):")
    print(f"    Per trade: Rs.{base_median:.2f}")
    print(f"    Monthly: Rs.{base_median * trades_per_month:.2f}")
    print(f"    Annual: Rs.{base_median * trades_per_month * 12:.2f}")
    print()
    print(f"  REALISTIC (mean with 10% stop slippage):")
    print(f"    Per trade: Rs.{realistic_mean:.2f}")
    print(f"    Monthly: Rs.{realistic_mean * trades_per_month:.2f}")
    print(f"    Annual: Rs.{realistic_mean * trades_per_month * 12:.2f}")
    print()
    print(f"  OPTIMISTIC (mean, no slippage, big winners repeat):")
    print(f"    Per trade: Rs.{base_mean:.2f}")
    print(f"    Monthly: Rs.{base_mean * trades_per_month:.2f}")
    print(f"    Annual: Rs.{base_mean * trades_per_month * 12:.2f}")
    print()
    
    # At 2L capital (4 lots)
    print(f"  AT Rs.2L CAPITAL (4 lots):")
    print(f"    Pessimistic: Rs.{base_median * trades_per_month * 4:.0f}/month ({base_median * trades_per_month * 4 / 200000 * 100:.1f}% return)")
    print(f"    Realistic:   Rs.{realistic_mean * trades_per_month * 4:.0f}/month ({realistic_mean * trades_per_month * 4 / 200000 * 100:.1f}% return)")
    print(f"    Optimistic:  Rs.{base_mean * trades_per_month * 4:.0f}/month ({base_mean * trades_per_month * 4 / 200000 * 100:.1f}% return)")
    print()
    
    # THE HONEST VERDICT
    print(f"{'='*70}")
    print("THE HONEST VERDICT")
    print(f"{'='*70}")
    print()
    if realistic_mean > 50:
        print("  F&O Iron Condor with HOLD + 1.5x stop has a SMALL but REAL edge.")
        print(f"  Expected: Rs.{realistic_mean:.0f}/lot/trade after slippage.")
        print(f"  This is NOT a get-rich strategy. It's a slow grinder.")
        print(f"  At 2L capital: Rs.{realistic_mean * trades_per_month * 4:.0f}/month = {realistic_mean * trades_per_month * 4 / 200000 * 100:.1f}% monthly.")
    elif realistic_mean > 0:
        print("  F&O has a MARGINAL edge that may not survive real-world friction.")
        print(f"  Expected: Rs.{realistic_mean:.0f}/lot/trade — barely covers charges.")
        print("  RECOMMENDATION: Continue paper for 30 more trades to confirm.")
    else:
        print("  F&O DOES NOT HAVE AN EDGE after realistic slippage.")
        print("  The strategy is a penny-in-front-of-steamroller trap.")
        print("  RECOMMENDATION: Do NOT go live. Rethink strategy entirely.")

if __name__ == "__main__":
    main()
