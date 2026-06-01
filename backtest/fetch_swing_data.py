"""
Fetch daily OHLC data for Nifty 500 universe via Dhan /v2/charts/historical.

Caches to cache/swing_daily/{SYMBOL}.json with structured format.
Rate limited: 200ms between API calls.

Usage:
    .venv/bin/python backtest/fetch_swing_data.py --profile vishal-live
    .venv/bin/python backtest/fetch_swing_data.py --profile vishal-live --force
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
MIN_CANDLES = 100  # Minimum candles to consider file valid


def fetch_all_swing_data(
    broker,
    force: bool = False,
    lookback_days: int = 180,
) -> dict:
    """Fetch daily OHLC for Nifty 500 universe and cache to disk.

    Args:
        broker: DhanBrokerClient instance with get_daily_ohlc method.
        force: If True, re-fetch even if cache exists.
        lookback_days: How many calendar days back to fetch (default 180 = ~6 months).

    Returns:
        dict with keys: success_count, failed_count, cached_count, total
    """
    from backtest.data_loader import load_nifty500_universe

    universe = load_nifty500_universe()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now(IST).strftime("%Y-%m-%d")
    from_date = (datetime.now(IST) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    total = len(universe)
    success_count = 0
    cached_count = 0
    failed_count = 0
    failed_symbols = []

    print(f"Fetching daily OHLC for {total} stocks")
    print(f"  Period: {from_date} to {today} ({lookback_days} calendar days)")
    print(f"  Cache dir: {CACHE_DIR}")
    print(f"  Force refresh: {force}")
    print()

    for idx, (symbol, sec_id) in enumerate(universe.items(), 1):
        cache_file = CACHE_DIR / f"{symbol}.json"

        # Skip if cached and not forcing
        if not force and cache_file.exists():
            try:
                with open(cache_file) as f:
                    existing = json.load(f)
                candle_count = len(existing.get("candles", []))
                if candle_count >= MIN_CANDLES:
                    cached_count += 1
                    if idx % 50 == 0:
                        print(f"  [{idx}/{total}] cached={cached_count} fetched={success_count} failed={failed_count}")
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # Re-fetch on corrupt cache

        # Fetch from Dhan API
        try:
            data = broker.get_daily_ohlc(
                security_id=str(sec_id),
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date=from_date,
                to_date=today,
            )
        except Exception as e:
            logger.warning("Error fetching %s: %s", symbol, e)
            data = None

        if data and data.get("open") and len(data["open"]) >= MIN_CANDLES:
            # Convert Dhan flat-list format to structured candles
            candles = []
            timestamps = data.get("timestamp", [])
            opens = data["open"]
            highs = data["high"]
            lows = data["low"]
            closes = data["close"]
            volumes = data.get("volume", [0] * len(opens))

            for i in range(len(opens)):
                # Dhan timestamps are epoch seconds
                if timestamps and i < len(timestamps):
                    ts = timestamps[i]
                    dt = datetime.fromtimestamp(ts, tz=IST)
                    date_str = dt.strftime("%Y-%m-%d")
                else:
                    date_str = ""

                candles.append({
                    "date": date_str,
                    "open": opens[i],
                    "high": highs[i],
                    "low": lows[i],
                    "close": closes[i],
                    "volume": volumes[i] if i < len(volumes) else 0,
                })

            # Write structured cache file
            cache_obj = {
                "symbol": symbol,
                "security_id": str(sec_id),
                "fetched_at": datetime.now(IST).isoformat(),
                "from_date": from_date,
                "to_date": today,
                "candles": candles,
            }
            with open(cache_file, "w") as f:
                json.dump(cache_obj, f, indent=2)

            success_count += 1
            logger.info("Fetched %s: %d candles", symbol, len(candles))

        elif data and data.get("open"):
            # Got data but too few candles
            n = len(data["open"])
            logger.debug("%s: only %d candles (need %d)", symbol, n, MIN_CANDLES)
            failed_count += 1
            failed_symbols.append(f"{symbol} ({n} candles)")
        else:
            logger.debug("%s: API returned None or empty", symbol)
            failed_count += 1
            failed_symbols.append(f"{symbol} (no data)")

        # Rate limit: 200ms between API calls
        time.sleep(0.2)

        # Progress every 50 stocks
        if idx % 50 == 0:
            print(f"  [{idx}/{total}] cached={cached_count} fetched={success_count} failed={failed_count}")

    print()
    print("=" * 60)
    print(f"SWING DATA FETCH COMPLETE")
    print(f"  Universe size: {total}")
    print(f"  From cache: {cached_count}")
    print(f"  Freshly fetched: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total usable: {cached_count + success_count}")
    print("=" * 60)

    if failed_symbols and len(failed_symbols) <= 30:
        print(f"\nFailed symbols ({len(failed_symbols)}):")
        for s in failed_symbols:
            print(f"    {s}")

    return {
        "total": total,
        "success_count": success_count,
        "cached_count": cached_count,
        "failed_count": failed_count,
        "failed_symbols": failed_symbols,
    }


def verify_data_quality(sample_size: int = 5) -> bool:
    """Spot-check cached data for sanity."""
    if not CACHE_DIR.exists():
        print("ERROR: cache/swing_daily/ does not exist")
        return False

    files = list(CACHE_DIR.glob("*.json"))
    print(f"\nDATA QUALITY CHECK")
    print(f"  Total cached files: {len(files)}")

    if len(files) == 0:
        print("  ERROR: No cached files found")
        return False

    # Check candle counts
    low_candle_files = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            n = len(data.get("candles", []))
            if n < MIN_CANDLES:
                low_candle_files.append((f.stem, n))
        except Exception:
            low_candle_files.append((f.stem, -1))

    if low_candle_files:
        print(f"  WARNING: {len(low_candle_files)} files with < {MIN_CANDLES} candles")

    # Spot check
    import random
    sample_files = random.sample(files, min(sample_size, len(files)))
    all_ok = True

    print(f"\n  Spot-checking {len(sample_files)} stocks:")
    for f in sample_files:
        with open(f) as fh:
            data = json.load(fh)
        candles = data.get("candles", [])
        symbol = data.get("symbol", f.stem)
        n = len(candles)

        issues = []
        if n < MIN_CANDLES:
            issues.append(f"only {n} candles")

        # OHLC sanity: close should be between low and high
        for c in candles[-5:]:  # Check last 5
            if c["close"] < c["low"] or c["close"] > c["high"]:
                issues.append("OHLC sanity fail")
                break

        # No future dates
        today_str = datetime.now(IST).strftime("%Y-%m-%d")
        for c in candles[-3:]:
            if c.get("date", "") > today_str:
                issues.append("future date detected")
                break

        status = "PASS" if not issues else f"FAIL ({', '.join(issues)})"
        if issues:
            all_ok = False
        print(f"    {symbol}: {n} candles — {status}")

    return all_ok


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch daily OHLC for Nifty 500 swing universe")
    parser.add_argument("--profile", default="vishal-live", help="Profile for broker auth")
    parser.add_argument("--force", action="store_true", help="Re-fetch all, ignore cache")
    parser.add_argument("--lookback", type=int, default=180, help="Calendar days to look back (default 180)")
    parser.add_argument("--verify-only", action="store_true", help="Only run data quality check")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.verify_only:
        verify_data_quality()
        return

    # Authenticate broker
    import yaml
    from intraday.auth_server import authenticate_broker

    profile = args.profile
    profile_path = Path(__file__).parent.parent / "config" / "profiles" / f"{profile}.yaml"
    if not profile_path.exists():
        print(f"ERROR: Profile config not found: {profile_path}")
        sys.exit(1)

    print(f"Authenticating as profile: {profile}")
    with open(profile_path) as f:
        cfg = yaml.safe_load(f)

    broker_cfg = cfg.get("dhan", cfg)
    broker = authenticate_broker("dhan", broker_cfg, dry_run=False, profile=profile)
    if broker is None:
        print("ERROR: Could not authenticate broker.")
        sys.exit(1)

    # Check that get_daily_ohlc exists
    if not hasattr(broker, "get_daily_ohlc"):
        print("ERROR: Broker does not have get_daily_ohlc method.")
        print("       Ensure intraday/dhan_broker.py has the method added.")
        sys.exit(1)

    # Fetch data
    result = fetch_all_swing_data(
        broker=broker,
        force=args.force,
        lookback_days=args.lookback,
    )

    # Verify quality
    verify_data_quality()


if __name__ == "__main__":
    main()
