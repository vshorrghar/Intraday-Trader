"""
Tests for fno/pnl_calculator.py
Covers the known P&L bug: strategy id=16 shows Rs.92K on Rs.216 premium.
These tests document the bug and will pass once it is fixed.
"""
import pytest


class TestPnLBug:
    def test_pnl_cannot_exceed_10x_premium_collected(self):
        """
        Known bug: strategy id=16 shows Rs.92K profit on Rs.216 premium.
        Max profit on Iron Condor = premium collected.
        This test documents the constraint — pnl <= premium × 10 at most.
        """
        pass  # skeleton — implement after reading pnl_calculator.py

    def test_iron_condor_max_profit_equals_premium(self):
        """For Iron Condor: max profit = net premium collected."""
        pass  # skeleton

    def test_negative_pnl_cannot_exceed_max_loss(self):
        """P&L loss cannot exceed the theoretical max loss."""
        pass  # skeleton


class TestPnLCalculation:
    def test_pnl_is_exit_minus_entry_times_qty(self):
        """
        For a SELL leg: P&L = (entry_premium - exit_premium) × qty
        For a BUY leg:  P&L = (exit_premium - entry_premium) × qty
        """
        pass  # skeleton

    def test_charges_deducted_from_gross(self):
        """Net P&L = gross P&L - charges."""
        pass  # skeleton
