"""
Earnings calendar for swing module.
Hardcoded for Phase 1. Automated via NSE/MoneyControl API in Week 4.

# TODO Week 4: Add news sentiment signal
# TODO Week 4: Add FII/DII flow integration
# TODO Week 4: Automate earnings calendar from NSE corporate actions API
"""

from datetime import datetime, timedelta

# Manual earnings dates (update weekly on Sunday)
# Format: "YYYY-MM-DD": ["SYMBOL1", "SYMBOL2"]
EARNINGS_CALENDAR = {
    "2026-05-22": ["TCS"],
    "2026-05-23": ["HDFCBANK", "ICICIBANK"],
    "2026-05-26": ["INFY", "WIPRO"],
    "2026-05-27": ["RELIANCE"],
    "2026-05-28": ["SBIN", "AXISBANK"],
    "2026-05-29": ["ITC", "HINDUNILVR"],
    "2026-05-30": ["BAJFINANCE", "KOTAKBANK"],
    "2026-06-02": ["LT", "MARUTI"],
    "2026-06-03": ["SUNPHARMA", "CIPLA"],
    "2026-06-04": ["TATASTEEL", "JSWSTEEL"],
    "2026-06-05": ["BHARTIARTL", "TITAN"],
}


def get_earnings_within_days(symbol: str, days: int = 5) -> bool:
    """Return True if symbol has earnings within X trading days."""
    today = datetime.now().date()
    end_date = today + timedelta(days=days + 2)  # buffer for weekends

    for date_str, symbols in EARNINGS_CALENDAR.items():
        try:
            earn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= earn_date <= end_date and symbol in symbols:
            return True
    return False


def get_next_earnings_date(symbol: str) -> str | None:
    """Return next earnings date string for symbol, or None."""
    today = datetime.now().date()
    for date_str, symbols in sorted(EARNINGS_CALENDAR.items()):
        try:
            earn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if earn_date >= today and symbol in symbols:
            return date_str
    return None
