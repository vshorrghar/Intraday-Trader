#!/usr/bin/env python3
"""Check how today's dry-run pick performed at end of day.

Reads the trade log, fetches closing price via Groww API,
and grades the pick: WIN / LOSS / MISSED / SKIP.

Usage (on EC2, after 3:30 PM IST):
    python3 -m llm.check_trade
    python3 -m llm.check_trade 2026-03-20   # check specific date
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def check_trade(date_str: str = None):
    if not date_str:
        date_str = datetime.now(IST).strftime("%Y-%m-%d")

    log_file = f"output/trades/trade_{date_str}.json"
    if not os.path.exists(log_file):
        print(f"❌ No trade log for {date_str}")
        return

    with open(log_file) as f:
        trades = json.load(f)

    print(f"\n{'='*50}")
    print(f"📊 Trade Review — {date_str}")
    print(f"{'='*50}\n")

    for i, trade in enumerate(trades):
        setup = trade.get("setup", {})
        action = setup.get("action", "SKIP")

        if action == "SKIP":
            print(f"  ⏭️  Pick #{i+1}: SKIPPED — {setup.get('reason', 'no reason')}")
            continue

        symbol = setup.get("nse_symbol", "")
        entry = setup.get("entry", 0)
        target = setup.get("target", 0)
        stop_loss = setup.get("stop_loss", 0)
        qty = setup.get("quantity", 0)

        print(f"  📝 Pick #{i+1}: {setup.get('stock', '')} ({symbol})")
        print(f"     Entry: ₹{entry} | Target: ₹{target} | SL: ₹{stop_loss} | Qty: {qty}")
        print(f"     Rationale: {setup.get('rationale', '')}")

        # Fetch closing price
        closing = 0
        high = 0
        low = 0
        try:
            from fetchers.groww_api import GrowwClient
            client = GrowwClient()
            client.authenticate()
            quote = client.get_quote("NSE", "CASH", symbol)
            closing = quote.ltp
            high = quote.high
            low = quote.low
            print(f"\n     📈 Actual: Close ₹{closing} | High ₹{high} | Low ₹{low}")
        except Exception as e:
            # Fallback: fetch from NSE directly
            try:
                import requests as _req
                s = _req.Session()
                s.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json',
                })
                r = s.get(f'https://www.nseindia.com/api/quote-equity?symbol={symbol}', timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    pi = d.get('priceInfo', {})
                    closing = pi.get('lastPrice', 0)
                    high = pi.get('intraDayHighLow', {}).get('max', 0)
                    low = pi.get('intraDayHighLow', {}).get('min', 0)
                    print(f"\n     📈 Actual (NSE): Close ₹{closing} | High ₹{high} | Low ₹{low}")
                else:
                    print(f"\n     ⚠️  NSE also failed ({r.status_code})")
                    print(f"     Check manually: https://www.google.com/finance/quote/{symbol}:NSE")
                    continue
            except Exception as e2:
                print(f"\n     ⚠️  Could not fetch price: {e2}")
                print(f"     Check manually: https://www.google.com/finance/quote/{symbol}:NSE")
                continue

        # Grade the pick
        if high == 0 and low == 0:
            print(f"     ❓ No price data — market might be closed")
            continue

        # Did entry price get hit during the day?
        entry_hit = low <= entry <= high

        if not entry_hit:
            if entry > high:
                print(f"     ⚪ MISSED — Entry ₹{entry} never reached (day high was ₹{high})")
            else:
                print(f"     ⚪ MISSED — Entry ₹{entry} was below day low ₹{low}")
            grade = "MISSED"
        elif high >= target:
            pnl = (target - entry) * qty
            print(f"     🟢 WIN — Target ₹{target} HIT! Profit: ₹{pnl:.0f}")
            grade = "WIN"
        elif low <= stop_loss:
            pnl = (stop_loss - entry) * qty
            print(f"     🔴 LOSS — Stop loss ₹{stop_loss} HIT. Loss: ₹{abs(pnl):.0f}")
            grade = "LOSS"
        else:
            # Neither target nor SL hit — check closing vs entry
            pnl = (closing - entry) * qty
            if closing > entry:
                print(f"     🟡 OPEN WIN — Close ₹{closing} > Entry ₹{entry}. Paper profit: ₹{pnl:.0f}")
                grade = "OPEN_WIN"
            else:
                print(f"     🟠 OPEN LOSS — Close ₹{closing} < Entry ₹{entry}. Paper loss: ₹{abs(pnl):.0f}")
                grade = "OPEN_LOSS"

        # Update trade log with result
        trade["result"] = {
            "closing_price": closing,
            "day_high": high,
            "day_low": low,
            "grade": grade,
            "pnl": round((closing - entry) * qty, 2) if entry_hit else 0,
            "checked_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        }

    # Save updated log
    with open(log_file, "w") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)

    # Send EOD email summary
    send_eod_email(date_str, trades)

    # Show running scorecard
    print(f"\n{'='*50}")
    print(f"📋 Running Scorecard")
    print(f"{'='*50}")
    show_scorecard()


def send_eod_email(date_str: str, trades: list):
    """Send EOD summary email with win/loss results."""
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml")
        if not os.path.exists(config_path):
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        aws = config.get("aws", {})
        sender = aws.get("ses_sender", "")
        recipient = aws.get("ses_recipient", "")
        region = aws.get("region", "ap-south-1")

        if not sender or not recipient:
            return

        # Build summary
        wins = losses = skips = missed = 0
        total_pnl = 0
        rows = ""

        for t in trades:
            setup = t.get("setup", {})
            result = t.get("result", {})
            grade = result.get("grade", "")

            if setup.get("action") == "SKIP":
                skips += 1
                continue

            symbol = setup.get("nse_symbol", "?")
            entry = setup.get("entry", 0)
            closing = result.get("closing_price", 0)
            pnl = result.get("pnl", 0)
            total_pnl += pnl

            if grade == "WIN":
                wins += 1
                icon = "🟢"
                color = "green"
            elif grade == "LOSS":
                losses += 1
                icon = "🔴"
                color = "red"
            elif grade == "MISSED":
                missed += 1
                icon = "⚪"
                color = "gray"
            elif grade == "OPEN_WIN":
                wins += 1
                icon = "🟡"
                color = "green"
            elif grade == "OPEN_LOSS":
                losses += 1
                icon = "🟠"
                color = "orange"
            else:
                icon = "❓"
                color = "gray"

            rows += f"""<tr>
                <td style="padding:8px;border-bottom:1px solid #eee">{icon} <b>{setup.get('stock', symbol)}</b></td>
                <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">₹{entry}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">₹{closing}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;color:{color};font-weight:bold">{grade}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;color:{color}">₹{pnl:+.0f}</td>
            </tr>"""

        total = wins + losses
        hit_rate = (wins / total * 100) if total > 0 else 0
        pnl_color = "green" if total_pnl >= 0 else "red"

        subject = f"📊 EOD Results — {'₹' + str(int(total_pnl))} | {wins}W {losses}L ({date_str})"

        body = f"""<h2>📊 EOD Trade Results — {date_str}</h2>
        <div style="background:#f5f5f5;padding:12px;border-radius:8px;margin-bottom:16px;font-size:18px;text-align:center">
            <span style="color:{pnl_color};font-weight:bold;font-size:24px">₹{total_pnl:+,.0f}</span><br>
            <span style="font-size:14px">Wins: {wins} | Losses: {losses} | Missed: {missed} | Skipped: {skips}</span><br>
            <span style="font-size:14px">Hit Rate: {hit_rate:.0f}%</span>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="background:#f5f5f5">
            <th style="padding:8px;text-align:left">Stock</th>
            <th style="padding:8px;text-align:right">Entry</th>
            <th style="padding:8px;text-align:right">Close</th>
            <th style="padding:8px;text-align:right">Result</th>
            <th style="padding:8px;text-align:right">P&L</th>
        </tr>
        {rows}
        </table>
        <p style="color:gray;font-size:12px;margin-top:16px">⚠️ DRY RUN — no real money involved</p>"""

        from reports.ses_sender import send_email
        sent = send_email(body, subject, sender, recipient, region)
        if sent:
            print(f"  📧 EOD email sent to {recipient}")
        else:
            print(f"  ⚠️ EOD email failed")
    except Exception as e:
        print(f"  ⚠️ EOD email error: {e}")


def show_scorecard():
    """Show win/loss stats across all trade logs."""
    trades_dir = "output/trades"
    if not os.path.exists(trades_dir):
        print("  No trades yet")
        return

    wins = losses = misses = skips = total_pnl = 0

    for f in sorted(os.listdir(trades_dir)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(trades_dir, f)) as fh:
            trades = json.load(fh)
        for t in trades:
            setup = t.get("setup", {})
            result = t.get("result", {})
            if setup.get("action") == "SKIP":
                skips += 1
            elif result.get("grade") == "WIN":
                wins += 1
                total_pnl += result.get("pnl", 0)
            elif result.get("grade") == "LOSS":
                losses += 1
                total_pnl += result.get("pnl", 0)
            elif result.get("grade") == "MISSED":
                misses += 1
            elif result.get("grade") in ("OPEN_WIN", "OPEN_LOSS"):
                total_pnl += result.get("pnl", 0)

    total = wins + losses
    hit_rate = (wins / total * 100) if total > 0 else 0

    print(f"  Wins: {wins} | Losses: {losses} | Missed: {misses} | Skipped: {skips}")
    print(f"  Hit rate: {hit_rate:.0f}% ({wins}/{total})")
    print(f"  Total P&L: ₹{total_pnl:,.0f}")
    print()


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else None
    check_trade(date)
