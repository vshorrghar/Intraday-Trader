"""Telegram alert sender for intraday auto-trader."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_alert(token: str, chat_id: str, message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping alert")
        return False
    try:
        url = TELEGRAM_API.format(token=token)
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram alert failed: %s", e)
        return False


def alert_order_placed(token: str, chat_id: str, profile: str, symbol: str,
                        action: str, qty: int, price: float, target: float,
                        sl: float, mode: str) -> None:
    emoji = "🔴 LIVE" if mode == "LIVE" else "🧪 PAPER"
    msg = (
        f"{emoji} Order Placed\n"
        f"Profile: {profile}\n"
        f"{action} {symbol} × {qty} @ ₹{price:.2f}\n"
        f"Target: ₹{target:.2f} | SL: ₹{sl:.2f}"
    )
    send_alert(token, chat_id, msg)


def alert_order_failed(token: str, chat_id: str, profile: str, symbol: str,
                        error: str, mode: str) -> None:
    emoji = "🔴 LIVE" if mode == "LIVE" else "🧪 PAPER"
    msg = (
        f"{emoji} ❌ Order Failed\n"
        f"Profile: {profile}\n"
        f"Symbol: {symbol}\n"
        f"Error: {error}"
    )
    send_alert(token, chat_id, msg)


def alert_target_hit(token: str, chat_id: str, profile: str, symbol: str,
                      pnl: float, mode: str) -> None:
    msg = (
        f"🎯 Target Hit\n"
        f"Profile: {profile}\n"
        f"{symbol} P&L: ₹{pnl:+.0f}"
    )
    send_alert(token, chat_id, msg)


def alert_sl_hit(token: str, chat_id: str, profile: str, symbol: str,
                  pnl: float, mode: str) -> None:
    msg = (
        f"🛑 Stop Loss Hit\n"
        f"Profile: {profile}\n"
        f"{symbol} P&L: ₹{pnl:+.0f}"
    )
    send_alert(token, chat_id, msg)


def alert_session_complete(token: str, chat_id: str, profile: str,
                            total_pnl: float, trades: int, wins: int,
                            mode: str) -> None:
    emoji = "🔴 LIVE" if mode == "LIVE" else "🧪 PAPER"
    wr = wins / trades * 100 if trades > 0 else 0
    pnl_emoji = "✅" if total_pnl >= 0 else "❌"
    msg = (
        f"{emoji} Session Complete\n"
        f"Profile: {profile}\n"
        f"{pnl_emoji} P&L: ₹{total_pnl:+.0f}\n"
        f"Trades: {trades} | Win Rate: {wr:.0f}%"
    )
    send_alert(token, chat_id, msg)
