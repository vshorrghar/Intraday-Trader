"""V3 Data Health Gate — validates data quality before trading."""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum percentage of valid candidates required to proceed
MIN_VALID_RATIO = 0.80


def check_data_health(candidates: list[dict[str, Any]]) -> dict:
    """Check data quality of fetched candidates.

    A candidate is "valid" if it has:
    - open > 0
    - volume > 0
    - ltp > 0

    Args:
        candidates: List of dicts with at least {symbol, open, volume, ltp}

    Returns:
        {
            "healthy": bool,
            "valid_count": int,
            "total": int,
            "valid_ratio": float,
            "drop_reasons": {"zero_open": N, "zero_volume": N, "zero_ltp": N}
        }
    """
    if not candidates:
        return {
            "healthy": False,
            "valid_count": 0,
            "total": 0,
            "valid_ratio": 0.0,
            "drop_reasons": {"no_candidates": 1},
        }

    total = len(candidates)
    zero_open = 0
    zero_volume = 0
    zero_ltp = 0
    valid_count = 0

    for c in candidates:
        has_open = float(c.get("open", 0) or 0) > 0
        has_volume = int(c.get("volume", 0) or 0) > 0
        has_ltp = float(c.get("ltp", 0) or 0) > 0

        if not has_open:
            zero_open += 1
        if not has_volume:
            zero_volume += 1
        if not has_ltp:
            zero_ltp += 1

        if has_open and has_volume and has_ltp:
            valid_count += 1

    valid_ratio = valid_count / total if total > 0 else 0.0
    healthy = valid_ratio >= MIN_VALID_RATIO

    result = {
        "healthy": healthy,
        "valid_count": valid_count,
        "total": total,
        "valid_ratio": round(valid_ratio, 3),
        "drop_reasons": {
            "zero_open": zero_open,
            "zero_volume": zero_volume,
            "zero_ltp": zero_ltp,
        },
    }

    if not healthy:
        logger.warning(
            "DATA_UNHEALTHY: only %d/%d (%.0f%%) candidates have valid OHLCV. "
            "Reasons: open=0 (%d), volume=0 (%d), ltp=0 (%d)",
            valid_count, total, valid_ratio * 100,
            zero_open, zero_volume, zero_ltp,
        )
    else:
        logger.info("Data health OK: %d/%d valid (%.0f%%)", valid_count, total, valid_ratio * 100)

    return result
