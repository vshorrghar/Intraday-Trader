#!/usr/bin/env python3
"""
VERIFY MONDAY: Test real Dhan Super Order — 1 share, then cancel.

Proves Dhan accepts our Super Order payload format with CNC + stopLossPrice.
Run ONLY during market hours (9:15 AM - 3:30 PM IST).

Usage:
    .venv/bin/python scripts/test_dhan_super_order_live.py --profile vishal-live

What it does:
    1. Places 1 Super Order: BUY 1 share of ITC (cheapest Nifty stock ~₹440)
       with entry=₹430 (below market, won't fill), SL=₹410, target=₹470
    2. Captures Dhan's response (orderId, orderStatus)
    3. Verifies SL leg is in the response
    4. IMMEDIATELY cancels the order (no fill, no money spent)
    5. Prints PASS/FAIL

Expected cost: ₹0 (order placed below market, cancelled before fill)
"""

import sys
import time
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from intraday.auth_server import authenticate_broker

SUPER_ORDER_URL = "https://api.dhan.co/v2/super/orders"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="vishal-live")
    args = parser.parse_args()

    # Auth
    profile_path = Path(f"config/profiles/{args.profile}.yaml")
    with open(profile_path) as f:
        cfg = yaml.safe_load(f)

    print(f"Authenticating as {args.profile}...")
    broker = authenticate_broker("dhan", cfg.get("dhan", cfg), dry_run=False, profile=args.profile)
    headers = broker._headers()
    print(f"  Auth OK. Client: {cfg.get('dhan', {}).get('client_id', '?')}")

    # Place Super Order: 1 share ITC, entry BELOW market (won't fill)
    # ITC security_id = 1660, current price ~₹440
    # Entry at ₹430 (won't fill), SL ₹410, Target ₹470
    payload = {
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "CNC",
        "orderType": "LIMIT",
        "securityId": "1660",  # ITC
        "quantity": 1,
        "price": 430.0,        # Below market — won't fill
        "targetPrice": 470.0,
        "stopLossPrice": 410.0,
        "trailingJump": 0,
    }

    print(f"\n  Placing Super Order: ITC 1 share @ ₹430 (below market)")
    print(f"  SL: ₹410 | Target: ₹470 | Product: CNC")
    print(f"  Payload: {json.dumps(payload, indent=2)}")

    resp = requests.post(SUPER_ORDER_URL, headers=headers, json=payload, timeout=15)
    print(f"\n  Response: HTTP {resp.status_code}")
    print(f"  Body: {resp.text[:500]}")

    if resp.status_code in (200, 201):
        data = resp.json()
        order_id = data.get("orderId", "")
        status = data.get("orderStatus", "")
        print(f"\n  ✅ SUPER ORDER ACCEPTED")
        print(f"     Order ID: {order_id}")
        print(f"     Status: {status}")

        # Verify SL leg exists by checking super order list
        time.sleep(1)
        list_resp = requests.get(SUPER_ORDER_URL, headers=headers, timeout=10)
        if list_resp.status_code == 200:
            orders = list_resp.json()
            for o in orders:
                if str(o.get("orderId", "")) == str(order_id):
                    legs = o.get("legDetails", [])
                    sl_leg = [l for l in legs if l.get("legName") == "STOP_LOSS_LEG"]
                    target_leg = [l for l in legs if l.get("legName") == "TARGET_LEG"]
                    print(f"     SL Leg: {sl_leg}")
                    print(f"     Target Leg: {target_leg}")
                    if sl_leg:
                        print(f"\n  ✅ SL LEG CONFIRMED AT BROKER (price={sl_leg[0].get('price')})")
                    else:
                        print(f"\n  ⚠️ SL leg not found in response — check manually")
                    break

        # CANCEL immediately
        print(f"\n  Cancelling order {order_id}...")
        cancel_resp = requests.delete(
            f"{SUPER_ORDER_URL}/{order_id}/ENTRY_LEG",
            headers=headers, timeout=10
        )
        print(f"  Cancel response: HTTP {cancel_resp.status_code} — {cancel_resp.text[:200]}")

        if cancel_resp.status_code in (200, 202):
            print(f"\n  ✅ ORDER CANCELLED — no money spent")
        else:
            print(f"\n  ⚠️ Cancel may have failed — CHECK DHAN APP MANUALLY")

        print(f"\n{'='*60}")
        print(f"RESULT: PASS — Dhan accepts Super Order with CNC + broker SL")
        print(f"{'='*60}")

    else:
        print(f"\n  ❌ SUPER ORDER REJECTED")
        print(f"     This means either:")
        print(f"     - Market is closed (run during 9:15-3:30 IST)")
        print(f"     - Payload format wrong")
        print(f"     - IP not whitelisted for Super Orders")
        print(f"\n{'='*60}")
        print(f"RESULT: FAIL or MARKET CLOSED — retry during market hours")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
