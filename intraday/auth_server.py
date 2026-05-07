"""Broker authentication server for the intraday auto-trader.

Handles daily broker login for both Dhan and Zerodha via two modes:

**MODE 1 — TOTP-based (headless, Dhan only)**:
    POST to ``https://auth.dhan.co/app/generateAccessToken`` with client_id,
    PIN, and a TOTP code generated from a stored secret.  No browser needed.

**MODE 2 — OAuth browser flow (both brokers)**:
    Start a Flask callback server on ``http://127.0.0.1:5000/callback``,
    open the broker login page in the default browser, and exchange the
    redirect token for an access token.

Session tokens are persisted to ``config/.broker_session.json`` so that
repeated runs on the same trading day reuse the token without re-login.

In **dry-run mode** authentication is skipped entirely and a
``DryRunBrokerClient`` is returned.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import requests

from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_FILE = Path("config/.broker_session.json")  # default; overridden by profile
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 5000
CALLBACK_URL = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"


def _get_session_file() -> Path:
    """Get the profile-specific session file path."""
    try:
        from config.profile import get_session_file
        return get_session_file()
    except (ImportError, Exception):
        return SESSION_FILE

DHAN_AUTH_BASE = "https://auth.dhan.co"
DHAN_GENERATE_TOKEN_URL = f"{DHAN_AUTH_BASE}/app/generateAccessToken"
DHAN_GENERATE_CONSENT_URL = f"{DHAN_AUTH_BASE}/app/generate-consent"
DHAN_CONSUME_CONSENT_URL = f"{DHAN_AUTH_BASE}/app/consumeApp-consent"
DHAN_LOGIN_URL = f"{DHAN_AUTH_BASE}/login/consentApp-login"

KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"


# ---------------------------------------------------------------------------
# DryRunBrokerClient
# ---------------------------------------------------------------------------

class DryRunBrokerClient(BrokerClient):
    """A simulated broker client for dry-run mode.

    Implements the full ``BrokerClient`` interface without making any real
    broker API calls.  Used when the ``--live`` flag is not set so the rest
    of the pipeline can run end-to-end.
    """

    _order_counter: int = 0

    def __init__(self, daily_capital_limit: float = 150_000.0) -> None:
        self.daily_capital_limit = daily_capital_limit

    def authenticate(self) -> bool:
        logger.info("DryRun: authentication skipped (dry-run mode)")
        return True

    def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        product_type: str,
        quantity: int,
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> dict:
        DryRunBrokerClient._order_counter += 1
        fake_id = f"DRY-{DryRunBrokerClient._order_counter:06d}"
        logger.info(
            "DryRun place_order: %s %s x%d @ %.2f → %s",
            transaction_type, symbol, quantity, price, fake_id,
        )
        return {"broker_order_id": fake_id, "status": "placed"}

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> dict:
        logger.info("DryRun modify_order: %s", order_id)
        return {"broker_order_id": str(order_id), "status": "modified"}

    def cancel_order(self, order_id: str) -> dict:
        logger.info("DryRun cancel_order: %s", order_id)
        return {"broker_order_id": str(order_id), "status": "cancelled"}

    def get_positions(self) -> list[dict]:
        logger.info("DryRun get_positions: returning empty list")
        return []

    def get_margins(self) -> dict:
        return {
            "available_cash": self.daily_capital_limit,
            "used_margin": 0.0,
        }

    # F&O methods for dry-run mode
    def place_fno_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        order_type: str,
        product_type: str,
        quantity: int,
        price: float = 0.0,
        trigger_price: float = 0.0,
    ) -> dict:
        DryRunBrokerClient._order_counter += 1
        fake_id = f"DRY-FNO-{DryRunBrokerClient._order_counter:06d}"
        logger.info(
            "DryRun place_fno_order: %s %s x%d @ %.2f → %s",
            transaction_type, tradingsymbol, quantity, price, fake_id,
        )
        return {"broker_order_id": fake_id, "status": "placed"}

    def get_fno_positions(self) -> list[dict]:
        logger.info("DryRun get_fno_positions: returning empty list")
        return []

    def get_fno_margins(self) -> dict:
        return {
            "available_margin": self.daily_capital_limit,
            "used_margin": 0.0,
            "span_margin": 0.0,
            "exposure_margin": 0.0,
        }

    def get_option_chain(self, index: str) -> dict:
        logger.info("DryRun get_option_chain: %s — returning empty (will use demo)", index)
        return {"index": index, "spot_price": 0, "strikes": []}


# ---------------------------------------------------------------------------
# Session file helpers
# ---------------------------------------------------------------------------

def _load_session(broker_name: str) -> Optional[dict]:
    """Load a same-day session from disk, or return ``None``."""
    if not SESSION_FILE.exists():
        return None

    try:
        data = json.loads(SESSION_FILE.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read session file: %s", exc)
        return None

    today = date.today().isoformat()
    if (
        data.get("broker") == broker_name
        and data.get("date") == today
        and data.get("access_token")
    ):
        # Check session age — reject if older than 6 hours
        saved_at = data.get("saved_at")
        if saved_at:
            from datetime import datetime
            age_hours = (datetime.now() - datetime.fromisoformat(saved_at)).total_seconds() / 3600
            if age_hours > 6:
                logger.info("Session too old (%.1f hours) — re-authenticating", age_hours)
                return None
        logger.info("Reusing same-day session for %s (date=%s)", broker_name, today)
        return data

    logger.info("Session file exists but is stale or for a different broker")
    return None


def _save_session(broker_name: str, access_token: str, client_id: str = "") -> None:
    """Persist a session to ``config/.broker_session.json``."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "broker": broker_name,
        "date": date.today().isoformat(),
        "saved_at": __import__("datetime").datetime.now().isoformat(),
        "access_token": access_token,
        "client_id": client_id,
    }
    SESSION_FILE.write_text(json.dumps(payload, indent=2))
    logger.info("Session saved for %s", broker_name)


def _delete_session() -> None:
    """Remove the session file (e.g. on token expiry)."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        logger.info("Deleted stale session file")


# ---------------------------------------------------------------------------
# Dhan TOTP-based auth (headless — MODE 1)
# ---------------------------------------------------------------------------

def _dhan_totp_auth(client_id: str, pin: str, totp_secret: str) -> Optional[str]:
    """Authenticate with Dhan using TOTP (no browser needed).

    POST ``https://auth.dhan.co/app/generateAccessToken``
    with ``dhanClientId``, ``pin``, and ``totp`` parameters.
    """
    try:
        import pyotp
    except ImportError:
        logger.error("pyotp not installed — cannot use TOTP auth")
        return None

    totp_code = pyotp.TOTP(totp_secret).now()
    logger.info("Dhan TOTP auth: generated code for client %s", client_id)

    url = (
        f"{DHAN_GENERATE_TOKEN_URL}"
        f"?dhanClientId={client_id}&pin={pin}&totp={totp_code}"
    )
    try:
        resp = requests.post(url, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token") or data.get("accessToken") or data.get("token")
            if token:
                logger.info("Dhan TOTP auth succeeded")
                return str(token)
            logger.error("Dhan TOTP auth: no token in response: %s", data)
        else:
            logger.error("Dhan TOTP auth failed — HTTP %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Dhan TOTP auth request failed: %s", exc)

    return None


# ---------------------------------------------------------------------------
# OAuth browser flow helpers (MODE 2)
# ---------------------------------------------------------------------------

def _run_flask_callback_server(result_holder: dict, shutdown_event: threading.Event) -> None:
    """Start a minimal Flask server that captures the OAuth callback.

    The server writes the received query parameters into *result_holder*
    and signals *shutdown_event* once a callback is received.
    """
    from flask import Flask, request as flask_request

    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)

    # Suppress werkzeug request logs
    wlog = logging.getLogger("werkzeug")
    wlog.setLevel(logging.ERROR)

    @app.route("/callback")
    def callback():  # type: ignore[no-untyped-def]
        result_holder.update(flask_request.args.to_dict())
        shutdown_event.set()
        return "<h3>Authentication successful. You can close this tab.</h3>"

    # Run in a daemon thread so it doesn't block the main process
    app.run(host=CALLBACK_HOST, port=CALLBACK_PORT, use_reloader=False)


def _start_callback_server() -> tuple[dict, threading.Event, threading.Thread]:
    """Launch the Flask callback server in a background thread.

    Returns:
        (result_holder, shutdown_event, server_thread)
    """
    result_holder: dict = {}
    shutdown_event = threading.Event()
    server_thread = threading.Thread(
        target=_run_flask_callback_server,
        args=(result_holder, shutdown_event),
        daemon=True,
    )
    server_thread.start()
    # Give Flask a moment to bind the port
    time.sleep(0.5)
    return result_holder, shutdown_event, server_thread


# ---------------------------------------------------------------------------
# Dhan OAuth browser flow (MODE 2)
# ---------------------------------------------------------------------------

def _dhan_oauth_browser(client_id: str, api_key: str, api_secret: str) -> Optional[str]:
    """Dhan 3-step OAuth: generate-consent → browser login → consume-consent.

    1. POST ``/app/generate-consent?client_id={id}`` → ``consentAppId``
    2. Open browser to ``/login/consentApp-login?consentAppId={id}``
    3. Callback receives ``tokenId``
    4. POST ``/app/consumeApp-consent?tokenId={id}`` → ``access_token``
    """
    # Step 1 — generate consent
    headers = {"app_id": api_key, "app_secret": api_secret, "Content-Type": "application/json"}
    try:
        resp = requests.post(
            f"{DHAN_GENERATE_CONSENT_URL}?client_id={client_id}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error("Dhan generate-consent failed — HTTP %s: %s", resp.status_code, resp.text)
            return None
        consent_data = resp.json()
        consent_app_id = consent_data.get("consentAppId") or consent_data.get("consent_app_id")
        if not consent_app_id:
            logger.error("Dhan generate-consent: no consentAppId in response: %s", consent_data)
            return None
    except Exception as exc:
        logger.error("Dhan generate-consent request failed: %s", exc)
        return None

    # Step 2 — open browser for user login
    result_holder, shutdown_event, _ = _start_callback_server()
    login_url = f"{DHAN_LOGIN_URL}?consentAppId={consent_app_id}"
    logger.info("Opening Dhan login in browser: %s", login_url)
    webbrowser.open(login_url)

    # Wait for callback (up to 120 seconds)
    if not shutdown_event.wait(timeout=120):
        logger.error("Dhan OAuth: timed out waiting for callback")
        return None

    token_id = result_holder.get("tokenId") or result_holder.get("token_id")
    if not token_id:
        logger.error("Dhan OAuth callback missing tokenId: %s", result_holder)
        return None

    # Step 3 — consume consent to get access token
    try:
        resp = requests.post(
            f"{DHAN_CONSUME_CONSENT_URL}?tokenId={token_id}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error("Dhan consume-consent failed — HTTP %s: %s", resp.status_code, resp.text)
            return None
        token_data = resp.json()
        access_token = token_data.get("access_token") or token_data.get("accessToken")
        if not access_token:
            logger.error("Dhan consume-consent: no access_token in response: %s", token_data)
            return None
        logger.info("Dhan OAuth browser flow succeeded")
        return str(access_token)
    except Exception as exc:
        logger.error("Dhan consume-consent request failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Zerodha OAuth browser flow (MODE 2)
# ---------------------------------------------------------------------------

def _zerodha_oauth_browser(api_key: str, api_secret: str) -> Optional[str]:
    """Zerodha Kite Connect OAuth flow.

    1. Open ``https://kite.zerodha.com/connect/login?v=3&api_key=<key>``
    2. Callback receives ``request_token``
    3. Call ``kite.generate_session(request_token, api_secret)``
    """
    try:
        from kiteconnect import KiteConnect  # type: ignore[import-untyped]
    except ImportError:
        logger.error("kiteconnect SDK not installed — cannot authenticate Zerodha")
        return None

    kite = KiteConnect(api_key=api_key)

    # Start callback server
    result_holder, shutdown_event, _ = _start_callback_server()

    login_url = f"{KITE_LOGIN_URL}?v=3&api_key={api_key}"
    logger.info("Opening Zerodha Kite login in browser: %s", login_url)
    webbrowser.open(login_url)

    # Wait for callback (up to 120 seconds)
    if not shutdown_event.wait(timeout=120):
        logger.error("Zerodha OAuth: timed out waiting for callback")
        return None

    request_token = result_holder.get("request_token")
    status = result_holder.get("status", "")
    if not request_token or status != "success":
        logger.error("Zerodha OAuth callback error: %s", result_holder)
        return None

    # Exchange request_token for access_token
    try:
        session_data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = session_data.get("access_token")
        if not access_token:
            logger.error("Zerodha generate_session: no access_token: %s", session_data)
            return None
        logger.info("Zerodha OAuth browser flow succeeded")
        return str(access_token)
    except Exception as exc:
        logger.error("Zerodha generate_session failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def authenticate_broker(
    broker_name: str,
    broker_config: dict,
    dry_run: bool = True,
) -> BrokerClient:
    """Authenticate with the selected broker and return a ready ``BrokerClient``.

    Args:
        broker_name: ``"dhan"`` or ``"zerodha"``.
        broker_config: The broker-specific config section from config.yaml.
        dry_run: If ``True``, skip auth and return a ``DryRunBrokerClient``.

    Returns:
        A concrete ``BrokerClient`` instance with a valid access token set.

    Raises:
        RuntimeError: If authentication fails after all attempts.
    """
    from intraday.broker_base import broker_factory

    # --- Dry-run mode: skip auth entirely ---
    if dry_run:
        logger.info("Dry-run mode — skipping broker authentication")
        return DryRunBrokerClient()

    name = broker_name.strip().lower()

    # --- Check for existing same-day session ---
    session = _load_session(name)
    if session:
        access_token = session["access_token"]
        config_with_token = {**broker_config, "access_token": access_token}
        client = broker_factory(name, config_with_token)
        logger.info("Reusing same-day %s session", name)
        return client

    # --- Fresh authentication ---
    access_token: Optional[str] = None

    if name == "dhan":
        # Try TOTP first (headless) if pin and totp_secret are available
        pin = broker_config.get("pin", "")
        totp_secret = broker_config.get("totp_secret", "")
        if pin and totp_secret:
            logger.info("Dhan: attempting TOTP-based auth (headless)")
            access_token = _dhan_totp_auth(
                client_id=broker_config.get("client_id", ""),
                pin=pin,
                totp_secret=totp_secret,
            )

        # Fall back to OAuth browser flow
        if not access_token:
            logger.info("Dhan: falling back to OAuth browser flow")
            access_token = _dhan_oauth_browser(
                client_id=broker_config.get("client_id", ""),
                api_key=broker_config.get("api_key", ""),
                api_secret=broker_config.get("api_secret", ""),
            )

    elif name == "zerodha":
        # Zerodha always uses OAuth browser flow
        logger.info("Zerodha: starting OAuth browser flow")
        access_token = _zerodha_oauth_browser(
            api_key=broker_config.get("api_key", ""),
            api_secret=broker_config.get("api_secret", ""),
        )

    else:
        raise ValueError(f"Unsupported broker: {broker_name}")

    if not access_token:
        _delete_session()
        raise RuntimeError(
            f"Failed to authenticate with {broker_name}. "
            "Check credentials and try again."
        )

    # Persist session for same-day reuse
    _save_session(name, access_token, client_id=broker_config.get("client_id", ""))

    # Build the real broker client with the fresh token
    config_with_token = {**broker_config, "access_token": access_token}
    client = broker_factory(name, config_with_token)
    logger.info("%s authentication complete", name.capitalize())
    return client
