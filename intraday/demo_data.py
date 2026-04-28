"""Demo data fetcher — pulls REAL NSE closing data for today's simulation.

Uses the NSE equity-stockIndices API (same session/cookie approach as
fetchers/nse_market_movers.py) to get full OHLCV data for Nifty 500 stocks.
Works after market hours because it uses closing data, not live feeds.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
NSE_BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

# Indices to fetch — Nifty 500 gives the widest coverage
_INDEX_URLS = [
    f"{NSE_BASE}/api/equity-stockIndices?index=NIFTY%20500",
    f"{NSE_BASE}/api/equity-stockIndices?index=NIFTY%2050",
]


def _get_nse_session() -> requests.Session:
    """Get a requests session with NSE cookies (mirrors nse_market_movers)."""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(NSE_BASE, timeout=10)
    except Exception:
        pass
    return s


def _parse_stock(item: dict) -> dict | None:
    """Parse a single stock entry from the NSE stockIndices response."""
    symbol = item.get("symbol", "")
    if not symbol or symbol == "NIFTY 500" or symbol.startswith("NIFTY"):
        return None

    open_price = float(item.get("open", 0) or 0)
    high = float(item.get("dayHigh", 0) or 0)
    low = float(item.get("dayLow", 0) or 0)
    ltp = float(item.get("lastPrice", 0) or 0)
    prev_close = float(item.get("previousClose", 0) or 0)
    volume = int(float(item.get("totalTradedVolume", 0) or 0))
    change_pct = float(item.get("pChange", 0) or 0)

    # Skip if essential data is missing
    if ltp <= 0 or prev_close <= 0:
        return None

    # Compute gap %
    gap_pct = 0.0
    if prev_close > 0 and open_price > 0:
        gap_pct = (open_price - prev_close) / prev_close * 100

    return {
        "symbol": symbol,
        "name": symbol,
        "ltp": ltp,
        "open_price": open_price,
        "high": high,
        "low": low,
        "close": ltp,  # after hours, LTP = closing price
        "prev_close": prev_close,
        "volume": volume,
        "change_pct": round(change_pct, 2),
        "gap_pct": round(gap_pct, 2),
        "category": "demo",
    }



def fetch_nse_stock_data() -> list[dict]:
    """Fetch today's OHLCV data for Nifty 500 stocks from NSE.

    Returns a list of candidate dicts with all fields populated:
    symbol, name, ltp, open_price, high, low, close, prev_close,
    volume, change_pct, gap_pct.

    Works after market hours — uses closing data.
    """
    session = _get_nse_session()
    time.sleep(0.5)  # let cookies settle

    seen: set[str] = set()
    all_stocks: list[dict] = []

    for url in _INDEX_URLS:
        try:
            logger.info("Fetching NSE data from: %s", url.split("index=")[1])
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", [])
            if not items:
                logger.warning("No 'data' array in response for %s", url)
                continue

            count = 0
            for item in items:
                parsed = _parse_stock(item)
                if parsed and parsed["symbol"] not in seen:
                    seen.add(parsed["symbol"])
                    all_stocks.append(parsed)
                    count += 1

            logger.info("Parsed %d stocks from %s", count, url.split("index=")[1])
            time.sleep(0.3)  # polite delay between requests

        except Exception as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            continue

    if not all_stocks:
        logger.error("Could not fetch any stock data from NSE")
        return []

    # Sort by absolute change % descending — most volatile first
    all_stocks.sort(key=lambda s: abs(s["change_pct"]), reverse=True)

    logger.info(
        "📊 Fetched %d stocks with real OHLCV data (date: %s)",
        len(all_stocks),
        datetime.now(IST).strftime("%Y-%m-%d"),
    )
    return all_stocks


def extract_vix_from_nse(session: requests.Session | None = None) -> float:
    """Fetch India VIX value from NSE allIndices endpoint."""
    s = session or _get_nse_session()
    try:
        resp = s.get(f"{NSE_BASE}/api/allIndices", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            if "VIX" in (item.get("index", "") or "").upper():
                return float(item.get("last", 0) or 0)
    except Exception as exc:
        logger.error("Failed to fetch VIX: %s", exc)
    return 14.0  # sensible default


def extract_sectors_from_nse(session: requests.Session | None = None) -> list[dict]:
    """Fetch sector indices from NSE for the LLM prompt."""
    s = session or _get_nse_session()
    sector_keywords = [
        "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO",
        "NIFTY FMCG", "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY",
        "NIFTY INFRA", "NIFTY FIN SERVICE", "NIFTY HEALTHCARE",
        "NIFTY PSU BANK", "NIFTY PRIVATE BANK", "NIFTY MEDIA",
        "NIFTY OIL AND GAS", "NIFTY COMMODITIES", "NIFTY CONSUMPTION",
        "NIFTY 50", "NIFTY NEXT 50",
    ]
    try:
        resp = s.get(f"{NSE_BASE}/api/allIndices", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        sectors = []
        for item in data.get("data", []):
            name = item.get("index", "")
            if any(kw.upper() in name.upper() for kw in sector_keywords):
                sectors.append({
                    "name": name,
                    "last_price": float(item.get("last", 0) or 0),
                    "change": float(item.get("variation", 0) or 0),
                    "change_pct": float(item.get("percentChange", 0) or 0),
                })
        sectors.sort(key=lambda x: x["change_pct"], reverse=True)
        return sectors
    except Exception as exc:
        logger.error("Failed to fetch sectors: %s", exc)
        return []


def simulate_trade_with_ohlcv(
    trade: dict,
    stock_data: dict[str, dict],
) -> dict:
    """Simulate a single trade using real OHLCV data.

    Logic:
    - Entry at the price Claude suggested (near open)
    - If HIGH >= target → CLOSED with profit
    - If LOW <= stop_loss → STOPPED_OUT with loss
    - If BOTH → assume SL hit first (conservative)
    - If NEITHER → FORCE_EXITED at close price

    Args:
        trade: Trade record dict with entry_price, target_price,
               stop_loss_price, quantity, tradingsymbol, etc.
        stock_data: Dict mapping symbol → OHLCV dict.

    Returns:
        Updated trade dict with status, pnl, exit_price filled in.
    """
    symbol = trade.get("nse_symbol") or trade.get("tradingsymbol", "")
    ohlcv = stock_data.get(symbol, {})

    entry = trade["entry_price"]
    target = trade["target_price"]
    sl = trade["stop_loss_price"]
    qty = trade["quantity"]

    high = ohlcv.get("high", 0)
    low = ohlcv.get("low", 0)
    close = ohlcv.get("close", 0) or ohlcv.get("ltp", 0)

    # If we don't have OHLCV data for this stock, force exit at entry
    if high <= 0 or low <= 0 or close <= 0:
        trade["status"] = "FORCE_EXITED"
        trade["exit_price"] = entry
        trade["pnl"] = 0.0
        trade["sim_note"] = "⚠️ No OHLCV data — flat exit"
        return trade

    hit_target = high >= target
    hit_sl = low <= sl

    if hit_sl and hit_target:
        # Conservative: assume SL hit first
        trade["status"] = "STOPPED_OUT"
        trade["exit_price"] = sl
        trade["pnl"] = round((sl - entry) * qty, 2)
        trade["sim_note"] = "🔀 Both target & SL hit — conservative SL assumed"
    elif hit_target:
        trade["status"] = "CLOSED"
        trade["exit_price"] = target
        trade["pnl"] = round((target - entry) * qty, 2)
        trade["sim_note"] = "🎯 Target reached!"
    elif hit_sl:
        trade["status"] = "STOPPED_OUT"
        trade["exit_price"] = sl
        trade["pnl"] = round((sl - entry) * qty, 2)
        trade["sim_note"] = "🛑 Stop loss triggered"
    else:
        trade["status"] = "FORCE_EXITED"
        trade["exit_price"] = close
        trade["pnl"] = round((close - entry) * qty, 2)
        trade["sim_note"] = "⏰ Force exit at close"

    # Add OHLCV context for display
    trade["day_high"] = high
    trade["day_low"] = low
    trade["day_close"] = close
    trade["day_open"] = ohlcv.get("open_price", 0)

    return trade


def simulate_all_trades(
    trades: list[dict],
    stock_data_list: list[dict],
) -> list[dict]:
    """Simulate all trades using real OHLCV data.

    Args:
        trades: List of placed trade record dicts.
        stock_data_list: Full list of stock dicts from fetch_nse_stock_data().

    Returns:
        List of trade dicts with simulation results filled in.
    """
    # Build lookup by symbol
    stock_map: dict[str, dict] = {}
    for s in stock_data_list:
        stock_map[s["symbol"]] = s

    results = []
    for trade in trades:
        simulated = simulate_trade_with_ohlcv(trade, stock_map)
        results.append(simulated)

    return results
