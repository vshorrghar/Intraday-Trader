"""V3 Regime Detector — classifies market regime once per day at 09:45 IST.

RELAXED 2026-05-28: thresholds widened (Universal Relaxation Pass).
API restored 2026-05-28: detect_regime + persistence preserved (Phase 7 dependency).

Thresholds (RELAXED):
  TRENDING_UP:   nifty_change > +0.25%  (was +0.4%)
  TRENDING_DOWN: nifty_change < -0.25%  (was -0.4%)
  RANGING:       |nifty_change| < 0.4%  (was 0.3%)
  VOLATILE:      vix > 25 OR range > 1.2%  (was vix > 22)
  UNCLEAR:       anything else
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

# Module-level string constants (for imports)
VOLATILE = "VOLATILE"
TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGING = "RANGING"
UNCLEAR = "UNCLEAR"

# Relaxed thresholds (2026-05-28 Universal Relaxation Pass)
TRENDING_UP_THRESHOLD = 0.25
TRENDING_DOWN_THRESHOLD = -0.25
RANGING_THRESHOLD = 0.4
VOLATILE_VIX_THRESHOLD = 25
VOLATILE_RANGE_THRESHOLD = 1.2


def _get_regime_file(date: str) -> Path:
    return LOGS_DIR / f"regime_{date}.json"


def _load_cached_regime(date: str) -> Optional[dict]:
    """Load cached regime for today if already computed."""
    path = _get_regime_file(date)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if data.get("regime") and data.get("date") == date:
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _save_regime(date: str, result: dict) -> None:
    """Persist regime decision for the day."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = _get_regime_file(date)
    path.write_text(json.dumps(result, indent=2))
    logger.info("Regime locked for %s: %s", date, result["regime"])


def classify_regime(
    nifty_change_pct: float,
    nifty_30min_range_pct: float = 0.5,
    breadth_pct: float = 50.0,
    vix: float = 16.0,
) -> dict:
    """Pure classification logic — no I/O, no caching.

    Supports both simple (2-param) and full (4-param) calling conventions.
    When breadth_pct is provided (not default 50), uses full decision tree.

    Args:
        nifty_change_pct: (NIFTY now - prev close) / prev close * 100
        nifty_30min_range_pct: (high - low) / open * 100 for first 30 min
        breadth_pct: % of Nifty500 stocks where ltp > prev_close (0-100)
        vix: India VIX value

    Returns:
        {"regime": str, "reasoning": str, "inputs": dict}
    """
    inputs = {
        "nifty_change_pct": nifty_change_pct,
        "nifty_30min_range_pct": nifty_30min_range_pct,
        "breadth_pct": breadth_pct,
        "vix": vix,
    }

    # Decision tree (RELAXED thresholds)
    if vix > VOLATILE_VIX_THRESHOLD or nifty_30min_range_pct > VOLATILE_RANGE_THRESHOLD:
        regime = VOLATILE
        reasoning = f"VIX={vix:.1f} (>{VOLATILE_VIX_THRESHOLD}) or 30min range={nifty_30min_range_pct:.2f}% (>{VOLATILE_RANGE_THRESHOLD}%)"
    elif nifty_change_pct > TRENDING_UP_THRESHOLD and breadth_pct > 60:
        regime = TRENDING_UP
        reasoning = f"Nifty +{nifty_change_pct:.2f}% (>{TRENDING_UP_THRESHOLD}) and breadth {breadth_pct:.0f}% (>60)"
    elif nifty_change_pct < TRENDING_DOWN_THRESHOLD and breadth_pct < 40:
        regime = TRENDING_DOWN
        reasoning = f"Nifty {nifty_change_pct:.2f}% (<{TRENDING_DOWN_THRESHOLD}) and breadth {breadth_pct:.0f}% (<40)"
    elif abs(nifty_change_pct) < RANGING_THRESHOLD and 40 <= breadth_pct <= 60 and vix < 18:
        regime = RANGING
        reasoning = f"Nifty {nifty_change_pct:+.2f}% (flat), breadth {breadth_pct:.0f}% (balanced), VIX {vix:.1f} (<18)"
    else:
        regime = UNCLEAR
        reasoning = f"Mixed signals: Nifty {nifty_change_pct:+.2f}%, breadth {breadth_pct:.0f}%, VIX {vix:.1f}"

    return {"regime": regime, "reasoning": reasoning, "inputs": inputs}


def detect_regime(
    nifty_change_pct: float,
    nifty_30min_range_pct: float = 0.5,
    breadth_pct: float = 50.0,
    vix: float = 16.0,
    date: str = None,
    force: bool = False,
) -> dict:
    """Detect regime with daily lock.

    First call of the day computes and caches. Subsequent calls return cached.

    Args:
        nifty_change_pct, nifty_30min_range_pct, breadth_pct, vix: market inputs
        date: Override date (for testing). Defaults to today IST.
        force: If True, recompute even if cached (for testing only).

    Returns:
        {"regime": str, "reasoning": str, "inputs": dict, "date": str, "locked_at": str}
    """
    if date is None:
        date = datetime.now(IST).strftime("%Y-%m-%d")

    # Check cache (regime locks for the day)
    if not force:
        cached = _load_cached_regime(date)
        if cached:
            logger.info("Regime already locked for %s: %s (cached)", date, cached["regime"])
            return cached

    # Compute fresh
    result = classify_regime(nifty_change_pct, nifty_30min_range_pct, breadth_pct, vix)
    result["date"] = date
    result["locked_at"] = datetime.now(IST).isoformat()

    # Persist
    _save_regime(date, result)
    return result
