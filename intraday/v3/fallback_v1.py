"""V3 Fallback — triggers Claude ranker at 10:30 IST if V2 produced 0 trades.

Only fires in TRENDING_UP regime. Max 1 per day.
Uses already-screened top 20 candidates (NOT raw 500).
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from intraday.v3.ranker_claude import rank_top_3

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

CREATE_FALLBACK_TABLE = """
CREATE TABLE IF NOT EXISTS v3_fallback_log (
    date TEXT PRIMARY KEY,
    triggered_at TEXT,
    candidates_count INTEGER,
    selected_symbol TEXT,
    reasoning TEXT
)
"""


def trigger_v1_fallback(
    candidates: list[dict],
    regime: str,
    bedrock_client,
    db_path: str,
    today: str = None,
) -> list[dict]:
    """Trigger Claude fallback if V2 produced 0 trades.

    ONLY fires when:
    - regime == 'TRENDING_UP'
    - 0 trades placed today (check DB)
    - fallback_count_today < 1 (max 1 per day)

    Args:
        candidates: Pre-screened top 20 candidates from V2 pipeline
        regime: Current market regime
        bedrock_client: Bedrock client instance
        db_path: Path to profile SQLite DB
        today: Override date for testing

    Returns:
        List of max 1 trade signal (from Claude's top pick).
        Empty list if conditions not met or Claude skips.
    """
    if today is None:
        today = datetime.now(IST).strftime("%Y-%m-%d")

    # Gate 1: Only in TRENDING_UP
    if regime != "TRENDING_UP":
        logger.info("V1 fallback: skipped — regime is %s (need TRENDING_UP)", regime)
        return []

    # Gate 2: Check if V2 already traded today
    trades_today = _count_trades_today(db_path, today)
    if trades_today > 0:
        logger.info("V1 fallback: skipped — V2 already placed %d trades today", trades_today)
        return []

    # Gate 3: Max 1 fallback per day
    if _fallback_already_triggered(db_path, today):
        logger.info("V1 fallback: skipped — already triggered today")
        return []

    # Gate 4: Need candidates
    if not candidates:
        logger.info("V1 fallback: skipped — no candidates available")
        return []

    logger.info("V1 fallback: TRIGGERING — regime=%s, 0 trades today, %d candidates",
                regime, len(candidates))

    # Call Claude ranker
    ranked = rank_top_3(candidates, regime, bedrock_client)

    # Take only top 1 (conservative fallback)
    result = ranked[:1]

    # Log fallback
    selected_symbol = result[0]["symbol"] if result else None
    reasoning = result[0].get("claude_reasoning", "") if result else "Claude returned no picks"
    _log_fallback(db_path, today, len(candidates), selected_symbol, reasoning)

    if result:
        logger.info("V1 fallback: selected %s (rank 1)", selected_symbol)
    else:
        logger.info("V1 fallback: Claude returned no picks")

    return result


def _count_trades_today(db_path: str, today: str) -> int:
    """Count trades placed today (non-rejected/cancelled)."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM intraday_trades WHERE trade_date = ? "
            "AND status NOT IN ('REJECTED', 'CANCELLED', 'PENDING')",
            (today,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0


def _fallback_already_triggered(db_path: str, today: str) -> bool:
    """Check if fallback was already triggered today."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(CREATE_FALLBACK_TABLE)
        row = conn.execute(
            "SELECT 1 FROM v3_fallback_log WHERE date = ?", (today,)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def _log_fallback(db_path: str, today: str, candidates_count: int,
                  selected_symbol: Optional[str], reasoning: str):
    """Record fallback trigger in DB."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(CREATE_FALLBACK_TABLE)
        conn.execute(
            "INSERT OR REPLACE INTO v3_fallback_log "
            "(date, triggered_at, candidates_count, selected_symbol, reasoning) "
            "VALUES (?, ?, ?, ?, ?)",
            (today, datetime.now(IST).isoformat(), candidates_count,
             selected_symbol, reasoning[:500] if reasoning else None)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to log fallback: %s", exc)
