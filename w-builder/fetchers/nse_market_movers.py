"""NSE market movers fetcher.

Fetches top gainers, losers, most active by volume, and sector indices
from NSE to identify market opportunities during crashes/rallies.
"""
from __future__ import annotations
import json, logging, os, time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import requests

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}


@dataclass
class MarketMover:
    symbol: str
    name: str
    ltp: float
    change: float
    change_pct: float
    volume: int = 0
    prev_close: float = 0
    open_price: float = 0
    high: float = 0
    low: float = 0
    high_52w: float = 0
    low_52w: float = 0
    category: str = ""  # gainer/loser/active/sector


@dataclass
class SectorIndex:
    name: str
    last_price: float
    change: float
    change_pct: float


def _get_nse_session():
    """Get a session with NSE cookies."""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(NSE_BASE, timeout=10)
    except Exception:
        pass
    return s


def fetch_top_gainers(session=None) -> list[MarketMover]:
    """Fetch Nifty 500 top gainers from NSE."""
    s = session or _get_nse_session()
    try:
        r = s.get(f"{NSE_BASE}/api/live-analysis-variations?index=gainers", timeout=15)
        r.raise_for_status()
        data = r.json()
        movers = []
        # Response can be {"NIFTY": [...]} or {"allSec": [...]} or just a list
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0:
                    items = val
                    break
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            movers.append(MarketMover(
                symbol=item.get("symbol", ""),
                name=item.get("symbol", ""),
                ltp=float(item.get("ltp", item.get("lastPrice", 0)) or 0),
                change=float(item.get("netPrice", item.get("change", 0)) or 0),
                change_pct=float(item.get("perChange", item.get("pChange", 0)) or 0),
                prev_close=float(item.get("previousPrice", item.get("previousClose", 0)) or 0),
                open_price=float(item.get("openPrice", item.get("open", 0)) or 0),
                volume=int(float(item.get("tradedQuantity", item.get("totalTradedVolume", 0)) or 0)),
                category="gainer",
            ))
        logger.info("Fetched %d top gainers", len(movers))
        return movers
    except Exception as e:
        logger.error("Failed to fetch top gainers: %s", e)
        return []


def fetch_top_losers(session=None) -> list[MarketMover]:
    """Fetch Nifty 500 top losers from NSE."""
    s = session or _get_nse_session()
    try:
        r = s.get(f"{NSE_BASE}/api/live-analysis-variations?index=losers", timeout=15)
        r.raise_for_status()
        data = r.json()
        movers = []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list) and len(val) > 0:
                    items = val
                    break
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            movers.append(MarketMover(
                symbol=item.get("symbol", ""),
                name=item.get("symbol", ""),
                ltp=float(item.get("ltp", item.get("lastPrice", 0)) or 0),
                change=float(item.get("netPrice", item.get("change", 0)) or 0),
                change_pct=float(item.get("perChange", item.get("pChange", 0)) or 0),
                prev_close=float(item.get("previousPrice", item.get("previousClose", 0)) or 0),
                volume=int(float(item.get("tradedQuantity", item.get("totalTradedVolume", 0)) or 0)),
                category="loser",
            ))
        logger.info("Fetched %d top losers", len(movers))
        return movers
    except Exception as e:
        logger.error("Failed to fetch top losers: %s", e)
        return []


def fetch_most_active(session=None) -> list[MarketMover]:
    """Fetch most active by volume from NSE."""
    s = session or _get_nse_session()
    try:
        r = s.get(f"{NSE_BASE}/api/live-analysis-most-active-securities?index=volume", timeout=15)
        r.raise_for_status()
        data = r.json()
        movers = []
        for item in data.get("data", [])[:20]:
            movers.append(MarketMover(
                symbol=item.get("symbol", ""),
                name=item.get("symbol", ""),
                ltp=float(item.get("ltp", 0)),
                change=float(item.get("netPrice", item.get("change", 0))),
                change_pct=float(item.get("perChange", item.get("pChange", 0))),
                volume=int(item.get("totalTradedVolume", item.get("quantityTraded", 0))),
                category="active",
            ))
        logger.info("Fetched %d most active stocks", len(movers))
        return movers
    except Exception as e:
        logger.error("Failed to fetch most active: %s", e)
        return []


def fetch_sector_indices(session=None) -> list[SectorIndex]:
    """Fetch all sector indices to identify sector rotation."""
    s = session or _get_nse_session()
    try:
        r = s.get(f"{NSE_BASE}/api/allIndices", timeout=15)
        r.raise_for_status()
        data = r.json()
        sectors = []
        sector_keywords = ["NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO",
                          "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY",
                          "NIFTY INFRA", "NIFTY PSE", "NIFTY MEDIA", "NIFTY PRIVATE BANK",
                          "NIFTY PSU BANK", "NIFTY FIN SERVICE", "NIFTY HEALTHCARE",
                          "NIFTY CONSR DURBL", "NIFTY OIL AND GAS", "NIFTY COMMODITIES",
                          "NIFTY CONSUMPTION", "NIFTY CPSE", "NIFTY MIDCAP", "NIFTY SMLCAP",
                          "NIFTY 50", "NIFTY NEXT 50", "INDIA VIX", "NIFTY DEFENSE"]
        for item in data.get("data", []):
            name = item.get("index", "")
            if any(kw in name.upper() for kw in [k.upper() for k in sector_keywords]):
                sectors.append(SectorIndex(
                    name=name,
                    last_price=float(item.get("last", 0)),
                    change=float(item.get("variation", 0)),
                    change_pct=float(item.get("percentChange", 0)),
                ))
        sectors.sort(key=lambda x: x.change_pct)
        logger.info("Fetched %d sector indices", len(sectors))
        return sectors
    except Exception as e:
        logger.error("Failed to fetch sector indices: %s", e)
        return []


def fetch_all_market_data(cache_dir: str = "cache") -> dict:
    """Fetch all market mover data in one call with session reuse."""
    session = _get_nse_session()
    time.sleep(0.5)

    data = {
        "gainers": [vars(m) for m in fetch_top_gainers(session)],
        "losers": [vars(m) for m in fetch_top_losers(session)],
        "most_active": [vars(m) for m in fetch_most_active(session)],
        "sectors": [vars(s) for s in fetch_sector_indices(session)],
        "fetched_at": datetime.now(IST).isoformat(),
    }

    # Cache
    os.makedirs(cache_dir, exist_ok=True)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    cache_path = os.path.join(cache_dir, f"market_movers_{today}.json")
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass

    return data
