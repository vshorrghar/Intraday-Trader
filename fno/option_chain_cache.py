"""Option chain cache layer for F&O mark-to-market.

Caches Dhan option chain responses for 5 minutes.
All profiles share the same cache file.
"""
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_path(index: str, expiry: str) -> Path:
    """Return cache file path for given index+expiry."""
    safe_expiry = expiry.replace("-", "").replace("/", "")
    return CACHE_DIR / f"option_chain_{index}_{safe_expiry}.json"


def get_cached_chain(index: str, expiry: str) -> dict | None:
    """Return cached option chain if fresh (< 5 min old), else None."""
    path = _cache_path(index, expiry)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Cache read failed for %s: %s", path.name, e)
        return None


def save_chain_to_cache(index: str, expiry: str, chain_data: dict) -> None:
    """Save option chain to cache file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(index, expiry)
    try:
        with open(path, "w") as f:
            json.dump(chain_data, f)
        logger.debug("Cached option chain: %s", path.name)
    except Exception as e:
        logger.warning("Cache write failed: %s", e)


def fetch_option_chain_with_cache(broker, index: str, expiry: str = "") -> dict:
    """Fetch option chain with caching + rate limiting.

    Args:
        broker: DhanBrokerClient instance (authenticated)
        index: 'NIFTY', 'BANKNIFTY', 'FINNIFTY'
        expiry: expiry date string (for cache key)

    Returns:
        dict with option chain data, or empty dict on failure
    """
    # Check cache first
    cached = get_cached_chain(index, expiry or "current")
    if cached:
        logger.debug("Using cached chain for %s", index)
        return cached

    # Fetch from Dhan with rate limiting
    time.sleep(2)  # Rate limit: 2s between calls
    try:
        chain = broker.get_option_chain(index)
        if chain and chain.get("strikes"):
            save_chain_to_cache(index, expiry or "current", chain)
            return chain
        else:
            logger.warning("Dhan option chain empty for %s", index)
            return {}
    except Exception as e:
        logger.warning("Dhan option chain fetch failed for %s: %s", index, e)
        return {}
