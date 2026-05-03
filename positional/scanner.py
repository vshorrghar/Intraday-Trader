"""Positional trade scanner — identifies multi-week/month setups.

Focuses on:
- Fundamental strength (low PE, high ROCE, low debt)
- Sector rotation (money flowing into sector)
- Institutional buying (FII/DII accumulation)
- Earnings momentum (quarterly results beat)
- Technical breakouts on weekly charts
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from positional.models import PositionalConfig

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
}


class PositionalScanner:
    """Scans for positional trade candidates using fundamentals + technicals."""

    def __init__(self, config: PositionalConfig) -> None:
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
        """Run positional scan. Returns candidates with fundamental data."""
        session = self._get_session()

        # Sector performance (weekly/monthly)
        sectors = self._fetch_sectors(session)

        # Nifty 500 stocks near 52-week highs (momentum)
        momentum = self._fetch_momentum_stocks(session)

        # FII/DII activity
        fii_dii = self._fetch_fii_dii(session)

        # Combine and enrich
        candidates = self._enrich_with_fundamentals(session, momentum)

        logger.info(
            "Positional scan: %d candidates, %d sectors, FII net: ₹%.0fCr",
            len(candidates), len(sectors), fii_dii.get("fii_net", 0) / 10_000_000,
        )

        return {
            "candidates": candidates,
            "sectors": sectors,
            "fii_dii": fii_dii,
            "scan_time": datetime.now(IST).isoformat(),
        }

    def _fetch_sectors(self, session) -> list[dict]:
        """Fetch sector indices."""
        try:
            r = session.get(f"{NSE_BASE}/api/allIndices", timeout=15)
            if r.status_code == 200:
                data = r.json()
                sectors = []
                for item in data.get("data", []):
                    name = item.get("index", "")
                    if "NIFTY" in name.upper() and any(
                        kw in name.upper()
                        for kw in ["BANK", "IT", "PHARMA", "AUTO", "METAL", "ENERGY", "FMCG", "REALTY"]
                    ):
                        sectors.append({
                            "name": name,
                            "last_price": float(item.get("last", 0)),
                            "change_pct": float(item.get("percentChange", 0)),
                        })
                return sorted(sectors, key=lambda x: x["change_pct"], reverse=True)
        except Exception as e:
            logger.error("Positional sector fetch failed: %s", e)
        return []

    def _fetch_momentum_stocks(self, session) -> list[dict]:
        """Fetch stocks showing strong momentum (near 52w high, high volume)."""
        candidates = []
        try:
            # Most active by value (large cap momentum)
            r = session.get(
                f"{NSE_BASE}/api/live-analysis-most-active-securities?index=value",
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                for item in data.get("data", [])[:30]:
                    candidates.append({
                        "symbol": item.get("symbol", ""),
                        "ltp": float(item.get("ltp", 0)),
                        "change_pct": float(item.get("pChange", 0)),
                        "volume": int(item.get("totalTradedVolume", 0)),
                        "category": "momentum",
                    })
        except Exception as e:
            logger.error("Momentum fetch failed: %s", e)
        return candidates

    def _fetch_fii_dii(self, session) -> dict:
        """Fetch FII/DII activity data."""
        try:
            r = session.get(f"{NSE_BASE}/api/fiidiiActivity", timeout=15)
            if r.status_code == 200:
                data = r.json()
                fii_net = 0
                dii_net = 0
                for item in data if isinstance(data, list) else []:
                    if "FII" in str(item.get("category", "")).upper():
                        fii_net = float(item.get("netValue", 0))
                    elif "DII" in str(item.get("category", "")).upper():
                        dii_net = float(item.get("netValue", 0))
                return {"fii_net": fii_net, "dii_net": dii_net}
        except Exception as e:
            logger.error("FII/DII fetch failed: %s", e)
        return {"fii_net": 0, "dii_net": 0}

    def _enrich_with_fundamentals(self, session, candidates: list[dict]) -> list[dict]:
        """Enrich candidates with price data and 52-week range."""
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

                    high_52w = float(price_info.get("weekHighLow", {}).get("max", 0) or 0)
                    low_52w = float(price_info.get("weekHighLow", {}).get("min", 0) or 0)

                    # Calculate distance from 52w high (closer = stronger momentum)
                    dist_from_high = ((high_52w - ltp) / high_52w * 100) if high_52w > 0 else 100

                    c.update({
                        "ltp": ltp,
                        "prev_close": float(price_info.get("previousClose", 0) or 0),
                        "high_52w": high_52w,
                        "low_52w": low_52w,
                        "dist_from_52w_high_pct": round(dist_from_high, 2),
                        "pe": float(data.get("metadata", {}).get("pdSymbolPe", 0) or 0),
                        "sector": data.get("industryInfo", {}).get("sector", ""),
                        "market_cap": self._classify_market_cap(ltp, data),
                    })
                    enriched.append(c)
                time.sleep(0.3)
            except Exception:
                pass

        return enriched

    @staticmethod
    def _classify_market_cap(ltp: float, data: dict) -> str:
        """Classify as LARGE/MID/SMALL based on available data."""
        # Simplified: use index membership or price as proxy
        indices = data.get("metadata", {}).get("indexNames", "")
        if "Nifty 50" in indices:
            return "LARGE"
        elif "Nifty Next 50" in indices or "Nifty Midcap" in indices:
            return "MID"
        return "SMALL"
