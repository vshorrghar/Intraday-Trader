"""
Dhan brokerage charges calculator for all segments.

Source: https://dhan.co/pricing-and-charges/
Reference: docs/DHAN_CHARGES.md
Last verified: 2026-05-12

If Dhan changes rates:
1. Update docs/DHAN_CHARGES.md first
2. Update constants in this file
3. Run self-test at bottom: python3 intraday/charges.py
"""

# ─────────────────────────────────────────────────────────────────
# CONSTANTS — update these when Dhan changes rates
# ─────────────────────────────────────────────────────────────────

# Common across segments
SEBI_TURNOVER_RATE = 0.0001 / 100           # 0.0001%
IPFT_RATE = 0.0000001 / 100                  # 0.0000001% (negligible)
GST_RATE = 0.18                              # 18%
NSE_DELIVERY_RATE = 0.0030699 / 100          # 0.0030699% delivery & intraday
NSE_FUTURES_RATE = 0.0018299 / 100           # 0.0018299% futures
NSE_OPTIONS_RATE = 0.0355299 / 100           # 0.0355299% on premium

# Brokerage caps
INTRADAY_BROKERAGE_CAP = 20.0                # ₹20 max per leg
INTRADAY_BROKERAGE_PCT = 0.03 / 100          # OR 0.03% whichever lower
FNO_BROKERAGE_FLAT = 20.0                    # ₹20 flat per leg

# STT rates
STT_DELIVERY = 0.10 / 100                    # 0.1% buy + sell
STT_INTRADAY = 0.025 / 100                   # 0.025% sell only
STT_FUTURES = 0.05 / 100                     # 0.05% sell only
STT_OPTIONS = 0.15 / 100                     # 0.15% sell on premium

# Stamp duty rates
STAMP_DELIVERY = 0.015 / 100                 # 0.015% buy
STAMP_INTRADAY = 0.003 / 100                 # 0.003% buy
STAMP_FUTURES = 0.002 / 100                  # 0.002% buy
STAMP_OPTIONS = 0.003 / 100                  # 0.003% buy


# ─────────────────────────────────────────────────────────────────
# CALCULATORS — one per segment
# ─────────────────────────────────────────────────────────────────

def calculate_intraday_charges(buy_price: float, sell_price: float, qty: int) -> float:
    """
    Equity intraday round-trip (MIS).
    Brokerage: min(₹20, 0.03%) per leg.
    """
    if qty <= 0 or buy_price <= 0 or sell_price <= 0:
        return 0.0

    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    brokerage_buy = min(INTRADAY_BROKERAGE_CAP, buy_turnover * INTRADAY_BROKERAGE_PCT)
    brokerage_sell = min(INTRADAY_BROKERAGE_CAP, sell_turnover * INTRADAY_BROKERAGE_PCT)
    brokerage = brokerage_buy + brokerage_sell

    stt = sell_turnover * STT_INTRADAY
    exchange = total_turnover * NSE_DELIVERY_RATE
    sebi = total_turnover * SEBI_TURNOVER_RATE
    ipft = total_turnover * IPFT_RATE
    stamp = buy_turnover * STAMP_INTRADAY

    gst = (brokerage + exchange + sebi + ipft) * GST_RATE

    return round(brokerage + stt + exchange + sebi + ipft + stamp + gst, 2)


def calculate_delivery_charges(buy_price: float, sell_price: float, qty: int) -> float:
    """
    Equity delivery (CNC) — for swing/positional.
    Brokerage: ₹0 (FREE).
    STT: 0.1% on BOTH buy and sell.
    """
    if qty <= 0 or buy_price <= 0 or sell_price <= 0:
        return 0.0

    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    brokerage = 0.0  # FREE for delivery

    stt = (buy_turnover + sell_turnover) * STT_DELIVERY
    exchange = total_turnover * NSE_DELIVERY_RATE
    sebi = total_turnover * SEBI_TURNOVER_RATE
    ipft = total_turnover * IPFT_RATE
    stamp = buy_turnover * STAMP_DELIVERY

    gst = (brokerage + exchange + sebi + ipft) * GST_RATE

    return round(brokerage + stt + exchange + sebi + ipft + stamp + gst, 2)


def calculate_futures_charges(buy_price: float, sell_price: float, qty: int) -> float:
    """
    Equity futures round-trip.
    Brokerage: ₹20 flat per leg.
    STT: 0.05% on sell only.
    """
    if qty <= 0 or buy_price <= 0 or sell_price <= 0:
        return 0.0

    buy_turnover = buy_price * qty
    sell_turnover = sell_price * qty
    total_turnover = buy_turnover + sell_turnover

    brokerage = FNO_BROKERAGE_FLAT * 2

    stt = sell_turnover * STT_FUTURES
    exchange = total_turnover * NSE_FUTURES_RATE
    sebi = total_turnover * SEBI_TURNOVER_RATE
    ipft = total_turnover * IPFT_RATE
    stamp = buy_turnover * STAMP_FUTURES

    gst = (brokerage + exchange + sebi + ipft) * GST_RATE

    return round(brokerage + stt + exchange + sebi + ipft + stamp + gst, 2)


def calculate_options_charges(buy_premium: float, sell_premium: float, qty: int) -> float:
    """
    Equity options round-trip.
    Brokerage: ₹20 flat per leg.
    STT: 0.15% on sell PREMIUM only.
    Exchange: 0.0355299% on PREMIUM (much higher than futures).
    """
    if qty <= 0 or buy_premium <= 0 or sell_premium <= 0:
        return 0.0

    buy_turnover = buy_premium * qty
    sell_turnover = sell_premium * qty
    total_turnover = buy_turnover + sell_turnover

    brokerage = FNO_BROKERAGE_FLAT * 2

    stt = sell_turnover * STT_OPTIONS
    exchange = total_turnover * NSE_OPTIONS_RATE
    sebi = total_turnover * SEBI_TURNOVER_RATE
    ipft = total_turnover * IPFT_RATE
    stamp = buy_turnover * STAMP_OPTIONS

    gst = (brokerage + exchange + sebi + ipft) * GST_RATE

    return round(brokerage + stt + exchange + sebi + ipft + stamp + gst, 2)


# ─────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Dhan Charges Self-Test ===\n")

    c = calculate_intraday_charges(297.35, 296.05, 13)
    print(f"Intraday ONGC (buy=297.35, sell=296.05, qty=13)")
    print(f"  Charges:    ₹{c:.2f}")
    print(f"  Expected:   ~₹4-5 (matches Dhan formula)")

    c = calculate_delivery_charges(2500, 2600, 10)
    print(f"\nDelivery RELIANCE (buy=2500, sell=2600, qty=10)")
    print(f"  Charges:    ₹{c:.2f}")

    c = calculate_futures_charges(24000, 24100, 50)
    print(f"\nFutures NIFTY 1 lot (buy=24000, sell=24100, qty=50)")
    print(f"  Charges:    ₹{c:.2f}")

    c = calculate_options_charges(150, 200, 50)
    print(f"\nOptions NIFTY 1 lot (buy=150, sell=200 premium, qty=50)")
    print(f"  Charges:    ₹{c:.2f}")
