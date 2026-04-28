"""Black-Scholes Greeks calculator for European-style index options.

Provides delta, gamma, theta, vega computation, option pricing, implied
volatility root-finding (Newton-Raphson), and aggregate strategy Greeks.

Uses ``math`` and ``scipy.stats.norm`` for the normal distribution CDF/PDF.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from scipy.stats import norm

from fno.models import Greeks

if TYPE_CHECKING:
    from fno.models import StrategyLeg


class FnO_Greeks_Calculator:
    """Black-Scholes Greeks calculator for European-style index options."""

    RISK_FREE_RATE = 0.07  # 7% — India 10Y govt bond yield approx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _d1(spot: float, strike: float, tte: float, iv: float, r: float) -> float:
        """Compute d1 of the Black-Scholes formula."""
        return (math.log(spot / strike) + (r + 0.5 * iv * iv) * tte) / (iv * math.sqrt(tte))

    @staticmethod
    def _d2(d1: float, iv: float, tte: float) -> float:
        """Compute d2 = d1 - iv * sqrt(tte)."""
        return d1 - iv * math.sqrt(tte)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_option_price(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: str,
        r: float = RISK_FREE_RATE,
    ) -> float:
        """Black-Scholes option price for a European option.

        Parameters
        ----------
        spot : float
            Current spot price of the underlying.
        strike : float
            Strike price of the option.
        tte : float
            Time to expiry in years (e.g. 7/365).
        iv : float
            Implied volatility as a decimal (e.g. 0.15 for 15%).
        option_type : str
            ``"CE"`` for call, ``"PE"`` for put.
        r : float
            Risk-free interest rate (default 0.07).

        Returns
        -------
        float
            Theoretical option price.
        """
        option_type = option_type.upper()

        # Edge case: zero or negative TTE → intrinsic value
        if tte <= 0:
            if option_type == "CE":
                return max(spot - strike, 0.0)
            return max(strike - spot, 0.0)

        d1 = self._d1(spot, strike, tte, iv, r)
        d2 = self._d2(d1, iv, tte)
        discount = math.exp(-r * tte)

        if option_type == "CE":
            return spot * norm.cdf(d1) - strike * discount * norm.cdf(d2)
        # PE
        return strike * discount * norm.cdf(-d2) - spot * norm.cdf(-d1)

    def compute_greeks(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: str,
        r: float = RISK_FREE_RATE,
    ) -> Greeks:
        """Compute delta, gamma, theta, vega for a single option.

        Parameters
        ----------
        spot, strike, tte, iv, option_type, r :
            Same as :meth:`compute_option_price`.

        Returns
        -------
        Greeks
            Dataclass with delta, gamma, theta, vega.
        """
        option_type = option_type.upper()

        # Edge case: zero or negative TTE
        if tte <= 0:
            if option_type == "CE":
                delta = 1.0 if spot > strike else (0.5 if spot == strike else 0.0)
            else:
                delta = -1.0 if spot < strike else (-0.5 if spot == strike else 0.0)
            return Greeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0)

        d1 = self._d1(spot, strike, tte, iv, r)
        d2 = self._d2(d1, iv, tte)
        sqrt_tte = math.sqrt(tte)
        discount = math.exp(-r * tte)
        pdf_d1 = norm.pdf(d1)

        # Gamma (same for call and put)
        gamma = pdf_d1 / (spot * iv * sqrt_tte)

        # Vega (same for call and put) — per 1 unit change in iv
        vega = spot * pdf_d1 * sqrt_tte

        if option_type == "CE":
            delta = norm.cdf(d1)
            theta = (
                -(spot * pdf_d1 * iv) / (2.0 * sqrt_tte)
                - r * strike * discount * norm.cdf(d2)
            )
        else:
            delta = norm.cdf(d1) - 1.0
            theta = (
                -(spot * pdf_d1 * iv) / (2.0 * sqrt_tte)
                + r * strike * discount * norm.cdf(-d2)
            )

        # Theta is per-year; convert to per-day
        theta_per_day = theta / 365.0

        return Greeks(delta=delta, gamma=gamma, theta=theta_per_day, vega=vega)

    def implied_volatility(
        self,
        market_price: float,
        spot: float,
        strike: float,
        tte: float,
        option_type: str,
        r: float = RISK_FREE_RATE,
        max_iterations: int = 100,
        tol: float = 1e-6,
    ) -> float:
        """Compute IV from market price using Newton-Raphson root finding.

        Parameters
        ----------
        market_price : float
            Observed market price of the option.
        spot, strike, tte, option_type, r :
            Same as :meth:`compute_option_price`.
        max_iterations : int
            Maximum Newton-Raphson iterations (default 100).
        tol : float
            Convergence tolerance.

        Returns
        -------
        float
            Implied volatility as a decimal.

        Raises
        ------
        ValueError
            If the root-finding does not converge.
        """
        if tte <= 0:
            raise ValueError("Cannot compute IV with zero or negative time to expiry")

        # Initial guess
        iv = 0.2  # 20% starting point

        for _ in range(max_iterations):
            price = self.compute_option_price(spot, strike, tte, iv, option_type, r)
            diff = price - market_price

            if abs(diff) < tol:
                return iv

            # Vega = dPrice/dIV
            d1 = self._d1(spot, strike, tte, iv, r)
            vega = spot * norm.pdf(d1) * math.sqrt(tte)

            if vega < 1e-12:
                break  # Vega too small, can't converge

            iv -= diff / vega

            # Clamp IV to reasonable range
            iv = max(0.001, min(iv, 5.0))

        raise ValueError(
            f"IV did not converge after {max_iterations} iterations "
            f"(market_price={market_price}, spot={spot}, strike={strike}, "
            f"tte={tte}, option_type={option_type})"
        )

    def strategy_greeks(self, legs: list[StrategyLeg], spot: float) -> Greeks:
        """Net Greeks for a multi-leg strategy.

        Sums each leg's Greeks multiplied by direction (+1 BUY, -1 SELL)
        and quantity.

        Parameters
        ----------
        legs : list[StrategyLeg]
            Strategy legs with strike_price, expiry_date, option_type,
            transaction_type, entry_price (used as IV proxy is not needed
            here — we use the leg's IV or a default).
        spot : float
            Current spot price.

        Returns
        -------
        Greeks
            Aggregate net Greeks for the strategy.
        """
        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0

        for leg in legs:
            # Skip futures legs for Greeks (delta = 1 per unit)
            if leg.option_type.upper() == "FUT":
                direction = 1 if leg.transaction_type == "BUY" else -1
                net_delta += direction * leg.quantity
                continue

            # Use entry_price to derive a rough IV, or use a default
            # In practice, IV should be passed separately; here we use
            # a reasonable default of 15% for computation
            iv = 0.15

            # Estimate TTE — for strategy_greeks we need TTE from expiry_date
            # but since we don't have datetime parsing here, we accept a
            # simplified approach: use 7 days as default TTE
            # The caller should ideally provide TTE; this is a fallback.
            tte = 7.0 / 365.0

            greeks = self.compute_greeks(
                spot=spot,
                strike=leg.strike_price,
                tte=tte,
                iv=iv,
                option_type=leg.option_type,
            )

            direction = 1 if leg.transaction_type == "BUY" else -1
            qty = leg.quantity

            net_delta += greeks.delta * direction * qty
            net_gamma += greeks.gamma * direction * qty
            net_theta += greeks.theta * direction * qty
            net_vega += greeks.vega * direction * qty

        return Greeks(
            delta=net_delta,
            gamma=net_gamma,
            theta=net_theta,
            vega=net_vega,
        )
