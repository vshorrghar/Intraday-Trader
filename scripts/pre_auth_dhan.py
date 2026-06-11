#!/usr/bin/env python3
"""Pre-authenticate Dhan accounts and store shared tokens.

Run ONCE before market open (9:25 AM IST / 03:55 UTC).
Generates one token per client_id. All profiles sharing that client_id
read from the same token file.

Token file: config/.dhan_token_{client_id}.json
Format: {"access_token": "...", "client_id": "...", "generated_at": "...", "date": "..."}

Usage:
    .venv/bin/python scripts/pre_auth_dhan.py
    
Cron:
    55 3 * * 1-5 cd ~/dev-sandbox && .venv/bin/python scripts/pre_auth_dhan.py >> logs/pre_auth.log 2>&1
"""

import json
import logging
import sys
import yaml
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pre_auth")

IST = timezone(timedelta(hours=5, minutes=30))
PROFILES_DIR = Path("config/profiles")
TOKEN_DIR = Path("config")


def get_unique_clients() -> dict:
    """Scan all profile YAMLs, return unique client_id → broker_config mapping."""
    clients = {}
    for f in sorted(PROFILES_DIR.glob("*.yaml")):
        if f.stem.startswith("_"):
            continue
        try:
            with open(f) as fh:
                cfg = yaml.safe_load(fh)
            dhan = cfg.get("dhan", {})
            cid = dhan.get("client_id", "")
            if cid and cid not in clients and cid != "REPLACE_ME":
                clients[cid] = {
                    "profile": f.stem,
                    "broker_config": dhan,
                }
        except Exception as e:
            logger.warning("Skipping %s: %s", f.name, e)
    return clients


def authenticate_client(client_id: str, broker_config: dict) -> str | None:
    """Authenticate one Dhan client_id via TOTP. Returns access_token or None."""
    from intraday.auth_server import _dhan_totp_auth
    
    pin = broker_config.get("pin", "")
    totp_secret = broker_config.get("totp_secret", "")
    
    if not pin or not totp_secret:
        logger.error("Missing pin or totp_secret for client_id %s", client_id)
        return None
    
    try:
        token = _dhan_totp_auth(
            client_id=client_id,
            pin=pin,
            totp_secret=totp_secret,
        )
        if token:
            logger.info("Auth SUCCESS for client_id %s", client_id)
            return token
        else:
            logger.error("Auth returned None for client_id %s", client_id)
            return None
    except Exception as e:
        logger.error("Auth FAILED for client_id %s: %s", client_id, e)
        return None


def save_shared_token(client_id: str, access_token: str) -> Path:
    """Save token to shared file that all profiles can read."""
    token_file = TOKEN_DIR / f".dhan_token_{client_id}.json"
    payload = {
        "access_token": access_token,
        "client_id": client_id,
        "generated_at": datetime.now(IST).isoformat(),
        "date": date.today().isoformat(),
    }
    token_file.write_text(json.dumps(payload, indent=2))
    logger.info("Shared token saved: %s", token_file)
    return token_file


def main():
    now = datetime.now(IST)
    logger.info("=== PRE-AUTH DHAN — %s ===", now.strftime("%Y-%m-%d %H:%M IST"))
    
    clients = get_unique_clients()
    logger.info("Found %d unique Dhan client_ids to authenticate", len(clients))
    
    success = 0
    for cid, info in clients.items():
        logger.info("Authenticating client_id %s (from profile: %s)...", cid, info["profile"])
        token = authenticate_client(cid, info["broker_config"])
        if token:
            save_shared_token(cid, token)
            success += 1
        else:
            logger.error("FAILED: client_id %s — will not have valid token today", cid)
    
    logger.info("=== DONE: %d/%d clients authenticated ===", success, len(clients))
    if success < len(clients):
        sys.exit(1)


if __name__ == "__main__":
    main()
