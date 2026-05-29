"""F&O Adjustment Engine — roll tested-side strikes when underlying challenges short strikes.

Prevents catastrophic losses on Iron Condors and credit spreads by rolling
the tested side further OTM when spot approaches short strikes.

Triggers:
- Iron Condor: spot within 0.5σ of either short strike
- Short Strangle: same as IC
- Bull Put Spread: spot within 1.0σ of short put
- Bear Call Spread: spot within 1.0σ of short call

Limits:
- Max 1 adjustment per strategy per day
- Max 2 adjustments per strategy lifetime
- If adjustment would lock loss > 2× max profit: exit instead
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database.db_manager import DBManager
    from intraday.broker_base import BrokerClient

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Strike intervals per index
STRIKE_INTERVALS = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}

# Max adjustments per strategy lifetime
MAX_ADJUSTMENTS_LIFETIME = 2

# Max adjustments per strategy per day
MAX_ADJUSTMENTS_PER_DAY = 1


def _compute_sigma(spot: float, atm_iv: float, dte_days: int) -> float:
    """Compute 1-sigma move for the underlying."""
    if dte_days <= 0:
        dte_days = 1
    return spot * (atm_iv / 100) * math.sqrt(dte_days / 365)


def _get_atm_iv_from_chain(chain: dict, spot: float) -> float:
    """Extract ATM IV from option chain dict."""
    strikes = chain.get("strikes", [])
    if not strikes:
        return 15.0

    best_iv = 15.0
    best_dist = float("inf")
    for s in strikes:
        strike = float(s.get("strike_price", s.get("strikePrice", 0)))
        iv = float(s.get("iv", 0))
        if iv > 0 and abs(strike - spot) < best_dist:
            best_dist = abs(strike - spot)
            best_iv = iv
    return best_iv


def _count_adjustments_today(db: Any, strategy_id: int) -> int:
    """Count adjustments made today for a strategy."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM fno_adjustments WHERE strategy_id=? AND adjustment_time LIKE ?",
            (strategy_id, f"{today}%"),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _count_adjustments_lifetime(db: Any, strategy_id: int) -> int:
    """Count total adjustments for a strategy."""
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM fno_adjustments WHERE strategy_id=?",
            (strategy_id,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def should_adjust(
    strategy: dict,
    current_spot: float,
    current_chain: dict,
    db: Any = None,
    vix: float = 15.0,
) -> dict | None:
    """Determine if a strategy needs adjustment.

    Args:
        strategy: dict from fno_strategies table row
        current_spot: current underlying spot price
        current_chain: option chain dict with 'strikes' list
        db: DBManager for adjustment history lookup
        vix: current VIX level

    Returns:
        Adjustment instruction dict or None if no adjustment needed.
        Instruction format:
        {
            "action": "ROLL_TESTED_SIDE" | "COLLAPSE_FAR_SIDE" | "EXIT_INSTEAD",
            "trigger_reason": str,
            "tested_side": "CE" | "PE",
            "legs_to_close": [...],
            "legs_to_open": [...],
            "estimated_pnl_impact": float,
        }
    """
    # Hard skip: VIX > 25 means don't adjust, just let force exit handle it
    if vix > 25:
        return None

    strategy_id = strategy.get("id")
    strategy_type = strategy.get("strategy_type", "").upper()
    status = strategy.get("status", "")

    # Only adjust OPEN strategies
    if status not in ("OPEN", "PARTIAL_BOOKED"):
        return None

    # Check adjustment limits
    if db:
        today_count = _count_adjustments_today(db, strategy_id)
        if today_count >= MAX_ADJUSTMENTS_PER_DAY:
            logger.debug("Strategy %d: max daily adjustments reached", strategy_id)
            return None

        lifetime_count = _count_adjustments_lifetime(db, strategy_id)
        if lifetime_count >= MAX_ADJUSTMENTS_LIFETIME:
            logger.debug("Strategy %d: max lifetime adjustments reached", strategy_id)
            return None

    # Parse legs
    legs_json = strategy.get("legs_json", "[]")
    try:
        legs = json.loads(legs_json) if isinstance(legs_json, str) else legs_json
    except (json.JSONDecodeError, TypeError):
        return None

    if not legs:
        return None

    # Get index info
    index = strategy.get("index_name", "NIFTY")
    interval = STRIKE_INTERVALS.get(index, 50)

    # Compute sigma
    try:
        expiry_str = legs[0].get("expiry_date", "")
        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        dte_days = max(1, (expiry_dt.date() - datetime.now(IST).date()).days)
    except Exception:
        dte_days = 7

    atm_iv = _get_atm_iv_from_chain(current_chain, current_spot)
    one_sigma = _compute_sigma(current_spot, atm_iv, dte_days)

    # Dispatch by strategy type
    if strategy_type == "IRON_CONDOR":
        return _check_iron_condor(strategy, legs, current_spot, one_sigma, interval, index)
    elif strategy_type == "SHORT_STRANGLE":
        return _check_short_strangle(strategy, legs, current_spot, one_sigma, interval, index)
    elif strategy_type == "BULL_PUT_SPREAD":
        return _check_bull_put_spread(strategy, legs, current_spot, one_sigma, interval, index)
    elif strategy_type == "BEAR_CALL_SPREAD":
        return _check_bear_call_spread(strategy, legs, current_spot, one_sigma, interval, index)

    return None


def _check_iron_condor(
    strategy: dict, legs: list, spot: float, sigma: float, interval: float, index: str,
) -> dict | None:
    """Check Iron Condor for adjustment trigger (0.5σ proximity)."""
    # Find short strikes
    ce_short = None
    pe_short = None
    ce_long = None
    pe_long = None

    for leg in legs:
        opt_type = leg.get("option_type", "")
        txn = leg.get("transaction_type", "")
        strike = float(leg.get("strike", leg.get("strike_price", 0)))

        if opt_type == "CE" and txn == "SELL":
            ce_short = strike
        elif opt_type == "CE" and txn == "BUY":
            ce_long = strike
        elif opt_type == "PE" and txn == "SELL":
            pe_short = strike
        elif opt_type == "PE" and txn == "BUY":
            pe_long = strike

    if ce_short is None or pe_short is None:
        return None

    trigger_distance = sigma * 0.5
    max_profit = float(strategy.get("max_profit", strategy.get("net_premium", 0)))

    # Check call side tested
    if spot >= ce_short - trigger_distance:
        # Roll call side further OTM
        new_ce_short = ce_short + interval
        new_ce_long = (ce_long + interval) if ce_long else new_ce_short + 200

        # Estimate P&L impact of rolling (rough: lose the width difference)
        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {
                "action": "EXIT_INSTEAD",
                "trigger_reason": f"spot {spot:.0f} tested short CE {ce_short:.0f} (within 0.5σ={trigger_distance:.0f}), but roll loss ₹{estimated_loss:.0f} > 2× max_profit ₹{max_profit*2:.0f}",
                "tested_side": "CE",
                "legs_to_close": [],
                "legs_to_open": [],
                "estimated_pnl_impact": -estimated_loss,
            }

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 0.5σ ({trigger_distance:.0f}) of short CE {ce_short:.0f}",
            "tested_side": "CE",
            "legs_to_close": [
                {"strike": ce_short, "option_type": "CE", "transaction_type": "BUY"},  # Buy back short
                {"strike": ce_long, "option_type": "CE", "transaction_type": "SELL"},  # Sell long
            ],
            "legs_to_open": [
                {"strike": new_ce_short, "option_type": "CE", "transaction_type": "SELL"},
                {"strike": new_ce_long, "option_type": "CE", "transaction_type": "BUY"},
            ],
            "estimated_pnl_impact": -estimated_loss,
        }

    # Check put side tested
    if spot <= pe_short + trigger_distance:
        new_pe_short = pe_short - interval
        new_pe_long = (pe_long - interval) if pe_long else new_pe_short - 200

        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {
                "action": "EXIT_INSTEAD",
                "trigger_reason": f"spot {spot:.0f} tested short PE {pe_short:.0f} (within 0.5σ={trigger_distance:.0f}), but roll loss ₹{estimated_loss:.0f} > 2× max_profit ₹{max_profit*2:.0f}",
                "tested_side": "PE",
                "legs_to_close": [],
                "legs_to_open": [],
                "estimated_pnl_impact": -estimated_loss,
            }

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 0.5σ ({trigger_distance:.0f}) of short PE {pe_short:.0f}",
            "tested_side": "PE",
            "legs_to_close": [
                {"strike": pe_short, "option_type": "PE", "transaction_type": "BUY"},
                {"strike": pe_long, "option_type": "PE", "transaction_type": "SELL"},
            ],
            "legs_to_open": [
                {"strike": new_pe_short, "option_type": "PE", "transaction_type": "SELL"},
                {"strike": new_pe_long, "option_type": "PE", "transaction_type": "BUY"},
            ],
            "estimated_pnl_impact": -estimated_loss,
        }

    # Check far side collapse opportunity (>30% of max profit captured)
    # If call side is safe and put side premium decayed >30%, collapse put side
    # (This is a profit-taking optimization, not a defensive adjustment)

    return None


def _check_short_strangle(
    strategy: dict, legs: list, spot: float, sigma: float, interval: float, index: str,
) -> dict | None:
    """Check Short Strangle for adjustment (same trigger as IC, 0.5σ)."""
    ce_short = None
    pe_short = None

    for leg in legs:
        opt_type = leg.get("option_type", "")
        txn = leg.get("transaction_type", "")
        strike = float(leg.get("strike", leg.get("strike_price", 0)))

        if opt_type == "CE" and txn == "SELL":
            ce_short = strike
        elif opt_type == "PE" and txn == "SELL":
            pe_short = strike

    if ce_short is None or pe_short is None:
        return None

    trigger_distance = sigma * 0.5
    max_profit = float(strategy.get("max_profit", strategy.get("net_premium", 0)))

    if spot >= ce_short - trigger_distance:
        new_ce_short = ce_short + interval
        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {"action": "EXIT_INSTEAD", "trigger_reason": f"strangle CE tested, roll too expensive", "tested_side": "CE", "legs_to_close": [], "legs_to_open": [], "estimated_pnl_impact": -estimated_loss}

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 0.5σ of short CE {ce_short:.0f}",
            "tested_side": "CE",
            "legs_to_close": [{"strike": ce_short, "option_type": "CE", "transaction_type": "BUY"}],
            "legs_to_open": [{"strike": new_ce_short, "option_type": "CE", "transaction_type": "SELL"}],
            "estimated_pnl_impact": -estimated_loss,
        }

    if spot <= pe_short + trigger_distance:
        new_pe_short = pe_short - interval
        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {"action": "EXIT_INSTEAD", "trigger_reason": f"strangle PE tested, roll too expensive", "tested_side": "PE", "legs_to_close": [], "legs_to_open": [], "estimated_pnl_impact": -estimated_loss}

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 0.5σ of short PE {pe_short:.0f}",
            "tested_side": "PE",
            "legs_to_close": [{"strike": pe_short, "option_type": "PE", "transaction_type": "BUY"}],
            "legs_to_open": [{"strike": new_pe_short, "option_type": "PE", "transaction_type": "SELL"}],
            "estimated_pnl_impact": -estimated_loss,
        }

    return None


def _check_bull_put_spread(
    strategy: dict, legs: list, spot: float, sigma: float, interval: float, index: str,
) -> dict | None:
    """Check Bull Put Spread for adjustment (1.0σ proximity to short put)."""
    pe_short = None
    pe_long = None

    for leg in legs:
        opt_type = leg.get("option_type", "")
        txn = leg.get("transaction_type", "")
        strike = float(leg.get("strike", leg.get("strike_price", 0)))

        if opt_type == "PE" and txn == "SELL":
            pe_short = strike
        elif opt_type == "PE" and txn == "BUY":
            pe_long = strike

    if pe_short is None:
        return None

    trigger_distance = sigma * 1.0  # Wider trigger for spreads
    max_profit = float(strategy.get("max_profit", strategy.get("net_premium", 0)))

    if spot <= pe_short + trigger_distance:
        new_pe_short = pe_short - interval
        new_pe_long = (pe_long - interval) if pe_long else new_pe_short - 200
        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {"action": "EXIT_INSTEAD", "trigger_reason": f"bull put short tested, roll too expensive", "tested_side": "PE", "legs_to_close": [], "legs_to_open": [], "estimated_pnl_impact": -estimated_loss}

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 1.0σ ({trigger_distance:.0f}) of short PE {pe_short:.0f}",
            "tested_side": "PE",
            "legs_to_close": [
                {"strike": pe_short, "option_type": "PE", "transaction_type": "BUY"},
                {"strike": pe_long, "option_type": "PE", "transaction_type": "SELL"} if pe_long else None,
            ],
            "legs_to_open": [
                {"strike": new_pe_short, "option_type": "PE", "transaction_type": "SELL"},
                {"strike": new_pe_long, "option_type": "PE", "transaction_type": "BUY"},
            ],
            "estimated_pnl_impact": -estimated_loss,
        }

    return None


def _check_bear_call_spread(
    strategy: dict, legs: list, spot: float, sigma: float, interval: float, index: str,
) -> dict | None:
    """Check Bear Call Spread for adjustment (1.0σ proximity to short call)."""
    ce_short = None
    ce_long = None

    for leg in legs:
        opt_type = leg.get("option_type", "")
        txn = leg.get("transaction_type", "")
        strike = float(leg.get("strike", leg.get("strike_price", 0)))

        if opt_type == "CE" and txn == "SELL":
            ce_short = strike
        elif opt_type == "CE" and txn == "BUY":
            ce_long = strike

    if ce_short is None:
        return None

    trigger_distance = sigma * 1.0
    max_profit = float(strategy.get("max_profit", strategy.get("net_premium", 0)))

    if spot >= ce_short - trigger_distance:
        new_ce_short = ce_short + interval
        new_ce_long = (ce_long + interval) if ce_long else new_ce_short + 200
        estimated_loss = interval * int(legs[0].get("num_lots", 1)) * _lot_size(index)

        if estimated_loss > max_profit * 2:
            return {"action": "EXIT_INSTEAD", "trigger_reason": f"bear call short tested, roll too expensive", "tested_side": "CE", "legs_to_close": [], "legs_to_open": [], "estimated_pnl_impact": -estimated_loss}

        return {
            "action": "ROLL_TESTED_SIDE",
            "trigger_reason": f"spot {spot:.0f} within 1.0σ ({trigger_distance:.0f}) of short CE {ce_short:.0f}",
            "tested_side": "CE",
            "legs_to_close": [
                {"strike": ce_short, "option_type": "CE", "transaction_type": "BUY"},
                {"strike": ce_long, "option_type": "CE", "transaction_type": "SELL"} if ce_long else None,
            ],
            "legs_to_open": [
                {"strike": new_ce_short, "option_type": "CE", "transaction_type": "SELL"},
                {"strike": new_ce_long, "option_type": "CE", "transaction_type": "BUY"},
            ],
            "estimated_pnl_impact": -estimated_loss,
        }

    return None


def execute_adjustment(
    strategy_id: int,
    instruction: dict,
    broker: Any,
    db: Any,
) -> dict:
    """Execute an adjustment: close tested legs, open new legs, record in DB.

    Args:
        strategy_id: fno_strategies.id
        instruction: dict from should_adjust()
        broker: BrokerClient instance
        db: DBManager instance

    Returns:
        dict with {success, adjustment_id, error}
    """
    now = datetime.now(IST)
    action = instruction.get("action", "")

    # If EXIT_INSTEAD, just mark for exit (monitor handles actual exit)
    if action == "EXIT_INSTEAD":
        logger.warning(
            "Strategy %d: EXIT_INSTEAD — %s",
            strategy_id, instruction.get("trigger_reason", ""),
        )
        _record_adjustment(db, strategy_id, instruction, now)
        return {"success": True, "action": "EXIT_INSTEAD", "adjustment_id": None}

    # ROLL_TESTED_SIDE: close old legs, open new legs
    legs_to_close = [l for l in instruction.get("legs_to_close", []) if l is not None]
    legs_to_open = [l for l in instruction.get("legs_to_open", []) if l is not None]

    if not legs_to_close or not legs_to_open:
        return {"success": False, "error": "No legs to close/open"}

    # In paper mode (DryRunBrokerClient), just record the adjustment
    # In live mode, would place actual orders here
    logger.info(
        "Strategy %d: ADJUSTING — closing %d legs, opening %d legs. Reason: %s",
        strategy_id, len(legs_to_close), len(legs_to_open),
        instruction.get("trigger_reason", ""),
    )

    # Record adjustment
    adj_id = _record_adjustment(db, strategy_id, instruction, now)

    # Update strategy legs_json with new legs
    _update_strategy_legs(db, strategy_id, instruction)

    return {"success": True, "action": "ROLL_TESTED_SIDE", "adjustment_id": adj_id}


def _record_adjustment(db: Any, strategy_id: int, instruction: dict, now: datetime) -> int | None:
    """Record adjustment in fno_adjustments table."""
    if not db:
        return None
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            """INSERT INTO fno_adjustments
               (strategy_id, adjustment_time, trigger_reason, legs_closed, legs_opened, net_pnl_impact)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                strategy_id,
                now.isoformat(),
                instruction.get("trigger_reason", ""),
                json.dumps(instruction.get("legs_to_close", [])),
                json.dumps(instruction.get("legs_to_open", [])),
                instruction.get("estimated_pnl_impact", 0),
            ),
        )
        db.conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error("Failed to record adjustment: %s", e)
        return None


def _update_strategy_legs(db: Any, strategy_id: int, instruction: dict) -> None:
    """Update strategy legs_json after adjustment."""
    if not db:
        return
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT legs_json FROM fno_strategies WHERE id=?", (strategy_id,))
        row = cursor.fetchone()
        if not row:
            return

        legs = json.loads(row[0] or "[]")
        legs_to_close = instruction.get("legs_to_close", [])
        legs_to_open = instruction.get("legs_to_open", [])

        # Remove closed legs
        for close_leg in legs_to_close:
            if close_leg is None:
                continue
            close_strike = close_leg.get("strike", 0)
            close_opt = close_leg.get("option_type", "")
            # Reverse transaction to find original leg
            orig_txn = "SELL" if close_leg.get("transaction_type") == "BUY" else "BUY"
            legs = [
                l for l in legs
                if not (
                    abs(float(l.get("strike", l.get("strike_price", 0))) - close_strike) < 0.01
                    and l.get("option_type", "") == close_opt
                    and l.get("transaction_type", "") == orig_txn
                )
            ]

        # Add new legs
        for new_leg in legs_to_open:
            if new_leg is None:
                continue
            legs.append(new_leg)

        cursor.execute(
            "UPDATE fno_strategies SET legs_json=? WHERE id=?",
            (json.dumps(legs), strategy_id),
        )
        db.conn.commit()
    except Exception as e:
        logger.error("Failed to update strategy legs: %s", e)


def _lot_size(index: str) -> int:
    """Get lot size for an index."""
    return {"NIFTY": 25, "BANKNIFTY": 15, "FINNIFTY": 25}.get(index, 25)
