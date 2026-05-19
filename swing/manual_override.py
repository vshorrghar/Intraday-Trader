"""
Manual override mechanism for swing trading emergencies.
Pause/resume trading, queue manual exits.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache")


def _pause_file(profile: str) -> Path:
    return CACHE_DIR / f"swing_paused_{profile}"


def _exit_queue_file(profile: str) -> Path:
    return CACHE_DIR / f"swing_manual_exits_{profile}.json"


def pause_swing_trading(profile: str, reason: str) -> bool:
    """Pause swing trading for a profile. Cron checks for flag, skips if exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    flag = _pause_file(profile)
    flag.write_text(json.dumps({
        "paused_at": datetime.now().isoformat(),
        "reason": reason,
        "profile": profile,
    }))
    logger.info("Swing trading PAUSED for %s: %s", profile, reason)
    return True


def resume_swing_trading(profile: str) -> bool:
    """Resume swing trading for a profile."""
    flag = _pause_file(profile)
    if flag.exists():
        flag.unlink()
        logger.info("Swing trading RESUMED for %s", profile)
        return True
    logger.info("Swing trading was not paused for %s", profile)
    return False


def is_paused(profile: str) -> tuple:
    """Check if swing trading is paused. Returns (paused: bool, reason: str|None)."""
    flag = _pause_file(profile)
    if flag.exists():
        try:
            data = json.loads(flag.read_text())
            return True, data.get("reason", "unknown")
        except Exception:
            return True, "flag file exists"
    return False, None


def manual_exit_position(profile: str, symbol: str, reason: str) -> bool:
    """Add symbol to manual exit queue. Monitor processes queue on next run."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    queue_file = _exit_queue_file(profile)

    queue = []
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text())
        except Exception:
            queue = []

    # Avoid duplicates
    if any(item["symbol"] == symbol for item in queue):
        logger.info("Symbol %s already in exit queue for %s", symbol, profile)
        return False

    queue.append({
        "symbol": symbol,
        "reason": reason,
        "queued_at": datetime.now().isoformat(),
    })
    queue_file.write_text(json.dumps(queue, indent=2))
    logger.info("Added %s to manual exit queue for %s: %s", symbol, profile, reason)
    return True


def get_manual_exit_queue(profile: str) -> list:
    """Get pending manual exits."""
    queue_file = _exit_queue_file(profile)
    if not queue_file.exists():
        return []
    try:
        return json.loads(queue_file.read_text())
    except Exception:
        return []


def clear_exit_from_queue(profile: str, symbol: str) -> bool:
    """Remove symbol from exit queue after processing."""
    queue_file = _exit_queue_file(profile)
    if not queue_file.exists():
        return False
    try:
        queue = json.loads(queue_file.read_text())
        queue = [item for item in queue if item["symbol"] != symbol]
        queue_file.write_text(json.dumps(queue, indent=2))
        return True
    except Exception:
        return False


def list_status(profile: str) -> dict:
    """Return full status for a profile."""
    paused, reason = is_paused(profile)
    queue = get_manual_exit_queue(profile)
    return {
        "profile": profile,
        "paused": paused,
        "pause_reason": reason,
        "manual_exit_queue": queue,
        "queue_count": len(queue),
    }
