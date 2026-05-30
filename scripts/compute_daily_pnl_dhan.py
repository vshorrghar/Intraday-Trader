#!/usr/bin/env python3
"""Compute daily P&L from DHAN ORDERS API (source of truth).

Unlike compute_daily_pnl.py which reads from our DB (often wrong),
this script pulls directly from Dhan's /v2/orders endpoint and
computes real P&L from actual filled orders.

Runs via cron at 3:45 PM IST (after market close, all orders settled).

Usage:
    python scripts/compute_daily_pnl_dhan.py                # today, all live profiles
    python scripts/compute_daily_pnl_dhan.py --date 2026-05-29  # specific date
"""
import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.profile_loader import load_profile
from intraday.auth_server import authenticate_broker

IST = timezone(timedelta(hours=5, minutes=30))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Profiles that trade real money via Dhan
LIVE_PROFILES = ["vishal-live-v2"]
CAPITAL = {"vishal-live-v2": 30000, "vishal-live": 30000}
S3_BUCKET = "dev-sandbox-dashboard-176767908884"
CF_DIST = "E3NXP6TCRJKVX1"


def estimate_charges(buy_value, sell_value):
    """Estimate intraday charges: brokerage + STT + exchange + GST + stamp."""
    turnover = buy_value + sell_value
    brokerage = min(40, turnover * 0.0003)  # 0.03% or Rs.20 per leg
    stt = sell_value * 0.00025  # 0.025% on sell
    exchange = turnover * 0.0000345  # NSE charges
    gst = brokerage * 0.18
    stamp = buy_value * 0.00003  # stamp on buy
    sebi = turnover * 0.000001
    return round(brokerage + stt + exchange + gst + stamp + sebi, 2)


def compute_from_dhan(profile_name: str, target_date: str) -> dict | None:
    """Pull orders from Dhan API and compute real P&L for the given date."""
    try:
        cfg = load_profile(profile_name)
        dhan_cfg = cfg.get("dhan", {})
        broker = authenticate_broker("dhan", dhan_cfg, dry_run=False, profile=profile_name)
        if broker is None:
            log.error(f"[{profile_name}] Auth failed")
            return None

        orders = broker.get_order_list()
        if not orders:
            log.info(f"[{profile_name}] No orders today")
            return _zero_day(profile_name, target_date, "No orders from Dhan API")

        # Filter to TRADED orders only
        traded = [o for o in orders if o.get("orderStatus") == "TRADED"]
        if not traded:
            rejected = [o for o in orders if o.get("orderStatus") == "REJECTED"]
            log.info(f"[{profile_name}] {len(orders)} orders but 0 traded ({len(rejected)} rejected)")
            return _zero_day(profile_name, target_date,
                           f"{len(orders)} orders placed, {len(rejected)} rejected, 0 filled")

        # Group by symbol: match BUY entries with SELL exits
        from collections import defaultdict
        by_symbol = defaultdict(lambda: {"buys": [], "sells": []})
        for o in traded:
            sym = o.get("tradingSymbol", "")
            action = o.get("transactionType", "")
            qty = int(o.get("filledQty", o.get("quantity", 0)))
            price = float(o.get("price", 0))
            if price == 0:
                price = float(o.get("averageTradedPrice", 0))
            if action == "BUY":
                by_symbol[sym]["buys"].append({"qty": qty, "price": price, "order_id": o.get("orderId")})
            elif action == "SELL":
                by_symbol[sym]["sells"].append({"qty": qty, "price": price, "order_id": o.get("orderId")})

        # Compute P&L per symbol
        trades = []
        total_gross = 0
        total_charges = 0

        for sym, sides in by_symbol.items():
            buy_qty = sum(b["qty"] for b in sides["buys"])
            sell_qty = sum(s["qty"] for s in sides["sells"])
            buy_value = sum(b["qty"] * b["price"] for b in sides["buys"])
            sell_value = sum(s["qty"] * s["price"] for s in sides["sells"])

            # Determine direction
            if buy_qty > 0 and sell_qty > 0:
                # Round trip (or partial)
                matched_qty = min(buy_qty, sell_qty)
                avg_buy = buy_value / buy_qty if buy_qty > 0 else 0
                avg_sell = sell_value / sell_qty if sell_qty > 0 else 0
                gross_pnl = (avg_sell - avg_buy) * matched_qty
                charges = estimate_charges(avg_buy * matched_qty, avg_sell * matched_qty)
                net_pnl = gross_pnl - charges

                trades.append({
                    "trade_id": f"dhan_{target_date}_{sym}",
                    "symbol": sym,
                    "direction": "LONG",
                    "qty": matched_qty,
                    "entry_price": round(avg_buy, 2),
                    "exit_price": round(avg_sell, 2),
                    "capital_used": round(avg_buy * matched_qty, 2),
                    "gross_pnl": round(gross_pnl, 2),
                    "charges": round(charges, 2),
                    "net_pnl": round(net_pnl, 2),
                    "status": "TARGET_HIT" if gross_pnl > 0 else "STOPPED_OUT",
                })
                total_gross += gross_pnl
                total_charges += charges
            elif sell_qty > 0 and buy_qty == 0:
                # Short trade (SELL first) — need historical context
                # For now mark as open short
                log.warning(f"[{sym}] SELL-only orders (short or exit of prior day)")
            elif buy_qty > 0 and sell_qty == 0:
                # Open position (bought but not sold yet)
                log.info(f"[{sym}] BUY-only — position still open")

        capital_configured = CAPITAL.get(profile_name, 30000)
        capital_deployed = sum(t["capital_used"] for t in trades)
        total_net = total_gross - total_charges
        wins = sum(1 for t in trades if t["net_pnl"] > 0)
        losses = sum(1 for t in trades if t["net_pnl"] < 0)

        return {
            "profile": profile_name,
            "date": target_date,
            "generated_at": datetime.now(IST).isoformat(),
            "source": "dhan_orders_api",
            "capital_configured": capital_configured,
            "capital_deployed_peak": round(capital_deployed, 2),
            "capital_deployed_pct": round(capital_deployed / capital_configured * 100, 1) if capital_configured > 0 else 0,
            "daily_gross_pnl": round(total_gross, 2),
            "daily_charges": round(total_charges, 2),
            "daily_net_pnl": round(total_net, 2),
            "daily_return_pct": round(total_net / capital_configured * 100, 3) if capital_configured > 0 else 0,
            "charge_ratio_pct": round(total_charges / abs(total_gross) * 100, 1) if abs(total_gross) > 0 else "n/a",
            "trade_count": len(trades),
            "wins": wins,
            "losses": losses,
            "trades": trades,
        }

    except Exception as e:
        log.error(f"[{profile_name}] {type(e).__name__}: {e}")
        return None



def _extract_skip_reasons(profile_name, date):
    """Extract skip reasons from log file for a zero-trade day."""
    import re as _re
    log_dir = Path("logs")
    log_file = log_dir / f"intraday_{profile_name}_{date}.log"
    result = {"system_ran": False, "scans_attempted": 0, "vix": None,
              "market_direction": None, "strategies_skipped": [], "errors": [],
              "no_trade_reason_summary": "Unknown"}
    if not log_file.exists():
        result["no_trade_reason_summary"] = "No log file - system did not run"
        return result
    result["system_ran"] = True
    content = log_file.read_text()
    scan_lines = [l for l in content.split("\n") if "Scan:" in l and "candidates" in l]
    result["scans_attempted"] = len(scan_lines)
    vix_matches = _re.findall(r"VIX[:\s]+([\d.]+)", content)
    if vix_matches:
        result["vix"] = float(vix_matches[-1])
    dir_matches = _re.findall(r"market (?:direction |)(FLAT|BULLISH|BEARISH|SIDEWAYS|FLAT SIDEWAYS)", content)
    if dir_matches:
        result["market_direction"] = dir_matches[-1]
    skip_matches = _re.findall(r"(\w+(?:_\w+)*): Skipping", content)
    seen = set()
    for s in skip_matches:
        if s not in seen:
            seen.add(s)
            result["strategies_skipped"].append({"strategy": s, "reason": "skipped"})
    if result["scans_attempted"] == 0:
        result["no_trade_reason_summary"] = "Log exists but no scans completed"
    elif result["strategies_skipped"]:
        names = [s["strategy"] for s in result["strategies_skipped"]]
        result["no_trade_reason_summary"] = "Scanned " + str(result["scans_attempted"]) + "x, skipped: " + ", ".join(names)
    else:
        result["no_trade_reason_summary"] = "Scanned " + str(result["scans_attempted"]) + "x, no valid setups"
    return result

def _zero_day(profile_name, date, reason):
    """Generate a zero-trade day JSON with reason."""
    # Also try to get skip reasons from log
# _extract_skip_reasons inlined below
    skip_info = _extract_skip_reasons(profile_name, date)
    if skip_info.get("no_trade_reason_summary") == "Unknown":
        skip_info["no_trade_reason_summary"] = reason

    return {
        "profile": profile_name,
        "date": date,
        "generated_at": datetime.now(IST).isoformat(),
        "source": "dhan_orders_api",
        "capital_configured": CAPITAL.get(profile_name, 30000),
        "capital_deployed_peak": 0,
        "capital_deployed_pct": 0.0,
        "daily_gross_pnl": 0.0,
        "daily_charges": 0.0,
        "daily_net_pnl": 0.0,
        "daily_return_pct": 0.0,
        "charge_ratio_pct": "n/a",
        "trade_count": 0,
        "wins": 0,
        "losses": 0,
        "trades": [],
        "no_trade_reason": skip_info,
    }


def write_and_sync(profile_name, date, data):
    """Write JSON to both profile paths and sync to S3."""
    for p in [profile_name, "vishal-live"]:
        out_dir = Path(f"dashboard/api/v2/{p}/daily_pnl")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{date}.json"
        out_file.write_text(json.dumps(data, indent=2, default=str))
        log.info(f"Written: {out_file}")

    # Sync to S3
    os.environ.setdefault("AWS_PROFILE", "vishal-admin")
    try:
        subprocess.run(
            ["aws", "s3", "sync", "dashboard/api/v2/", f"s3://{S3_BUCKET}/api/v2/",
             "--exclude", "*.DS_Store", "--exclude", "._*"],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["aws", "cloudfront", "create-invalidation",
             "--distribution-id", CF_DIST, "--paths", "/api/v2/*",
             "--region", "us-east-1"],
            check=True, capture_output=True, text=True
        )
        log.info("S3 synced + CloudFront invalidated")
    except subprocess.CalledProcessError as e:
        log.error(f"S3/CF error: {e.stderr}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    today = args.date or datetime.now(IST).strftime("%Y-%m-%d")
    log.info(f"Computing daily P&L from Dhan API for {today}")

    for profile in LIVE_PROFILES:
        data = compute_from_dhan(profile, today)
        if data:
            sign = "+" if data["daily_net_pnl"] >= 0 else ""
            log.info(f"[{profile}] {sign}Rs.{data['daily_net_pnl']:.2f} "
                    f"({data['trade_count']} trades, {data['wins']}W/{data['losses']}L)")
            write_and_sync(profile, today, data)
        else:
            log.warning(f"[{profile}] Failed to compute — check auth/API")


if __name__ == "__main__":
    main()
