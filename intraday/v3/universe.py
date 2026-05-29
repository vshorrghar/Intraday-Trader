"""V3 Universe loader — loads Nifty500 constituents with Dhan IDs."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONSTITUENTS_PATH = Path(__file__).parent.parent.parent / "config" / "nifty500_constituents.json"
_universe_cache = None


def load_universe() -> dict:
    """Load Nifty500 universe from pre-built JSON.

    Returns dict: {symbol: {security_id, sector, mcap_bucket, isin, is_priority, is_suspended}}
    """
    global _universe_cache
    if _universe_cache is not None:
        return _universe_cache

    if not _CONSTITUENTS_PATH.exists():
        raise FileNotFoundError(
            f"Universe file not found: {_CONSTITUENTS_PATH}. "
            "Run: python scripts/build_universe.py"
        )

    data = json.loads(_CONSTITUENTS_PATH.read_text())
    assert len(data) >= 400, f"Universe too small: {len(data)} stocks (expected 500+)"

    # Filter to stocks with valid Dhan security_id
    valid = {k: v for k, v in data.items() if v.get("security_id")}
    logger.info("Universe loaded: %d total, %d with Dhan ID", len(data), len(valid))

    _universe_cache = data
    return data


def get_tradeable_universe() -> dict:
    """Returns only stocks with Dhan ID and not suspended."""
    universe = load_universe()
    return {
        sym: info for sym, info in universe.items()
        if info.get("security_id") and not info.get("is_suspended")
    }


def get_priority_stocks() -> set:
    """Returns set of priority/whitelist symbols."""
    universe = load_universe()
    return {sym for sym, info in universe.items() if info.get("is_priority")}


def get_sector_map() -> dict:
    """Returns {sector: [symbols]}."""
    universe = load_universe()
    sectors = {}
    for sym, info in universe.items():
        sector = info.get("sector", "Unknown")
        sectors.setdefault(sector, []).append(sym)
    return sectors
