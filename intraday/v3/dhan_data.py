"""V3 Dhan Data Fetcher — bulk LTP and intraday candles.

Uses Dhan /v2/marketfeed/ltp for bulk quotes (100 per call).
Uses existing broker.get_historical_ohlc() for detailed candles.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DHAN_BASE = "https://api.dhan.co"
BATCH_SIZE = 100  # Dhan max per call


def fetch_bulk_ltp(broker, security_ids: list[str]) -> dict:
    """Fetch LTP for up to 500 stocks via Dhan /v2/marketfeed/ltp.

    Splits into batches of 100 (Dhan max per call).

    Args:
        broker: Authenticated DhanBrokerClient instance
        security_ids: List of Dhan security ID strings

    Returns:
        {security_id: {ltp, open, high, low, close, volume, prev_close}}
        Missing/failed stocks are omitted from result.
    """
    results = {}
    batches = [security_ids[i:i + BATCH_SIZE] for i in range(0, len(security_ids), BATCH_SIZE)]

    headers = {
        "access-token": broker.access_token,
        "client-id": str(broker.client_id),
        "Content-Type": "application/json",
    }

    for batch_idx, batch in enumerate(batches):
        try:
            payload = {"NSE_EQ": batch}
            resp = requests.post(
                f"{DHAN_BASE}/v2/marketfeed/ltp",
                json=payload,
                headers=headers,
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                # Dhan returns: {"data": {"NSE_EQ": {sec_id: {ltp, ...}, ...}}}
                nse_data = data.get("data", {}).get("NSE_EQ", {})
                if isinstance(nse_data, dict):
                    for sec_id, quote in nse_data.items():
                        if isinstance(quote, dict):
                            results[str(sec_id)] = {
                                "ltp": float(quote.get("last_price", 0) or quote.get("ltp", 0) or 0),
                                "open": float(quote.get("open", 0) or 0),
                                "high": float(quote.get("high", 0) or 0),
                                "low": float(quote.get("low", 0) or 0),
                                "close": float(quote.get("close", 0) or 0),
                                "volume": int(quote.get("volume", 0) or 0),
                                "prev_close": float(quote.get("prev_close", 0) or quote.get("previous_close", 0) or 0),
                            }
                else:
                    logger.warning("Batch %d: unexpected response format: %s", batch_idx, type(nse_data))
            elif resp.status_code == 429:
                logger.warning("Batch %d: rate limited, waiting 1s", batch_idx)
                time.sleep(1)
            else:
                logger.warning("Batch %d: HTTP %d — %s", batch_idx, resp.status_code, resp.text[:200])

        except Exception as exc:
            logger.error("Batch %d failed: %s", batch_idx, exc)

        # Small delay between batches to avoid rate limiting
        if batch_idx < len(batches) - 1:
            time.sleep(0.3)

    logger.info("Bulk LTP: fetched %d/%d stocks in %d batches", len(results), len(security_ids), len(batches))
    return results


def fetch_intraday_candles(broker, security_id: str, date: str) -> Optional[list]:
    """Fetch 5-min OHLC candles for one stock for given date.

    Reuses broker.get_historical_ohlc() which is already working.

    Args:
        broker: Authenticated DhanBrokerClient
        security_id: Dhan security ID string
        date: Date string YYYY-MM-DD

    Returns:
        List of candle dicts [{open, high, low, close, volume, time}, ...] or None
    """
    try:
        result = broker.get_historical_ohlc(
            security_id=security_id,
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            interval="5",
            from_date=date,
            to_date=date,
        )
        if result and isinstance(result, dict) and result.get("open"):
            # Convert columnar format to list of candles
            opens = result["open"]
            highs = result["high"]
            lows = result["low"]
            closes = result["close"]
            volumes = result.get("volume", [0] * len(opens))
            timestamps = result.get("timestamp", result.get("start_Time", [None] * len(opens)))

            candles = []
            for i in range(len(opens)):
                candles.append({
                    "open": opens[i],
                    "high": highs[i],
                    "low": lows[i],
                    "close": closes[i],
                    "volume": volumes[i] if i < len(volumes) else 0,
                    "timestamp": timestamps[i] if timestamps and i < len(timestamps) else None,
                })
            return candles
        return None
    except Exception as exc:
        logger.error("Candles fetch failed for %s: %s", security_id, exc)
        return None
