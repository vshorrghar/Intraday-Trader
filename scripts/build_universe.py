#!/usr/bin/env python3
"""Build nifty500_constituents.json from official CSV + Dhan security IDs.

Reads config/nifty500_official.csv and maps each symbol to its Dhan security_id,
sector, mcap_bucket, and priority/suspension flags.

Usage:
    cd ~/dev-sandbox && .venv/bin/python scripts/build_universe.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV_PATH = ROOT / "config" / "nifty500_official.csv"
IDS_PATH = ROOT / "config" / "nse_security_ids.json"
OUTPUT_PATH = ROOT / "config" / "nifty500_constituents.json"

# From selector_v2.py
BLACKLIST = {
    "MRF", "SAIL", "LAURUSLABS", "IPCALAB", "CONCOR", "PRESTIGE", "GNFC",
    "BSE", "SONACOMS", "ANGELONE", "PVRINOX", "PIIND", "MCDOWELL-N",
    "GODREJCP", "UBL", "TATASTEEL", "BPCL", "ASIANPAINT", "HINDUNILVR",
    "TATACONSUM", "HDFCLIFE", "ADANIPOWER", "BEL", "COFORGE", "IREDA",
    "NAUKRI", "BDL", "CANBK", "MAZDOCK", "ASTRAL", "FEDERALBNK", "OFSS",
    "BAJAJFINSV", "BAJFINANCE", "HEROMOTOCO", "BAJAJ-AUTO", "JSWSTEEL",
    "INDIGO", "COCHINSHIP",
}

WHITELIST = {
    "HINDZINC", "NESTLEIND", "PNBHOUSING", "BHEL", "ADANIENSOL", "NTPC",
    "SHRIRAMFIN", "GRANULES", "ULTRACEMCO", "GRASIM", "GAIL", "BOSCHLTD",
    "DRREDDY", "MOTHERSON", "PFC", "LICI", "POWERGRID", "CHOLAFIN",
    "TATACHEM", "IIFLSEC", "TIINDIA", "IRCON", "MARUTI",
}


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found")
        sys.exit(1)

    # Load existing security IDs
    security_ids = {}
    if IDS_PATH.exists():
        security_ids = json.loads(IDS_PATH.read_text())
        print(f"Loaded {len(security_ids)} security IDs from {IDS_PATH.name}")

    # Parse CSV
    stocks = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row.get("Symbol", "").strip()
            if not symbol:
                continue
            stocks.append({
                "symbol": symbol,
                "company": row.get("Company Name", "").strip(),
                "sector": row.get("Industry", "").strip(),
                "isin": row.get("ISIN Code", "").strip(),
            })

    print(f"Parsed {len(stocks)} stocks from CSV")

    # Assign mcap_bucket by position (CSV is roughly ordered by market cap)
    for i, s in enumerate(stocks):
        rank = i + 1
        if rank <= 100:
            s["mcap_bucket"] = "LARGE"
        elif rank <= 300:
            s["mcap_bucket"] = "MID"
        else:
            s["mcap_bucket"] = "SMALL"

    # Map security IDs + flags
    constituents = {}
    mapped = 0
    missing = []

    for s in stocks:
        sym = s["symbol"]
        sec_id = security_ids.get(sym)
        if sec_id:
            mapped += 1
        else:
            missing.append(sym)

        constituents[sym] = {
            "security_id": str(sec_id) if sec_id else None,
            "sector": s["sector"],
            "mcap_bucket": s["mcap_bucket"],
            "isin": s["isin"],
            "company": s["company"],
            "is_priority": sym in WHITELIST,
            "is_suspended": sym in BLACKLIST,
        }

    # Write output
    OUTPUT_PATH.write_text(json.dumps(constituents, indent=2))

    # Summary
    print(f"\nResults:")
    print(f"  Total stocks: {len(constituents)}")
    print(f"  Mapped to Dhan ID: {mapped} ({mapped*100//len(constituents)}%)")
    print(f"  Missing Dhan ID: {len(missing)}")
    print(f"  Priority (whitelist): {sum(1 for v in constituents.values() if v['is_priority'])}")
    print(f"  Suspended (blacklist): {sum(1 for v in constituents.values() if v['is_suspended'])}")
    print(f"  LARGE: {sum(1 for v in constituents.values() if v['mcap_bucket']=='LARGE')}")
    print(f"  MID: {sum(1 for v in constituents.values() if v['mcap_bucket']=='MID')}")
    print(f"  SMALL: {sum(1 for v in constituents.values() if v['mcap_bucket']=='SMALL')}")
    print(f"\n  Output: {OUTPUT_PATH}")

    if missing:
        print(f"\n  First 10 missing IDs: {missing[:10]}")


if __name__ == "__main__":
    main()
