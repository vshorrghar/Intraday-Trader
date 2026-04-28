"""F&O trading symbol construction and parsing for Dhan and Zerodha.

Constructs broker-specific trading symbols for index options and futures,
and parses them back to their constituent parts.

Symbol formats:
  - Dhan options:   ``{INDEX}{YY}{MMM}{STRIKE}{CE/PE}``   e.g. ``NIFTY25JUL24500CE``
  - Zerodha options: ``{INDEX}{YY}{M}{DD}{STRIKE}{CE/PE}`` e.g. ``NIFTY2572524500CE``
  - Dhan futures:   ``{INDEX}{YY}{MMM}FUT``                e.g. ``NIFTY25JULFUT``
  - Zerodha futures: ``{INDEX}{YY}{M}{DD}FUT``             e.g. ``NIFTY25725FUT``
"""

from __future__ import annotations

import re
from datetime import date


# Valid indices for NSE F&O
VALID_INDICES = {"NIFTY", "BANKNIFTY", "FINNIFTY"}

# Valid option types
VALID_OPTION_TYPES = {"CE", "PE"}


class Symbol_Builder:
    """Constructs and parses broker-specific F&O trading symbols."""

    MONTH_CODES_ZERODHA: dict[int, str] = {
        1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
        7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
    }

    MONTH_NAMES_DHAN: dict[int, str] = {
        1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
    }

    # Reverse mappings for parsing
    _DHAN_MONTH_TO_NUM: dict[str, int] = {v: k for k, v in MONTH_NAMES_DHAN.items()}
    _ZERODHA_CODE_TO_NUM: dict[str, int] = {v: k for k, v in MONTH_CODES_ZERODHA.items()}

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_index(index: str) -> str:
        """Validate and normalize index name."""
        idx = index.upper()
        if idx not in VALID_INDICES:
            raise ValueError(
                f"Invalid index '{index}'. Valid indices: {sorted(VALID_INDICES)}"
            )
        return idx

    @staticmethod
    def _validate_option_type(option_type: str) -> str:
        """Validate and normalize option type."""
        ot = option_type.upper()
        if ot not in VALID_OPTION_TYPES:
            raise ValueError(
                f"Invalid option_type '{option_type}'. Valid types: {sorted(VALID_OPTION_TYPES)}"
            )
        return ot

    @staticmethod
    def _validate_strike(strike: float) -> float:
        """Validate strike price."""
        if strike <= 0:
            raise ValueError(
                f"Invalid strike price {strike}. Strike must be positive."
            )
        return strike

    @staticmethod
    def _format_strike(strike: float) -> str:
        """Format strike price: integer if whole, else with decimals."""
        if strike == int(strike):
            return str(int(strike))
        return f"{strike:.2f}".rstrip("0").rstrip(".")

    # ------------------------------------------------------------------
    # Option symbol builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_dhan(
        index: str, expiry: date, strike: float, option_type: str,
    ) -> str:
        """Build a Dhan-format option symbol.

        Format: ``{INDEX}{YY}{MMM}{STRIKE}{CE/PE}``

        Example: ``NIFTY25JUL24500CE``
        """
        idx = Symbol_Builder._validate_index(index)
        ot = Symbol_Builder._validate_option_type(option_type)
        Symbol_Builder._validate_strike(strike)

        yy = f"{expiry.year % 100:02d}"
        mmm = Symbol_Builder.MONTH_NAMES_DHAN[expiry.month]
        strike_str = Symbol_Builder._format_strike(strike)

        return f"{idx}{yy}{mmm}{strike_str}{ot}"

    @staticmethod
    def build_zerodha(
        index: str, expiry: date, strike: float, option_type: str,
    ) -> str:
        """Build a Zerodha-format option symbol.

        Format: ``{INDEX}{YY}{M}{DD}{STRIKE}{CE/PE}``

        Example: ``NIFTY2572524500CE``
        """
        idx = Symbol_Builder._validate_index(index)
        ot = Symbol_Builder._validate_option_type(option_type)
        Symbol_Builder._validate_strike(strike)

        yy = f"{expiry.year % 100:02d}"
        m = Symbol_Builder.MONTH_CODES_ZERODHA[expiry.month]
        dd = f"{expiry.day:02d}"
        strike_str = Symbol_Builder._format_strike(strike)

        return f"{idx}{yy}{m}{dd}{strike_str}{ot}"

    # ------------------------------------------------------------------
    # Futures symbol builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_futures_dhan(index: str, expiry: date) -> str:
        """Build a Dhan-format futures symbol.

        Format: ``{INDEX}{YY}{MMM}FUT``

        Example: ``NIFTY25JULFUT``
        """
        idx = Symbol_Builder._validate_index(index)
        yy = f"{expiry.year % 100:02d}"
        mmm = Symbol_Builder.MONTH_NAMES_DHAN[expiry.month]
        return f"{idx}{yy}{mmm}FUT"

    @staticmethod
    def build_futures_zerodha(index: str, expiry: date) -> str:
        """Build a Zerodha-format futures symbol.

        Format: ``{INDEX}{YY}{M}{DD}FUT``

        Example: ``NIFTY25725FUT``
        """
        idx = Symbol_Builder._validate_index(index)
        yy = f"{expiry.year % 100:02d}"
        m = Symbol_Builder.MONTH_CODES_ZERODHA[expiry.month]
        dd = f"{expiry.day:02d}"
        return f"{idx}{yy}{m}{dd}FUT"

    # ------------------------------------------------------------------
    # Symbol parser
    # ------------------------------------------------------------------

    @staticmethod
    def parse_symbol(symbol: str, broker: str) -> dict:
        """Parse a trading symbol back to its components.

        Parameters
        ----------
        symbol : str
            The broker-specific trading symbol.
        broker : str
            ``"dhan"`` or ``"zerodha"``.

        Returns
        -------
        dict
            ``{"index": str, "expiry": date, "strike": float,
            "option_type": str}``
            For futures, ``strike`` is 0 and ``option_type`` is ``"FUT"``.

        Raises
        ------
        ValueError
            If the symbol cannot be parsed.
        """
        broker = broker.strip().lower()

        if broker == "dhan":
            return Symbol_Builder._parse_dhan(symbol)
        if broker == "zerodha":
            return Symbol_Builder._parse_zerodha(symbol)

        raise ValueError(f"Unsupported broker '{broker}'. Use 'dhan' or 'zerodha'.")

    @staticmethod
    def _parse_dhan(symbol: str) -> dict:
        """Parse a Dhan-format symbol."""
        # Try futures first: {INDEX}{YY}{MMM}FUT
        for idx in sorted(VALID_INDICES, key=len, reverse=True):
            if symbol.startswith(idx):
                rest = symbol[len(idx):]
                # Futures: YY + MMM + FUT
                fut_match = re.match(r"^(\d{2})([A-Z]{3})FUT$", rest)
                if fut_match:
                    yy = int(fut_match.group(1))
                    mmm = fut_match.group(2)
                    month = Symbol_Builder._DHAN_MONTH_TO_NUM.get(mmm)
                    if month is None:
                        raise ValueError(f"Invalid month code '{mmm}' in symbol '{symbol}'")
                    year = 2000 + yy
                    # For Dhan futures, we don't have the day — use last day of month
                    # as a convention (the actual expiry day is determined by exchange)
                    import calendar
                    last_day = calendar.monthrange(year, month)[1]
                    return {
                        "index": idx,
                        "expiry": date(year, month, last_day),
                        "strike": 0.0,
                        "option_type": "FUT",
                    }

                # Options: YY + MMM + STRIKE + CE/PE
                opt_match = re.match(
                    r"^(\d{2})([A-Z]{3})([\d.]+)(CE|PE)$", rest
                )
                if opt_match:
                    yy = int(opt_match.group(1))
                    mmm = opt_match.group(2)
                    strike = float(opt_match.group(3))
                    option_type = opt_match.group(4)
                    month = Symbol_Builder._DHAN_MONTH_TO_NUM.get(mmm)
                    if month is None:
                        raise ValueError(f"Invalid month code '{mmm}' in symbol '{symbol}'")
                    year = 2000 + yy
                    import calendar
                    last_day = calendar.monthrange(year, month)[1]
                    return {
                        "index": idx,
                        "expiry": date(year, month, last_day),
                        "strike": strike,
                        "option_type": option_type,
                    }

        raise ValueError(f"Cannot parse Dhan symbol: '{symbol}'")

    @staticmethod
    def _parse_zerodha(symbol: str) -> dict:
        """Parse a Zerodha-format symbol."""
        for idx in sorted(VALID_INDICES, key=len, reverse=True):
            if symbol.startswith(idx):
                rest = symbol[len(idx):]
                # Futures: YY + M + DD + FUT
                fut_match = re.match(r"^(\d{2})([0-9OND])(\d{2})FUT$", rest)
                if fut_match:
                    yy = int(fut_match.group(1))
                    m_code = fut_match.group(2)
                    dd = int(fut_match.group(3))
                    month = Symbol_Builder._ZERODHA_CODE_TO_NUM.get(m_code)
                    if month is None:
                        raise ValueError(f"Invalid month code '{m_code}' in symbol '{symbol}'")
                    year = 2000 + yy
                    return {
                        "index": idx,
                        "expiry": date(year, month, dd),
                        "strike": 0.0,
                        "option_type": "FUT",
                    }

                # Options: YY + M + DD + STRIKE + CE/PE
                opt_match = re.match(
                    r"^(\d{2})([0-9OND])(\d{2})([\d.]+)(CE|PE)$", rest
                )
                if opt_match:
                    yy = int(opt_match.group(1))
                    m_code = opt_match.group(2)
                    dd = int(opt_match.group(3))
                    strike = float(opt_match.group(4))
                    option_type = opt_match.group(5)
                    month = Symbol_Builder._ZERODHA_CODE_TO_NUM.get(m_code)
                    if month is None:
                        raise ValueError(f"Invalid month code '{m_code}' in symbol '{symbol}'")
                    year = 2000 + yy
                    return {
                        "index": idx,
                        "expiry": date(year, month, dd),
                        "strike": strike,
                        "option_type": option_type,
                    }

        raise ValueError(f"Cannot parse Zerodha symbol: '{symbol}'")
