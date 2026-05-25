"""
Three Strategy Backtest — Full Day V2 Coverage
Tests Strategy 1 (ORB), Strategy 2 (VWAP Reclaim), Strategy 3 (Trend Continuation)
Capital configs: Rs.30K, Rs.1L, Rs.3L
Universe: 195 stocks, 75 days of 15-min data

Run:
    cd ~/dev-sandbox
    nohup .venv/bin/python3 backtest/run_three_strategy_backtest.py \
        > backtest/results/three_strategy_run.log 2>&1 &
    echo PID: $!
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.rule_engine import (
    get_candles_for_date,
    get_prev_close,
    generate_orb_signals,
    generate_vwap_reclaim_signals,
    generate_trend_continuation_signals,
    get_market_direction,
    calculate_vwap,
    calculate_atr,
)
from backtest.universes import NIFTY500
from intraday.charges import calculate_intraday_charges

IST = timezone(timedelta(hours=5, minutes=30))

BLACKLIST = {
    "MRF", "SAIL", "LAURUSLABS", "IPCALAB", "CONCOR", "PRESTIGE",
    "GNFC", "BSE", "SONACOMS", "ANGELONE", "PVRINOX", "PIIND",
    "MCDOWELL-N", "GODREJCP", "UBL", "TATASTEEL", "BPCL",
    "ASIANPAINT", "HINDUNILVR", "TATACONSUM", "HDFCLIFE",
    "ADANIPOWER", "BEL", "COFORGE", "IREDA", "NAUKRI", "BDL",
    "CANBK", "MAZDOCK", "ASTRAL", "FEDERALBNK", "OFSS",
    "BAJAJFINSV", "BAJFINANCE", "HEROMOTOCO", "BAJAJ-AUTO",
    "JSWSTEEL", "INDIGO", "COCHINSHIP",
}

CAPITAL_CONFIGS = [
    {"name": "Rs30K_live",  "total": 30_000,  "per_trade": 10_000, "max_trades": 3},
    {"name": "Rs1L_paper",  "total": 100_000, "per_trade": 25_000, "max_trades": 4},
    {"name": "Rs3L_paper",  "total": 300_000, "per_trade": 75_000, "max_trades": 4},
]


def load_all_cached_data(cache_dir: str = "cache/historical_v2") -> dict:
    """Load all cached 15-min OHLC data."""
    cache_path = Path(cache_dir)
    data = {}
    for fpath in cache_path.glob("*.json"):
        sym = fpath.stem.split("_")[0]
        try:
            with open(fpath) as f:
                ohlc = json.load(f)
            if ohlc and ohlc.get("open"):
                data[sym] = ohlc
        except Exception:
            continue
    print(f"Loaded {len(data)} stocks from cache")
    return data


def get_all_trading_dates(historical_data: dict) -> list:
    """Extract all unique trading dates."""
    dates = set()
    for symbol, ohlc in historical_data.items():
        if not ohlc or not ohlc.get("timestamp"):
            continue
        for ts in ohlc["timestamp"]:
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                dt_ist = dt.astimezone(IST)
                # Only market days 9:15 - 15:30
                if dt_ist.weekday() < 5:
                    dates.add(dt_ist.strftime("%Y-%m-%d"))
            except Exception:
                continue
    return sorted(dates)


def simulate_exit(candles: list, entry_price: float, target: float,
                  sl: float, entry_idx: int) -> tuple:
    """
    Simulate trade exit candle by candle after entry.
    Returns (exit_price, exit_reason, bars_held)
    """
    for i in range(entry_idx + 1, len(candles)):
        c = candles[i]
        # Check SL first
        if c["low"] <= sl:
            return sl, "SL", i - entry_idx
        # Check target
        if c["high"] >= target:
            return target, "TARGET", i - entry_idx
        # Force exit at 15:15 IST
        if c["time"].hour == 15 and c["time"].minute >= 15:
            return c["close"], "EOD", i - entry_idx
    # Last candle
    if candles:
        last = candles[-1]
        return last["close"], "EOD", len(candles) - entry_idx
    return entry_price, "NO_EXIT", 0


def run_backtest_for_config(
    historical_data: dict,
    trading_dates: list,
    capital_config: dict,
    universe: dict,
) -> dict:
    """Run full backtest for one capital config across all 3 strategies."""

    per_trade = capital_config["per_trade"]
    max_trades = capital_config["max_trades"]
    config_name = capital_config["name"]

    orb_config = {
        "per_trade_max_capital": per_trade,
        "max_trades_per_day": max_trades,
        "daily_loss_limit": per_trade * 0.1,
    }

    # Results per strategy
    results = {
        "S1_ORB":         {"trades": [], "wins": 0, "losses": 0, "total_pnl": 0},
        "S2_VWAP_RECLAIM":{"trades": [], "wins": 0, "losses": 0, "total_pnl": 0},
        "S3_TREND_CONT":  {"trades": [], "wins": 0, "losses": 0, "total_pnl": 0},
        "COMBINED":       {"trades": [], "wins": 0, "losses": 0, "total_pnl": 0},
    }

    daily_pnl = []

    for date_str in trading_dates:
        day_trades = 0
        day_pnl = 0.0
        day_results = {"date": date_str, "trades": [], "pnl": 0}

        # Build universe for this date
        active_universe = {
            sym: sid for sym, sid in universe.items()
            if sym not in BLACKLIST and sym in historical_data
        }

        # Nifty data proxy — use NIFTY50 member with most data
        nifty_proxy = historical_data.get("RELIANCE") or historical_data.get("HDFCBANK")

        # ── Strategy 1: ORB Gap (simulate morning window) ──
        if day_trades < max_trades:
            slots = max_trades - day_trades
            try:
                v6_signals = generate_orb_signals(
                    target_date=date_str,
                    historical_data=historical_data,
                    universe=active_universe,
                    config={**orb_config, "max_trades_per_day": slots},
                    strategy_variant="V6",
                    nifty_data=nifty_proxy,
                )
                v6_signals = [s for s in v6_signals
                              if s.get("direction") == "LONG"
                              and s.get("gap_pct", 0) > 0][:slots]

                remaining = slots - len(v6_signals)
                v4_signals = []
                if remaining > 0:
                    v6_syms = {s["symbol"] for s in v6_signals}
                    all_v4 = generate_orb_signals(
                        target_date=date_str,
                        historical_data=historical_data,
                        universe=active_universe,
                        config={**orb_config, "max_trades_per_day": remaining + 3},
                        strategy_variant="V4",
                        nifty_data=nifty_proxy,
                    )
                    v4_signals = [s for s in all_v4
                                  if s.get("direction") == "LONG"
                                  and s["symbol"] not in v6_syms][:remaining]

                for sig in (v6_signals + v4_signals)[:slots]:
                    sym = sig["symbol"]
                    candles = get_candles_for_date(historical_data[sym], date_str)
                    if not candles:
                        continue

                    # Find entry candle index
                    entry_price = sig["entry_price"]
                    entry_idx = 0
                    for i, c in enumerate(candles):
                        if c["close"] >= entry_price * 0.998:
                            entry_idx = i
                            break

                    exit_price, reason, bars = simulate_exit(
                        candles, entry_price,
                        sig["target_price"], sig["stop_loss_price"], entry_idx
                    )

                    qty = max(1, int(per_trade / entry_price))
                    gross_pnl = (exit_price - entry_price) * qty
                    charges = calculate_intraday_charges(entry_price, exit_price, qty)
                    net_pnl = gross_pnl - charges

                    strategy_key = "S1_ORB"
                    results[strategy_key]["trades"].append(net_pnl)
                    results["COMBINED"]["trades"].append(net_pnl)
                    if net_pnl > 0:
                        results[strategy_key]["wins"] += 1
                        results["COMBINED"]["wins"] += 1
                    else:
                        results[strategy_key]["losses"] += 1
                        results["COMBINED"]["losses"] += 1
                    results[strategy_key]["total_pnl"] += net_pnl
                    results["COMBINED"]["total_pnl"] += net_pnl

                    day_trades += 1
                    day_pnl += net_pnl
                    day_results["trades"].append({
                        "sym": sym, "strategy": "S1_ORB",
                        "entry": entry_price, "exit": exit_price,
                        "qty": qty, "pnl": round(net_pnl, 2), "reason": reason
                    })

            except Exception as e:
                pass

        # ── Strategy 2: VWAP Reclaim (simulate midday) ──
        if day_trades < max_trades:
            slots = max_trades - day_trades
            try:
                vwap_signals = generate_vwap_reclaim_signals(
                    target_date=date_str,
                    historical_data=historical_data,
                    universe=active_universe,
                    config=orb_config,
                    nifty_data=nifty_proxy,
                )
                vwap_signals = [s for s in vwap_signals
                                if s.get("direction") == "LONG"][:slots]

                for sig in vwap_signals:
                    sym = sig["symbol"]
                    candles = get_candles_for_date(historical_data[sym], date_str)
                    if not candles:
                        continue

                    entry_price = sig["entry_price"]
                    entry_idx = 0
                    for i, c in enumerate(candles):
                        if c["time"].hour >= 11:
                            entry_idx = i
                            break

                    exit_price, reason, bars = simulate_exit(
                        candles, entry_price,
                        sig["target_price"], sig["stop_loss_price"], entry_idx
                    )

                    qty = max(1, int(per_trade / entry_price))
                    gross_pnl = (exit_price - entry_price) * qty
                    charges = calculate_intraday_charges(entry_price, exit_price, qty)
                    net_pnl = gross_pnl - charges

                    results["S2_VWAP_RECLAIM"]["trades"].append(net_pnl)
                    results["COMBINED"]["trades"].append(net_pnl)
                    if net_pnl > 0:
                        results["S2_VWAP_RECLAIM"]["wins"] += 1
                        results["COMBINED"]["wins"] += 1
                    else:
                        results["S2_VWAP_RECLAIM"]["losses"] += 1
                        results["COMBINED"]["losses"] += 1
                    results["S2_VWAP_RECLAIM"]["total_pnl"] += net_pnl
                    results["COMBINED"]["total_pnl"] += net_pnl

                    day_trades += 1
                    day_pnl += net_pnl
                    day_results["trades"].append({
                        "sym": sym, "strategy": "S2_VWAP",
                        "entry": entry_price, "exit": exit_price,
                        "qty": qty, "pnl": round(net_pnl, 2), "reason": reason
                    })

            except Exception as e:
                pass

        # ── Strategy 3: Trend Continuation (simulate afternoon) ──
        if day_trades < max_trades:
            slots = max_trades - day_trades
            try:
                trend_signals = generate_trend_continuation_signals(
                    target_date=date_str,
                    historical_data=historical_data,
                    universe=active_universe,
                    config=orb_config,
                    nifty_data=nifty_proxy,
                )
                trend_signals = [s for s in trend_signals
                                 if s.get("direction") == "LONG"][:slots]

                for sig in trend_signals:
                    sym = sig["symbol"]
                    candles = get_candles_for_date(historical_data[sym], date_str)
                    if not candles:
                        continue

                    entry_price = sig["entry_price"]
                    entry_idx = 0
                    for i, c in enumerate(candles):
                        if c["time"].hour >= 13:
                            entry_idx = i
                            break

                    exit_price, reason, bars = simulate_exit(
                        candles, entry_price,
                        sig["target_price"], sig["stop_loss_price"], entry_idx
                    )

                    qty = max(1, int(per_trade / entry_price))
                    gross_pnl = (exit_price - entry_price) * qty
                    charges = calculate_intraday_charges(entry_price, exit_price, qty)
                    net_pnl = gross_pnl - charges

                    results["S3_TREND_CONT"]["trades"].append(net_pnl)
                    results["COMBINED"]["trades"].append(net_pnl)
                    if net_pnl > 0:
                        results["S3_TREND_CONT"]["wins"] += 1
                        results["COMBINED"]["wins"] += 1
                    else:
                        results["S3_TREND_CONT"]["losses"] += 1
                        results["COMBINED"]["losses"] += 1
                    results["S3_TREND_CONT"]["total_pnl"] += net_pnl
                    results["COMBINED"]["total_pnl"] += net_pnl

                    day_trades += 1
                    day_pnl += net_pnl
                    day_results["trades"].append({
                        "sym": sym, "strategy": "S3_TREND",
                        "entry": entry_price, "exit": exit_price,
                        "qty": qty, "pnl": round(net_pnl, 2), "reason": reason
                    })

            except Exception as e:
                pass

        day_results["pnl"] = round(day_pnl, 2)
        day_results["trades_count"] = day_trades
        daily_pnl.append(day_results)

    return {"results": results, "daily_pnl": daily_pnl}


def print_report(config_name: str, data: dict, trading_days: int):
    """Print clean trader-friendly report."""
    results = data["results"]
    print(f"\n{'='*65}")
    print(f"  {config_name} — {trading_days} trading days")
    print(f"{'='*65}")
    print(f"{'Strategy':<22} {'Trades':>7} {'WR%':>7} {'PF':>6} {'Net P&L':>10} {'Per Day':>9}")
    print(f"{'-'*65}")

    for strat, r in results.items():
        trades = r["trades"]
        n = len(trades)
        if n == 0:
            print(f"{strat:<22} {'0':>7} {'N/A':>7} {'N/A':>6} {'N/A':>10} {'N/A':>9}")
            continue

        wins = r["wins"]
        wr = (wins / n) * 100
        total_pnl = r["total_pnl"]
        per_day = total_pnl / max(trading_days, 1)

        gross_wins = sum(p for p in trades if p > 0)
        gross_losses = abs(sum(p for p in trades if p < 0))
        pf = gross_wins / gross_losses if gross_losses > 0 else 999

        flag = ""
        if strat != "COMBINED":
            if wr >= 55 and pf >= 1.5:
                flag = "✅ DEPLOY"
            elif wr >= 45 and pf >= 1.2:
                flag = "⚠️  PAPER"
            else:
                flag = "❌ WEAK"

        print(f"{strat:<22} {n:>7} {wr:>6.1f}% {pf:>6.2f} {total_pnl:>9.0f} {per_day:>8.0f}  {flag}")

    # Monthly projection
    combined = results["COMBINED"]
    monthly = (combined["total_pnl"] / max(trading_days, 1)) * 22
    print(f"\n  Monthly projection (22 days): Rs.{monthly:,.0f}")
    print(f"  Total trades: {len(combined['trades'])}")

    # Best and worst days
    daily = data["daily_pnl"]
    if daily:
        best = max(daily, key=lambda x: x["pnl"])
        worst = min(daily, key=lambda x: x["pnl"])
        print(f"  Best day:  {best['date']} Rs.{best['pnl']:,.0f} ({best['trades_count']} trades)")
        print(f"  Worst day: {worst['date']} Rs.{worst['pnl']:,.0f} ({worst['trades_count']} trades)")


if __name__ == "__main__":
    print("=" * 65)
    print("  THREE STRATEGY BACKTEST — V2 Full Day Coverage")
    print("=" * 65)

    # Load cached data
    historical_data = load_all_cached_data("cache/historical_v2")

    if len(historical_data) < 10:
        print("ERROR: Not enough cached data. Run data fetch first.")
        print("Check: tail -f backtest/results/fetch_log.txt")
        sys.exit(1)

    # Get trading dates
    trading_dates = get_all_trading_dates(historical_data)
    print(f"Trading dates found: {len(trading_dates)}")
    if trading_dates:
        print(f"Range: {trading_dates[0]} to {trading_dates[-1]}")

    # Clean universe
    universe = {sym: sid for sym, sid in NIFTY500.items()
                if sym not in BLACKLIST}
    print(f"Universe: {len(universe)} stocks (after blacklist)")

    # Run for each capital config
    all_results = {}
    for cap_cfg in CAPITAL_CONFIGS:
        print(f"\nRunning {cap_cfg['name']}...")
        result = run_backtest_for_config(
            historical_data=historical_data,
            trading_dates=trading_dates,
            capital_config=cap_cfg,
            universe=universe,
        )
        all_results[cap_cfg["name"]] = result
        print_report(cap_cfg["name"], result, len(trading_dates))

    # Save full results
    out_file = "backtest/results/three_strategy_backtest.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\nFull results saved: {out_file}")
    print("\nDONE.")
