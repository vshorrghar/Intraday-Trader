"""Pre-market scanner for the intraday auto-trader.

Fetches NSE pre-open data, previous-day movers, and sector indices,
then computes gap percentages, ranks sectors, and identifies volume spikes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fetchers.nse_market_movers import (
    MarketMover,
    SectorIndex,
    fetch_all_market_data,
    fetch_most_active,
    fetch_sector_indices,
    fetch_top_gainers,
    fetch_top_losers,
)

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 5


@dataclass
class ScanResult:
    """Output of the pre-market scan."""

    candidates: list[dict] = field(default_factory=list)
    sectors: list[dict] = field(default_factory=list)
    vix_value: float = 0.0
    gainers: list[dict] = field(default_factory=list)
    losers: list[dict] = field(default_factory=list)


def compute_gap_pct(open_price: float, prev_close: float) -> float:
    """Compute gap-up/gap-down percentage.

    Returns ``(open_price - prev_close) / prev_close * 100``.
    Returns 0.0 when *prev_close* is zero or negative.
    """
    if prev_close <= 0:
        return 0.0
    return (open_price - prev_close) / prev_close * 100


def rank_sectors(sectors: list[SectorIndex]) -> list[dict]:
    """Rank sectors by change percentage descending (strongest first)."""
    ranked = sorted(sectors, key=lambda s: s.change_pct, reverse=True)
    return [
        {
            "name": s.name,
            "last_price": s.last_price,
            "change": s.change,
            "change_pct": s.change_pct,
        }
        for s in ranked
    ]


def _extract_vix(sectors: list[SectorIndex]) -> float:
    """Extract India VIX value from sector indices list."""
    for s in sectors:
        if "VIX" in s.name.upper():
            return s.last_price
    return 0.0


def _mover_to_candidate(mover: MarketMover) -> dict:
    """Convert a MarketMover to a candidate dict with gap_pct."""
    gap_pct = compute_gap_pct(mover.open_price, mover.prev_close)
    return {
        "symbol": mover.symbol,
        "name": mover.name,
        "ltp": mover.ltp,
        "open_price": mover.open_price,
        "prev_close": mover.prev_close,
        "change": mover.change,
        "change_pct": mover.change_pct,
        "volume": mover.volume,
        "gap_pct": gap_pct,
        "category": mover.category,
        "high": mover.high,
        "low": mover.low,
    }


def _mover_to_summary(mover: MarketMover) -> dict:
    """Convert a MarketMover to a summary dict for gainers/losers."""
    return {
        "symbol": mover.symbol,
        "name": mover.name,
        "ltp": mover.ltp,
        "change_pct": mover.change_pct,
        "volume": mover.volume,
    }


def _identify_volume_spikes(candidates: list[dict], active_stocks: list[MarketMover]) -> list[dict]:
    """Flag candidates with volume spikes by comparing to most-active data."""
    active_volumes: dict[str, int] = {}
    for m in active_stocks:
        if m.symbol and m.volume > 0:
            active_volumes[m.symbol] = m.volume

    for c in candidates:
        sym = c.get("symbol", "")
        active_vol = active_volumes.get(sym, 0)
        c["volume_spike"] = active_vol > 0 and c.get("volume", 0) > 0
        c["active_volume"] = active_vol
    return candidates


def _enrich_with_live_quotes(candidates: list[dict]) -> list[dict]:
    """Fetch live NSE quotes for candidates missing price data.

    If a candidate has ltp=0 or open_price=0, fetches from NSE quote API.
    This handles the case where gainers/losers API is empty but most_active
    returns symbols without full OHLCV data.
    """
    import requests

    needs_enrichment = [c for c in candidates if c.get("ltp", 0) == 0]
    if not needs_enrichment:
        return candidates

    logger.info("Enriching %d candidates with live NSE quotes…", len(needs_enrichment))

    nse_base = "https://www.nseindia.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/",
    }

    try:
        session = requests.Session()
        session.headers.update(headers)
        session.get(nse_base, timeout=10)
        time.sleep(0.5)

        enriched = 0
        for c in needs_enrichment:
            sym = c.get("symbol", "")
            if not sym:
                continue
            try:
                r = session.get(f"{nse_base}/api/quote-equity?symbol={sym}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    price_info = data.get("priceInfo", {})
                    ltp = float(price_info.get("lastPrice", 0) or 0)
                    open_p = float(price_info.get("open", 0) or 0)
                    high = float(price_info.get("intraDayHighLow", {}).get("max", 0) or 0)
                    low = float(price_info.get("intraDayHighLow", {}).get("min", 0) or 0)
                    prev_close = float(price_info.get("previousClose", 0) or 0)
                    change_pct = float(price_info.get("pChange", 0) or 0)
                    change = float(price_info.get("change", 0) or 0)

                    if ltp > 0:
                        c["ltp"] = ltp
                        c["open_price"] = open_p
                        c["high"] = high
                        c["low"] = low
                        c["prev_close"] = prev_close
                        c["change_pct"] = change_pct
                        c["change"] = change
                        c["gap_pct"] = compute_gap_pct(open_p, prev_close)
                        enriched += 1
                time.sleep(0.3)  # rate limit
            except Exception:
                pass

        logger.info("Enriched %d/%d candidates with live quotes", enriched, len(needs_enrichment))
    except Exception as exc:
        logger.error("Quote enrichment failed: %s", exc)

    return candidates


def _fetch_with_retry(fetch_fn, label: str):
    """Call *fetch_fn*; on empty/failure retry once after RETRY_DELAY_SECONDS.

    Returns the result list, or ``None`` if both attempts fail.
    """
    result = fetch_fn()
    if result:
        return result

    logger.warning("First attempt to fetch %s failed or returned empty. Retrying in %ds…", label, RETRY_DELAY_SECONDS)
    time.sleep(RETRY_DELAY_SECONDS)

    result = fetch_fn()
    if result:
        return result

    logger.error("Retry for %s also failed. Aborting.", label)
    return None


class Pre_Market_Scanner:
    """Scans NSE pre-market data and produces a :class:`ScanResult`."""

    def scan(self) -> ScanResult | None:
        """Run the full pre-market scan.

        Returns a :class:`ScanResult` on success, or ``None`` if data
        fetching fails after retry.
        """
        # --- Fetch sector indices (includes VIX) ---
        sectors_raw = _fetch_with_retry(fetch_sector_indices, "sector indices")
        if sectors_raw is None:
            return None

        vix_value = _extract_vix(sectors_raw)
        ranked_sectors = rank_sectors(sectors_raw)
        logger.info("India VIX: %.2f | %d sectors fetched", vix_value, len(ranked_sectors))

        # --- Fetch gainers (soft fail — continue if empty) ---
        gainers_raw = _fetch_with_retry(fetch_top_gainers, "top gainers") or []
        if not gainers_raw:
            logger.warning("No gainers data — continuing with other sources")

        # --- Fetch losers (soft fail — continue if empty) ---
        losers_raw = _fetch_with_retry(fetch_top_losers, "top losers") or []
        if not losers_raw:
            logger.warning("No losers data — continuing with other sources")

        # --- Fetch most active (soft fail — continue if empty) ---
        active_raw = _fetch_with_retry(fetch_most_active, "most active") or []
        if not active_raw:
            logger.warning("No most-active data — continuing with other sources")

        # If ALL sources failed, try fetch_all_market_data (session reuse — more reliable)
        if not gainers_raw and not losers_raw and not active_raw:
            logger.warning("Individual fetches failed — trying fetch_all_market_data with session reuse")
            try:
                all_data = fetch_all_market_data()
                # Rebuild from cached/fetched data
                for item in all_data.get("gainers", []):
                    gainers_raw.append(MarketMover(
                        symbol=item.get("symbol", ""), name=item.get("name", ""),
                        ltp=float(item.get("ltp", 0)), change=float(item.get("change", 0)),
                        change_pct=float(item.get("change_pct", 0)),
                        volume=int(item.get("volume", 0)),
                        prev_close=float(item.get("prev_close", 0)),
                        open_price=float(item.get("open_price", 0)),
                        category="gainer",
                    ))
                for item in all_data.get("losers", []):
                    losers_raw.append(MarketMover(
                        symbol=item.get("symbol", ""), name=item.get("name", ""),
                        ltp=float(item.get("ltp", 0)), change=float(item.get("change", 0)),
                        change_pct=float(item.get("change_pct", 0)),
                        volume=int(item.get("volume", 0)),
                        prev_close=float(item.get("prev_close", 0)),
                        open_price=float(item.get("open_price", 0)),
                        category="loser",
                    ))
                for item in all_data.get("most_active", []):
                    active_raw.append(MarketMover(
                        symbol=item.get("symbol", ""), name=item.get("name", ""),
                        ltp=float(item.get("ltp", 0)), change=float(item.get("change", 0)),
                        change_pct=float(item.get("change_pct", 0)),
                        volume=int(item.get("volume", 0)),
                        category="active",
                    ))
                logger.info("Fallback fetch: %d gainers, %d losers, %d active",
                           len(gainers_raw), len(losers_raw), len(active_raw))
            except Exception as exc:
                logger.error("Fallback fetch_all_market_data also failed: %s", exc)

        if not gainers_raw and not losers_raw and not active_raw:
            logger.error("All data sources returned empty — aborting scan")
            return None

        # --- Build candidate list from gainers + losers ---
        seen: set[str] = set()
        candidates: list[dict] = []
        for mover in gainers_raw + losers_raw:
            if mover.symbol and mover.symbol not in seen:
                seen.add(mover.symbol)
                candidates.append(_mover_to_candidate(mover))

        # Also add most-active stocks not already present
        for mover in active_raw:
            if mover.symbol and mover.symbol not in seen:
                seen.add(mover.symbol)
                candidates.append(_mover_to_candidate(mover))

        # --- Volume spike identification ---
        candidates = _identify_volume_spikes(candidates, active_raw)

        # --- Enrich candidates with live NSE quotes if prices are missing ---
        candidates = _enrich_with_live_quotes(candidates)

        # --- Summaries ---
        gainers_summary = [_mover_to_summary(m) for m in gainers_raw[:10]]
        losers_summary = [_mover_to_summary(m) for m in losers_raw[:10]]

        logger.info("Scan complete: %d candidates, %d sectors", len(candidates), len(ranked_sectors))

        return ScanResult(
            candidates=candidates,
            sectors=ranked_sectors,
            vix_value=vix_value,
            gainers=gainers_summary,
            losers=losers_summary,
        )
