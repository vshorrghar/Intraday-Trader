#!/usr/bin/env python3
"""Orphan-order detector (Bug B / B-2 family).

A STOP_LOSS order left PENDING on Dhan for a symbol with NO matching open
position can fire later and create an unprotected phantom position. This
flags that condition.

IMPORTANT: this script is READ-ONLY and does NOT authenticate. It reads the
shared token minted by pre_auth_dhan.py (config/.dhan_token_<client_id>.json)
and uses it directly. It never calls authenticate_broker, so it cannot mint a
new session or invalidate the live trading session under Dhan's one-IP rule.
If the shared token is missing/expired, it reports DATA_FAIL (never all-clear).

Prints JSON. Exit codes:
  0 = checked successfully, no orphans
  1 = token missing / data fetch failed (CANNOT verify -- treat as alert)
  2 = orphans found

Usage: python3 scripts/check_orphan_orders.py [PROFILE]   (default vishal-live-v2)
"""
from __future__ import annotations

import sys
sys.path.insert(0, "/home/ec2-user/dev-sandbox")

import json
from collections import defaultdict
from pathlib import Path

import requests
import yaml

DEFAULT_PROFILE = "vishal-live-v2"
PENDING_STATUSES = {"PENDING", "TRANSIT", "TRIGGER_PENDING", "PART_TRADED", "MODIFIED"}
BASE_URL = "https://api.dhan.co/v2"


def _fail(msg: dict) -> None:
    # FAIL LOUD: never let a failed check look like a clean all-clear.
    # JSON to stdout (machine-readable), plus an ERROR line to stderr so it
    # stands out in cron logs and trips any stderr-based alerting. Exit 1 so
    # callers/cron can distinguish "could not verify" from "no orphans".
    print(json.dumps(msg))
    print(f"ERROR orphan-check could NOT verify account: {msg.get('status')} "
          f"{msg.get('http', '')} {msg.get('error', '')}".rstrip(), file=sys.stderr)
    sys.exit(1)


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROFILE

    with open(f"config/profiles/{profile}.yaml") as fh:
        cfg = yaml.safe_load(fh)
    client_id = str(cfg.get("dhan", {}).get("client_id", ""))
    if not client_id:
        _fail({"status": "CONFIG_FAIL", "error": f"no client_id in {profile}.yaml"})

    # READ the shared token file -- do NOT authenticate (avoid session churn).
    token_file = Path("config") / f".dhan_token_{client_id}.json"
    if not token_file.exists():
        _fail({"status": "DATA_FAIL", "error": f"shared token file missing: {token_file} "
               "(pre_auth_dhan.py must run first)"})
    try:
        tok = json.loads(token_file.read_text())
    except Exception as exc:  # noqa: BLE001
        _fail({"status": "DATA_FAIL", "error": f"token file unreadable: {exc}"})

    access_token = tok.get("access_token", "")
    if not access_token:
        _fail({"status": "DATA_FAIL", "error": "token file has no access_token"})

    headers = {"access-token": access_token, "client-id": client_id,
               "Content-Type": "application/json"}

    # --- Orders (raw call; distinguishes empty-genuine from cannot-read) ---
    try:
        r = requests.get(f"{BASE_URL}/orders", headers=headers, timeout=15)
    except Exception as exc:  # noqa: BLE001
        _fail({"status": "DATA_FAIL", "error": str(exc)})
    if r.status_code != 200:
        _fail({"status": "DATA_FAIL", "http": r.status_code, "body": r.text[:300]})

    orders = r.json()
    if isinstance(orders, dict):
        orders = orders.get("data", []) or []

    # --- Positions (raw call, same token) ---
    try:
        rp = requests.get(f"{BASE_URL}/positions", headers=headers, timeout=15)
    except Exception as exc:  # noqa: BLE001
        _fail({"status": "DATA_FAIL", "error": f"positions: {exc}"})
    if rp.status_code != 200:
        _fail({"status": "DATA_FAIL", "http": rp.status_code, "body": rp.text[:300]})

    positions = rp.json()
    if isinstance(positions, dict):
        positions = positions.get("data", positions.get("positions", [])) or []

    open_qty: dict[str, int] = defaultdict(int)
    for pos in positions:
        sym = str(pos.get("tradingSymbol", "")).upper()
        qty = int(pos.get("netQty", pos.get("quantity", 0)) or 0)
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
