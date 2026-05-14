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

        # --- Build candidate list from Nifty 500 (primary) ---
        candidates = _fetch_nifty500_candidates(
            price_min=50,
            price_max=5000,
            min_volume=500_000,
            top_n_long=15,
            top_n_short=15,
            ranked_sectors=ranked_sectors,
        )

        # --- Fallback to gainers/losers/active if Nifty500 failed ---
        if not candidates:
            logger.warning("Nifty500 scan failed — falling back to gainers/losers/active")
            seen: set[str] = set()
            for mover in gainers_raw + losers_raw:
                if mover.symbol and mover.symbol not in seen:
                    seen.add(mover.symbol)
                    candidates.append(_mover_to_candidate(mover))
            for mover in active_raw:
                if mover.symbol and mover.symbol not in seen:
                    seen.add(mover.symbol)
                    candidates.append(_mover_to_candidate(mover))
            candidates = _identify_volume_spikes(candidates, active_raw)
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


def _fetch_nifty500_candidates(
    price_min: float = 50,
    price_max: float = 5000,
    min_volume: int = 500_000,
    top_n_long: int = 15,
    top_n_short: int = 15,
    ranked_sectors: list = None,
) -> list[dict]:
    """Fetch Nifty 500 stocks and return top long + short candidates.

    Filters by price range and minimum volume.
    Scores long setups (gap up, volume surge, green on green day).
    Scores short setups (gap down, volume surge, red on red day).
    Returns top_n_long + top_n_short candidates combined.
    """
    from fetchers.nse_market_movers import _get_nse_session
    try:
        s = _get_nse_session()
        r = s.get(
            "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500",
            timeout=20,
        )
        r.raise_for_status()
        raw = r.json().get("data", [])
    except Exception as exc:
        logger.error("Nifty500 fetch failed: %s", exc)
        return []

    candidates = []
    for item in raw:
        symbol = item.get("symbol", "")
        if not symbol:
            continue

        ltp = float(item.get("lastPrice") or 0)
        open_price = float(item.get("open") or 0)
        prev_close = float(item.get("previousClose") or 0)
        volume = int(item.get("totalTradedVolume") or 0)
        day_high = float(item.get("dayHigh") or 0)
        day_low = float(item.get("dayLow") or 0)
        change_pct = float(item.get("pChange") or 0)
        year_high = float(item.get("yearHigh") or 0)
        year_low = float(item.get("yearLow") or 0)
        industry = item.get("meta", {}).get("industry", "")
        is_fno = item.get("meta", {}).get("isFNOSec", False)

        # Basic filters
        if ltp < price_min or ltp > price_max:
            continue
        if volume < min_volume:
            continue
        if prev_close <= 0 or open_price <= 0:
            continue

        gap_pct = (open_price - prev_close) / prev_close * 100
        change_from_open = (ltp - open_price) / open_price * 100 if open_price > 0 else 0
        near_52w_high = (year_high - ltp) / year_high * 100 if year_high > 0 else 100
        near_52w_low = (ltp - year_low) / year_low * 100 if year_low > 0 else 100
        day_range = (day_high - day_low) / prev_close * 100 if prev_close > 0 else 0
        high_volatility = day_range > 5 or abs(gap_pct) > 8

        # RS-FIRST Scoring Model — momentum continuation over volume
        # Signal 1: Intraday continuation (0-5 pts) — MOST IMPORTANT
        long_score = 0
        if change_from_open > 4.0:
            long_score += 5
        elif change_from_open > 2.0:
            long_score += 4
        elif change_from_open > 1.0:
            long_score += 3
        elif change_from_open > 0.5:
            long_score += 2
        elif change_from_open > 0.0:
            long_score += 1

        # Signal 2: Momentum strength (0-8 pts) — reward true winners
        if change_pct > 15.0:
            long_score += 8  # rare massive winner
        elif change_pct > 10.0:
            long_score += 6  # huge winner
        elif change_pct > 7.0:
            long_score += 5  # strong winner
        elif change_pct > 5.0:
            long_score += 4
        elif change_pct > 3.0:
            long_score += 3
        elif change_pct > 2.0:
            long_score += 2
        elif change_pct > 1.0:
            long_score += 1

        # Signal 3: Price near day high (0-2 pts)
        pct_from_high = ((day_high - ltp) / day_high * 100) if day_high > 0 else 99
        if pct_from_high < 0.5:
            long_score += 2
        elif pct_from_high < 1.5:
            long_score += 1

        # Signal 4: Volume confirmation (0-2 pts) — confirms only
        if volume > 5_000_000:
            long_score += 2
        elif volume > 2_000_000:
            long_score += 1

        # Signal 5: FNO liquidity bonus (0-1 pt)
        if is_fno:
            long_score += 1

        # Signal 6: Sector rotation bonus (0-5 pts)
        sector_rank = None
        sector_chg = 0
        for i, s in enumerate(ranked_sectors or [], 1):
            s_name = s.get('name', '').upper()
            ind_prefix = industry.upper()[:6]
            if ind_prefix and (s_name.startswith(ind_prefix) or ind_prefix in s_name):
                sector_rank = i
                sector_chg = s.get('change_pct', 0)
                break
        if sector_rank:
            if sector_rank <= 3:
                long_score += 3  # leading sector
            elif sector_rank <= 5:
                long_score += 2
            elif sector_rank <= 8:
                long_score += 1
            # Outperforming sector = relative strength
            if change_pct > sector_chg + 2.0:
                long_score += 2

        # Fade detector — penalize only stocks falling from day high
        # NOT stocks that are simply up a lot
        # Strong stocks at day high stay strong all day
        fade_pct = ((day_high - ltp) / day_high * 100) if day_high > 0 else 0
        if fade_pct > 3.0:
            long_score -= 3  # significant fade from high
        elif fade_pct > 1.5:
            long_score -= 1  # mild pullback from high
        # No penalty for stocks at/near day high regardless of gain
        if gap_pct > 2.0 and change_from_open < 0:
            long_score -= 3  # gap fade — opened high, now selling
        if gap_pct > 3.0 and change_from_open < 0.5:
            long_score -= 2  # gap exhaustion — no follow through

        # Trap detector
        if gap_pct > 5.0 and sector_chg < 0:
            long_score -= 5  # gap with no sector support = trap
        if near_52w_high < 1.0 and change_pct > 8.0:
            long_score -= 2  # buying climax risk at 52w high

        # Time-aware multiplier — early entries get more credit
        from datetime import datetime, timezone, timedelta
        _ist = timezone(timedelta(hours=5, minutes=30))
        _now = datetime.now(_ist)
        hrs_since_open = max(0, (_now.hour - 9) + (_now.minute - 15) / 60.0)
        if hrs_since_open < 1.0:
            time_multiplier = 1.5
        elif hrs_since_open < 2.5:
            time_multiplier = 1.0
        elif hrs_since_open < 4.0:
            time_multiplier = 0.7
        else:
            time_multiplier = 0.4
        long_score = int(long_score * time_multiplier)

        # Short score — mirror logic for shorts
        short_score = 0
        if change_from_open < -4.0:
            short_score += 5
        elif change_from_open < -2.0:
            short_score += 4
        elif change_from_open < -1.0:
            short_score += 3
        elif change_from_open < -0.5:
            short_score += 2
        elif change_from_open < 0.0:
            short_score += 1
        if change_pct < -15.0:
            short_score += 8  # rare massive drop
        elif change_pct < -10.0:
            short_score += 6  # huge drop
        elif change_pct < -7.0:
            short_score += 5  # strong drop
        elif change_pct < -5.0:
            short_score += 4
        elif change_pct < -3.0:
            short_score += 3
        elif change_pct < -2.0:
            short_score += 2
        elif change_pct < -1.0:
            short_score += 1
        pct_from_low = ((ltp - day_low) / day_low * 100) if day_low > 0 else 99
        if pct_from_low < 0.5:
            short_score += 2
        elif pct_from_low < 1.5:
            short_score += 1
        if volume > 5_000_000:
            short_score += 2
        elif volume > 2_000_000:
            short_score += 1
        if is_fno:
            short_score += 1
        # Fade detector for shorts — penalize stocks bouncing from day low
        fade_from_low = ((ltp - day_low) / day_low * 100) if day_low > 0 else 0
        if fade_from_low > 3.0:
            short_score -= 3  # bouncing from low
        elif fade_from_low > 1.5:
            short_score -= 1  # mild bounce
        if high_volatility:
            short_score -= 3

        candidates.append({
            "symbol": symbol,
            "name": item.get("meta", {}).get("companyName", symbol),
            "ltp": ltp,
            "open_price": open_price,
            "prev_close": prev_close,
            "change": float(item.get("change") or 0),
            "change_pct": change_pct,
            "volume": volume,
            "gap_pct": round(gap_pct, 2),
            "day_high": day_high,
            "day_low": day_low,
            "year_high": year_high,
            "year_low": year_low,
            "near_52w_high_pct": round(near_52w_high, 2),
            "near_52w_low_pct": round(near_52w_low, 2),
            "change_from_open": round(change_from_open, 2),
            "high_volatility": high_volatility,
            "is_fno": is_fno,
            "industry": industry,
            "category": "active",
            "high": day_high,
            "low": day_low,
            "long_score": long_score,
            "short_score": short_score,
            "setup_type": "",
        })

    # Pick top long and short candidates
    long_candidates = sorted(
        [c for c in candidates if c["long_score"] > 0],
        key=lambda x: x["long_score"],
        reverse=True,
    )[:top_n_long]

    short_candidates = sorted(
        [c for c in candidates if c["short_score"] > 0 and c["change_pct"] < 0],
        key=lambda x: x["short_score"],
        reverse=True,
    )[:top_n_short]

    for c in long_candidates:
        c["setup_type"] = "LONG"
    for c in short_candidates:
        c["setup_type"] = "SHORT"

    # Deduplicate — if same stock in both, keep the higher scored one
    seen: set[str] = set()
    result = []
    for c in long_candidates + short_candidates:
        if c["symbol"] not in seen:
            seen.add(c["symbol"])
            result.append(c)

    logger.info(
        "Nifty500 scan: %d total, %d long candidates, %d short candidates, %d combined",
        len(candidates),
        len(long_candidates),
        len(short_candidates),
        len(result),
    )
    return result
