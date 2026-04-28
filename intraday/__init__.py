"""
Intraday Auto-Trader module for Wealth Builder Pro.

Provides automated intraday trading on NSE equity cash segment with:
- Pre-market scanning and AI-driven stock selection (Claude Sonnet 4.5)
- Broker-agnostic order execution (Dhan / Zerodha)
- Real-time position monitoring with trailing SL and partial profit booking
- Risk management with daily capital limits and VIX-based volatility checks
- End-of-day reporting and dashboard integration

All times are IST, all amounts are INR.
"""
