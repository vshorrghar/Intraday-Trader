"""
Integration test: full swing flow
scanner → rules_selector → risk_manager → (mock) executor
"""
import pytest


class TestSwingFlowSmoke:
    def test_scanner_to_selector_pipeline(self):
        """
        scanner.scan_universe() output format is compatible
        with rules_selector.select_swing_trades() input.
        """
        pass  # skeleton

    def test_selector_output_compatible_with_executor(self):
        """
        rules_selector output (SwingTradeSetup) must have all fields
        required by SwingExecutor.execute_trades().
        """
        pass  # skeleton
