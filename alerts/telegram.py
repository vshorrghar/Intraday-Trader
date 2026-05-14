"""Telegram alert sender for intraday auto-trader.

Config-aware: reads token/chat_id/enabled from config.
If not enabled or no token: silently returns (never crashes).
"""
from __future__ import annotations

import logging
import yaml
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Global config cache
_config = None

def _load_config():
    global _config
    if _config is not None:
        return _config
    try:
        cfg_path = Path(__file__).parent.parent / "config" / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        _config = cfg.get("telegram", {})
    except Exception:
        _config = {}
    return _config

def _is_enabled():
    cfg = _load_config()
    return cfg.get("enabled", False) and cfg.get("token") and cfg.get("chat_id")

def _get_creds():
    cfg = _load_config()
    return cfg.get("token", ""), cfg.get("chat_id", "")

def send_alert(token: str, chat_id: str, message: str) -> bool:
    if not token or not chat_id:
        return False
    try:
        url = TELEGRAM_API.format(token=token)
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram alert failed: %s", e)
        return False

def send_trade_placed(profile, symbol, direction, entry, target, sl, qty, capital):
    if not _is_enabled(): return
    token, chat_id = _get_creds()
    mode = "LIVE" if "live" in profile else "PAPER"
    emoji = "\U0001f534 LIVE" if "live" in profile else "\U0001f9ea PAPER"
    msg = (f"{emoji} Order Placed\n"
           f"Profile: {profile}\n"
           f"{direction} {symbol} x {qty} @ \u20b9{entry:.2f}\n"
           f"Target: \u20b9{target:.2f} | SL: \u20b9{sl:.2f}\n"
           f"Capital: \u20b9{capital:.0f}")
    send_alert(token, chat_id, msg)

def send_target_hit(profile, symbol, entry, exit_price, gross, net):
    if not _is_enabled(): return
    token, chat_id = _get_creds()
    msg = (f"\U0001f3af Target Hit!\n"
           f"Profile: {profile}\n"
           f"{symbol}: \u20b9{entry:.2f} \u2192 \u20b9{exit_price:.2f}\n"
           f"Gross: \u20b9{gross:+.0f} | Net: \u20b9{net:+.0f}")
    send_alert(token, chat_id, msg)

def send_sl_hit(profile, symbol, entry, exit_price, loss):
    if not _is_enabled(): return
    token, chat_id = _get_creds()
    msg = (f"\U0001f6d1 Stop Loss Hit\n"
           f"Profile: {profile}\n"
           f"{symbol}: \u20b9{entry:.2f} \u2192 \u20b9{exit_price:.2f}\n"
           f"Loss: \u20b9{loss:+.0f}")
    send_alert(token, chat_id, msg)

def send_force_exit(profile, symbol, pnl):
    if not _is_enabled(): return
    token, chat_id = _get_creds()
    msg = (f"\u23f0 Force Exit (3:15 PM)\n"
           f"Profile: {profile}\n"
           f"{symbol} P&L: \u20b9{pnl:+.0f}")
    send_alert(token, chat_id, msg)

def send_daily_summary(profile, trades, total_pnl, win_rate):
    if not _is_enabled(): return
    token, chat_id = _get_creds()
    emoji = "\u2705" if total_pnl >= 0 else "\u274c"
    mode = "LIVE" if "live" in profile else "PAPER"
    msg = (f"\U0001f4ca Daily Summary ({mode})\n"
           f"Profile: {profile}\n"
           f"{emoji} P&L: \u20b9{total_pnl:+.0f}\n"
           f"Trades: {trades} | Win Rate: {win_rate:.0f}%")
    send_alert(token, chat_id, msg)

# Legacy aliases for backward compatibility
alert_order_placed = lambda token, chat_id, profile, symbol, action, qty, price, target, sl, mode: send_trade_placed(profile, symbol, action, price, target, sl, qty, price*qty)
alert_target_hit = lambda token, chat_id, profile, symbol, pnl, mode: send_target_hit(profile, symbol, 0, 0, pnl, pnl)
alert_sl_hit = lambda token, chat_id, profile, symbol, pnl, mode: send_sl_hit(profile, symbol, 0, 0, pnl)
alert_session_complete = lambda token, chat_id, profile, total_pnl, trades, wins, mode: send_daily_summary(profile, trades, total_pnl, wins/trades*100 if trades>0 else 0)
