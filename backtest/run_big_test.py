"""
BIG TEST — Intraday + F&O simulation
Tests expanded universe with real capital sizes.

TEST A: Intraday ₹2L capital, F&O universe, V6 long only
TEST B: F&O simulation ₹2L capital, same signals, options proxy

Run in background:
    cd ~/dev-sandbox
    nohup .venv/bin/python3 -m backtest.run_big_test \
        > backtest/results/big_test.log 2>&1 &
"""

import json
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.universes import get_universe, get_universe_filtered, BLACKLIST
from backtest.rule_engine import (
    get_candles_for_date, get_prev_close, generate_orb_signals,
    get_market_direction,
)
from backtest.data_loader import fetch_and_cache_historical
from intraday.charges import calculate_intraday_charges

IST = timezone(timedelta(hours=5, minutes=30))

# ============================================================
# CONFIGURATION
# ============================================================

INTRADAY_CAPITAL = 200000
INTRADAY_PER_TRADE = 50000
INTRADAY_MAX_TRADES = 4  # 4 positions × ₹50K = ₹2L deployed

FNO_CAPITAL = 200000
FNO_PER_LOT = 15000       # avg ATM option cost
FNO_MAX_LOTS = 4          # 4 lots × ₹15K = ₹60K max exposure
FNO_LEVERAGE_MULTIPLE = 5 # options move ~5x the stock on good days
FNO_WIN_RATE_DISCOUNT = 0.85  # options expire worthless more often

DATE_CHUNKS = [
    ("2025-12-01", "2026-03-01"),
    ("2026-03-01", "2026-05-23"),
]

# ============================================================
# DATA FETCHING
# ============================================================

def fetch_universe_data(broker, universe_name: str) -> dict:
    """Fetch 6 months data for universe. Cache aggressively."""
    universe = get_universe(universe_name)
    all_data = {}

    print(f"\nFetching {len(universe)} stocks ({universe_name})...")

    for from_date, to_date in DATE_CHUNKS:
        print(f"  {from_date} → {to_date}")
        chunk = fetch_and_cache_historical(
            symbols=universe,
            from_date=from_date,
            to_date=to_date,
            interval="15",
            cache_dir="cache/historical_6m",
            broker=broker,
        )
        for symbol, ohlc in chunk.items():
            if symbol not in all_data:
                all_data[symbol] = {
                    k: list(v) for k, v in ohlc.items()
                }
            else:
                for key in ["open","high","low","close","volume","timestamp"]:
                    all_data[symbol][key].extend(ohlc.get(key, []))

    print(f"  Got data for {len(all_data)} stocks")
    return all_data


def get_trading_days(historical_data: dict) -> list:
    """Get all unique trading days from data."""
    from datetime import datetime
    days = set()
    sample = next(iter(historical_data))
    for ts in historical_data[sample].get("timestamp", []):
        dt = datetime.fromtimestamp(ts, tz=IST)
        days.add(dt.strftime("%Y-%m-%d"))
    return sorted(days)


# ============================================================
# TEST A: INTRADAY SIMULATION
# ============================================================

def simulate_intraday_day(
    target_date: str,
    historical_data: dict,
    universe: dict,
    nifty_data: dict,
) -> dict:
    """Simulate one day of intraday trading with ₹2L capital."""

    config = {
        "per_trade_max_capital": INTRADAY_PER_TRADE,
        "max_trades_per_day": INTRADAY_MAX_TRADES,
        "daily_loss_limit": INTRADAY_CAPITAL * 0.02,  # 2% daily loss limit
    }

    signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant="V6",
        nifty_data=nifty_data,
    )
    # LONG ONLY: filter out short signals
    signals = [s for s in signals
               if s.get("direction", "LONG") == "LONG"
               and s.get("gap_pct", 0) > 0]

    if not signals:
        return {
            "date": target_date, "trades": [],
            "gross": 0, "charges": 0, "net": 0,
            "winners": 0, "losers": 0, "skipped": True,
        }

    trades = []
    cum_loss = 0.0

    for signal in signals[:INTRADAY_MAX_TRADES]:
        if cum_loss >= INTRADAY_CAPITAL * 0.02:
            break

        symbol = signal["symbol"]
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if not candles:
            continue

        entry = signal["entry_price"]
        target_p = signal["target_price"]
        sl = signal["stop_loss_price"]
        qty = max(1, int(INTRADAY_PER_TRADE / entry))

        exit_price = None
        exit_reason = None
        exit_time = None

        # Find entry candle index first
        entry_idx = None
        breakout_t = signal.get("breakout_time", "09:35")
        for idx, c in enumerate(candles):
            if c["time"].strftime("%H:%M") >= breakout_t:
                entry_idx = idx
                break

        if entry_idx is None:
            entry_idx = 0

        # Walk candles AFTER entry only
        for c in candles[entry_idx + 1:]:
            ct = c["time"]

            # Time stop at 14:30
            if ct.hour > 14 or (ct.hour == 14 and ct.minute >= 30):
                exit_price = c["close"]
                exit_reason = "TIME_STOP"
                exit_time = ct.strftime("%H:%M")
                break

            # Stop loss: price drops to SL (LONG trade)
            if c["low"] <= sl:
                exit_price = sl
                exit_reason = "STOPPED_OUT"
                exit_time = ct.strftime("%H:%M")
                break

            # Target hit: price rises to target (LONG trade)
            if c["high"] >= target_p:
                exit_price = target_p
                exit_reason = "TARGET_HIT"
                exit_time = ct.strftime("%H:%M")
                break

        if exit_price is None:
            exit_price = candles[-1]["close"]
            exit_reason = "EOD"
            exit_time = "15:30"

        direction = signal.get("direction", "LONG")
        if direction == "LONG":
            gross = (exit_price - entry) * qty
            charges = calculate_intraday_charges(entry, exit_price, qty)
        else:
            gross = (entry - exit_price) * qty
            charges = calculate_intraday_charges(exit_price, entry, qty)
        net = round(gross - charges, 2)

        if net < 0:
            cum_loss += abs(net)

        trades.append({
            "symbol": symbol,
            "entry": entry,
            "exit": round(exit_price, 2),
            "qty": qty,
            "gross": round(gross, 2),
            "charges": round(charges, 2),
            "net": net,
            "exit_reason": exit_reason,
            "gap_pct": signal.get("gap_pct", 0),
            "score": signal.get("score", 0),
        })

    total_gross = sum(t["gross"] for t in trades)
    total_charges = sum(t["charges"] for t in trades)
    total_net = sum(t["net"] for t in trades)
    winners = sum(1 for t in trades if t["net"] > 0)
    losers = sum(1 for t in trades if t["net"] <= 0)

    return {
        "date": target_date,
        "trades": trades,
        "gross": round(total_gross, 2),
        "charges": round(total_charges, 2),
        "net": round(total_net, 2),
        "winners": winners,
        "losers": losers,
        "skipped": False,
    }


# ============================================================
# TEST B: F&O SIMULATION (proxy model)
# ============================================================

def simulate_fno_day(
    target_date: str,
    historical_data: dict,
    universe: dict,
    nifty_data: dict,
    intraday_signals: list,
) -> dict:
    """
    Simulate F&O options trading using same V6 signals.

    Model:
    - When V6 triggers on stock X, buy 1 ATM call option lot
    - Option cost: ₹15,000 per lot (approximate ATM premium)
    - If stock reaches target: option gains 4-6x the stock move
    - If stock hits SL: option loses 60-80% of premium paid
    - If time stop: option loses 20-40% (theta decay)

    This is a PROXY model, not real options pricing.
    Real options behave differently due to IV, Greeks etc.
    """

    if not intraday_signals:
        return {
            "date": target_date, "trades": [],
            "premium_deployed": 0, "net": 0,
            "winners": 0, "losers": 0, "skipped": True,
        }

    trades = []
    premium_deployed = 0

    for signal in intraday_signals[:FNO_MAX_LOTS]:
        if premium_deployed >= FNO_CAPITAL * 0.3:  # max 30% in options
            break

        symbol = signal["symbol"]
        ohlc = historical_data.get(symbol)
        if not ohlc:
            continue

        candles = get_candles_for_date(ohlc, target_date)
        if not candles:
            continue

        entry = signal["entry_price"]
        target_p = signal["target_price"]
        sl = signal["stop_loss_price"]

        # Simulate option outcome based on stock price path
        exit_reason = None
        stock_outcome = None

        for c in candles:
            if c["time"].hour >= 14 and c["time"].minute >= 30:
                exit_reason = "TIME_STOP"
                stock_pnl_pct = (c["close"] - entry) / entry
                stock_outcome = "TIME"
                break
            if c["low"] <= sl and c["time"].strftime("%H:%M") > "09:35":
                exit_reason = "STOPPED_OUT"
                stock_pnl_pct = (sl - entry) / entry
                stock_outcome = "LOSS"
                break
            if c["high"] >= target_p and c["time"].strftime("%H:%M") > "09:35":
                exit_reason = "TARGET_HIT"
                stock_pnl_pct = (target_p - entry) / entry
                stock_outcome = "WIN"
                break

        if exit_reason is None:
            exit_reason = "EOD"
            stock_pnl_pct = (candles[-1]["close"] - entry) / entry
            stock_outcome = "TIME"

        # Options P&L model
        lot_cost = FNO_PER_LOT
        premium_deployed += lot_cost

        if stock_outcome == "WIN":
            # Target hit: option gains 4-5x stock percentage move
            option_gain_pct = stock_pnl_pct * FNO_LEVERAGE_MULTIPLE * FNO_WIN_RATE_DISCOUNT
            option_pnl = lot_cost * option_gain_pct
        elif stock_outcome == "LOSS":
            # SL hit: option loses 60-75% of premium
            option_pnl = -lot_cost * 0.65
        else:
            # Time stop: option loses 25-35% from theta
            if stock_pnl_pct > 0:
                option_pnl = lot_cost * stock_pnl_pct * 2
            else:
                option_pnl = -lot_cost * 0.30

        # F&O charges (STT + exchange + brokerage)
        fno_charges = lot_cost * 0.003  # approx 0.3% of premium

        net_pnl = round(option_pnl - fno_charges, 2)

        trades.append({
            "symbol": symbol,
            "lot_cost": lot_cost,
            "stock_outcome": stock_outcome,
            "stock_pnl_pct": round(stock_pnl_pct * 100, 2),
            "option_pnl": round(option_pnl, 2),
            "charges": round(fno_charges, 2),
            "net": net_pnl,
            "exit_reason": exit_reason,
        })

    total_net = sum(t["net"] for t in trades)
    winners = sum(1 for t in trades if t["net"] > 0)
    losers = sum(1 for t in trades if t["net"] <= 0)

    return {
        "date": target_date,
        "trades": trades,
        "premium_deployed": round(premium_deployed, 2),
        "net": round(total_net, 2),
        "winners": winners,
        "losers": losers,
        "skipped": False,
    }


# ============================================================
# REPORT
# ============================================================

def generate_report(intraday_days: list, fno_days: list, output_path: str):
    """Generate combined intraday + F&O report."""

    lines = []
    lines.append("=" * 70)
    lines.append("BIG TEST REPORT — Intraday + F&O Simulation")
    lines.append(f"Capital: Intraday ₹{INTRADAY_CAPITAL:,} | F&O ₹{FNO_CAPITAL:,}")
    lines.append(f"Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    lines.append("=" * 70)

    # ── INTRADAY SECTION ──
    intraday_trades = [t for d in intraday_days for t in d.get("trades", [])]
    total_days = len(intraday_days)
    active_days = sum(1 for d in intraday_days if not d.get("skipped"))
    skipped_days = total_days - active_days
    total_net = sum(d["net"] for d in intraday_days)
    total_gross = sum(d["gross"] for d in intraday_days)
    total_charges = sum(d["charges"] for d in intraday_days)
    total_winners = sum(d["winners"] for d in intraday_days)
    total_losers = sum(d["losers"] for d in intraday_days)
    total_trades = total_winners + total_losers
    wr = total_winners / total_trades * 100 if total_trades > 0 else 0
    pf = abs(total_gross / total_charges) if total_charges > 0 else 0

    lines.append("\n" + "─" * 70)
    lines.append("TEST A — INTRADAY (V6 Strategy, F&O Universe)")
    lines.append("─" * 70)
    lines.append(f"  Capital:        ₹{INTRADAY_CAPITAL:,}")
    lines.append(f"  Per trade:      ₹{INTRADAY_PER_TRADE:,}")
    lines.append(f"  Max positions:  {INTRADAY_MAX_TRADES} simultaneous")
    lines.append(f"  Period:         Dec 2025 — May 2026 (~6 months)")
    lines.append(f"  Total days:     {total_days}")
    lines.append(f"  Active days:    {active_days} (signal fired)")
    lines.append(f"  Skipped days:   {skipped_days} (no catalyst gap)")
    lines.append(f"  Total trades:   {total_trades}")
    lines.append(f"  Win rate:       {wr:.1f}%  ({total_winners}W / {total_losers}L)")
    lines.append(f"  Profit factor:  {pf:.2f}")
    lines.append(f"  Total gross:    ₹{total_gross:,.2f}")
    lines.append(f"  Total charges:  ₹{total_charges:,.2f}")
    lines.append(f"  Total net 6m:   ₹{total_net:,.2f}")
    lines.append(f"  Monthly avg:    ₹{total_net/6:,.2f}")
    lines.append(f"  Per trade avg:  ₹{total_net/max(total_trades,1):,.2f}")
    lines.append(f"  Annual proj:    ₹{total_net*2:,.2f}")

    # Monthly breakdown
    monthly = {}
    for d in intraday_days:
        month = d["date"][:7]
        if month not in monthly:
            monthly[month] = {"net": 0, "trades": 0}
        monthly[month]["net"] += d["net"]
        monthly[month]["trades"] += len(d.get("trades", []))

    lines.append(f"\n  Monthly breakdown:")
    for month, stats in sorted(monthly.items()):
        lines.append(f"    {month}: ₹{stats['net']:>+8,.0f}  ({stats['trades']} trades)")

    # Top and bottom stocks
    by_stock = {}
    for t in intraday_trades:
        s = t["symbol"]
        if s not in by_stock:
            by_stock[s] = {"trades": 0, "net": 0, "wins": 0}
        by_stock[s]["trades"] += 1
        by_stock[s]["net"] += t["net"]
        if t["net"] > 0:
            by_stock[s]["wins"] += 1

    lines.append(f"\n  Top 10 stocks:")
    for s, st in sorted(by_stock.items(), key=lambda x: -x[1]["net"])[:10]:
        wr_s = st["wins"] / st["trades"] * 100 if st["trades"] > 0 else 0
        lines.append(f"    {s:15}: {st['trades']:3} trades, {wr_s:.0f}% WR, ₹{st['net']:>+8,.0f}")

    lines.append(f"\n  Bottom 5 stocks (consider blacklisting):")
    for s, st in sorted(by_stock.items(), key=lambda x: x[1]["net"])[:5]:
        wr_s = st["wins"] / st["trades"] * 100 if st["trades"] > 0 else 0
        lines.append(f"    {s:15}: {st['trades']:3} trades, {wr_s:.0f}% WR, ₹{st['net']:>+8,.0f}")

    # ── F&O SECTION ──
    fno_trades = [t for d in fno_days for t in d.get("trades", [])]
    fno_total_net = sum(d["net"] for d in fno_days)
    fno_active = sum(1 for d in fno_days if not d.get("skipped"))
    fno_total_trades = len(fno_trades)
    fno_winners = sum(1 for t in fno_trades if t["net"] > 0)
    fno_losers = sum(1 for t in fno_trades if t["net"] <= 0)
    fno_wr = fno_winners / fno_total_trades * 100 if fno_total_trades > 0 else 0
    total_premium = sum(d["premium_deployed"] for d in fno_days)

    lines.append("\n" + "─" * 70)
    lines.append("TEST B — F&O SIMULATION (Options proxy model)")
    lines.append("─" * 70)
    lines.append(f"  Capital:        ₹{FNO_CAPITAL:,}")
    lines.append(f"  Per lot cost:   ₹{FNO_PER_LOT:,} (ATM option estimate)")
    lines.append(f"  Leverage model: {FNO_LEVERAGE_MULTIPLE}x stock move")
    lines.append(f"  ⚠️  NOTE: This is a PROXY model, not real options pricing")
    lines.append(f"  ⚠️  Real options affected by IV, Greeks, theta decay")
    lines.append(f"  ⚠️  Use this for direction only, not exact numbers")
    lines.append(f"")
    lines.append(f"  Active days:    {fno_active}")
    lines.append(f"  Total trades:   {fno_total_trades} lots")
    lines.append(f"  Win rate:       {fno_wr:.1f}%  ({fno_winners}W / {fno_losers}L)")
    lines.append(f"  Premium used:   ₹{total_premium:,.2f}")
    lines.append(f"  Total net 6m:   ₹{fno_total_net:,.2f}")
    lines.append(f"  Monthly avg:    ₹{fno_total_net/6:,.2f}")
    lines.append(f"  Annual proj:    ₹{fno_total_net*2:,.2f}")

    # Monthly F&O breakdown
    fno_monthly = {}
    for d in fno_days:
        month = d["date"][:7]
        if month not in fno_monthly:
            fno_monthly[month] = {"net": 0, "trades": 0}
        fno_monthly[month]["net"] += d["net"]
        fno_monthly[month]["trades"] += len(d.get("trades", []))

    lines.append(f"\n  Monthly breakdown:")
    for month, stats in sorted(fno_monthly.items()):
        lines.append(f"    {month}: ₹{stats['net']:>+8,.0f}  ({stats['trades']} lots)")

    # ── COMBINED SECTION ──
    combined_net = total_net + fno_total_net
    combined_monthly = combined_net / 6
    total_capital = INTRADAY_CAPITAL + FNO_CAPITAL

    lines.append("\n" + "=" * 70)
    lines.append("COMBINED RESULTS — Both streams together")
    lines.append("=" * 70)
    lines.append(f"  Total capital deployed: ₹{total_capital:,}")
    lines.append(f"  Intraday net 6m:        ₹{total_net:>+10,.2f}")
    lines.append(f"  F&O net 6m:             ₹{fno_total_net:>+10,.2f}")
    lines.append(f"  Combined net 6m:        ₹{combined_net:>+10,.2f}")
    lines.append(f"  Combined monthly avg:   ₹{combined_monthly:>+10,.2f}")
    lines.append(f"  Combined annual proj:   ₹{combined_net*2:>+10,.2f}")
    lines.append(f"  Return on ₹4L capital:  {combined_net/total_capital*100:.1f}% in 6 months")
    lines.append(f"")

    if combined_monthly >= 100000:
        lines.append(f"  🎯 TARGET ACHIEVED: ₹1 lakh/month milestone reached!")
    elif combined_monthly >= 50000:
        lines.append(f"  📈 PROGRESS: ₹{combined_monthly:,.0f}/month — halfway to ₹1L target")
        lines.append(f"  Next step: Scale capital or add swing trading stream")
    elif combined_monthly >= 20000:
        lines.append(f"  🔄 BUILDING: ₹{combined_monthly:,.0f}/month — foundation established")
        lines.append(f"  Recommendation: Validate in paper, then scale capital")
    else:
        lines.append(f"  ⚠️  BELOW TARGET: ₹{combined_monthly:,.0f}/month")
        lines.append(f"  Need: More signals, larger capital, or add swing stream")

    lines.append("\n" + "=" * 70)
    lines.append("WHAT TO DO NEXT")
    lines.append("=" * 70)
    lines.append(f"  1. Paper trade intraday V6 for 2 weeks (validate backtest)")
    lines.append(f"  2. Paper trade F&O alongside (learn real options behavior)")
    lines.append(f"  3. After 30 paper trades: deploy intraday live at ₹2L")
    lines.append(f"  4. After 30 more: deploy F&O live at ₹1L (reduced)")
    lines.append(f"  5. Add swing trading as 3rd stream (₹2L more)")
    lines.append(f"  6. Combined target: ₹1L/month within 6-9 months")
    lines.append("=" * 70)

    report_text = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(report_text)
    print(report_text)
    return report_text


# ============================================================
# MAIN
# ============================================================

def run():
    start = time.time()
    print("=" * 70)
    print("BIG TEST — Intraday + F&O Simulation")
    print(f"Intraday capital: ₹{INTRADAY_CAPITAL:,} | F&O capital: ₹{FNO_CAPITAL:,}")
    print("=" * 70)

    # Load broker
    with open("config/profiles/vishal.yaml") as f:
        config = yaml.safe_load(f)
    from intraday.auth_server import authenticate_broker
    broker = authenticate_broker(
        broker_name="dhan",
        broker_config=config.get("dhan", {}),
        dry_run=False,
    )
    print("Broker ready")

    # Fetch Nifty index
    print("\nFetching Nifty index data...")
    nifty_data = None
    for from_d, to_d in DATE_CHUNKS:
        chunk = broker.get_historical_ohlc(
            security_id="13",
            exchange_segment="IDX_I",
            instrument="INDEX",
            interval="15",
            from_date=from_d,
            to_date=to_d,
        )
        if chunk and chunk.get("open"):
            if nifty_data is None:
                nifty_data = chunk
            else:
                for key in ["open","high","low","close","volume","timestamp"]:
                    nifty_data[key].extend(chunk.get(key, []))
    print(f"Nifty: {len(nifty_data.get('open',[]))} candles")

    # Fetch F&O universe data
    historical_data = fetch_universe_data(broker, "fno")
    universe = get_universe_filtered("fno")
    trading_days = get_trading_days(historical_data)
    print(f"\nTrading days found: {len(trading_days)}")

    # Run both tests simultaneously
    print("\nRunning Test A (Intraday) + Test B (F&O) simultaneously...")
    intraday_days = []
    fno_days = []

    for i, day in enumerate(trading_days):
        # Generate signals once, use for both tests
        config_day = {
            "per_trade_max_capital": INTRADAY_PER_TRADE,
            "max_trades_per_day": INTRADAY_MAX_TRADES,
            "daily_loss_limit": INTRADAY_CAPITAL * 0.02,
        }

        signals = generate_orb_signals(
            target_date=day,
            historical_data=historical_data,
            universe=universe,
            config=config_day,
            strategy_variant="V6",
            nifty_data=nifty_data,
        )
        # LONG ONLY: filter out short signals
        signals = [s for s in signals
                   if s.get("direction", "LONG") == "LONG"
                   and s.get("gap_pct", 0) > 0]

        # Test A: Intraday
        intraday_result = simulate_intraday_day(
            day, historical_data, universe, nifty_data
        )
        intraday_days.append(intraday_result)

        # Test B: F&O (uses same signals)
        fno_result = simulate_fno_day(
            day, historical_data, universe, nifty_data, signals
        )
        fno_days.append(fno_result)

        # Progress
        if (i + 1) % 10 == 0:
            intra_net = sum(d["net"] for d in intraday_days)
            fno_net = sum(d["net"] for d in fno_days)
            print(f"  Day {i+1}/{len(trading_days)}: "
                  f"Intraday ₹{intra_net:+,.0f} | "
                  f"F&O ₹{fno_net:+,.0f} | "
                  f"Combined ₹{intra_net+fno_net:+,.0f}")

    # Save and report
    output_dir = Path("backtest/results")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")

    report_path = output_dir / f"big_test_report_{ts}.txt"
    json_path = output_dir / f"big_test_data_{ts}.json"

    print(f"\nGenerating report...")
    generate_report(intraday_days, fno_days, str(report_path))

    with open(json_path, "w") as f:
        json.dump({
            "intraday": intraday_days,
            "fno": fno_days,
            "config": {
                "intraday_capital": INTRADAY_CAPITAL,
                "intraday_per_trade": INTRADAY_PER_TRADE,
                "fno_capital": FNO_CAPITAL,
                "fno_per_lot": FNO_PER_LOT,
            }
        }, f, indent=2, default=str)

    elapsed = time.time() - start
    print(f"\nCompleted in {elapsed/60:.1f} minutes")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    run()
