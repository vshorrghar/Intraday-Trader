#!/usr/bin/env python3
"""Pretty-print swing 2L regime backtest results from JSON."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.backtest_swing_2L_regime import print_summary


def main():
    result_file = Path(__file__).parent.parent / "backtest" / "results" / "swing_2L_3mo.json"
    if not result_file.exists():
        print("ERROR: No results file found. Run backtest_swing_2L_regime.py first.")
        sys.exit(1)

    with open(result_file) as f:
        results = json.load(f)

    print(f"  Reading: {result_file}")
    print_summary(results)


if __name__ == "__main__":
    main()
