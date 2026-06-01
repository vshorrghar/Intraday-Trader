#!/usr/bin/env python3
"""
Swing module end-to-end smoke test.

Runs the full pipeline without placing orders:
  1. Load universe from cache
  2. Run scanner
  3. Run rules_selector
  4. Print summary

Usage:
    .venv/bin/python scripts/swing_smoke_test.py --profile vishal-live --dry-run
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from swing.data_loader import load_universe_for_scanner, get_universe_with_data
from swing.scanner import scan_universe
from swing.rules_selector import select_swing_trades
from swing.models import SwingConfig


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Swing module smoke test")
    parser.add_argument("--profile", default="vishal-live", help="Profile name")
    parser.add_argument("--dry-run", action="store_true", help="No orders (always true for smoke test)")
    parser.add_argument("--min-score", type=int, default=8, help="Minimum scanner score")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug logs")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print("SWING MODULE SMOKE TEST")
    print("=" * 60)
    print()

    # Step 1: Load universe from cache
    print("Step 1: Loading universe from cache...")
    symbols_with_data = get_universe_with_data(min_candles=200)
    print(f"  Universe loaded: {len(symbols_with_data)} stocks with data")

    if len(symbols_with_data) == 0:
        print("  ERROR: No stocks with sufficient data. Run fetch_swing_data.py first.")
        sys.exit(1)

    universe_data = load_universe_for_scanner(min_candles=200)
    print(f"  Scanner-ready: {len(universe_data)} stocks")
    print()

    # Step 2: Run scanner
    print(f"Step 2: Running scanner (min_score={args.min_score})...")
    candidates = scan_universe(universe_data, min_score=args.min_score)
    print(f"  Scanner produced: {len(candidates)} candidates (score >= {args.min_score})")

    if candidates:
        print()
        print("  Top 10 candidates:")
        print(f"  {'Rank':<5} {'Symbol':<12} {'Score':<6} {'Close':<8} {'20DMA':<8} {'RSI2':<6} {'Sector':<15}")
        print(f"  {'-'*5} {'-'*12} {'-'*6} {'-'*8} {'-'*8} {'-'*6} {'-'*15}")
        for i, c in enumerate(candidates[:10], 1):
            print(f"  {i:<5} {c['symbol']:<12} {c['score']:<6} "
                  f"{c['latest_close']:<8.1f} {c['dma_20']:<8.1f} "
                  f"{c['rsi2']:<6.1f} {c.get('sector', ''):<15}")
    print()

    # Step 3: Run rules_selector
    print("Step 3: Running rules_selector...")
    config = SwingConfig()  # Use defaults
    trades = select_swing_trades(candidates, config, live_mode=False)
    print(f"  Rules selector picked: {len(trades)} trades")

    if trades:
        print()
        for i, t in enumerate(trades, 1):
            rr = 0
            if t.stop_loss_price and t.entry_price and t.target_price:
                risk = t.entry_price - t.stop_loss_price
                if risk > 0:
                    rr = (t.target_price - t.entry_price) / risk
            print(f"  {i}. SYMBOL={t.nse_symbol} entry={t.entry_price:.2f} "
                  f"sl={t.stop_loss_price:.2f} target={t.target_price:.2f} "
                  f"score={t.confidence_score} R:R={rr:.1f}")
    elif candidates:
        print()
        print("  No trades selected. Possible reasons:")
        print("  - All candidates filtered by delta_from_20dma [-2%, +1%]")
        print("  - RSI(2) not oversold enough (< 50 required)")
        print("  - R:R < 2.0 after price computation")
        print("  - Confidence below threshold")
        print()
        # Show why top candidates were filtered
        print("  Top 3 candidates that didn't pass:")
        for c in candidates[:3]:
            reasons = []
            delta = c.get("delta_from_20dma", 99)
            if delta < -2.0 or delta > 1.0:
                reasons.append(f"delta={delta:.1f}% (need -2 to +1)")
            rsi = c.get("rsi2", 100)
            if rsi >= 50:
                reasons.append(f"rsi2={rsi:.0f} (need <50)")
            ret5d = c.get("last_5d_return", -99)
            if ret5d <= -8.0:
                reasons.append(f"5d_ret={ret5d:.1f}% (falling knife)")
            turnover = c.get("avg_turnover_cr", 0)
            if turnover < 5.0:
                reasons.append(f"turnover={turnover:.1f}Cr (need >=5)")
            if not reasons:
                reasons.append("R:R or confidence filter")
            print(f"    {c['symbol']} (score={c['score']}): {', '.join(reasons)}")

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print(f"  Stocks scanned: {len(universe_data)}")
    print(f"  Candidates (score >= {args.min_score}): {len(candidates)}")
    print(f"  Final picks: {len(trades)}")
    print(f"  Status: {'PASS' if len(candidates) > 0 else 'FAIL — no candidates'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
