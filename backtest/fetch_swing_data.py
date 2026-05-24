"""
Fetch daily OHLC data for swing universe via Dhan Data API.

Uses broker.get_daily_ohlc() which calls /v2/charts/historical.
Caches to cache/swing_daily/{symbol}_daily.json.
Rate limited: 1 second between API calls.

Per Rule 26: Dhan Data API is the primary data source. We pay for it — use it.

Usage:
    python -m backtest.fetch_swing_data
    python -m backtest.fetch_swing_data --force-refresh
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_DIR = Path(__file__).parent.parent / "cache" / "swing_daily"
MIN_CANDLES = 200  # Minimum candles needed for swing scoring (20-DMA needs 200)


def fetch_swing_universe_data(
    broker,
    cache_dir: str = str(CACHE_DIR),
    force_refresh: bool = False,
) -> dict[str, dict]:
    """Fetch 1 year of daily OHLC for all stocks in FNO universe.

    Uses Dhan /v2/charts/historical endpoint via broker.get_daily_ohlc().
    Caches results to avoid repeated API calls.

    Args:
        broker: DhanBrokerClient instance (must have get_daily_ohlc method)
        cache_dir: directory to store cached JSON files
        force_refresh: if True, re-fetch even if cache exists

    Returns:
        dict of {symbol: ohlc_dict} for all stocks with >= 200 candles.
        ohlc_dict has keys: open, high, low, close, volume, timestamp
    """
    from backtest.universes import get_universe

    universe = get_universe("fno")
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    # Date range: 1 year ago to today
    today = datetime.now(IST).strftime("%Y-%m-%d")
    one_year_ago = (datetime.now(IST) - timedelta(days=365)).strftime("%Y-%m-%d")

    results = {}
    total = len(universe)
    fetched = 0
    cached = 0
    failed = 0

    for i, (symbol, sec_id) in enumerate(universe.items()):
        cache_file = cache_path / f"{symbol}_daily.json"

        # Check cache
        if not force_refresh and cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                if len(data.get("close", [])) >= MIN_CANDLES:
                    results[symbol] = data
                    cached += 1
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # Re-fetch if cache is corrupt

        # Fetch from Dhan API
        sec_id_str = str(sec_id)
        data = broker.get_daily_ohlc(
            security_id=sec_id_str,
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date=one_year_ago,
            to_date=today,
        )

        if data and len(data.get("close", [])) >= MIN_CANDLES:
            # Save to cache
            with open(cache_file, "w") as f:
                json.dump(data, f)
            results[symbol] = data
            fetched += 1
        elif data:
            # Got data but too few candles
            logger.debug("%s: only %d candles (need %d) — skipping",
                         symbol, len(data.get("close", [])), MIN_CANDLES)
            failed += 1
        else:
            logger.debug("%s: API returned None — skipping", symbol)
            failed += 1

        # Progress every 10 stocks
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{total} (fetched={fetched}, cached={cached}, failed={failed})")

        # Rate limit: 1 second between API calls
        time.sleep(1.0)

    print(f"\nSwing data fetch complete:")
    print(f"  Total universe: {total}")
    print(f"  From cache: {cached}")
    print(f"  Freshly fetched: {fetched}")
    print(f"  Failed/insufficient: {failed}")
    print(f"  Usable stocks (>={MIN_CANDLES} candles): {len(results)}")

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch swing daily OHLC data from Dhan")
    parser.add_argument("--force-refresh", action="store_true", help="Re-fetch all, ignore cache")
    parser.add_argument("--profile", default="vishal", help="Profile for broker auth")
    args = parser.parse_args()

    # Initialize broker
    from intraday.auth_server import get_authenticated_broker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print(f"Authenticating as profile: {args.profile}")
    broker = get_authenticated_broker(args.profile)
    if broker is None:
        print("ERROR: Could not authenticate broker. Check profile config.")
        sys.exit(1)

    print(f"Fetching daily OHLC for FNO universe (~188 stocks)...")
    print(f"Cache dir: {CACHE_DIR}")
    print(f"Force refresh: {args.force_refresh}")
    print()

    results = fetch_swing_universe_data(broker, force_refresh=args.force_refresh)
    print(f"\nDone. {len(results)} stocks ready for swing backtest.")


if __name__ == "__main__":
    main()
