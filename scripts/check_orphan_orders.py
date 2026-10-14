#!/usr/bin/env python3
"""Orphan-order detector (Bug B / B-2 family).

A STOP_LOSS order left PENDING on Dhan for a symbol with NO matching open
position can fire later and create an unprotected phantom position. This
flags that condition.

Read-only. Prints JSON. Exit codes:
  0 = checked successfully, no orphans
  1 = auth or data fetch failed (CANNOT verify -- treat as alert, NOT all-clear)
  2 = orphans found

Usage: python3 scripts/check_orphan_orders.py [PROFILE]   (default vishal-live-v2)
"""
from __future__ import annotations

import sys
sys.path.insert(0, "/home/ec2-user/dev-sandbox")

import json
from collections import defaultdict

import requests
import yaml

from intraday.auth_server import authenticate_broker

DEFAULT_PROFILE = "vishal-live-v2"
PENDING_STATUSES = {"PENDING", "TRANSIT", "TRIGGER_PENDING", "PART_TRADED", "MODIFIED"}


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROFILE

    with open(f"config/profiles/{profile}.yaml") as fh:
        cfg = yaml.safe_load(fh)

    try:
        broker = authenticate_broker("dhan", cfg.get("dhan", {}), dry_run=False, profile=profile)
    except Exception as exc:
        print(json.dumps({"status": "AUTH_FAIL", "error": str(exc)}))
        sys.exit(1)

    # Confirm the token actually works before trusting any empty result.
    # broker.get_order_list()/get_positions() return [] on HTTP error, so a
    # bare empty list is ambiguous -- a raw call lets us distinguish
    # "genuinely no orders" from "could not read account".
    try:
        r = requests.get(
            "https://api.dhan.co/v2/orders",
            headers={"access-token": broker.access_token,
                     "client-id": broker.client_id,
                     "Content-Type": "application/json"},
            timeout=15,
        )
    except Exception as exc:
        print(json.dumps({"status": "DATA_FAIL", "error": str(exc)}))
        sys.exit(1)

    if r.status_code != 200:
        print(json.dumps({"status": "DATA_FAIL", "http": r.status_code, "body": r.text[:300]}))
        sys.exit(1)  # cannot verify -- explicitly NOT all-clear

    orders = r.json()
    if isinstance(orders, dict):
        orders = orders.get("data", []) or []

    open_qty: dict[str, int] = defaultdict(int)
    for pos in broker.get_positions():
        sym = str(pos.get("tradingsymbol", "")).upper()
        qty = int(pos.get("quantity", 0) or 0)
        if sym and qty != 0:
            open_qty[sym] += qty

    orphans = []
    pending_seen = 0
    for o in orders:
        status = str(o.get("orderStatus", "")).upper()
        if status not in PENDING_STATUSES:
            continue
        pending_seen += 1
        sym = str(o.get("tradingSymbol", "")).upper()
        if open_qty.get(sym, 0) == 0:
            orphans.append({
                "symbol": sym,
                "order_id": o.get("orderId"),
                "order_type": o.get("orderType"),
                "transaction_type": o.get("transactionType"),
                "status": status,
                "quantity": o.get("quantity"),
                "trigger_price": o.get("triggerPrice"),
            })

    result = {
        "status": "OK",
        "profile": profile,
        "open_positions": len(open_qty),
        "pending_orders": pending_seen,
        "orphan_count": len(orphans),
        "orphans": orphans,
    }
    print(json.dumps(result, indent=2))
    sys.exit(2 if orphans else 0)


if __name__ == "__main__":
    main()
