#!/usr/bin/env python3
"""
Telegram Bot Skeleton — Intraday Trader

Phase 1: /ping and /status commands only.
Phase 4 will wire real trade alerts.

Usage:
    cd ~/dev-sandbox && .venv/bin/python alerts/telegram_bot.py

Config file (config/telegram.yaml):
    bot_token: "123456:ABC-DEF..."
    allowed_chat_ids:
      - "123456789"

Does NOT:
- Send real trade alerts (Phase 4)
- Modify any trading code
- Access profile credentials
- Place or cancel orders
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("telegram_bot")

IST = timezone(timedelta(hours=5, minutes=30))
POLL_INTERVAL = 2


def _api_url(token, method):
    return "https://api.telegram.org/bot" + token + "/" + method


def load_config():
    """Load bot config from config/telegram.yaml or env vars."""
    config_path = PROJECT_ROOT / "config" / "telegram.yaml"
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        return {
            "bot_token": cfg.get("bot_token", ""),
            "allowed_chat_ids": [str(c) for c in cfg.get("allowed_chat_ids", [])],
        }
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_ids = os.environ.get("TELEGRAM_ALLOWED_CHATS", "").split(",")
    return {"bot_token": token, "allowed_chat_ids": [c.strip() for c in chat_ids if c.strip()]}


def send_message(token, chat_id, text, parse_mode="Markdown"):
    """Send a message to a Telegram chat."""
    try:
        r = requests.post(
            _api_url(token, "sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        logger.error("Send failed: HTTP %d", r.status_code)
        return False
    except Exception as e:
        logger.error("Send exception: %s", e)
        return False


def get_updates(token, offset=0, timeout=30):
    """Long-poll for new messages."""
    try:
        r = requests.get(
            _api_url(token, "getUpdates"),
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 5,
        )
        if r.status_code == 200:
            return r.json().get("result", [])
        return []
    except requests.exceptions.Timeout:
        return []
    except Exception as e:
        logger.error("getUpdates error: %s", e)
        return []


def handle_ping(token, chat_id):
    """Respond to /ping."""
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    send_message(token, chat_id, "*Pong!*\n\nBot alive at `" + now + "`")


def handle_status(token, chat_id):
    """Respond to /status — show system overview."""
    now = datetime.now(IST)
    ist_min = now.hour * 60 + now.minute
    weekday = now.weekday()
    if weekday < 5 and 555 <= ist_min <= 930:
        market = "Open"
    else:
        market = "Closed"

    today_str = now.strftime("%Y-%m-%d")
    log_file = PROJECT_ROOT / "logs" / ("intraday_vishal-live_" + today_str + ".log")
    if log_file.exists():
        age = (time.time() - log_file.stat().st_mtime) / 60
        log_status = "Active (" + str(int(age)) + "m ago)" if age < 30 else "Stale (" + str(int(age)) + "m)"
    else:
        log_status = "No log today"

    msg = (
        "*Intraday Trader Status*\n\n"
        + "Time: `" + now.strftime("%H:%M:%S IST") + "`\n"
        + "Market: " + market + "\n"
        + "vishal-live log: " + log_status + "\n\n"
        + "*Profiles:*\n"
        + "  vishal-live: LIVE (15K)\n"
        + "  neha-live: STOPPED\n"
        + "  vishal: Paper (3L)\n"
        + "  neha: Paper (3L)\n\n"
        + "_Phase 1 skeleton_"
    )
    send_message(token, chat_id, msg)


def handle_help(token, chat_id):
    """Respond to /help."""
    msg = (
        "*Intraday Trader Bot*\n\n"
        "/ping - Check bot alive\n"
        "/status - System overview\n"
        "/help - This message\n\n"
        "_Phase 1 skeleton. Real alerts Phase 4._"
    )
    send_message(token, chat_id, msg)


COMMANDS = {
    "/ping": handle_ping,
    "/status": handle_status,
    "/help": handle_help,
    "/start": handle_help,
}


def main():
    config = load_config()
    token = config["bot_token"]
    allowed = config["allowed_chat_ids"]

    if not token:
        logger.error("No bot token. Set config/telegram.yaml or TELEGRAM_BOT_TOKEN env.")
        sys.exit(1)

    logger.info("Telegram bot starting (Phase 1 skeleton)")
    logger.info("Allowed chats: %s", allowed if allowed else "ALL")

    offset = 0
    while True:
        updates = get_updates(token, offset=offset, timeout=30)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()
            if not text:
                continue
            if allowed and chat_id not in allowed:
                logger.warning("Unauthorized: %s", chat_id)
                continue
            logger.info("Chat %s: %s", chat_id, text[:80])
            cmd = text.split()[0].lower().split("@")[0]
            handler = COMMANDS.get(cmd)
            if handler:
                handler(token, chat_id)
            elif text.startswith("/"):
                send_message(token, chat_id, "Unknown: `" + text + "`\nTry /help")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
