"""V3 Diversifier — enforces sector and market-cap distribution limits.

Prevents Nifty50 domination by capping stocks per sector and
optionally enforcing mcap bucket quotas.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_PER_SECTOR = 2
DEFAULT_MCAP_QUOTAS = {"LARGE": 0.4, "MID": 0.3, "SMALL": 0.3}


def apply_diversification(
    candidates: list[dict],
    universe_dict: dict,
    max_per_sector: int = DEFAULT_MAX_PER_SECTOR,
    mcap_quotas: Optional[dict] = None,
    max_output: int = 20,
) -> list[dict]:
    """Apply sector and mcap diversification to candidate list.

    Args:
        candidates: List of signal dicts, must have 'symbol' key.
                    Should be pre-sorted by score/quality (best first).
        universe_dict: From load_universe() — {symbol: {sector, mcap_bucket, ...}}
        max_per_sector: Maximum stocks from same sector (default 2)
        mcap_quotas: Optional {LARGE: 0.4, MID: 0.3, SMALL: 0.3}
                     If provided, enforces approximate distribution.
        max_output: Maximum candidates to return (default 20)

    Returns:
        Filtered list respecting sector caps and optional mcap quotas.
        Preserves input order within constraints.
    """
    if not candidates:
        return []

    # Sort by score if available (preserve existing order otherwise)
    sorted_candidates = sorted(
        candidates,
        key=lambda c: c.get("score", c.get("long_score", 0)),
        reverse=True,
    )

    sector_count: dict[str, int] = {}
    mcap_count: dict[str, int] = {"LARGE": 0, "MID": 0, "SMALL": 0}
    result = []

    # Compute mcap limits if quotas provided
    mcap_limits = None
    if mcap_quotas:
        mcap_limits = {
            bucket: max(1, int(max_output * quota))
            for bucket, quota in mcap_quotas.items()
        }

    for candidate in sorted_candidates:
        if len(result) >= max_output:
            break

        symbol = candidate.get("symbol", "")
        info = universe_dict.get(symbol, {})
        sector = info.get("sector", "Unknown")
        mcap_bucket = info.get("mcap_bucket", "LARGE")

        # Sector cap check
        if sector_count.get(sector, 0) >= max_per_sector:
            logger.debug("Diversifier: skipping %s — sector %s at cap (%d)",
                         symbol, sector, max_per_sector)
            continue

        # Mcap quota check (if enabled)
        if mcap_limits and mcap_count.get(mcap_bucket, 0) >= mcap_limits.get(mcap_bucket, max_output):
            logger.debug("Diversifier: skipping %s — mcap %s at quota",
                         symbol, mcap_bucket)
            continue

        # Accept candidate
        result.append(candidate)
        sector_count[sector] = sector_count.get(sector, 0) + 1
        mcap_count[mcap_bucket] = mcap_count.get(mcap_bucket, 0) + 1

    logger.info(
        "Diversifier: %d → %d candidates (sectors: %d, mcap: L=%d M=%d S=%d)",
        len(candidates), len(result), len(sector_count),
        mcap_count["LARGE"], mcap_count["MID"], mcap_count["SMALL"],
    )
    return result
