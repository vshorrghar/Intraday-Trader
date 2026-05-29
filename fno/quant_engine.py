"""Quant Edge Engine — 6 institutional-grade quantitative signals.

Computes IV Percentile, OI Change Velocity, IV Skew, Gamma Exposure (GEX),
Volatility Risk Premium (VRP), and a weighted Confluence Score.  Every
candidate strategy must pass through this engine before the LLM sees it.

"No edge, no trade."
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fno.models import OptionChainSnapshot, QuantSignals

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.greeks import FnO_Greeks_Calculator

logger = logging.getLogger(__name__)

# OI velocity threshold for institutional positioning (contracts)
OI_VELOCITY_THRESHOLD = 500_000

# Default weights for confluence sub-scores
DEFAULT_WEIGHTS: dict[str, float] = {
    "ivp": 20.0,
    "oi": 20.0,
    "skew": 15.0,
    "gex": 15.0,
    "vrp": 15.0,
    "pcr_mp": 15.0,
}

# Minimum trading days before adaptive weighting kicks in
MIN_ADAPTIVE_DAYS = 20


class Quant_Edge_Engine:
    """Computes 6 institutional-grade quantitative signals."""

    def __init__(self, db: DBManager, config: FnO_Config) -> None:
        self.db = db
        self.config = config

    # ==================================================================
    # 1. IV Percentile
    # ==================================================================

    def compute_iv_percentile(self, index: str, current_atm_iv: float) -> float:
        """IVP = % of last 252 days where ATM IV < today's ATM IV.

        Bootstraps from 30 days on first run.  Returns 50.0 (neutral) if
        insufficient history (< 1 day).

        Parameters
        ----------
        index : str
            Index name (NIFTY, BANKNIFTY, FINNIFTY).
        current_atm_iv : float
            Today's ATM implied volatility (percentage, e.g. 15.0).

        Returns
        -------
        float
            IV Percentile in [0, 100].
        """
        history = self.db.get_fno_iv_history(index, days=252)
        if not history:
            logger.warning(
                "No IV history for %s — returning neutral IVP 50.0", index
            )
            return 50.0

        iv_values = [row["atm_iv"] for row in history]
        days_below = sum(1 for iv in iv_values if iv < current_atm_iv)
        ivp = (days_below / len(iv_values)) * 100.0
        return round(min(100.0, max(0.0, ivp)), 2)

    @staticmethod
    def ivp_signal(ivp: float) -> str:
        """Map IV Percentile to a trading signal."""
        if ivp > 70:
            return "SELL_PREMIUM"
        if ivp < 30:
            return "BUY_PREMIUM"
        return "USE_SPREADS"

    # ==================================================================
    # 2. OI Change Velocity
    # ==================================================================

    def compute_oi_velocity(
        self, snapshots: list[OptionChainSnapshot],
    ) -> tuple[list[dict], list[dict]]:
        """Compare OI between latest and ~30-min-ago snapshot.

        Flags strikes where Put OI increased > 500K as institutional support.
        Flags strikes where Call OI increased > 500K as institutional resistance.

        Parameters
        ----------
        snapshots : list[OptionChainSnapshot]
            Rolling buffer of snapshots (oldest first, newest last).

        Returns
        -------
        tuple[list[dict], list[dict]]
            (support_flags, resistance_flags) — each entry is
            ``{"strike": float, "oi_change_30m": int, "flag": str}``.
        """
        if len(snapshots) < 2:
            logger.warning("Insufficient snapshots for OI velocity (need ≥2)")
            return [], []

        latest = snapshots[-1]
        oldest = snapshots[0]

        # Build OI maps: {(strike, option_type): oi}
        def _oi_map(snap: OptionChainSnapshot) -> dict[tuple[float, str], int]:
            return {
                (s.strike_price, s.option_type): s.open_interest
                for s in snap.strikes
            }

        latest_oi = _oi_map(latest)
        oldest_oi = _oi_map(oldest)

        support: list[dict] = []
        resistance: list[dict] = []

        # Check all strikes present in latest snapshot
        for (strike, opt_type), oi_now in latest_oi.items():
            oi_before = oldest_oi.get((strike, opt_type), 0)
            delta_oi = oi_now - oi_before

            if opt_type == "PE" and delta_oi > OI_VELOCITY_THRESHOLD:
                support.append({
                    "strike": strike,
                    "oi_change_30m": delta_oi,
                    "flag": "institutional_support",
                })
            elif opt_type == "CE" and delta_oi > OI_VELOCITY_THRESHOLD:
                resistance.append({
                    "strike": strike,
                    "oi_change_30m": delta_oi,
                    "flag": "institutional_resistance",
                })

        # Sort by OI change descending
        support.sort(key=lambda x: x["oi_change_30m"], reverse=True)
        resistance.sort(key=lambda x: x["oi_change_30m"], reverse=True)

        return support, resistance

    # ==================================================================
    # 3. IV Skew
    # ==================================================================

    def compute_iv_skew(
        self,
        chain: OptionChainSnapshot,
        greeks_calc: FnO_Greeks_Calculator,
    ) -> tuple[float, str]:
        """IV of 25-delta Put minus IV of 25-delta Call.

        Finds the strikes closest to 25-delta for puts and calls, then
        computes the skew.  Widening skew → BEARISH, narrowing → BULLISH.

        Parameters
        ----------
        chain : OptionChainSnapshot
            Current option chain snapshot.
        greeks_calc : FnO_Greeks_Calculator
            Greeks calculator for delta computation.

        Returns
        -------
        tuple[float, str]
            (skew_value, signal) where signal is BEARISH/BULLISH/NEUTRAL.
        """
        spot = chain.spot_price
        now_dt = _safe_parse_timestamp(chain.timestamp)
        expiry_dt = _safe_parse_date(chain.expiry_date)
        tte = max((expiry_dt - now_dt).total_seconds() / (365.25 * 86400), 0.001)

        target_delta = 0.25
        best_put_strike = None
        best_put_iv = 0.0
        best_put_diff = float("inf")

        best_call_strike = None
        best_call_iv = 0.0
        best_call_diff = float("inf")

        for s in chain.strikes:
            if s.iv <= 0 or s.ltp <= 0.05:
                continue
            iv_dec = s.iv / 100.0  # Convert percentage to decimal
            try:
                greeks = greeks_calc.compute_greeks(
                    spot, s.strike_price, tte, iv_dec, s.option_type,
                )
            except Exception:
                continue

            if s.option_type == "PE":
                # Put delta is negative; we want |delta| ≈ 0.25
                diff = abs(abs(greeks.delta) - target_delta)
                if diff < best_put_diff:
                    best_put_diff = diff
                    best_put_strike = s.strike_price
                    best_put_iv = s.iv
            elif s.option_type == "CE":
                diff = abs(greeks.delta - target_delta)
                if diff < best_call_diff:
                    best_call_diff = diff
                    best_call_strike = s.strike_price
                    best_call_iv = s.iv

        if best_put_strike is None or best_call_strike is None:
            logger.warning("Could not find 25-delta strikes for IV skew")
            return 0.0, "NEUTRAL"

        skew = best_put_iv - best_call_iv

        # Signal: positive skew (puts more expensive) is normal;
        # widening = BEARISH, narrowing = BULLISH
        if skew > 3.0:
            signal = "BEARISH"
        elif skew < -1.0:
            signal = "BULLISH"
        else:
            signal = "NEUTRAL"

        return round(skew, 2), signal

    # ==================================================================
    # 4. GEX (Gamma Exposure)
    # ==================================================================

    def compute_gex(
        self,
        chain: OptionChainSnapshot,
        greeks_calc: FnO_Greeks_Calculator,
    ) -> tuple[list[dict], float, str]:
        """Compute Gamma Exposure at each strike.

        GEX_strike = Σ(OI × gamma × lot_size × spot / 100)
        Call gamma is positive, put gamma is negative.

        Parameters
        ----------
        chain : OptionChainSnapshot
            Current option chain snapshot.
        greeks_calc : FnO_Greeks_Calculator
            Greeks calculator for gamma computation.

        Returns
        -------
        tuple[list[dict], float, str]
            (gex_map, gravity_center, regime)
            - gex_map: list of ``{"strike": float, "net_gex": float}``
            - gravity_center: strike with highest positive GEX
            - regime: ``"PINNED"`` (total GEX > 0) or ``"TRENDING"`` (total GEX < 0)
        """
        spot = chain.spot_price
        lot_size = chain.lot_size
        now_dt = _safe_parse_timestamp(chain.timestamp)
        expiry_dt = _safe_parse_date(chain.expiry_date)
        tte = max((expiry_dt - now_dt).total_seconds() / (365.25 * 86400), 0.001)

        # Accumulate GEX per strike
        gex_by_strike: dict[float, float] = {}

        for s in chain.strikes:
            if s.iv <= 0 or s.open_interest <= 0:
                continue
            iv_dec = s.iv / 100.0
            try:
                greeks = greeks_calc.compute_greeks(
                    spot, s.strike_price, tte, iv_dec, s.option_type,
                )
            except Exception:
                continue

            # Call gamma positive, put gamma negative for market makers
            if s.option_type == "CE":
                gex_contribution = s.open_interest * greeks.gamma * lot_size * spot / 100.0
            else:
                gex_contribution = -s.open_interest * greeks.gamma * lot_size * spot / 100.0

            gex_by_strike[s.strike_price] = (
                gex_by_strike.get(s.strike_price, 0.0) + gex_contribution
            )

        gex_map = [
            {"strike": strike, "net_gex": round(gex, 2)}
            for strike, gex in sorted(gex_by_strike.items())
        ]

        total_gex = sum(item["net_gex"] for item in gex_map)

        # Gravity center = strike with highest positive GEX
        positive_gex = [item for item in gex_map if item["net_gex"] > 0]
        if positive_gex:
            gravity_center = max(positive_gex, key=lambda x: x["net_gex"])["strike"]
        elif gex_map:
            gravity_center = gex_map[len(gex_map) // 2]["strike"]
        else:
            gravity_center = chain.atm_strike

        regime = "PINNED" if total_gex >= 0 else "TRENDING"

        return gex_map, gravity_center, regime

    # ==================================================================
    # 5. VRP (Volatility Risk Premium)
    # ==================================================================

    def compute_vrp(self, index: str, atm_iv: float) -> tuple[float, str]:
        """VRP = ATM_IV - RV_20d.

        RV_20d = std(last 20 log returns) × √252 × 100.

        Parameters
        ----------
        index : str
            Index name.
        atm_iv : float
            Current ATM implied volatility (percentage, e.g. 15.0).

        Returns
        -------
        tuple[float, str]
            (vrp_value, signal) where signal is one of:
            STRONG_SELL, MODERATE_SELL, WEAK_EDGE, BUY_PREMIUM.
        """
        history = self.db.get_fno_spot_history(index, days=25)
        if len(history) < 21:
            logger.warning(
                "Insufficient spot history for %s (%d days, need 21) — "
                "returning neutral VRP 0.0",
                index, len(history),
            )
            return 0.0, "WEAK_EDGE"

        # History is newest-first; reverse for chronological order
        log_returns = [
            row["log_return"] for row in reversed(history)
            if row.get("log_return") is not None
        ]

        if len(log_returns) < 20:
            logger.warning(
                "Insufficient log returns for %s (%d, need 20)",
                index, len(log_returns),
            )
            return 0.0, "WEAK_EDGE"

        # Use last 20 log returns
        recent_returns = log_returns[-20:]
        mean_ret = sum(recent_returns) / len(recent_returns)
        variance = sum((r - mean_ret) ** 2 for r in recent_returns) / len(recent_returns)
        rv_20d = math.sqrt(variance) * math.sqrt(252) * 100.0

        vrp = atm_iv - rv_20d

        signal = _vrp_signal(vrp)
        return round(vrp, 2), signal

    # ==================================================================
    # 6. Confluence Score
    # ==================================================================

    def compute_confluence_score(
        self,
        ivp: float,
        oi_support: list[dict],
        oi_resistance: list[dict],
        iv_skew: float,
        gex_regime: str,
        vrp: float,
        pcr: float,
        max_pain: float,
        spot: float,
        strategy_type: str,
    ) -> tuple[float, dict]:
        """Weighted confluence score (0-100) with sub-score breakdown.

        Sub-score ranges:
        - IV Percentile:  0-20 points
        - OI Velocity:    0-20 points
        - IV Skew:        0-15 points
        - GEX:            0-15 points
        - VRP:            0-15 points
        - PCR + Max Pain: 0-15 points

        Thresholds:
        - >= 75: naked selling allowed
        - >= 60: any strategy allowed
        - >= 50: hedged strategies only
        - < 50:  no trade

        Parameters
        ----------
        ivp : float
            IV Percentile (0-100).
        oi_support, oi_resistance : list[dict]
            OI velocity flags.
        iv_skew : float
            IV skew value.
        gex_regime : str
            "PINNED" or "TRENDING".
        vrp : float
            Volatility Risk Premium.
        pcr : float
            Put-Call Ratio.
        max_pain : float
            Max Pain strike.
        spot : float
            Current spot price.
        strategy_type : str
            Strategy being evaluated (for adaptive weighting).

        Returns
        -------
        tuple[float, dict]
            (total_score, breakdown_dict).
        """
        weights = self.get_adaptive_weights(strategy_type)
        is_selling = strategy_type in (
            "SHORT_STRANGLE", "SHORT_STRADDLE", "IRON_CONDOR",
            "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "NAKED_CE", "NAKED_PE",
            "STRADDLE", "STRANGLE",
        )

        # --- IVP sub-score (0-20) ---
        if is_selling:
            # Higher IVP = better for selling
            ivp_score = min(20.0, (ivp / 100.0) * 20.0)
        else:
            # Lower IVP = better for buying
            ivp_score = min(20.0, ((100.0 - ivp) / 100.0) * 20.0)

        # --- OI Velocity sub-score (0-20) ---
        oi_score = 0.0
        if oi_support or oi_resistance:
            # More institutional walls = stronger signal
            wall_count = len(oi_support) + len(oi_resistance)
            oi_score = min(20.0, wall_count * 5.0)
            # Bonus if walls align with strategy direction
            if is_selling and oi_support and oi_resistance:
                oi_score = min(20.0, oi_score + 5.0)

        # --- IV Skew sub-score (0-15) ---
        skew_score = 0.0
        abs_skew = abs(iv_skew)
        if abs_skew > 5.0:
            skew_score = 15.0  # Strong directional signal
        elif abs_skew > 2.0:
            skew_score = 10.0
        elif abs_skew > 0.5:
            skew_score = 5.0
        # Reduce if skew contradicts strategy
        if is_selling and abs_skew > 5.0:
            skew_score *= 0.5  # High skew is risky for sellers

        # --- GEX sub-score (0-15) ---
        gex_score = 0.0
        if gex_regime == "PINNED" and is_selling:
            gex_score = 15.0  # Pinned market great for sellers
        elif gex_regime == "PINNED":
            gex_score = 5.0
        elif gex_regime == "TRENDING" and not is_selling:
            gex_score = 15.0  # Trending market great for buyers
        elif gex_regime == "TRENDING":
            gex_score = 5.0

        # --- VRP sub-score (0-15) ---
        vrp_score = 0.0
        if is_selling:
            if vrp > 5:
                vrp_score = 15.0
            elif vrp > 2:
                vrp_score = 10.0
            elif vrp > 0:
                vrp_score = 5.0
        else:
            if vrp < 0:
                vrp_score = 15.0  # Negative VRP = buy premium
            elif vrp < 2:
                vrp_score = 8.0
            else:
                vrp_score = 3.0

        # --- PCR + Max Pain sub-score (0-15) ---
        pcr_mp_score = 0.0
        # PCR signal
        if pcr != float("inf"):
            if 0.8 <= pcr <= 1.2:
                pcr_mp_score += 5.0  # Balanced = good for selling
            elif pcr > 1.2:
                pcr_mp_score += 7.0  # Bullish put writing
            elif pcr < 0.8:
                pcr_mp_score += 3.0  # Bearish
        # Max Pain proximity
        if spot > 0:
            mp_distance_pct = abs(max_pain - spot) / spot * 100
            if mp_distance_pct < 0.5:
                pcr_mp_score += 8.0  # Very close to max pain
            elif mp_distance_pct < 1.0:
                pcr_mp_score += 5.0
            elif mp_distance_pct < 2.0:
                pcr_mp_score += 3.0
        pcr_mp_score = min(15.0, pcr_mp_score)

        # --- Apply adaptive weights ---
        w = weights
        raw_total = (
            ivp_score * (w["ivp"] / DEFAULT_WEIGHTS["ivp"])
            + oi_score * (w["oi"] / DEFAULT_WEIGHTS["oi"])
            + skew_score * (w["skew"] / DEFAULT_WEIGHTS["skew"])
            + gex_score * (w["gex"] / DEFAULT_WEIGHTS["gex"])
            + vrp_score * (w["vrp"] / DEFAULT_WEIGHTS["vrp"])
            + pcr_mp_score * (w["pcr_mp"] / DEFAULT_WEIGHTS["pcr_mp"])
        )

        # Clamp to [0, 100]
        total = round(min(100.0, max(0.0, raw_total)), 2)

        breakdown = {
            "ivp": round(ivp_score, 2),
            "oi": round(oi_score, 2),
            "skew": round(skew_score, 2),
            "gex": round(gex_score, 2),
            "vrp": round(vrp_score, 2),
            "pcr_mp": round(pcr_mp_score, 2),
        }

        return total, breakdown

    # ==================================================================
    # 7. Adaptive Weights
    # ==================================================================

    def get_adaptive_weights(self, strategy_type: str) -> dict[str, float]:
        """After 20+ trading days, adjust weights based on historical win rates.

        If insufficient history, returns default weights unchanged.

        Parameters
        ----------
        strategy_type : str
            The strategy type to look up historical performance for.

        Returns
        -------
        dict[str, float]
            Weight dict with keys: ivp, oi, skew, gex, vrp, pcr_mp.
        """
        weights = dict(DEFAULT_WEIGHTS)

        try:
            history = self.db.get_paper_trading_history(weeks=52)
        except Exception:
            return weights

        if len(history) < MIN_ADAPTIVE_DAYS:
            return weights

        # Query strategy-specific win rate from fno_strategies table
        # Prefer corrected_pnl over realized_pnl (Bug f77de67 data correction)
        try:
            cursor = self.db.conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN COALESCE(corrected_pnl, realized_pnl) > 0 THEN 1 ELSE 0 END) as wins "
                "FROM fno_strategies WHERE strategy_type = ? "
                "AND COALESCE(corrected_pnl, realized_pnl) IS NOT NULL",
                (strategy_type,),
            )
            row = cursor.fetchone()
            if row is None or row["total"] < MIN_ADAPTIVE_DAYS:
                return weights

            total = row["total"]
            wins = row["wins"] or 0
            win_rate = (wins / total) * 100.0 if total > 0 else 50.0
        except Exception:
            return weights

        # Adjust weights based on win rate
        # Win rate > 60% → boost signal weights that contributed
        # Win rate < 40% → reduce signal weights
        if win_rate > 60:
            adjustment = 1.0 + (win_rate - 60) / 100.0  # e.g. 70% → 1.10
        elif win_rate < 40:
            adjustment = 1.0 - (40 - win_rate) / 100.0  # e.g. 30% → 0.90
        else:
            return weights  # No adjustment in 40-60% range

        # Apply adjustment proportionally
        for key in weights:
            weights[key] = round(weights[key] * adjustment, 2)

        return weights

    # ==================================================================
    # 8. Orchestrator
    # ==================================================================

    def compute_all_signals(
        self,
        chain: OptionChainSnapshot,
        greeks_calc: FnO_Greeks_Calculator,
        snapshots: list[OptionChainSnapshot] | None = None,
    ) -> QuantSignals:
        """Compute all 6 signals and return a QuantSignals dataclass.

        Parameters
        ----------
        chain : OptionChainSnapshot
            Current option chain snapshot.
        greeks_calc : FnO_Greeks_Calculator
            Greeks calculator instance.
        snapshots : list[OptionChainSnapshot] | None
            Rolling snapshot buffer for OI velocity. If None, OI velocity
            returns empty lists.

        Returns
        -------
        QuantSignals
            All quantitative signals with confluence score.
        """
        index = chain.index

        # --- ATM IV ---
        atm_iv = self._get_atm_iv(chain)

        # --- 1. IV Percentile ---
        ivp = self.compute_iv_percentile(index, atm_iv)
        ivp_sig = self.ivp_signal(ivp)

        # --- 2. OI Velocity ---
        if snapshots and len(snapshots) >= 2:
            oi_support, oi_resistance = self.compute_oi_velocity(snapshots)
        else:
            oi_support, oi_resistance = [], []

        # --- 3. IV Skew ---
        iv_skew_val, iv_skew_sig = self.compute_iv_skew(chain, greeks_calc)

        # --- 4. GEX ---
        gex_map, gex_gravity, gex_regime = self.compute_gex(chain, greeks_calc)

        # --- 5. VRP ---
        vrp_val, vrp_sig = self.compute_vrp(index, atm_iv)

        # --- 6. Confluence Score (use a generic strategy type for initial scan) ---
        confluence, breakdown = self.compute_confluence_score(
            ivp=ivp,
            oi_support=oi_support,
            oi_resistance=oi_resistance,
            iv_skew=iv_skew_val,
            gex_regime=gex_regime,
            vrp=vrp_val,
            pcr=chain.pcr,
            max_pain=chain.max_pain,
            spot=chain.spot_price,
            strategy_type="IRON_CONDOR",  # Default for initial scan
        )

        return QuantSignals(
            iv_percentile=ivp,
            iv_percentile_signal=ivp_sig,
            oi_velocity_support=oi_support,
            oi_velocity_resistance=oi_resistance,
            iv_skew=iv_skew_val,
            iv_skew_signal=iv_skew_sig,
            gex_map=gex_map,
            gex_gravity_center=gex_gravity,
            gex_regime=gex_regime,
            vrp=vrp_val,
            vrp_signal=vrp_sig,
            confluence_score=confluence,
            confluence_breakdown=breakdown,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_atm_iv(chain: OptionChainSnapshot) -> float:
        """Extract ATM IV from the chain (average of ATM CE and PE IV)."""
        atm = chain.atm_strike
        atm_ivs = [
            s.iv for s in chain.strikes
            if s.strike_price == atm and s.iv > 0
        ]
        if not atm_ivs:
            logger.warning("No ATM IV found — using default 15.0")
            return 15.0
        return sum(atm_ivs) / len(atm_ivs)


# ======================================================================
# Module-level helpers
# ======================================================================

def _vrp_signal(vrp: float) -> str:
    """Map VRP value to a trading signal."""
    if vrp > 5:
        return "STRONG_SELL"
    if vrp >= 2:
        return "MODERATE_SELL"
    if vrp >= 0:
        return "WEAK_EDGE"
    return "BUY_PREMIUM"


def _safe_parse_timestamp(ts: str) -> "datetime":
    """Parse an ISO 8601 timestamp, falling back to now() on failure."""
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return datetime.now(IST)


def _safe_parse_date(date_str: str) -> "datetime":
    """Parse a YYYY-MM-DD date string into a datetime at 15:30 IST."""
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(hour=15, minute=30, tzinfo=IST)
    except (ValueError, TypeError):
        return datetime.now(IST) + timedelta(days=7)
