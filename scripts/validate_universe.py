#!/usr/bin/env python3
"""Validate nifty500_constituents.json meets V3 requirements."""
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent
CONSTITUENTS = ROOT / "config" / "nifty500_constituents.json"


def main():
    if not CONSTITUENTS.exists():
        print("✗ nifty500_constituents.json not found. Run build_universe.py first.")
        sys.exit(1)

    data = json.loads(CONSTITUENTS.read_text())
    errors = []

    # Check 1: Size
    if len(data) >= 500:
        print(f"✓ Universe size: {len(data)} stocks")
    else:
        errors.append(f"✗ Universe too small: {len(data)} (need 500+)")

    # Check 2: Security IDs
    with_id = sum(1 for v in data.values() if v.get("security_id"))
    pct = with_id * 100 // len(data)
    if pct >= 95:
        print(f"✓ Dhan ID coverage: {with_id}/{len(data)} ({pct}%)")
    elif pct >= 80:
        print(f"⚠ Dhan ID coverage: {with_id}/{len(data)} ({pct}%) — acceptable but not ideal")
    else:
        errors.append(f"✗ Dhan ID coverage too low: {with_id}/{len(data)} ({pct}%)")

    # Check 3: Sector distribution
    sectors = Counter(v.get("sector", "Unknown") for v in data.values())
    max_sector_pct = max(sectors.values()) * 100 // len(data)
    if max_sector_pct <= 25:
        print(f"✓ Sector distribution: {len(sectors)} sectors, max {max_sector_pct}% in one")
    else:
        errors.append(f"✗ Sector concentration: {max_sector_pct}% in one sector")

    # Check 4: Mcap distribution
    mcap = Counter(v.get("mcap_bucket", "?") for v in data.values())
    print(f"✓ Mcap: LARGE={mcap.get('LARGE',0)}, MID={mcap.get('MID',0)}, SMALL={mcap.get('SMALL',0)}")

    # Check 5: Priority stocks
    priority = sum(1 for v in data.values() if v.get("is_priority"))
    print(f"✓ Priority stocks: {priority}")

    # Check 6: Suspended stocks
    suspended = sum(1 for v in data.values() if v.get("is_suspended"))
    print(f"✓ Suspended stocks: {suspended}")

    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("\n✓ All checks passed")


if __name__ == "__main__":
    main()
