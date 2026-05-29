"""V3 Funnel Logger — tracks stock attrition through each pipeline stage."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


class FunnelLogger:
    """Tracks how many stocks pass each stage of the V3 pipeline.

    Usage:
        funnel = FunnelLogger(date="2026-05-27", profile="vishal-live-v2")
        funnel.log_stage("universe_loaded", 504)
        funnel.log_stage("data_available", 487, drop_reasons={"no_dhan_id": 4, "no_data": 13})
        funnel.log_stage("passed_liquidity", 312, drop_reasons={"volume_low": 175})
        ...
        funnel.set_regime("TRENDING_UP")
        funnel.set_fallback_triggered(False)
        funnel.write_daily_json()
    """

    def __init__(self, date: str = None, profile: str = "unknown"):
        self.date = date or datetime.now(IST).strftime("%Y-%m-%d")
        self.profile = profile
        self.stages: list[dict] = []
        self.regime: str = "UNKNOWN"
        self.fallback_triggered: bool = False
        self._start_time = datetime.now(IST)

    def log_stage(self, stage_name: str, passed_count: int, drop_reasons: dict = None):
        """Record a pipeline stage with count and optional drop reasons."""
        entry = {
            "stage": stage_name,
            "passed": passed_count,
            "timestamp": datetime.now(IST).isoformat(),
        }
        if drop_reasons:
            entry["drop_reasons"] = drop_reasons

        self.stages.append(entry)
        logger.info("[FUNNEL] %s: %d passed%s",
                    stage_name, passed_count,
                    f" (dropped: {drop_reasons})" if drop_reasons else "")

    def set_regime(self, regime: str):
        self.regime = regime

    def set_fallback_triggered(self, triggered: bool):
        self.fallback_triggered = triggered

    def write_daily_json(self) -> Path:
        """Write funnel log to logs/funnel_YYYY-MM-DD.json."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = LOGS_DIR / f"funnel_{self.date}.json"

        # Build stage summary dict
        stage_summary = {}
        for s in self.stages:
            stage_summary[s["stage"]] = s["passed"]

        # Build drop reasons summary
        all_drops = {}
        for s in self.stages:
            if "drop_reasons" in s:
                for reason, count in s["drop_reasons"].items():
                    all_drops[reason] = all_drops.get(reason, 0) + count

        data = {
            "date": self.date,
            "profile": self.profile,
            "regime": self.regime,
            "generated_at": datetime.now(IST).isoformat(),
            "elapsed_seconds": (datetime.now(IST) - self._start_time).total_seconds(),
            "stages": stage_summary,
            "stage_details": self.stages,
            "fallback_triggered": self.fallback_triggered,
            "drop_reasons_summary": all_drops,
        }

        output_path.write_text(json.dumps(data, indent=2))
        logger.info("Funnel log written: %s", output_path)
        return output_path

    def get_summary_line(self) -> str:
        """One-line summary for log output."""
        parts = [f"{s['stage']}={s['passed']}" for s in self.stages]
        return f"[FUNNEL] {self.date} | regime={self.regime} | " + " → ".join(parts)
