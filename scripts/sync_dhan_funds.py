#!/usr/bin/env python3
"""Sync Dhan funds/balance to dashboard JSON + S3.

Pulls live margin data from Dhan API and writes to:
  dashboard/api/{profile}/dhan_live.json
Then syncs to S3 and invalidates CloudFront.

Cron: */30 4-10 * * 1-5 (every 30 min, 9:30 AM - 3:30 PM IST)

Usage:
    python scripts/sync_dhan_funds.py
"""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.profile_loader import load_profile
from intraday.auth_server import authenticate_broker

IST = timezone(timedelta(hours=5, minutes=30))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

ACTIVE_PROFILES = ["vishal-live-v2", "vishal-live"]
S3_BUCKET = "dev-sandbox-dashboard-176767908884"
CF_DIST = "E3NXP6TCRJKVX1"


def sync_profile(profile_name: str) -> bool:
    """Pull funds from Dhan and write dashboard JSON."""
    try:
        profile_cfg = load_profile(profile_name)
        dhan_cfg = profile_cfg.get("dhan", {})

        broker = authenticate_broker(
            broker_name="dhan",
            broker_config=dhan_cfg,
            dry_run=False,
            profile=profile_name,
        )
        if broker is None:
            log.error(f"[{profile_name}] Auth failed")
            return False

        funds = broker.get_margins()
        if not funds:
            log.error(f"[{profile_name}] get_margins empty")
            return False

        # DhanBrokerClient.get_margins() returns: {available_cash, used_margin}
        available = funds.get("available_cash", funds.get("availabelBalance", 0))
        used = funds.get("used_margin", funds.get("utilizedAmount", 0))
        sod = funds.get("sodLimit", round(available + used, 2))

        data = {
            "funds": funds,
            "summary": {
                "available_balance": available,
                "utilized_amount": used,
                "total_capital": round(available + used, 2),
                "sod_limit": sod,
            },
            "timestamp": datetime.now(IST).isoformat(),
            "profile": profile_name,
        }

        out_dir = Path(f"dashboard/api/{profile_name}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "dhan_live.json"
        out_file.write_text(json.dumps(data, indent=2, default=str))
        log.info(f"[{profile_name}] OK: available=Rs.{available:.2f} used=Rs.{used:.2f} total=Rs.{available+used:.2f}")
        return True

    except Exception as e:
        log.error(f"[{profile_name}] {type(e).__name__}: {e}")
        return False


def sync_to_s3():
    """Push dashboard API to S3 and invalidate CloudFront."""
    try:
        os.environ.setdefault("AWS_PROFILE", "vishal-admin")
        subprocess.run(
            ["aws", "s3", "sync", "dashboard/api/", f"s3://{S3_BUCKET}/api/",
             "--exclude", "*.DS_Store", "--exclude", "._*"],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["aws", "cloudfront", "create-invalidation",
             "--distribution-id", CF_DIST, "--paths", "/api/*", "/v2/app.html",
             "--region", "us-east-1"],
            check=True, capture_output=True, text=True
        )
        log.info("S3 synced + CloudFront invalidated")
    except subprocess.CalledProcessError as e:
        log.error(f"S3/CF error: {e.stderr}")


def main():
    success = 0
    for p in ACTIVE_PROFILES:
        if sync_profile(p):
            success += 1
            break  # Same Dhan account, one success is enough

    # Copy to both paths (same account)
    v2_file = Path("dashboard/api/vishal-live-v2/dhan_live.json")
    v1_file = Path("dashboard/api/vishal-live/dhan_live.json")
    if v2_file.exists():
        import shutil
        v1_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v2_file, v1_file)

    if success > 0:
        sync_to_s3()

    log.info(f"Done: {success} profile(s) synced")


if __name__ == "__main__":
    main()
