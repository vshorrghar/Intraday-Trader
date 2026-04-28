"""Option chain fetcher for the F&O Auto-Trader.

Retrieves complete option chain data for NSE index derivatives (NIFTY,
BANKNIFTY, FINNIFTY), computes derived analytics (ATM strike, PCR, Max Pain,
highest OI strikes, bid-ask spreads), and maintains a rolling snapshot buffer
for OI velocity computation.

Supports both real broker API calls and a demo/mock mode that generates
realistic option chain data for testing and paper trading.
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fno.models import OptionChainSnapshot, OptionStrike

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Exchange lot sizes for NSE index derivatives
LOT_SIZES: dict[str, int] = {
    "NIFTY": 25,
    "BANKNIFTY": 15,
    "FINNIFTY": 25,
}

# Strike interval (tick size) per index
STRIKE_INTERVALS: dict[str, float] = {
    "NIFTY": 50.0,
    "BANKNIFTY": 100.0,
    "FINNIFTY": 50.0,
}

# Typical spot price ranges for demo data generation
SPOT_RANGES: dict[str, tuple[float, float]] = {
    "NIFTY": (22000.0, 26000.0),
    "BANKNIFTY": (48000.0, 56000.0),
    "FINNIFTY": (22000.0, 25000.0),
}


class OptionChainFetcher:
    """Fetches and processes option chain data for NSE index derivatives.

    Maintains a per-index rolling buffer of the last 6 snapshots (~30 min
    at 5-min intervals) for OI velocity computation by the Quant Edge Engine.
    """

    MAX_SNAPSHOTS = 6  # ~30 min at 5-min intervals

    def __init__(self) -> None:
        # Per-index rolling snapshot buffers
        self._snapshot_buffers: dict[str, deque[OptionChainSnapshot]] = {}

    def get_snapshot_buffer(self, index: str) -> list[OptionChainSnapshot]:
        """Return the rolling snapshot buffer for an index (oldest first)."""
        buf = self._snapshot_buffers.get(index.upper(), deque())
        return list(buf)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_option_chain(
        self,
        index: str,
        broker_client=None,
        *,
        demo: bool = True,
        spot_price: float | None = None,
    ) -> list[OptionChainSnapshot]:
        """Fetch option chain for current and next weekly expiry.

        Parameters
        ----------
        index : str
            Index name — ``"NIFTY"``, ``"BANKNIFTY"``, or ``"FINNIFTY"``.
        broker_client :
            Optional broker client with a ``get_option_chain()`` method.
            When *None* or *demo=True*, generates demo data instead.
        demo : bool
            If True, use ``generate_demo_chain`` regardless of broker_client.
        spot_price : float | None
            Override spot price for demo mode. If None, a realistic random
            spot is generated.

        Returns
        -------
        list[OptionChainSnapshot]
            Two snapshots: current expiry and next expiry.

        Raises
        ------
        RuntimeError
            If both the initial fetch and the retry fail.
        """
        index = index.upper()
        if index not in LOT_SIZES:
            raise ValueError(f"Invalid index '{index}'. Valid: {sorted(LOT_SIZES)}")

        if demo or broker_client is None:
            return self._fetch_demo(index, spot_price)

        return self._fetch_live(index, broker_client)

    # ------------------------------------------------------------------
    # Demo / mock mode
    # ------------------------------------------------------------------

    def _fetch_demo(
        self, index: str, spot_price: float | None,
    ) -> list[OptionChainSnapshot]:
        """Generate demo option chain data for both expiries."""
        if spot_price is None:
            lo, hi = SPOT_RANGES.get(index, (20000.0, 25000.0))
            spot_price = round(random.uniform(lo, hi), 2)

        now = datetime.now(IST)
        current_expiry = _next_weekly_expiry(now)
        next_expiry = _next_weekly_expiry(current_expiry + timedelta(days=1))

        snapshots: list[OptionChainSnapshot] = []
        for expiry in (current_expiry, next_expiry):
            chain = generate_demo_chain(index, spot_price, expiry_date=expiry)
            snapshots.append(chain)

        # Add current-expiry snapshot to rolling buffer
        self._add_to_buffer(index, snapshots[0])
        return snapshots

    # ------------------------------------------------------------------
    # Live broker mode (with retry)
    # ------------------------------------------------------------------

    def _fetch_live(
        self, index: str, broker_client,
    ) -> list[OptionChainSnapshot]:
        """Fetch live option chain with retry logic.

        Retry once after 30 s on failure; raise RuntimeError if retry fails.
        """
        for attempt in range(2):
            try:
                raw = broker_client.get_option_chain(index)
                snapshots = self._parse_broker_chain(index, raw)
                if snapshots:
                    self._add_to_buffer(index, snapshots[0])
                    return snapshots
                raise ValueError("Empty option chain returned by broker")
            except Exception as exc:
                if attempt == 0:
                    logger.warning(
                        "Option chain fetch failed for %s (attempt 1): %s — "
                        "retrying in 30 s",
                        index, exc,
                    )
                    time.sleep(30)
                else:
                    logger.error(
                        "Option chain fetch failed for %s after retry: %s — "
                        "aborting session",
                        index, exc,
                    )
                    raise RuntimeError(
                        f"Option chain fetch failed for {index} after retry: {exc}"
                    ) from exc
        # Should not reach here, but satisfy type checker
        raise RuntimeError(f"Option chain fetch failed for {index}")  # pragma: no cover

    def _parse_broker_chain(
        self, index: str, raw: dict,
    ) -> list[OptionChainSnapshot]:
        """Parse normalized broker response into OptionChainSnapshot objects.

        Expects the format returned by DhanBrokerClient.get_option_chain():
        {"index": str, "spot_price": float, "strikes": [{"strike_price", "option_type", ...}]}
        """
        spot_price = float(raw.get("spot_price", 0))
        raw_strikes = raw.get("strikes", [])

        if not raw_strikes or spot_price <= 0:
            logger.warning(
                "Broker chain for %s has no strikes or invalid spot — falling back to demo",
                index,
            )
            return self._fetch_demo(index, None)

        # Convert raw dicts to OptionStrike objects
        all_strikes: list[OptionStrike] = []
        for s in raw_strikes:
            ltp = float(s.get("ltp", 0))
            bid = float(s.get("bid_price", ltp * 0.98))
            ask = float(s.get("ask_price", ltp * 1.02))
            all_strikes.append(OptionStrike(
                strike_price=float(s["strike_price"]),
                expiry_date=str(s.get("expiry_date", "")),
                option_type=str(s.get("option_type", "")),
                ltp=ltp,
                bid_price=bid,
                ask_price=ask,
                open_interest=int(s.get("open_interest", 0)),
                oi_change=int(s.get("oi_change", 0)),
                volume=int(s.get("volume", 0)),
                iv=float(s.get("iv", 0)),
                bid_ask_spread=round(ask - bid, 2),
            ))

        if not all_strikes:
            return self._fetch_demo(index, None)

        # Compute analytics
        unique_strikes = sorted(set(s.strike_price for s in all_strikes))
        atm = identify_atm_strike(spot_price, unique_strikes)
        pcr = compute_pcr(all_strikes)
        max_pain = compute_max_pain(all_strikes)
        h_call_oi = highest_oi_strike(all_strikes, "CE")
        h_put_oi = highest_oi_strike(all_strikes, "PE")

        # Get expiry from first strike
        expiry_date = all_strikes[0].expiry_date or _next_weekly_expiry(
            datetime.now(IST)
        ).strftime("%Y-%m-%d")

        lot_size = LOT_SIZES.get(index.upper(), 25)

        snapshot = OptionChainSnapshot(
            index=index.upper(),
            spot_price=spot_price,
            timestamp=datetime.now(IST).isoformat(),
            expiry_date=expiry_date,
            lot_size=lot_size,
            strikes=all_strikes,
            atm_strike=atm,
            pcr=round(pcr, 4) if pcr != float("inf") else float("inf"),
            max_pain=max_pain,
            highest_call_oi_strike=h_call_oi,
            highest_put_oi_strike=h_put_oi,
        )

        return [snapshot]

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _add_to_buffer(self, index: str, snapshot: OptionChainSnapshot) -> None:
        """Add a snapshot to the rolling buffer (max 6)."""
        idx = index.upper()
        if idx not in self._snapshot_buffers:
            self._snapshot_buffers[idx] = deque(maxlen=self.MAX_SNAPSHOTS)
        self._snapshot_buffers[idx].append(snapshot)


# ======================================================================
# Static / module-level helpers
# ======================================================================

def identify_atm_strike(spot_price: float, strikes: list[float]) -> float:
    """Identify the ATM strike closest to spot; lower strike wins ties.

    Parameters
    ----------
    spot_price : float
        Current spot price of the underlying.
    strikes : list[float]
        Available strike prices (must be non-empty).

    Returns
    -------
    float
        The ATM strike price.
    """
    if not strikes:
        raise ValueError("Strike list is empty")
    best = strikes[0]
    best_diff = abs(strikes[0] - spot_price)
    for s in strikes[1:]:
        diff = abs(s - spot_price)
        if diff < best_diff or (diff == best_diff and s < best):
            best = s
            best_diff = diff
    return best


def compute_pcr(strikes: list[OptionStrike]) -> float:
    """Compute Put-Call Ratio = total Put OI / total Call OI.

    Returns ``float('inf')`` if total Call OI is zero.
    """
    total_call_oi = sum(s.open_interest for s in strikes if s.option_type == "CE")
    total_put_oi = sum(s.open_interest for s in strikes if s.option_type == "PE")
    if total_call_oi == 0:
        return float("inf")
    return total_put_oi / total_call_oi


def compute_max_pain(strikes: list[OptionStrike]) -> float:
    """Compute Max Pain — the strike minimizing total pain.

    Pain at candidate strike *K* = Σ over all strikes *S*:
        max(0, K - S) × Call_OI_at_S  +  max(0, S - K) × Put_OI_at_S

    Returns the strike from the chain that minimizes this sum.
    """
    # Build OI maps keyed by strike price
    call_oi: dict[float, int] = {}
    put_oi: dict[float, int] = {}
    unique_strikes: set[float] = set()

    for s in strikes:
        unique_strikes.add(s.strike_price)
        if s.option_type == "CE":
            call_oi[s.strike_price] = call_oi.get(s.strike_price, 0) + s.open_interest
        else:
            put_oi[s.strike_price] = put_oi.get(s.strike_price, 0) + s.open_interest

    if not unique_strikes:
        raise ValueError("No strikes provided for Max Pain computation")

    sorted_strikes = sorted(unique_strikes)
    best_strike = sorted_strikes[0]
    best_pain = float("inf")

    for k in sorted_strikes:
        pain = 0.0
        for s in sorted_strikes:
            # Call holders lose when K > S (call expires ITM at K)
            pain += max(0.0, k - s) * call_oi.get(s, 0)
            # Put holders lose when S > K (put expires ITM at K)
            pain += max(0.0, s - k) * put_oi.get(s, 0)
        if pain < best_pain:
            best_pain = pain
            best_strike = k

    return best_strike


def compute_bid_ask_spread(strike: OptionStrike) -> float:
    """Compute bid-ask spread for a single contract."""
    return max(0.0, strike.ask_price - strike.bid_price)


def highest_oi_strike(strikes: list[OptionStrike], option_type: str) -> float:
    """Return the strike price with the highest OI for the given option type.

    Parameters
    ----------
    strikes : list[OptionStrike]
        All strikes in the chain.
    option_type : str
        ``"CE"`` or ``"PE"``.

    Returns
    -------
    float
        Strike price with highest OI, or 0.0 if none found.
    """
    filtered = [s for s in strikes if s.option_type == option_type]
    if not filtered:
        return 0.0
    return max(filtered, key=lambda s: s.open_interest).strike_price


# ======================================================================
# Demo data generator
# ======================================================================

def generate_demo_chain(
    index: str,
    spot_price: float,
    *,
    expiry_date: datetime | None = None,
    num_strikes_each_side: int = 15,
) -> OptionChainSnapshot:
    """Generate a realistic option chain snapshot for testing/demo.

    Creates strikes around the ATM level with realistic premiums, OI
    distribution, IV smile, and volume patterns.

    Parameters
    ----------
    index : str
        Index name.
    spot_price : float
        Current spot price.
    expiry_date : datetime | None
        Expiry date. Defaults to next weekly expiry from now.
    num_strikes_each_side : int
        Number of strikes above and below ATM (default 15).

    Returns
    -------
    OptionChainSnapshot
        A complete snapshot with all derived analytics.
    """
    index = index.upper()
    interval = STRIKE_INTERVALS.get(index, 50.0)
    lot_size = LOT_SIZES.get(index, 25)

    if expiry_date is None:
        expiry_date = _next_weekly_expiry(datetime.now(IST))

    # Round spot to nearest strike interval for ATM
    atm_raw = round(spot_price / interval) * interval
    # Build strike range
    strike_prices = [
        atm_raw + i * interval
        for i in range(-num_strikes_each_side, num_strikes_each_side + 1)
    ]

    now = datetime.now(IST)
    dte = max((expiry_date - now).total_seconds() / 86400.0, 0.01)
    tte = dte / 365.0
    base_iv = random.uniform(0.12, 0.22)  # 12-22% base IV

    all_strikes: list[OptionStrike] = []

    for strike in strike_prices:
        moneyness = (strike - spot_price) / spot_price

        # IV smile: higher IV for OTM options
        iv_smile = base_iv + 0.03 * abs(moneyness) * 10
        iv_pct = iv_smile * 100  # Store as percentage

        for opt_type in ("CE", "PE"):
            # Intrinsic value
            if opt_type == "CE":
                intrinsic = max(0.0, spot_price - strike)
            else:
                intrinsic = max(0.0, strike - spot_price)

            # Time value using simplified BS approximation
            time_value = spot_price * iv_smile * math.sqrt(tte) * 0.4
            # Adjust for moneyness
            if opt_type == "CE":
                otm_factor = max(0.0, 1.0 - max(0.0, moneyness) * 5)
            else:
                otm_factor = max(0.0, 1.0 + min(0.0, moneyness) * 5)
            time_value *= max(0.05, otm_factor)

            ltp = round(max(0.05, intrinsic + time_value), 2)
            spread_pct = random.uniform(0.01, 0.05)
            bid = round(max(0.05, ltp * (1 - spread_pct / 2)), 2)
            ask = round(ltp * (1 + spread_pct / 2), 2)

            # OI distribution: higher near ATM, decaying outward
            # Put OI peaks slightly below ATM, Call OI peaks slightly above
            distance = abs(strike - spot_price) / interval
            if opt_type == "PE":
                oi_peak_offset = -2  # Puts peak 2 strikes below ATM
            else:
                oi_peak_offset = 2   # Calls peak 2 strikes above ATM
            adjusted_dist = abs(distance - oi_peak_offset)
            base_oi = int(random.uniform(500_000, 3_000_000) * math.exp(-0.15 * adjusted_dist))
            base_oi = max(1000, base_oi)

            oi_change = int(random.uniform(-0.1, 0.15) * base_oi)
            volume = int(base_oi * random.uniform(0.05, 0.3))

            bid_ask_spread = round(ask - bid, 2)

            all_strikes.append(OptionStrike(
                strike_price=strike,
                expiry_date=expiry_date.strftime("%Y-%m-%d"),
                option_type=opt_type,
                ltp=ltp,
                bid_price=bid,
                ask_price=ask,
                open_interest=base_oi,
                oi_change=oi_change,
                volume=volume,
                iv=round(iv_pct, 2),
                bid_ask_spread=bid_ask_spread,
            ))

    # Identify ATM
    unique_strikes = sorted(set(s.strike_price for s in all_strikes))
    atm = identify_atm_strike(spot_price, unique_strikes)

    # Compute analytics
    pcr = compute_pcr(all_strikes)
    max_pain = compute_max_pain(all_strikes)
    h_call_oi = highest_oi_strike(all_strikes, "CE")
    h_put_oi = highest_oi_strike(all_strikes, "PE")

    return OptionChainSnapshot(
        index=index,
        spot_price=spot_price,
        timestamp=now.isoformat(),
        expiry_date=expiry_date.strftime("%Y-%m-%d"),
        lot_size=lot_size,
        strikes=all_strikes,
        atm_strike=atm,
        pcr=round(pcr, 4) if pcr != float("inf") else float("inf"),
        max_pain=max_pain,
        highest_call_oi_strike=h_call_oi,
        highest_put_oi_strike=h_put_oi,
    )


# ======================================================================
# Date helpers
# ======================================================================

def _next_weekly_expiry(from_date: datetime) -> datetime:
    """Return the next Thursday (NSE weekly expiry) on or after *from_date*.

    For simplicity, all indices use Thursday as the weekly expiry day.
    In reality, BankNifty uses Wednesday — this can be refined later.
    """
    # Thursday = weekday 3
    days_ahead = (3 - from_date.weekday()) % 7
    if days_ahead == 0 and from_date.hour >= 15 and from_date.minute >= 30:
        days_ahead = 7  # Past market close on expiry day → next week
    expiry = from_date + timedelta(days=days_ahead)
    return expiry.replace(hour=15, minute=30, second=0, microsecond=0)
