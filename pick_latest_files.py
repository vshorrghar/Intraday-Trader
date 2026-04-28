#!/usr/bin/env python3
"""Pick latest Groww XLSX files from Downloads and copy to input/.

Scans ~/Downloads for Groww export files, picks the newest of each type
(stocks, MF, P&L) independently, and copies them to input/ with standard names.

Groww file patterns:
  Stocks_Holdings_Statement_5440360876_DD-MM-YYYY.xlsx
  Mutual_Funds_5440360876_DD-MM-YYYY_DD-MM-YYYY.xlsx
  Stocks_PnL_Report_5440360876_DD-MM-YYYY_DD-MM-YYYY.xlsx
"""

import glob
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from typing import Optional

DOWNLOADS = os.path.expanduser("~/Downloads")
INPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input")

# Pattern → standard name mapping
# Each key is a list of prefixes to try (underscore and hyphen variants)
FILE_TYPES = {
    ("Stocks_Holdings_Statement", "Stocks-Holdings-Statement"): "Stocks_Holdings_Statement.xlsx",
    ("Mutual_Funds_5", "Mutual-Funds-5"): "Mutual_Funds.xlsx",  # "5" suffix to avoid matching Order_History
    ("Stocks_PnL_Report", "Stocks-PnL-Report"): "Stocks_PnL_Report.xlsx",
    ("Stocks_Order_History", "Stocks-Order-History"): "Stocks_Order_History.xlsx",
    ("Mutual_Funds_Order_History", "Mutual-Funds-Order-History", "MF_Order_History"): "MF_Order_History.xlsx",
}


def extract_date(filename: str) -> Optional[datetime]:
    """Extract the latest date from a Groww filename.

    Handles formats like:
      Stocks_Holdings_Statement_5440360876_11-03-2026.xlsx  → 11-03-2026
      Mutual_Funds_5440360876_10-07-2025_10-07-2025.xlsx   → 10-07-2025 (last date)
      Stocks_PnL_Report_5440360876_09-02-2026_11-03-2026.xlsx → 11-03-2026 (last date)
    """
    # Find all DD-MM-YYYY patterns in filename
    dates = re.findall(r"(\d{2}-\d{2}-\d{4})", filename)
    if not dates:
        return None

    # Parse all dates, return the latest one
    parsed = []
    for d in dates:
        try:
            parsed.append(datetime.strptime(d, "%d-%m-%Y"))
        except ValueError:
            continue

    return max(parsed) if parsed else None


def find_latest(prefixes) -> Optional[str]:
    """Find the latest file matching any of the prefixes in Downloads."""
    if isinstance(prefixes, str):
        prefixes = (prefixes,)

    all_files = []
    for prefix in prefixes:
        pattern = os.path.join(DOWNLOADS, f"{prefix}*.xlsx")
        all_files.extend(glob.glob(pattern))

    if not all_files:
        return None

    # Sort by extracted date (newest first)
    dated = []
    for f in all_files:
        dt = extract_date(os.path.basename(f))
        if dt:
            dated.append((dt, f))

    if not dated:
        # Fallback: sort by file modification time
        return max(all_files, key=os.path.getmtime)

    dated.sort(key=lambda x: x[0], reverse=True)
    return dated[0][1]


def main():
    os.makedirs(INPUT_DIR, exist_ok=True)

    print("🔍 Scanning ~/Downloads for latest Groww files...\n")

    for prefixes, target_name in FILE_TYPES.items():
        latest = find_latest(prefixes)
        target = os.path.join(INPUT_DIR, target_name)

        if latest:
            basename = os.path.basename(latest)
            dt = extract_date(basename)
            date_str = dt.strftime("%d-%b-%Y") if dt else "unknown date"

            # Check if it's newer than what we have
            if os.path.exists(target):
                existing_mtime = os.path.getmtime(target)
                new_mtime = os.path.getmtime(latest)
                if new_mtime <= existing_mtime:
                    print(f"  ⏭️  {target_name} — already up to date ({date_str})")
                    continue

            shutil.copy2(latest, target)
            print(f"  ✅ {target_name} ← {basename} ({date_str})")
        else:
            if os.path.exists(target):
                print(f"  ℹ️  {target_name} — no newer file found, keeping existing")
            else:
                print(f"  ❌ {target_name} — not found in Downloads")

    print(f"\n📂 Files in input/:")
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.endswith('.xlsx'):
            size = os.path.getsize(os.path.join(INPUT_DIR, f))
            print(f"  {f} ({size // 1024} KB)")


if __name__ == "__main__":
    main()
