"""Tests for F&O Adjustment Engine (Phase 4).

Tests trigger logic, limits, and strategy-specific adjustment behavior.
All tests use mocked data — no live API calls.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from fno.adjustment_engine import (
    should_adjust,
    execute_adjustment,
    MAX_ADJUSTMENTS_LIFETIME,
    MAX_ADJUSTMENTS_PER_DAY,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _make_db():
    """Create in-memory DB with fno_adjustments table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE fno_adjustments (
        id INTEGER PRIMARY KEY,
        strategy_id INTEGER,
        adjustment_time TEXT,
        trigger_reason TEXT,
        legs_closed TEXT,
        legs_opened TEXT,
        net_pnl_impact REAL
    )""")
    conn.execute("""CREATE TABLE fno_strategies (
        id INTEGER PRIMARY KEY,
        legs_json TEXT,
        status TEXT DEFAULT 'OPEN'
    )""")
    conn.commit()
    db = MagicMock()
    db.conn = conn
    return db


def _make_chain(spot: float, atm_iv: float = 15.0):
    """Create mock option chain with ATM IV."""
    return {
        "strikes": [
            {"strike_price": spot, "option_type": "CE", "iv": atm_iv, "ltp": 100},
            {"strike_price": spot, "option_type": "PE", "iv": atm_iv, "ltp": 100},
        ]
    }


def _iron_condor_strategy(
    ce_short=24200, ce_long=24400, pe_short=23800, pe_long=23600,
    index="NIFTY", num_lots=1, net_premium=500, max_profit=500,
):
    """Create a mock Iron Condor strategy dict."""
    legs = [
        {"strike": ce_short, "option_type": "CE", "transaction_type": "SELL", "num_lots": num_lots, "expiry_date": "2026-06-05"},
        {"strike": ce_long, "option_type": "CE", "transaction_type": "BUY", "num_lots": num_lots, "expiry_date": "2026-06-05"},
        {"strike": pe_short, "option_type": "PE", "transaction_type": "SELL", "num_lots": num_lots, "expiry_date": "2026-06-05"},
        {"strike": pe_long, "option_type": "PE", "transaction_type": "BUY", "num_lots": num_lots, "expiry_date": "2026-06-05"},
    ]
    return {
        "id": 1,
        "strategy_type": "IRON_CONDOR",
        "index_name": index,
        "status": "OPEN",
        "legs_json": json.dumps(legs),
        "net_premium": net_premium,
        "max_profit": max_profit,
    }


class TestIronCondorAdjustment:
    """Test Iron Condor adjustment triggers."""

    def test_iron_condor_short_call_tested_triggers_roll(self):
        """When spot approaches short CE within 0.5σ, should trigger roll."""
        # IC with high max_profit so roll cost doesn't exceed 2× limit
        # Roll cost = 50 (interval) × 1 (lots) × 25 (lot_size) = 1250
        # Need max_profit > 1250/2 = 625
        strategy = _iron_condor_strategy(ce_short=24200, pe_short=23600, max_profit=2000, net_premium=2000)
        chain = _make_chain(spot=24150, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db)

        assert result is not None
        assert result["action"] == "ROLL_TESTED_SIDE"
        assert result["tested_side"] == "CE"
        assert "short CE 24200" in result["trigger_reason"]
        assert len(result["legs_to_close"]) == 2
        assert len(result["legs_to_open"]) == 2

    def test_iron_condor_short_put_tested_triggers_roll(self):
        """When spot approaches short PE within 0.5σ, should trigger roll."""
        strategy = _iron_condor_strategy(ce_short=24400, pe_short=23800, max_profit=2000, net_premium=2000)
        chain = _make_chain(spot=23850, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=23850, current_chain=chain, db=db)

        assert result is not None
        assert result["action"] == "ROLL_TESTED_SIDE"
        assert result["tested_side"] == "PE"
        assert "short PE 23800" in result["trigger_reason"]

    def test_iron_condor_far_side_collapse_when_safe(self):
        """When spot is far from both strikes, no adjustment needed."""
        # Wide strikes so spot at 24000 is well outside 0.5σ of both
        strategy = _iron_condor_strategy(ce_short=24500, pe_short=23500, max_profit=2000, net_premium=2000)
        chain = _make_chain(spot=24000, atm_iv=10.0)  # Low IV = small sigma (~100pts)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24000, current_chain=chain, db=db)

        assert result is None  # No adjustment when spot is centered

    def test_iron_condor_no_trigger_when_spot_safe(self):
        """Spot at 24000 with shorts at 24200/23800 — no trigger (>0.5σ away)."""
        strategy = _iron_condor_strategy(ce_short=24200, pe_short=23800)
        chain = _make_chain(spot=24000, atm_iv=12.0)  # Low IV = small sigma
        db = _make_db()

        result = should_adjust(strategy, current_spot=24000, current_chain=chain, db=db)
        assert result is None


class TestAdjustmentLimits:
    """Test adjustment frequency limits."""

    def test_max_2_adjustments_per_strategy(self):
        """After 2 lifetime adjustments, no more adjustments allowed."""
        strategy = _iron_condor_strategy(ce_short=24200, pe_short=23800)
        chain = _make_chain(spot=24150, atm_iv=15.0)
        db = _make_db()

        # Insert 2 prior adjustments
        now = datetime.now(IST)
        for i in range(2):
            db.conn.execute(
                "INSERT INTO fno_adjustments (strategy_id, adjustment_time, trigger_reason, legs_closed, legs_opened, net_pnl_impact) VALUES (?,?,?,?,?,?)",
                (1, (now - timedelta(days=i+1)).isoformat(), "test", "[]", "[]", -100),
            )
        db.conn.commit()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db)
        assert result is None  # Blocked by lifetime limit

    def test_max_1_adjustment_per_day(self):
        """After 1 adjustment today, no more today."""
        strategy = _iron_condor_strategy(ce_short=24200, pe_short=23800)
        chain = _make_chain(spot=24150, atm_iv=15.0)
        db = _make_db()

        # Insert 1 adjustment today
        now = datetime.now(IST)
        db.conn.execute(
            "INSERT INTO fno_adjustments (strategy_id, adjustment_time, trigger_reason, legs_closed, legs_opened, net_pnl_impact) VALUES (?,?,?,?,?,?)",
            (1, now.isoformat(), "test", "[]", "[]", -100),
        )
        db.conn.commit()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db)
        assert result is None  # Blocked by daily limit

    def test_adjustment_skipped_if_loss_too_large(self):
        """If roll would lock loss > 2× max_profit, EXIT_INSTEAD."""
        # Small max_profit (100) but large roll cost (50pts × 25 = 1250)
        strategy = _iron_condor_strategy(
            ce_short=24200, pe_short=23800,
            net_premium=100, max_profit=100,
        )
        chain = _make_chain(spot=24150, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db)

        assert result is not None
        assert result["action"] == "EXIT_INSTEAD"
        assert "roll loss" in result["trigger_reason"] or "too expensive" in result["trigger_reason"]


class TestOtherStrategies:
    """Test adjustment for non-IC strategies."""

    def test_short_strangle_adjustment(self):
        """Short strangle CE tested should trigger roll."""
        legs = [
            {"strike": 24200, "option_type": "CE", "transaction_type": "SELL", "num_lots": 1, "expiry_date": "2026-06-05"},
            {"strike": 23800, "option_type": "PE", "transaction_type": "SELL", "num_lots": 1, "expiry_date": "2026-06-05"},
        ]
        strategy = {
            "id": 2, "strategy_type": "SHORT_STRANGLE", "index_name": "NIFTY",
            "status": "OPEN", "legs_json": json.dumps(legs),
            "net_premium": 800, "max_profit": 800,
        }
        chain = _make_chain(spot=24150, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db)

        assert result is not None
        assert result["action"] == "ROLL_TESTED_SIDE"
        assert result["tested_side"] == "CE"

    def test_bull_put_spread_roll_down(self):
        """Bull put spread: spot approaching short put triggers roll down."""
        legs = [
            {"strike": 23800, "option_type": "PE", "transaction_type": "SELL", "num_lots": 1, "expiry_date": "2026-06-05"},
            {"strike": 23600, "option_type": "PE", "transaction_type": "BUY", "num_lots": 1, "expiry_date": "2026-06-05"},
        ]
        strategy = {
            "id": 3, "strategy_type": "BULL_PUT_SPREAD", "index_name": "NIFTY",
            "status": "OPEN", "legs_json": json.dumps(legs),
            "net_premium": 2000, "max_profit": 2000,
        }
        # Spot at 23850 — within 1.0σ of short PE 23800
        chain = _make_chain(spot=23850, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=23850, current_chain=chain, db=db)

        assert result is not None
        assert result["tested_side"] == "PE"
        # New legs should have lower strikes
        new_legs = result["legs_to_open"]
        sell_legs = [l for l in new_legs if l and l.get("transaction_type") == "SELL"]
        assert len(sell_legs) > 0
        assert sell_legs[0]["strike"] < 23800  # Rolled down

    def test_bear_call_spread_roll_up(self):
        """Bear call spread: spot approaching short call triggers roll up."""
        legs = [
            {"strike": 24200, "option_type": "CE", "transaction_type": "SELL", "num_lots": 1, "expiry_date": "2026-06-05"},
            {"strike": 24400, "option_type": "CE", "transaction_type": "BUY", "num_lots": 1, "expiry_date": "2026-06-05"},
        ]
        strategy = {
            "id": 4, "strategy_type": "BEAR_CALL_SPREAD", "index_name": "NIFTY",
            "status": "OPEN", "legs_json": json.dumps(legs),
            "net_premium": 2000, "max_profit": 2000,
        }
        # Spot at 24100 — within 1.0σ of short CE 24200
        chain = _make_chain(spot=24100, atm_iv=15.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24100, current_chain=chain, db=db)

        assert result is not None
        assert result["tested_side"] == "CE"
        # New legs should have higher strikes
        new_legs = result["legs_to_open"]
        sell_legs = [l for l in new_legs if l and l.get("transaction_type") == "SELL"]
        assert len(sell_legs) > 0
        assert sell_legs[0]["strike"] > 24200  # Rolled up

    def test_adjustment_skipped_when_vix_too_high(self):
        """VIX > 25 should skip adjustment entirely."""
        strategy = _iron_condor_strategy(ce_short=24200, pe_short=23800)
        chain = _make_chain(spot=24150, atm_iv=25.0)
        db = _make_db()

        result = should_adjust(strategy, current_spot=24150, current_chain=chain, db=db, vix=26.0)

        assert result is None  # VIX gate blocks adjustment
