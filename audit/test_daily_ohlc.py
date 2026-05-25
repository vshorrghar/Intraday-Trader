#!/usr/bin/env python3
"""Quick test: verify get_daily_ohlc works with Dhan API."""
import sys
sys.path.insert(0, ".")

import yaml
from intraday.auth_server import authenticate_broker

with open("config/profiles/vishal.yaml") as f:
    cfg = yaml.safe_load(f)

broker = authenticate_broker("dhan", cfg.get("dhan", cfg), dry_run=False, profile="vishal")
print(f"Broker: {type(broker).__name__}")

result = broker.get_daily_ohlc(
    security_id="11536",  # TCS
    from_date="2025-06-01",
    to_date="2026-05-23",
)

if result and "close" in result:
    n = len(result["close"])
    print(f"SUCCESS: TCS has {n} daily candles")
    print(f"  First close: {result['close'][0]}")
    print(f"  Last close: {result['close'][-1]}")
else:
    print(f"FAILED: result = {result}")
