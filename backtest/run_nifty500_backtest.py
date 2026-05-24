"""
Nifty 500 Comprehensive Backtest
Tests V4, V6, and V4+V6 combined strategies
Capital: ₹3L, ₹5L, ₹10L
Universe: Nifty 500 (~193 stocks)
Period: Dec 2025 — May 2026

Run in background:
    cd ~/dev-sandbox
    nohup .venv/bin/python3 -m backtest.run_nifty500_backtest \
        > backtest/results/nifty500_run.log 2>&1 &
    echo "PID: $!"
"""

import json
import sys
import time
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.universes import NIFTY500, GAP_STRATEGY_BLACKLIST, BLACKLIST
from backtest.rule_engine import (
    get_candles_for_date,
    get_prev_close,
    generate_orb_signals,
    get_market_direction,
)
from backtest.data_loader import fetch_and_cache_historical
from intraday.charges import calculate_intraday_charges

IST = timezone(timedelta(hours=5, minutes=30))

# ============================================================
# CONFIGURATION
# ============================================================

# Capital configurations to test
CAPITAL_CONFIGS = [
    {"total": 300_000,   "per_trade": 75_000,   "max_trades": 4},
    {"total": 500_000,   "per_trade": 100_000,  "max_trades": 5},
    {"total": 1_000_000, "per_trade": 200_000,  "max_trades": 5},
]

# Strategy variants to test
STRATEGY_VARIANTS = ["V4", "V6", "V4V6_COMBINED"]

# Date range: 6 months
DATE_CHUNKS = [
    ("2025-12-01", "2026-03-01"),
    ("2026-03-01", "2026-05-23"),
]

# Per-stock blacklist — chronic losers from previous backtests
INTRADAY_BLACKLIST = BLACKLIST | GAP_STRATEGY_BLACKLIST | {
    # V6 chronic losers from nifty50 backtest
    "TATASTEEL", "TECHM", "BPCL", "ASIANPAINT", "HINDUNILVR",
    # V4 chronic losers from tier1 backtest
    "TATACONSUM", "HDFCLIFE", "ADANIPOWER", "BEL", "COFORGE",
    # next50 chronic losers
    "IREDA", "NAUKRI", "BDL", "CANBK", "MAZDOCK",
    # Big test losers
    "HAL", "ASTRAL", "FEDERALBNK", "OFSS",
    # From original audit
    "BAJAJFINSV", "BAJFINANCE", "HEROMOTOCO", "BAJAJ_AUTO",
    "JSWSTEEL", "HDFCLIFE",
}

# ============================================================
# UNIVERSE
# ============================================================

def get_nifty500_clean() -> dict:
    """Nifty500 with all blacklists applied."""
    return {
        k: v for k, v in NIFTY500.items()
        if k not in INTRADAY_BLACKLIST
    }

# ============================================================
# DATA FETCHING
# ============================================================

def fetch_all_data(broker) -> dict:
    """Fetch 6 months 15-min data for Nifty500. Cache aggressively."""
    universe = get_nifty500_clean()
    all_data = {}

    print(f"\nFetching data for {len(universe)} stocks (Nifty500 cleaned)...")
    print(f"Blacklisted: {len(INTRADAY_BLACKLIST)} stocks removed")

    for from_date, to_date in DATE_CHUNKS:
        print(f"\n  Chunk: {from_date} → {to_date}")
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
                all_data[symbol] = {k: list(v) for k, v in ohlc.items()}
            else:
                for key in ["open", "high", "low", "close", "volume", "timestamp"]:
                    all_data[symbol][key].extend(ohlc.get(key, []))

    print(f"\n  Data ready: {len(all_data)} stocks")
    return all_data


def get_trading_days(historical_data: dict) -> list:
    """Extract all unique trading days from cached data."""
    days = set()
    sample = next(iter(historical_data))
    for ts in historical_data[sample].get("timestamp", []):
        dt = datetime.fromtimestamp(ts, tz=IST)
        days.add(dt.strftime("%Y-%m-%d"))
    return sorted(days)


def fetch_nifty_data(broker) -> dict:
    """Fetch Nifty index data for market direction."""
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
                for key in ["open", "high", "low", "close", "volume", "timestamp"]:
                    nifty_data[key].extend(chunk.get(key, []))
    candles = len(nifty_data.get("open", [])) if nifty_data else 0
    print(f"  Nifty: {candles} candles")
    return nifty_data

# ============================================================
# SINGLE DAY SIMULATION
# ============================================================

def simulate_day_v4v6_combined(
    target_date: str,
    historical_data: dict,
    universe: dict,
    nifty_data: dict,
    per_trade_cap: int,
    max_trades: int,
    daily_loss_limit: float,
) -> dict:
    """
    V4+V6 Combined: V6 signals first (gap catalyst),
    fill remaining slots with V4 signals.
    LONG only.
    """
    config = {
        "per_trade_max_capital": per_trade_cap,
        "max_trades_per_day": max_trades,
        "daily_loss_limit": daily_loss_limit,
    }

    # Step 1: Generate V6 signals (gap + ORB)
    v6_signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant="V6",
        nifty_data=nifty_data,
    )
    # LONG only, positive gap only
    v6_signals = [
        s for s in v6_signals
        if s.get("direction") == "LONG" and s.get("gap_pct", 0) > 0
    ]

    # Step 2: If slots remaining, get V4 signals
    remaining_slots = max_trades - len(v6_signals)
    v4_signals = []
    if remaining_slots > 0:
        v4_config = {**config, "max_trades_per_day": remaining_slots + 3}
        all_v4 = generate_orb_signals(
            target_date=target_date,
            historical_data=historical_data,
            universe=universe,
            config=v4_config,
            strategy_variant="V4",
            nifty_data=nifty_data,
        )
        # LONG only, exclude stocks already in V6
        v6_symbols = {s["symbol"] for s in v6_signals}
        v4_signals = [
            s for s in all_v4
            if s.get("direction") == "LONG"
            and s["symbol"] not in v6_symbols
        ][:remaining_slots]

    # Combine: V6 first, V4 fill
    signals = (v6_signals + v4_signals)[:max_trades]

    if not signals:
        return {
            "date": target_date,
            "trades": [],
            "gross": 0, "charges": 0, "net": 0,
            "winners": 0, "losers": 0,
            "v6_count": 0, "v4_count": 0,
            "skipped": True,
            "skip_reason": "NO_SIGNALS",
        }

    trades = []
    cum_loss = 0.0
    v6_count = 0
    v4_count = 0

    for signal in signals:
        if cum_loss >= daily_loss_limit:
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
        qty = max(1, int(per_trade_cap / entry))
        is_v6 = signal.get("strategy_type", "").startswith("ORB_V6")

        # Find entry candle index
        breakout_t = signal.get("breakout_time", "09:35")
        entry_idx = 0
        for idx, c in enumerate(candles):
            if c["time"].strftime("%H:%M") >= breakout_t:
                entry_idx = idx
                break

        # Walk candles after entry
        exit_price = None
        exit_reason = None
        exit_time = None

        for c in candles[entry_idx + 1:]:
            ct = c["time"]

            # Time stop 14:30
            if ct.hour > 14 or (ct.hour == 14 and ct.minute >= 30):
                exit_price = c["close"]
                exit_reason = "TIME_STOP"
                exit_time = ct.strftime("%H:%M")
                break

            # Stop loss
            if c["low"] <= sl:
                exit_price = sl
                exit_reason = "STOPPED_OUT"
                exit_time = ct.strftime("%H:%M")
                break

            # Target hit
            if c["high"] >= target_p:
                exit_price = target_p
                exit_reason = "TARGET_HIT"
                exit_time = ct.strftime("%H:%M")
                break

        if exit_price is None:
            exit_price = candles[-1]["close"]
            exit_reason = "EOD"
            exit_time = "15:30"

        gross = (exit_price - entry) * qty
        charges = calculate_intraday_charges(entry, exit_price, qty)
        net = round(gross - charges, 2)

        if net < 0:
            cum_loss += abs(net)

        if is_v6:
            v6_count += 1
        else:
            v4_count += 1

        trades.append({
            "symbol": symbol,
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "qty": qty,
            "gross": round(gross, 2),
            "charges": round(charges, 2),
            "net": net,
            "exit_reason": exit_reason,
            "exit_time": exit_time,
            "gap_pct": signal.get("gap_pct", 0),
            "score": signal.get("score", 0),
            "signal_type": "V6" if is_v6 else "V4",
            "market_dir": signal.get("market_direction", ""),
        })

    total_gross = sum(t["gross"] for t in trades)
    total_charges = sum(t["charges"] for t in trades)
    total_net = sum(t["net"] for t in trades)

    return {
        "date": target_date,
        "trades": trades,
        "gross": round(total_gross, 2),
        "charges": round(total_charges, 2),
        "net": round(total_net, 2),
        "winners": sum(1 for t in trades if t["net"] > 0),
        "losers": sum(1 for t in trades if t["net"] <= 0),
        "v6_count": v6_count,
        "v4_count": v4_count,
        "skipped": False,
    }


def simulate_day_single(
    target_date: str,
    historical_data: dict,
    universe: dict,
    nifty_data: dict,
    strategy_variant: str,
    per_trade_cap: int,
    max_trades: int,
    daily_loss_limit: float,
) -> dict:
    """Simulate single strategy variant day."""
    config = {
        "per_trade_max_capital": per_trade_cap,
        "max_trades_per_day": max_trades,
        "daily_loss_limit": daily_loss_limit,
    }

    signals = generate_orb_signals(
        target_date=target_date,
        historical_data=historical_data,
        universe=universe,
        config=config,
        strategy_variant=strategy_variant,
        nifty_data=nifty_data,
    )
    # LONG only
    signals = [s for s in signals if s.get("direction") == "LONG"]
    if strategy_variant == "V6":
        signals = [s for s in signals if s.get("gap_pct", 0) > 0]

    if not signals:
        return {
            "date": target_date, "trades": [],
            "gross": 0, "charges": 0, "net": 0,
            "winners": 0, "losers": 0,
            "v6_count": 0, "v4_count": 0,
            "skipped": True, "skip_reason": "NO_SIGNALS",
        }

    trades = []
    cum_loss = 0.0

    for signal in signals[:max_trades]:
        if cum_loss >= daily_loss_limit:
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
        qty = max(1, int(per_trade_cap / entry))

        breakout_t = signal.get("breakout_time", "09:35")
        entry_idx = 0
        for idx, c in enumerate(candles):
            if c["time"].strftime("%H:%M") >= breakout_t:
                entry_idx = idx
                break

        exit_price = None
        exit_reason = None
        exit_time = None

        for c in candles[entry_idx + 1:]:
            ct = c["time"]
            if ct.hour > 14 or (ct.hour == 14 and ct.minute >= 30):
                exit_price = c["close"]
                exit_reason = "TIME_STOP"
                exit_time = ct.strftime("%H:%M")
                break
            if c["low"] <= sl:
                exit_price = sl
                exit_reason = "STOPPED_OUT"
                exit_time = ct.strftime("%H:%M")
                break
            if c["high"] >= target_p:
                exit_price = target_p
                exit_reason = "TARGET_HIT"
                exit_time = ct.strftime("%H:%M")
                break

        if exit_price is None:
            exit_price = candles[-1]["close"]
            exit_reason = "EOD"
            exit_time = "15:30"

        gross = (exit_price - entry) * qty
        charges = calculate_intraday_charges(entry, exit_price, qty)
        net = round(gross - charges, 2)

        if net < 0:
            cum_loss += abs(net)

        trades.append({
            "symbol": symbol,
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "qty": qty,
            "gross": round(gross, 2),
            "charges": round(charges, 2),
            "net": net,
            "exit_reason": exit_reason,
            "exit_time": exit_time,
            "gap_pct": signal.get("gap_pct", 0),
            "score": signal.get("score", 0),
            "signal_type": strategy_variant,
            "market_dir": signal.get("market_direction", ""),
        })

    return {
        "date": target_date,
        "trades": trades,
        "gross": round(sum(t["gross"] for t in trades), 2),
        "charges": round(sum(t["charges"] for t in trades), 2),
        "net": round(sum(t["net"] for t in trades), 2),
        "winners": sum(1 for t in trades if t["net"] > 0),
        "losers": sum(1 for t in trades if t["net"] <= 0),
        "v6_count": len(trades) if strategy_variant == "V6" else 0,
        "v4_count": len(trades) if strategy_variant == "V4" else 0,
        "skipped": False,
    }

# ============================================================
# REPORT
# ============================================================

def generate_report(all_results: dict, output_path: str) -> str:
    """Generate comprehensive backtest report."""
    lines = []
    lines.append("=" * 72)
    lines.append("NIFTY 500 COMPREHENSIVE BACKTEST REPORT")
    lines.append("Strategies: V4, V6, V4+V6 Combined")
    lines.append("Universe: Nifty 500 (blacklist applied)")
    lines.append(f"Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    lines.append("=" * 72)

    # Summary table first
    lines.append("\n📊 SUMMARY TABLE")
    lines.append("─" * 72)
    lines.append(f"{'Strategy':<16} {'Capital':>10} {'Trades':>7} {'WR':>6} {'PF':>6} {'Net 6m':>12} {'Monthly':>10} {'Verdict'}")
    lines.append("─" * 72)

    for combo_key, result in sorted(all_results.items()):
        days = result["days"]
        all_trades = [t for d in days for t in d.get("trades", [])]
        total_net = sum(d["net"] for d in days)
        total_gross = sum(d["gross"] for d in days)
        total_charges = sum(d["charges"] for d in days)
        total_w = sum(d["winners"] for d in days)
        total_l = sum(d["losers"] for d in days)
        total_t = total_w + total_l
        wr = total_w / total_t * 100 if total_t > 0 else 0
        pf = abs(
            sum(t["gross"] for t in all_trades if t["gross"] > 0) /
            abs(sum(t["gross"] for t in all_trades if t["gross"] < 0))
        ) if any(t["gross"] < 0 for t in all_trades) else 0
        monthly = total_net / 6

        if wr >= 45 and pf >= 1.3 and total_net > 0:
            verdict = "✅ DEPLOY"
        elif wr >= 40 and total_net > 0:
            verdict = "⚠️  PAPER"
        else:
            verdict = "❌ NO"

        cap = result["per_trade_cap"] * result["max_trades"]
        lines.append(
            f"{result['strategy']:<16} ₹{cap/100000:>6.1f}L"
            f" {total_t:>7} {wr:>5.1f}%"
            f" {pf:>6.2f} ₹{total_net:>+10,.0f}"
            f" ₹{monthly:>+8,.0f}  {verdict}"
        )

    lines.append("─" * 72)

    # Detailed sections
    for combo_key, result in sorted(all_results.items()):
        strategy = result["strategy"]
        per_trade = result["per_trade_cap"]
        max_trades = result["max_trades"]
        days = result["days"]

        all_trades = [t for d in days for t in d.get("trades", [])]
        total_days = len(days)
        active_days = sum(1 for d in days if not d.get("skipped"))
        skipped_days = total_days - active_days
        total_net = sum(d["net"] for d in days)
        total_gross = sum(d["gross"] for d in days)
        total_charges = sum(d["charges"] for d in days)
        total_w = sum(d["winners"] for d in days)
        total_l = sum(d["losers"] for d in days)
        total_t = total_w + total_l
        wr = total_w / total_t * 100 if total_t > 0 else 0

        wins_gross = sum(t["gross"] for t in all_trades if t["gross"] > 0)
        loss_gross = abs(sum(t["gross"] for t in all_trades if t["gross"] < 0))
        pf = wins_gross / loss_gross if loss_gross > 0 else 0

        deployed = per_trade * max_trades
        roi = total_net / deployed * 100 if deployed > 0 else 0

        lines.append(f"\n{'─'*72}")
        lines.append(f"Strategy: {strategy} | Per trade: ₹{per_trade:,} | Max: {max_trades} trades")
        lines.append(f"Total capital: ₹{deployed:,} | Period: Dec 2025 — May 2026")
        lines.append(f"{'─'*72}")
        lines.append(f"  Trading days:    {active_days} active / {skipped_days} skipped")
        lines.append(f"  Total trades:    {total_t}")
        lines.append(f"  Win rate:        {wr:.1f}%  ({total_w}W / {total_l}L)")
        lines.append(f"  Profit factor:   {pf:.2f}")
        lines.append(f"  Total gross:     ₹{total_gross:>+12,.2f}")
        lines.append(f"  Total charges:   ₹{total_charges:>12,.2f}")
        lines.append(f"  Total net 6m:    ₹{total_net:>+12,.2f}")
        lines.append(f"  Monthly avg:     ₹{total_net/6:>+12,.2f}")
        lines.append(f"  Per trade avg:   ₹{total_net/max(total_t,1):>+12,.2f}")
        lines.append(f"  ROI on capital:  {roi:.1f}% in 6 months")
        lines.append(f"  Annualised ROI:  {roi*2:.1f}%")

        # Scaling projection
        if total_net > 0:
            monthly_per_lakh = (total_net / 6) / (deployed / 100000)
            lines.append(f"\n  📈 SCALING PROJECTION:")
            lines.append(f"  ₹10L capital  → ₹{monthly_per_lakh*10:>+8,.0f}/month")
            lines.append(f"  ₹20L capital  → ₹{monthly_per_lakh*20:>+8,.0f}/month")
            lines.append(f"  ₹50L capital  → ₹{monthly_per_lakh*50:>+8,.0f}/month")
            target_capital = 100000 / monthly_per_lakh if monthly_per_lakh > 0 else 0
            lines.append(f"  Capital needed for ₹1L/month → ₹{target_capital:.1f}L")

        # Monthly breakdown
        monthly = {}
        for d in days:
            m = d["date"][:7]
            if m not in monthly:
                monthly[m] = {"net": 0, "trades": 0, "winners": 0}
            monthly[m]["net"] += d["net"]
            monthly[m]["trades"] += len(d.get("trades", []))
            monthly[m]["winners"] += d.get("winners", 0)

        lines.append(f"\n  Monthly breakdown:")
        for m, s in sorted(monthly.items()):
            wr_m = s["winners"] / s["trades"] * 100 if s["trades"] > 0 else 0
            lines.append(
                f"    {m}: ₹{s['net']:>+8,.0f}  "
                f"({s['trades']} trades, {wr_m:.0f}% WR)"
            )

        # Exit reason analysis
        exit_reasons = {}
        for t in all_trades:
            r = t.get("exit_reason", "UNKNOWN")
            if r not in exit_reasons:
                exit_reasons[r] = {"count": 0, "net": 0, "wins": 0}
            exit_reasons[r]["count"] += 1
            exit_reasons[r]["net"] += t["net"]
            if t["net"] > 0:
                exit_reasons[r]["wins"] += 1

        lines.append(f"\n  Exit reason breakdown:")
        for r, s in sorted(exit_reasons.items(), key=lambda x: -x[1]["count"]):
            wr_r = s["wins"] / s["count"] * 100 if s["count"] > 0 else 0
            lines.append(
                f"    {r:<15}: {s['count']:>4} trades, "
                f"{wr_r:>5.1f}% WR, ₹{s['net']:>+8,.0f}"
            )

        # V6 vs V4 split (for combined strategy)
        if strategy == "V4V6_COMBINED":
            v6_trades = [t for t in all_trades if t.get("signal_type") == "V6"]
            v4_trades = [t for t in all_trades if t.get("signal_type") == "V4"]

            def stats(tlist):
                if not tlist:
                    return 0, 0, 0
                w = sum(1 for t in tlist if t["net"] > 0)
                wr_ = w / len(tlist) * 100
                net_ = sum(t["net"] for t in tlist)
                return len(tlist), wr_, net_

            v6_c, v6_wr, v6_net = stats(v6_trades)
            v4_c, v4_wr, v4_net = stats(v4_trades)
            lines.append(f"\n  V6 vs V4 split:")
            lines.append(f"    V6 signals: {v6_c:>4} trades, {v6_wr:.1f}% WR, ₹{v6_net:>+8,.0f}")
            lines.append(f"    V4 signals: {v4_c:>4} trades, {v4_wr:.1f}% WR, ₹{v4_net:>+8,.0f}")

        # By market direction
        by_dir = {}
        for t in all_trades:
            md = t.get("market_dir", "UNKNOWN")
            if md not in by_dir:
                by_dir[md] = {"count": 0, "net": 0, "wins": 0}
            by_dir[md]["count"] += 1
            by_dir[md]["net"] += t["net"]
            if t["net"] > 0:
                by_dir[md]["wins"] += 1

        lines.append(f"\n  By market direction:")
        for md, s in sorted(by_dir.items()):
            wr_d = s["wins"] / s["count"] * 100 if s["count"] > 0 else 0
            lines.append(
                f"    {md:<8}: {s['count']:>4} trades, "
                f"{wr_d:>5.1f}% WR, ₹{s['net']:>+8,.0f}"
            )

        # Top / Bottom stocks
        by_stock = {}
        for t in all_trades:
            s = t["symbol"]
            if s not in by_stock:
                by_stock[s] = {"count": 0, "net": 0, "wins": 0, "gross": 0}
            by_stock[s]["count"] += 1
            by_stock[s]["net"] += t["net"]
            by_stock[s]["gross"] += t["gross"]
            if t["net"] > 0:
                by_stock[s]["wins"] += 1

        lines.append(f"\n  Top 15 stocks (add to whitelist):")
        for s, st in sorted(by_stock.items(), key=lambda x: -x[1]["net"])[:15]:
            wr_s = st["wins"] / st["count"] * 100 if st["count"] > 0 else 0
            lines.append(
                f"    {s:<16}: {st['count']:>3} trades, "
                f"{wr_s:>5.1f}% WR, ₹{st['net']:>+8,.0f}"
            )

        lines.append(f"\n  Bottom 15 stocks (add to blacklist):")
        for s, st in sorted(by_stock.items(), key=lambda x: x[1]["net"])[:15]:
            wr_s = st["wins"] / st["count"] * 100 if st["count"] > 0 else 0
            lines.append(
                f"    {s:<16}: {st['count']:>3} trades, "
                f"{wr_s:>5.1f}% WR, ₹{st['net']:>+8,.0f}"
            )

        # Verdict
        lines.append(f"\n  VERDICT:")
        if wr >= 45 and pf >= 1.3 and total_net > 0:
            lines.append(f"  ✅ DEPLOY — Edge confirmed.")
            lines.append(f"     Win rate {wr:.1f}% and PF {pf:.2f} meet criteria.")
        elif wr >= 40 and total_net > 0:
            lines.append(f"  ⚠️  PAPER ONLY — Marginal edge.")
            lines.append(f"     Test in paper before live deployment.")
        else:
            lines.append(f"  ❌ DO NOT DEPLOY — No consistent edge.")

    # Final recommendation
    lines.append(f"\n{'='*72}")
    lines.append("FINAL RECOMMENDATION — PATH TO ₹1L/MONTH")
    lines.append(f"{'='*72}")

    best_monthly = 0
    best_combo = None
    for combo_key, result in all_results.items():
        days = result["days"]
        total_net = sum(d["net"] for d in days)
        monthly = total_net / 6
        all_trades = [t for d in days for t in d.get("trades", [])]
        total_t = len(all_trades)
        total_w = sum(1 for t in all_trades if t["net"] > 0)
        wr = total_w / total_t * 100 if total_t > 0 else 0
        pf_wins = sum(t["gross"] for t in all_trades if t["gross"] > 0)
        pf_loss = abs(sum(t["gross"] for t in all_trades if t["gross"] < 0))
        pf = pf_wins / pf_loss if pf_loss > 0 else 0

        if wr >= 45 and pf >= 1.3 and monthly > best_monthly:
            best_monthly = monthly
            best_combo = (combo_key, result, wr, pf, monthly)

    if best_combo:
        combo_key, result, wr, pf, monthly = best_combo
        deployed = result["per_trade_cap"] * result["max_trades"]
        monthly_per_lakh = monthly / (deployed / 100000)
        target_cap = 100000 / monthly_per_lakh if monthly_per_lakh > 0 else 0

        lines.append(f"\n  Best proven strategy: {result['strategy']}")
        lines.append(f"  Win rate: {wr:.1f}% | PF: {pf:.2f}")
        lines.append(f"  At ₹{deployed/100000:.0f}L capital: ₹{monthly:,.0f}/month")
        lines.append(f"  Monthly per ₹1L deployed: ₹{monthly_per_lakh:,.0f}")
        lines.append(f"\n  Capital needed for ₹1L/month: ₹{target_cap:.1f}L")
        lines.append(f"\n  Deployment roadmap:")
        lines.append(f"    Month 1-2: Paper trade, validate signal accuracy")
        lines.append(f"    Month 3:   ₹{min(deployed,500000)/100000:.0f}L live → ₹{monthly_per_lakh*min(deployed,500000)/100000:,.0f}/month")
        lines.append(f"    Month 4-5: Scale to ₹{target_cap*0.5:.0f}L → ₹{monthly_per_lakh*target_cap*0.5:,.0f}/month")
        lines.append(f"    Month 6+:  Full ₹{target_cap:.0f}L → ₹1,00,000/month")
        lines.append(f"\n  Add swing + F&O streams for faster path:")
        lines.append(f"    Swing (if backtested): ₹{target_cap*0.4:.0f}L → ₹40K/month target")
        lines.append(f"    F&O Iron Condor:       ₹{target_cap*0.3:.0f}L → ₹30K/month target")
        lines.append(f"    Combined capital:      ₹{target_cap*1.7:.0f}L → ₹1L+/month")
    else:
        lines.append("\n  No strategy met deploy criteria at tested capital levels.")
        lines.append("  Recommendation: Review blacklist and universe, re-run.")

    lines.append(f"\n{'='*72}")
    lines.append("END OF REPORT")
    lines.append(f"{'='*72}")

    report_text = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(report_text)
    print(report_text)
    return report_text

# ============================================================
# MAIN
# ============================================================

def run():
    import time as time_module
    start = time_module.time()

    print("=" * 72)
    print("NIFTY 500 COMPREHENSIVE BACKTEST")
    print(f"Strategies: {STRATEGY_VARIANTS}")
    print(f"Capital configs: {len(CAPITAL_CONFIGS)}")
    print(f"Universe: Nifty500 (~{len(get_nifty500_clean())} stocks after blacklist)")
    print("=" * 72)

    # Auth
    print("\n[1] Authenticating...")
    with open("config/profiles/vishal.yaml") as f:
        config = yaml.safe_load(f)
    from intraday.auth_server import authenticate_broker
    broker = authenticate_broker(
        broker_name="dhan",
        broker_config=config.get("dhan", {}),
        dry_run=False,
    )
    print("  ✓ Broker ready")

    # Fetch data
    nifty_data = fetch_nifty_data(broker)
    universe = get_nifty500_clean()
    historical_data = fetch_all_data(broker)
    trading_days = get_trading_days(historical_data)

    print(f"\n[2] Data summary:")
    print(f"  Universe: {len(universe)} stocks")
    print(f"  Historical data: {len(historical_data)} stocks fetched")
    print(f"  Trading days: {len(trading_days)}")
    print(f"  Date range: {trading_days[0]} to {trading_days[-1]}")

    # Run all combinations
    all_results = {}
    output_dir = Path("backtest/results")
    output_dir.mkdir(exist_ok=True)

    total_combos = len(STRATEGY_VARIANTS) * len(CAPITAL_CONFIGS)
    combo_num = 0

    print(f"\n[3] Running {total_combos} combinations...")

    for cap_cfg in CAPITAL_CONFIGS:
        per_trade = cap_cfg["per_trade"]
        max_trades = cap_cfg["max_trades"]
        total_cap = cap_cfg["total"]
        daily_loss = total_cap * 0.02  # 2% daily loss limit

        for strategy in STRATEGY_VARIANTS:
            combo_num += 1
            combo_key = f"{strategy}_cap{total_cap//100000}L"
            print(f"\n  [{combo_num}/{total_combos}] {combo_key}")

            day_results = []
            for i, day in enumerate(trading_days):
                if strategy == "V4V6_COMBINED":
                    result = simulate_day_v4v6_combined(
                        day, historical_data, universe,
                        nifty_data, per_trade, max_trades, daily_loss,
                    )
                else:
                    result = simulate_day_single(
                        day, historical_data, universe,
                        nifty_data, strategy, per_trade, max_trades, daily_loss,
                    )
                day_results.append(result)

                if (i + 1) % 20 == 0:
                    cum_net = sum(d["net"] for d in day_results)
                    active = sum(1 for d in day_results if not d.get("skipped"))
                    print(
                        f"    Day {i+1}/{len(trading_days)}: "
                        f"{active} active, ₹{cum_net:+,.0f} net"
                    )

            # Quick stats
            all_t = [t for d in day_results for t in d.get("trades", [])]
            total_net = sum(d["net"] for d in day_results)
            total_w = sum(d["winners"] for d in day_results)
            total_l = sum(d["losers"] for d in day_results)
            total_t = total_w + total_l
            wr = total_w / total_t * 100 if total_t > 0 else 0
            print(
                f"    DONE: {total_t} trades, "
                f"{wr:.1f}% WR, ₹{total_net:+,.0f} net"
            )

            all_results[combo_key] = {
                "strategy": strategy,
                "per_trade_cap": per_trade,
                "max_trades": max_trades,
                "days": day_results,
            }

            # Save intermediate
            inter_path = output_dir / f"n500_{combo_key}.json"
            with open(inter_path, "w") as f:
                json.dump(all_results[combo_key], f, default=str)

    # Generate report
    elapsed = time_module.time() - start
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"nifty500_report_{ts}.txt"
    json_path = output_dir / f"nifty500_full_{ts}.json"

    print(f"\n[4] Generating report...")
    generate_report(all_results, str(report_path))

    with open(json_path, "w") as f:
        json.dump(all_results, f, default=str)

    print(f"\n✅ Completed in {elapsed/60:.1f} minutes")
    print(f"   Report: {report_path}")
    print(f"   Data:   {json_path}")


if __name__ == "__main__":
    run()
