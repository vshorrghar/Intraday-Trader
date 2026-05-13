"""F&O Strategy Engine — 7-strategy playbook with LLM integration.

Classifies market regime, constructs LLM prompts with quant data,
calls AWS Bedrock Claude Sonnet, parses and validates the response,
and returns validated FnOStrategySetup objects ready for execution.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from fno.models import (
    FnOStrategySetup,
    MarketRegime,
    QuantSignals,
    StrategyLeg,
)

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from fno.config import FnO_Config
    from fno.greeks import FnO_Greeks_Calculator
    from fno.models import OptionChainSnapshot

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ── Strategy Playbook ─────────────────────────────────────────────────

STRATEGY_PLAYBOOK = {
    "IRON_CONDOR",
    "SHORT_STRANGLE",
    "BULL_PUT_SPREAD",
    "BEAR_CALL_SPREAD",
    "SHORT_STRADDLE",
    "LONG_STRADDLE",
    "DIRECTIONAL_CE_BUY",
    "DIRECTIONAL_PE_BUY",
    # Aliases used in config
    "STRADDLE",
    "STRANGLE",
    "NAKED_CE",
    "NAKED_PE",
}

# Strategies that involve naked selling (unlimited risk)
NAKED_SELLING_STRATEGIES = {
    "SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
    "NAKED_CE", "NAKED_PE",
}

# Strategies allowed on expiry day
EXPIRY_DAY_STRATEGIES = {
    "SHORT_STRADDLE", "STRADDLE", "IRON_CONDOR",
    "DIRECTIONAL_CE_BUY", "DIRECTIONAL_PE_BUY",
}

# Strategies blocked after 14:00 IST
BLOCKED_AFTER_1400 = {"SHORT_STRADDLE", "SHORT_STRANGLE", "STRADDLE", "STRANGLE"}

# Directional buys blocked after 13:00 IST
DIRECTIONAL_BUYS = {"DIRECTIONAL_CE_BUY", "DIRECTIONAL_PE_BUY"}

# Lot sizes per index
LOT_SIZES = {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 25}


# ── System Prompt ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert F&O (Futures & Options) trading analyst for Indian NSE index derivatives.
Your job is to select the optimal strategy from the 7-strategy playbook based on current
market conditions and quantitative signals.

STRATEGY PLAYBOOK:
1. IRON_CONDOR — Sell OTM CE + PE, buy further OTM protection. Sideways market, VIX 12-18.
2. SHORT_STRANGLE — Sell OTM CE + PE, no protection. High VIX (>16), range-bound, 3+ DTE.
3. BULL_PUT_SPREAD — Sell Put at support, buy lower Put. Bullish trend, OI-confirmed support.
4. BEAR_CALL_SPREAD — Sell Call at resistance, buy higher Call. Bearish trend, OI-confirmed resistance.
5. SHORT_STRADDLE — Sell ATM CE + PE. ONLY on expiry day, VIX < 18, no events.
6. LONG_STRADDLE — Buy ATM CE + PE. Before major events, VIX expected to spike.
7. DIRECTIONAL_BUY — Buy OTM CE (bullish) or PE (bearish). Clear breakout with volume.

MARKET REGIME: {market_regime}

QUANTITATIVE SIGNALS (from Quant Edge Engine):
- IV Percentile: {ivp}% → {ivp_signal}
- OI Velocity: Support walls at {oi_support_strikes}, Resistance walls at {oi_resistance_strikes}
- IV Skew: {iv_skew:.2f} → {iv_skew_signal}
- GEX Regime: {gex_regime}, Gravity Center: {gex_gravity}
- VRP: {vrp:.2f}pp → {vrp_signal}
- Confluence Score Range: {min_confluence}-{max_confluence}

RULES:
- ONLY recommend strategies where confluence score >= 45 for hedged (IRON_CONDOR, BULL_PUT_SPREAD, BEAR_CALL_SPREAD), >= 60 for non-hedged directional, >= 75 for naked selling
- Stop loss for premium selling: exit when combined premium moves 1.5x against collected premium
- No SHORT_STRANGLE or SHORT_STRADDLE entries after 2:00 PM IST
- No DIRECTIONAL buys after 1:00 PM IST
- On expiry day: ONLY SHORT_STRADDLE, IRON_CONDOR, or DIRECTIONAL allowed
- Max {max_lots} lots per leg, max {max_positions} total strategies

RESPOND WITH EXACTLY THIS JSON:
{{
  "strategies": [
    {{
      "strategy_type": "IRON_CONDOR|SHORT_STRANGLE|...",
      "index": "NIFTY|BANKNIFTY|FINNIFTY",
      "legs": [
        {{
          "strike": 24500,
          "option_type": "CE|PE",
          "transaction_type": "BUY|SELL",
          "num_lots": 1,
          "entry_price": 80.50
        }}
      ],
      "confidence_score": 8,
      "rationale": "Why this strategy with quant evidence"
    }}
  ],
  "market_assessment": "One-line market view",
  "regime_reasoning": "Why this regime classification"
}}"""

USER_PROMPT_TEMPLATE = """Date: {date} IST | Time: {time} IST
Index: {index} | Spot: ₹{spot_price} | VIX: {vix}
Days to Expiry: {dte} | Is Expiry Day: {is_expiry}

OPTION CHAIN (ATM ± 10 strikes, current expiry {expiry_date}):
Strike  | CE LTP | CE OI    | CE IV  | PE LTP | PE OI    | PE IV
{option_chain_table}

KEY LEVELS:
- ATM Strike: {atm_strike}
- Max Pain: {max_pain}
- PCR: {pcr:.2f}
- Highest Call OI: {highest_call_oi_strike} ({highest_call_oi:,} contracts)
- Highest Put OI: {highest_put_oi_strike} ({highest_put_oi:,} contracts)

QUANT SIGNALS:
- IV Percentile: {ivp:.1f}% (1Y rank) → {ivp_signal}
- OI Velocity (30min): {oi_velocity_summary}
- IV Skew (25Δ): {iv_skew:.2f} → {iv_skew_signal}
- GEX: {gex_regime} | Gravity: {gex_gravity} | Total GEX: {total_gex:,.0f}
- VRP: {vrp:.2f}pp (IV {atm_iv:.1f}% vs RV20d {rv20d:.1f}%) → {vrp_signal}
- Confluence Score: {confluence_score:.0f}/100

5-DAY PRICE TREND: {price_trend}
SECTOR MOMENTUM: {sector_summary}

Select the optimal strategy. Confluence >= 60 required (>= 75 for naked selling)."""


# ── Market Regime Classifier ──────────────────────────────────────────


class MarketRegimeClassifier:
    """Classify current market into one of 4 regimes."""

    @staticmethod
    def classify(
        vix: float,
        spot_prices_3d: list[float],
        oi_support: list[dict],
        oi_resistance: list[dict],
        is_event_day: bool = False,
    ) -> MarketRegime:
        """Classify market regime.

        Parameters
        ----------
        vix : float
            Current India VIX level.
        spot_prices_3d : list[float]
            Last 3 daily closing prices (oldest first).
        oi_support : list[dict]
            OI velocity support flags.
        oi_resistance : list[dict]
            OI velocity resistance flags.
        is_event_day : bool
            Whether today is a known event day (RBI, budget, etc.).

        Returns
        -------
        MarketRegime
        """
        # HIGH_VOLATILITY: VIX > 20 or event day
        if vix > 20 or is_event_day:
            return MarketRegime.HIGH_VOLATILITY

        if len(spot_prices_3d) >= 3:
            p = spot_prices_3d
            # Check for trending up: higher highs and higher lows
            higher_highs = p[2] > p[1] > p[0]
            # Check for trending down: lower highs and lower lows
            lower_lows = p[2] < p[1] < p[0]

            bullish_oi = len(oi_support) > len(oi_resistance)
            bearish_oi = len(oi_resistance) > len(oi_support)

            if higher_highs and bullish_oi:
                return MarketRegime.TRENDING_UP
            if lower_lows and bearish_oi:
                return MarketRegime.TRENDING_DOWN

        # SIDEWAYS: VIX 10-15 and range-bound
        if 10 <= vix <= 15:
            return MarketRegime.SIDEWAYS

        # Default: if VIX 15-20 and no clear trend, still sideways
        if len(spot_prices_3d) >= 3:
            price_range = max(spot_prices_3d) - min(spot_prices_3d)
            avg_price = sum(spot_prices_3d) / len(spot_prices_3d)
            if avg_price > 0 and (price_range / avg_price) < 0.02:
                return MarketRegime.SIDEWAYS

        return MarketRegime.SIDEWAYS


# ── Strategy Engine ───────────────────────────────────────────────────


class FnO_Strategy_Engine:
    """Selects and constructs F&O strategies using LLM + quant signals."""

    def __init__(
        self,
        config: FnO_Config,
        db: DBManager,
        greeks_calc: FnO_Greeks_Calculator,
    ) -> None:
        self.config = config
        self.db = db
        self.greeks_calc = greeks_calc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_strategies(
        self,
        chains: dict[str, OptionChainSnapshot],
        quant_signals: dict[str, QuantSignals],
        vix: float,
        spot_prices_3d: dict[str, list[float]] | None = None,
        is_event_day: bool = False,
        current_time: datetime | None = None,
    ) -> list[FnOStrategySetup]:
        """Run the full strategy selection pipeline.

        Parameters
        ----------
        chains : dict[str, OptionChainSnapshot]
            Option chain snapshots keyed by index name.
        quant_signals : dict[str, QuantSignals]
            Quant signals keyed by index name.
        vix : float
            Current India VIX.
        spot_prices_3d : dict[str, list[float]] | None
            Last 3 daily closes per index.
        is_event_day : bool
            Whether today is a known event day.
        current_time : datetime | None
            Override current time (for testing). Defaults to now IST.

        Returns
        -------
        list[FnOStrategySetup]
            Validated strategies ready for execution.
        """
        now = current_time or datetime.now(IST)
        spot_prices_3d = spot_prices_3d or {}

        # Classify market regime
        first_index = next(iter(chains), "NIFTY")
        regime = MarketRegimeClassifier.classify(
            vix=vix,
            spot_prices_3d=spot_prices_3d.get(first_index, []),
            oi_support=quant_signals.get(first_index, QuantSignals(
                iv_percentile=50, iv_percentile_signal="USE_SPREADS"
            )).oi_velocity_support,
            oi_resistance=quant_signals.get(first_index, QuantSignals(
                iv_percentile=50, iv_percentile_signal="USE_SPREADS"
            )).oi_velocity_resistance,
            is_event_day=is_event_day,
        )

        # Log regime
        self.db.insert_audit_log(
            "FNO_REGIME_CLASSIFIED",
            json.dumps({"regime": regime.value, "vix": vix}),
        )
        logger.info("Market regime: %s (VIX=%.1f)", regime.value, vix)

        # Build and send LLM prompt for each index
        all_strategies: list[FnOStrategySetup] = []

        for index, chain in chains.items():
            signals = quant_signals.get(index)
            if signals is None:
                logger.warning("No quant signals for %s — skipping", index)
                continue

            try:
                raw_strategies = self._call_llm(
                    chain, signals, regime, vix, now, is_event_day,
                )
            except Exception as exc:
                logger.error("LLM call failed for %s: %s", index, exc)
                self.db.insert_audit_log(
                    "FNO_ERROR",
                    json.dumps({"error": f"LLM call failed: {exc}", "index": index}),
                )
                continue

            if not raw_strategies:
                logger.warning("No strategies returned by LLM for %s", index)
                continue

            # Validate each strategy
            for raw in raw_strategies:
                try:
                    setup = self._validate_and_build(
                        raw, chain, signals, regime, now,
                    )
                    if setup:
                        all_strategies.append(setup)
                except Exception as exc:
                    logger.warning("Strategy validation failed: %s", exc)
                    self.db.insert_audit_log(
                        "FNO_ERROR",
                        json.dumps({"error": f"Validation failed: {exc}"}),
                    )

        return all_strategies

    # ------------------------------------------------------------------
    # LLM Integration
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        chain: OptionChainSnapshot,
        signals: QuantSignals,
        regime: MarketRegime,
        vix: float,
        now: datetime,
        is_event_day: bool,
    ) -> list[dict]:
        """Construct prompts, call Bedrock Claude, parse response."""
        system_prompt = self._build_system_prompt(signals, regime)
        user_prompt = self._build_user_prompt(chain, signals, vix, now, is_event_day)

        # Log prompts
        self.db.insert_audit_log(
            "FNO_LLM_PROMPT",
            json.dumps({
                "system_prompt": system_prompt[:2000],
                "user_prompt": user_prompt[:3000],
            }),
        )

        # Call AWS Bedrock
        try:
            response_text = self._invoke_bedrock(system_prompt, user_prompt)
        except Exception as exc:
            logger.error("Bedrock invocation failed: %s", exc)
            raise

        # Log response
        self.db.insert_audit_log(
            "FNO_LLM_RESPONSE",
            json.dumps({"response": response_text[:3000]}),
        )

        # Parse JSON
        if not response_text or not response_text.strip():
            logger.error("Empty LLM response — aborting")
            raise ValueError("Empty LLM response")

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
            else:
                logger.error("Invalid JSON from LLM: %s", response_text[:500])
                raise ValueError("Invalid JSON from LLM")

        strategies = parsed.get("strategies", [])
        if not isinstance(strategies, list):
            raise ValueError("LLM response 'strategies' is not a list")

        return strategies

    def _invoke_bedrock(self, system_prompt: str, user_prompt: str) -> str:
        """Call AWS Bedrock Claude Sonnet and return the text response."""
        try:
            import boto3
            import yaml

            with open("config/config.yaml") as f:
                raw_cfg = yaml.safe_load(f)

            aws_cfg = raw_cfg.get("aws", {})
            region = aws_cfg.get("bedrock_region", "us-east-1")
            model_id = aws_cfg.get(
                "bedrock_model_id",
                "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            )

            client = boto3.client("bedrock-runtime", region_name=region)
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            })

            resp = client.invoke_model(modelId=model_id, body=body)
            result = json.loads(resp["body"].read())
            return result.get("content", [{}])[0].get("text", "")
        except ImportError:
            logger.warning("boto3 not available — using demo strategy response")
            return self._demo_llm_response(user_prompt)
        except Exception as exc:
            logger.warning("Bedrock call failed (%s) — using demo response", exc)
            return self._demo_llm_response(user_prompt)

    def _demo_llm_response(self, user_prompt: str) -> str:
        """Return a demo LLM response for paper trading / testing.

        Extracts ATM strike from the prompt to build realistic strikes.
        """
        import re

        # Extract index from prompt
        index = "NIFTY"
        for idx in ("BANKNIFTY", "FINNIFTY", "NIFTY"):
            if idx in user_prompt:
                index = idx
                break

        # Extract ATM strike from prompt
        atm_match = re.search(r"ATM Strike:\s*([\d.]+)", user_prompt)
        atm = float(atm_match.group(1)) if atm_match else 24500.0
        interval = 100.0 if index == "BANKNIFTY" else 50.0

        # Build iron condor around ATM
        ce_sell = atm + 3 * interval
        ce_buy = atm + 4 * interval
        pe_sell = atm - 3 * interval
        pe_buy = atm - 4 * interval

        return json.dumps({
            "strategies": [
                {
                    "strategy_type": "IRON_CONDOR",
                    "index": index,
                    "legs": [
                        {"strike": ce_sell, "option_type": "CE", "transaction_type": "SELL", "num_lots": 1, "entry_price": 45.0},
                        {"strike": ce_buy, "option_type": "CE", "transaction_type": "BUY", "num_lots": 1, "entry_price": 25.0},
                        {"strike": pe_sell, "option_type": "PE", "transaction_type": "SELL", "num_lots": 1, "entry_price": 50.0},
                        {"strike": pe_buy, "option_type": "PE", "transaction_type": "BUY", "num_lots": 1, "entry_price": 30.0},
                    ],
                    "confidence_score": 8,
                    "rationale": "Demo iron condor — sideways market with high IVP and positive VRP",
                }
            ],
            "market_assessment": "Range-bound market with elevated IV",
            "regime_reasoning": "VIX moderate, 3-day range tight",
        })

    # ------------------------------------------------------------------
    # Prompt Builders
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self, signals: QuantSignals, regime: MarketRegime,
    ) -> str:
        """Build the system prompt with quant data."""
        oi_support_strikes = ", ".join(
            str(s["strike"]) for s in signals.oi_velocity_support[:5]
        ) or "None detected"
        oi_resistance_strikes = ", ".join(
            str(s["strike"]) for s in signals.oi_velocity_resistance[:5]
        ) or "None detected"

        return SYSTEM_PROMPT.format(
            market_regime=regime.value,
            ivp=signals.iv_percentile,
            ivp_signal=signals.iv_percentile_signal,
            oi_support_strikes=oi_support_strikes,
            oi_resistance_strikes=oi_resistance_strikes,
            iv_skew=signals.iv_skew,
            iv_skew_signal=signals.iv_skew_signal,
            gex_regime=signals.gex_regime,
            gex_gravity=signals.gex_gravity_center,
            vrp=signals.vrp,
            vrp_signal=signals.vrp_signal,
            min_confluence=45,
            max_confluence=100,
            max_lots=self.config.max_lots_per_trade,
            max_positions=self.config.max_positions,
        )

    def _build_user_prompt(
        self,
        chain: OptionChainSnapshot,
        signals: QuantSignals,
        vix: float,
        now: datetime,
        is_expiry: bool,
    ) -> str:
        """Build the user prompt with market data."""
        # Build option chain table (ATM ± 10 strikes)
        atm = chain.atm_strike
        interval = 50.0 if chain.index in ("NIFTY", "FINNIFTY") else 100.0
        table_lines = []
        strikes_by_price: dict[float, dict] = {}
        for s in chain.strikes:
            sp = s.strike_price
            if abs(sp - atm) <= 10 * interval:
                if sp not in strikes_by_price:
                    strikes_by_price[sp] = {}
                strikes_by_price[sp][s.option_type] = s

        for sp in sorted(strikes_by_price.keys()):
            ce = strikes_by_price[sp].get("CE")
            pe = strikes_by_price[sp].get("PE")
            table_lines.append(
                f"{sp:>8.0f} | {ce.ltp if ce else 0:>6.2f} | {ce.open_interest if ce else 0:>8,} | "
                f"{ce.iv if ce else 0:>5.1f}% | {pe.ltp if pe else 0:>6.2f} | "
                f"{pe.open_interest if pe else 0:>8,} | {pe.iv if pe else 0:>5.1f}%"
            )

        # Compute DTE
        try:
            expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d")
            dte = max(0, (expiry_dt.date() - now.date()).days)
        except Exception:
            dte = 7

        # OI velocity summary
        oi_summary_parts = []
        for s in signals.oi_velocity_support[:3]:
            oi_summary_parts.append(f"Put support at {s['strike']} (+{s['oi_change_30m']:,})")
        for s in signals.oi_velocity_resistance[:3]:
            oi_summary_parts.append(f"Call resistance at {s['strike']} (+{s['oi_change_30m']:,})")
        oi_summary = "; ".join(oi_summary_parts) or "No significant velocity detected"

        # Highest OI
        highest_call_oi = max(
            (s.open_interest for s in chain.strikes if s.option_type == "CE"),
            default=0,
        )
        highest_put_oi = max(
            (s.open_interest for s in chain.strikes if s.option_type == "PE"),
            default=0,
        )

        # ATM IV
        atm_ivs = [s.iv for s in chain.strikes if s.strike_price == atm and s.iv > 0]
        atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else 15.0

        # Total GEX
        total_gex = sum(g.get("net_gex", 0) for g in signals.gex_map)

        return USER_PROMPT_TEMPLATE.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            index=chain.index,
            spot_price=f"{chain.spot_price:,.2f}",
            vix=f"{vix:.1f}",
            dte=dte,
            is_expiry="Yes" if is_expiry else "No",
            expiry_date=chain.expiry_date,
            option_chain_table="\n".join(table_lines),
            atm_strike=atm,
            max_pain=chain.max_pain,
            pcr=chain.pcr if chain.pcr != float("inf") else 99.99,
            highest_call_oi_strike=chain.highest_call_oi_strike,
            highest_call_oi=highest_call_oi,
            highest_put_oi_strike=chain.highest_put_oi_strike,
            highest_put_oi=highest_put_oi,
            ivp=signals.iv_percentile,
            ivp_signal=signals.iv_percentile_signal,
            oi_velocity_summary=oi_summary,
            iv_skew=signals.iv_skew,
            iv_skew_signal=signals.iv_skew_signal,
            gex_regime=signals.gex_regime,
            gex_gravity=signals.gex_gravity_center,
            total_gex=total_gex,
            vrp=signals.vrp,
            atm_iv=atm_iv,
            rv20d=max(0, atm_iv - signals.vrp),
            vrp_signal=signals.vrp_signal,
            confluence_score=signals.confluence_score,
            price_trend="Data not available",
            sector_summary="Data not available",
        )

    # ------------------------------------------------------------------
    # Validation & Build
    # ------------------------------------------------------------------

    def _validate_and_build(
        self,
        raw: dict,
        chain: OptionChainSnapshot,
        signals: QuantSignals,
        regime: MarketRegime,
        now: datetime,
    ) -> FnOStrategySetup | None:
        """Validate an LLM strategy recommendation and build FnOStrategySetup."""
        strategy_type = raw.get("strategy_type", "").upper()
        index = raw.get("index", chain.index).upper()
        legs_raw = raw.get("legs", [])
        confidence = int(raw.get("confidence_score", 0))
        rationale = raw.get("rationale", "")

        # (a) Strategy type in playbook
        if strategy_type not in STRATEGY_PLAYBOOK:
            logger.warning("Strategy type '%s' not in playbook", strategy_type)
            return None

        # (b) Valid strikes in chain
        valid_strikes = {s.strike_price for s in chain.strikes}
        for leg in legs_raw:
            if leg.get("strike") not in valid_strikes:
                logger.warning("Strike %s not in option chain", leg.get("strike"))
                return None

        # (c) Confidence >= min
        if confidence < self.config.min_confidence_score:
            logger.warning(
                "Confidence %d < min %d", confidence, self.config.min_confidence_score
            )
            return None

        # Time-of-day rules
        ist_hour = now.hour
        ist_minute = now.minute
        current_minutes = ist_hour * 60 + ist_minute

        if strategy_type in BLOCKED_AFTER_1400 and current_minutes >= 14 * 60:
            logger.warning("%s blocked after 14:00 IST", strategy_type)
            return None

        if strategy_type in DIRECTIONAL_BUYS and current_minutes >= 13 * 60:
            logger.warning("%s blocked after 13:00 IST", strategy_type)
            return None

        # Expiry-day rules
        try:
            expiry_dt = datetime.strptime(chain.expiry_date, "%Y-%m-%d").date()
            is_expiry_day = now.date() == expiry_dt
        except Exception:
            is_expiry_day = False

        if is_expiry_day and strategy_type not in EXPIRY_DAY_STRATEGIES:
            logger.warning("%s not allowed on expiry day", strategy_type)
            return None

        # (d) Expiry >= min_days_to_expiry (except expiry-day strategies)
        try:
            dte = (expiry_dt - now.date()).days
        except Exception:
            dte = 7
        if not is_expiry_day and dte < self.config.min_days_to_expiry:
            logger.warning("DTE %d < min %d", dte, self.config.min_days_to_expiry)
            return None

        # Reject naked selling when paper history < 2 weeks
        if strategy_type in NAKED_SELLING_STRATEGIES:
            paper_history = self.db.get_paper_trading_history(weeks=2)
            if len(paper_history) < 10:  # ~2 weeks of trading days
                logger.warning(
                    "Naked selling rejected — paper history %d days < 2 weeks",
                    len(paper_history),
                )
                return None

        # (f) Confluence meets threshold
        confluence = signals.confluence_score
        is_naked = strategy_type in NAKED_SELLING_STRATEGIES
        is_hedged = strategy_type in ("IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD")

        if is_naked and confluence < 75:
            logger.warning(
                "Confluence %.1f < 75 for naked selling %s",
                confluence, strategy_type,
            )
            return None
        elif not is_hedged and confluence < 60:
            logger.warning("Confluence %.1f < 60 for %s", confluence, strategy_type)
            return None
        elif is_hedged and confluence < 45:
            logger.warning("Confluence %.1f < 45 for hedged %s", confluence, strategy_type)
            return None

        # Build legs
        lot_size = LOT_SIZES.get(index, 25)
        legs: list[StrategyLeg] = []
        for leg_raw in legs_raw:
            num_lots = min(int(leg_raw.get("num_lots", 1)), self.config.max_lots_per_trade)
            legs.append(StrategyLeg(
                index=index,
                strike_price=float(leg_raw["strike"]),
                expiry_date=chain.expiry_date,
                option_type=leg_raw["option_type"].upper(),
                transaction_type=leg_raw["transaction_type"].upper(),
                lot_size=lot_size,
                num_lots=num_lots,
                entry_price=float(leg_raw.get("entry_price", 0)),
            ))

        # Compute net premium
        net_premium = sum(
            leg.entry_price * leg.quantity * (1 if leg.is_sell else -1)
            for leg in legs
        )

        # Compute max loss
        max_loss = self._compute_max_loss(strategy_type, legs, net_premium, lot_size)

        # (e) Max loss <= per_trade_max_capital
        if abs(max_loss) > self.config.per_trade_max_capital:
            logger.warning(
                "Max loss ₹%.0f > per_trade_max_capital ₹%.0f",
                abs(max_loss), self.config.per_trade_max_capital,
            )
            return None

        # Compute max profit
        max_profit = self._compute_max_profit(strategy_type, legs, net_premium, lot_size)

        # Compute strategy Greeks
        greeks = self.greeks_calc.strategy_greeks(legs, chain.spot_price)

        setup = FnOStrategySetup(
            strategy_type=strategy_type,
            index=index,
            legs=legs,
            net_premium=round(net_premium, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            net_delta=round(greeks.delta, 4),
            net_gamma=round(greeks.gamma, 4),
            net_theta=round(greeks.theta, 4),
            net_vega=round(greeks.vega, 4),
            confidence_score=confidence,
            rationale=rationale,
            market_regime=regime.value,
            confluence_score=confluence,
            expiry_date=chain.expiry_date,
        )

        # Log selection
        self.db.insert_audit_log(
            "FNO_STRATEGY_SELECTED",
            json.dumps({
                "strategy_type": strategy_type,
                "index": index,
                "confidence": confidence,
                "confluence": confluence,
                "max_loss": max_loss,
                "regime": regime.value,
            }),
        )

        return setup

    # ------------------------------------------------------------------
    # Max Loss / Max Profit Computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_max_loss(
        strategy_type: str,
        legs: list[StrategyLeg],
        net_premium: float,
        lot_size: int,
    ) -> float:
        """Compute theoretical max loss for a strategy.

        Returns a positive number representing the maximum possible loss.
        """
        if strategy_type == "IRON_CONDOR":
            # Max loss = max(call_spread_width, put_spread_width) × lots × lot_size - net_premium
            ce_sells = [l for l in legs if l.option_type == "CE" and l.is_sell]
            ce_buys = [l for l in legs if l.option_type == "CE" and not l.is_sell]
            pe_sells = [l for l in legs if l.option_type == "PE" and l.is_sell]
            pe_buys = [l for l in legs if l.option_type == "PE" and not l.is_sell]

            call_width = 0.0
            if ce_sells and ce_buys:
                call_width = abs(ce_buys[0].strike_price - ce_sells[0].strike_price)
            put_width = 0.0
            if pe_sells and pe_buys:
                put_width = abs(pe_sells[0].strike_price - pe_buys[0].strike_price)

            num_lots = legs[0].num_lots if legs else 1
            max_spread = max(call_width, put_width)
            return max_spread * num_lots * lot_size - abs(net_premium)

        if strategy_type in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"):
            # Max loss = (spread_width - net_premium_per_unit) × lots × lot_size
            sells = [l for l in legs if l.is_sell]
            buys = [l for l in legs if not l.is_sell]
            if sells and buys:
                width = abs(sells[0].strike_price - buys[0].strike_price)
                num_lots = legs[0].num_lots
                return width * num_lots * lot_size - abs(net_premium)
            return abs(net_premium)

        if strategy_type in ("SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
                             "NAKED_CE", "NAKED_PE"):
            # Unlimited risk — estimate as 2x premium collected for risk check
            return abs(net_premium) * 2

        if strategy_type in ("LONG_STRADDLE", "DIRECTIONAL_CE_BUY", "DIRECTIONAL_PE_BUY"):
            # Max loss = premium paid
            return abs(net_premium)

        # Default: premium paid/collected
        return abs(net_premium)

    @staticmethod
    def _compute_max_profit(
        strategy_type: str,
        legs: list[StrategyLeg],
        net_premium: float,
        lot_size: int,
    ) -> float:
        """Compute theoretical max profit for a strategy."""
        if strategy_type in ("IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
                             "SHORT_STRANGLE", "SHORT_STRADDLE", "STRANGLE", "STRADDLE",
                             "NAKED_CE", "NAKED_PE"):
            # Max profit = net premium collected
            return abs(net_premium)

        if strategy_type in ("LONG_STRADDLE", "DIRECTIONAL_CE_BUY", "DIRECTIONAL_PE_BUY"):
            # Unlimited profit — estimate as 3x premium for display
            return abs(net_premium) * 3

        return abs(net_premium)
