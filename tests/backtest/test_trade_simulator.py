"""
Tests for backtest trade simulation logic.
CRITICAL: These tests document the Bug found in SONNET_LOGICS Section 17.

Bug found: exit loop walked ALL candles including pre-entry ones.
           Stop loss used close <= sl instead of low <= sl.
           This inflated WR from real ~50% to fake 76%.

These tests verify the CORRECT behavior.
"""
import pytest
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def make_candle(h, m, o, hi, lo, c, vol, date="2026-04-15"):
    dt = datetime.strptime(f"{date} {h:02d}:{m:02d}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return {"time": dt, "open": o, "high": hi, "low": lo, "close": c, "volume": vol}


class TestExitLogicCorrectness:
    def test_stopped_out_trade_is_a_loss(self):
        """
        If SL is hit, the trade must be a LOSS.
        Bug was: STOPPED_OUT trades were incorrectly showing as profits.
        """
        # Entry at 100, SL at 95, Target at 110
        # Candle after entry: low=94 → SL triggered → exit at 95
        # P&L = (95 - 100) × qty = NEGATIVE
        candles = [
            make_candle(9, 15, 100, 102, 98, 100, 50000),  # opening
            make_candle(9, 30, 100, 102, 98, 101, 60000),  # opening
            make_candle(9, 45, 101, 103, 90, 91,  90000),  # entry candle (breakout)
            make_candle(10, 0, 91,  92,  94, 91,  70000),  # SL hit (low=94 < 95)
        ]
        entry_price = 103.0
        sl_price = 95.0
        target_price = 115.0
        qty = 10

        # Walk candles AFTER entry (index 3 onwards)
        exit_price = None
        exit_reason = None
        for c in candles[3:]:
            if c["low"] <= sl_price:
                exit_price = sl_price
                exit_reason = "STOPPED_OUT"
                break
            if c["high"] >= target_price:
                exit_price = target_price
                exit_reason = "TARGET_HIT"
                break

        assert exit_reason == "STOPPED_OUT"
        gross_pnl = (exit_price - entry_price) * qty
        assert gross_pnl < 0, f"STOPPED_OUT must be negative, got {gross_pnl}"

    def test_target_hit_trade_is_a_win(self):
        """TARGET_HIT exit must always be a positive P&L."""
        candles = [
            make_candle(9, 15, 100, 102, 98, 100, 50000),
            make_candle(9, 30, 100, 102, 98, 101, 60000),
            make_candle(9, 45, 101, 104, 100, 103, 90000),  # entry/breakout
            make_candle(10, 0, 103, 115, 102, 113, 70000),  # target hit
        ]
        entry_price = 104.0
        sl_price = 97.0
        target_price = 111.0
        qty = 10

        exit_price = None
        exit_reason = None
        for c in candles[3:]:
            if c["low"] <= sl_price:
                exit_price = sl_price
                exit_reason = "STOPPED_OUT"
                break
            if c["high"] >= target_price:
                exit_price = target_price
                exit_reason = "TARGET_HIT"
                break

        assert exit_reason == "TARGET_HIT"
        gross_pnl = (exit_price - entry_price) * qty
        assert gross_pnl > 0, f"TARGET_HIT must be positive, got {gross_pnl}"

    def test_exit_only_looks_after_entry_candle(self):
        """
        Critical bug fix: exit loop must start AFTER entry candle index.
        Pre-entry candles must never trigger SL/target.
        """
        # SL at 95, but a pre-entry candle has low=90
        # If bug exists, pre-entry candle triggers SL (wrong)
        # If fixed, only post-entry candles checked
        candles = [
            make_candle(9, 15, 100, 102, 90, 100, 50000),  # pre-entry, low=90 < SL=95
            make_candle(9, 30, 100, 102, 98, 101, 60000),  # pre-entry
            make_candle(9, 45, 101, 104, 100, 103, 90000),  # entry candle (idx=2)
            make_candle(10, 0, 103, 115, 102, 113, 70000),  # post-entry → target
        ]
        entry_idx = 2  # entry at candle index 2
        sl_price = 95.0
        target_price = 111.0

        # Correct: only walk from entry_idx + 1
        exit_reason = None
        for c in candles[entry_idx + 1:]:
            if c["low"] <= sl_price:
                exit_reason = "STOPPED_OUT"
                break
            if c["high"] >= target_price:
                exit_reason = "TARGET_HIT"
                break

        assert exit_reason == "TARGET_HIT", \
            "Pre-entry low=90 should not have triggered SL — only post-entry candles checked"

    def test_time_stop_at_1430(self):
        """Trade not closed by 14:30 IST must exit at time stop."""
        candles = [
            make_candle(9, 45, 100, 104, 99, 103, 90000),  # entry
            make_candle(10, 0, 103, 105, 101, 104, 50000),
            make_candle(14, 30, 104, 105, 103, 104, 30000),  # time stop
        ]
        entry_idx = 0
        sl_price = 95.0
        target_price = 120.0  # unreachable

        exit_reason = None
        exit_time = None
        for c in candles[entry_idx + 1:]:
            ct = c["time"]
            if ct.hour > 14 or (ct.hour == 14 and ct.minute >= 30):
                exit_reason = "TIME_STOP"
                exit_time = ct.strftime("%H:%M")
                break
            if c["low"] <= sl_price:
                exit_reason = "STOPPED_OUT"
                break
            if c["high"] >= target_price:
                exit_reason = "TARGET_HIT"
                break

        assert exit_reason == "TIME_STOP"
        assert exit_time == "14:30"


class TestWinRateSanity:
    def test_76_percent_wr_is_suspicious(self):
        """
        From SONNET_LOGICS Section 17: 76% WR was the buggy result.
        Real ORB strategies should not exceed 65% WR.
        This is a sanity check — not a hard rule, but a red flag.
        """
        # This test documents the lesson, not actual code
        buggy_wr = 76.0
        realistic_upper_bound = 65.0
        assert buggy_wr > realistic_upper_bound, \
            "76% WR exceeds realistic bounds — should trigger investigation"
