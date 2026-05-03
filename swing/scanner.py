"""Swing trade scanner — identifies multi-day setups from NSE data.

Runs after market close (3:30 PM IST), scans for:
- Breakouts above resistance with volume confirmation
- Pullbacks to support in uptrending stocks
- Reversals at key levels with bullish candle patterns
- Momentum stocks with strong sector tailwinds
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from swing.models import SwingConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


class SwingScanner:
    """Scans NSE for swing trade candidates."""

    def __init__(self, config: SwingConfig) -> None:
        self.config = config
        self._session = None

    def _get_session(self):
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update(HEADERS)
            try:
                self._session.get(NSE_BASE, timeout=10)
            except Exception:
                pass
        return self._session

    def scan(self) -> dict:
        """Run full swing scan. Returns candidates with technical data."""
        session = self._get_session()

        # Fetch sector indices for sector strength
        sectors = self._fetch_sectors(session)

        # Fetch Nifty 500 stocks with delivery data (high delivery = swing interest)
        candidates = self._fetch_delivery_leaders(session)

        # Fetch 52-week high/low breakouts
        breakouts = self._fetch_52w_breakouts(session)

        # Enrich with live quotes
        enriched = self._enrich_candidates(session, candidates + breakouts)

        logger.info("Swing scan: %d candidates, %d sectors", len(enriched), len(sectors))

        return {
            "candidates": enriched,
            "sectors": sectors,
            "scan_time": datetime.now(IST).isoformat(),
        }

    def _fetch_sectors(self, session) -> list[dict]:
        """Fetch sector indices for sector rotation analysis."""
        try:
            r = session.get(f"{NSE_BASE}/api/allIndices", timeout=15)
            if r.status_code == 200:
                data = r.json()
                sectors = []
                for item in data.get("data", []):
                    name = item.get("index", "")
                    if "NIFTY" in name.upper():
                        sectors.append({
                            "name": name,
                            "last_price": float(item.get("last", 0)),
                            "change_pct": float(item.get("percentChange", 0)),
                        })
                return sorted(sectors, key=lambda x: x["change_pct"], reverse=True)
        except Exception as e:
            logger.error("Failed to fetch sectors: %s", e)
        return []

    def _fetch_delivery_leaders(self, session) -> list[dict]:
        """Fetch stocks with high delivery percentage (institutional interest)."""
        try:
            r = session.get(
                f"{NSE_BASE}/api/live-analysis-most-active-securities?index=volume",
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                candidates = []
                for item in data.get("data", [])[:30]:
                    candidates.append({
                        "symbol": item.get("symbol", ""),
                        "ltp": float(item.get("ltp", 0)),
                        "change_pct": float(item.get("pChange", 0)),
                        "volume": int(item.get("totalTradedVolume", 0)),
                        "category": "delivery_leader",
                    })
                return candidates
        except Exception as e:
            logger.error("Failed to fetch delivery leaders: %s", e)
        return []

    def _fetch_52w_breakouts(self, session) -> list[dict]:
        """Fetch stocks near 52-week highs (breakout candidates)."""
        try:
            r = session.get(
                f"{NSE_BASE}/api/live-analysis-variations?index=gainers",
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                items = []
                if isinstance(data, dict):
                    for val in data.values():
                        if isinstance(val, list):
                            items = val
                            break
                elif isinstance(data, list):
                    items = data

                breakouts = []
                for item in items[:20]:
                    if not isinstance(item, dict):
                        continue
                    breakouts.append({
                        "symbol": item.get("symbol", ""),
                        "ltp": float(item.get("ltp", item.get("lastPrice", 0)) or 0),
                        "change_pct": float(item.get("perChange", item.get("pChange", 0)) or 0),
                        "volume": int(float(item.get("tradedQuantity", 0) or 0)),
                        "category": "breakout",
                    })
                return breakouts
        except Exception as e:
            logger.error("Failed to fetch breakouts: %s", e)
        return []

    def _enrich_candidates(self, session, candidates: list[dict]) -> list[dict]:
        """Enrich candidates with full OHLCV data from NSE quote API."""
        enriched = []
        seen = set()

        for c in candidates:
            sym = c.get("symbol", "")
            if not sym or sym in seen:
                continue
            seen.add(sym)

            try:
                r = session.get(f"{NSE_BASE}/api/quote-equity?symbol={sym}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    price_info = data.get("priceInfo", {})
                    ltp = float(price_info.get("lastPrice", 0) or 0)

                    if ltp < self.config.price_range_min or ltp > self.config.price_range_max:
                        continue

                    c["ltp"] = ltp
                    c["open"] = float(price_info.get("open", 0) or 0)
                    c["high"] = float(price_info.get("intraDayHighLow", {}).get("max", 0) or 0)
                    c["low"] = float(price_info.get("intraDayHighLow", {}).get("min", 0) or 0)
                    c["prev_close"] = float(price_info.get("previousClose", 0) or 0)
                    c["change_pct"] = float(price_info.get("pChange", 0) or 0)
                    c["high_52w"] = float(price_info.get("weekHighLow", {}).get("max", 0) or 0)
                    c["low_52w"] = float(price_info.get("weekHighLow", {}).get("min", 0) or 0)

                    enriched.append(c)
                time.sleep(0.3)
            except Exception:
                pass

        logger.info("Enriched %d swing candidates with live data", len(enriched))
        return enriched
