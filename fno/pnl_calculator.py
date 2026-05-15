"""F&O P&L Calculator — pure logic, data-source agnostic.

Accepts a callable `get_option_chain_func(index, expiry)` to fetch prices.
This keeps the calculator independent of Dhan/NSE/cache implementation.
"""
import json
import logging
import sqlite3
from typing import Callable

logger = logging.getLogger(__name__)


def get_current_premium(
    strike: float,
    option_type: str,
    expiry: str,
    index: str,
    get_chain_func: Callable,
) -> float | None:
    """Fetch current option premium using provided chain function.

    Args:
        strike: Strike price (e.g., 24500)
        option_type: 'CE' or 'PE'
        expiry: Expiry date string
        index: 'NIFTY', 'BANKNIFTY', 'FINNIFTY'
        get_chain_func: callable(index, expiry) -> dict with 'strikes' list

    Returns:
        Current LTP as float, or None if not found
    """
    chain = get_chain_func(index, expiry)
    if not chain or not chain.get("strikes"):
        return None

    strikes = chain["strikes"]
    for item in strikes:
        if not isinstance(item, dict):
            continue
        item_strike = item.get("strikePrice", item.get("strike", 0))
        if abs(float(item_strike) - strike) < 0.01:
            opt_data = item.get(option_type, {})
            if isinstance(opt_data, dict):
                ltp = opt_data.get("lastPrice", opt_data.get("ltp", 0))
                if ltp and float(ltp) > 0:
                    return float(ltp)
    return None


def compute_leg_pnl(leg_dict: dict, get_chain_func: Callable) -> dict:
    """Compute P&L for one option leg.

    Args:
        leg_dict: dict with action, entry_price, quantity, strike_price,
                  option_type, expiry_date, index_name
        get_chain_func: callable(index, expiry) -> chain dict

    Returns:
        dict {current_premium, pnl_per_unit, total_pnl, priced}
    """
    strike = float(leg_dict.get("strike_price", 0))
    option_type = leg_dict.get("option_type", "CE")
    expiry = leg_dict.get("expiry_date", "")
    index = leg_dict.get("index_name", "NIFTY")
    action = leg_dict.get("action", "BUY")
    entry_price = float(leg_dict.get("entry_price", 0))
    quantity = int(leg_dict.get("quantity", leg_dict.get("lots", 1)) or 1)

    current_premium = get_current_premium(strike, option_type, expiry, index, get_chain_func)

    if current_premium is None:
        return {"current_premium": None, "pnl_per_unit": 0, "total_pnl": 0, "priced": False}

    # P&L calculation:
    # SELL leg: profit when premium drops (entry - current)
    # BUY leg: profit when premium rises (current - entry)
    if action.upper() == "SELL":
        pnl_per_unit = entry_price - current_premium
    else:
        pnl_per_unit = current_premium - entry_price

    total_pnl = pnl_per_unit * quantity

    return {
        "current_premium": current_premium,
        "pnl_per_unit": round(pnl_per_unit, 2),
        "total_pnl": round(total_pnl, 2),
        "priced": True,
    }


def compute_strategy_pnl(db_path: str, strategy_id: int, get_chain_func: Callable) -> dict:
    """Aggregate P&L across all legs of a strategy.

    Returns:
        dict {strategy_id, total_pnl, legs_pnl: list, all_legs_priced: bool}
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    legs = con.execute(
        "SELECT * FROM fno_trades WHERE strategy_id=? AND action IN ('BUY','SELL')",
        (strategy_id,)
    ).fetchall()
    con.close()

    if not legs:
        return {"strategy_id": strategy_id, "total_pnl": 0, "legs_pnl": [], "all_legs_priced": False}

    legs_pnl = []
    total_pnl = 0
    all_priced = True

    for leg in legs:
        leg_dict = dict(leg)
        result = compute_leg_pnl(leg_dict, get_chain_func)
        result["tradingsymbol"] = leg_dict.get("tradingsymbol", "")
        result["strike_price"] = leg_dict.get("strike_price")
        result["option_type"] = leg_dict.get("option_type")
        result["action"] = leg_dict.get("action")
        legs_pnl.append(result)
        total_pnl += result["total_pnl"]
        if not result["priced"]:
            all_priced = False

    return {
        "strategy_id": strategy_id,
        "total_pnl": round(total_pnl, 2),
        "legs_pnl": legs_pnl,
        "all_legs_priced": all_priced,
    }


def update_strategy_pnl_in_db(db_path: str, strategy_id: int, legs_pnl: list) -> None:
    """Update fno_trades with current_price for each leg."""
    con = sqlite3.connect(db_path)
    for leg in legs_pnl:
        if leg.get("priced") and leg.get("current_premium") is not None:
            con.execute(
                "UPDATE fno_trades SET current_price=?, pnl=? WHERE strategy_id=? AND strike_price=? AND option_type=? AND action=?",
                (leg["current_premium"], leg["total_pnl"], strategy_id,
                 leg["strike_price"], leg["option_type"], leg["action"])
            )
    con.commit()
    con.close()
