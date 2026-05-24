"""
Integration test: full intraday flow
scanner → rule_engine → risk_manager → (mock) executor
No broker calls. Uses synthetic data.
"""
import pytest


class TestIntradayFlowSmoke:
    def test_rule_engine_output_compatible_with_risk_manager(self):
        """
        rule_engine.generate_orb_signals() output format must be
        compatible with what risk_manager expects.
        This is a format contract test.
        """
        pass  # skeleton — fill after both modules verified

    def test_signal_fields_present(self):
        """
        Each signal from rule_engine must have:
        symbol, direction, entry_price, target_price, stop_loss_price,
        qty, strategy_type, score.
        """
        pass  # skeleton
