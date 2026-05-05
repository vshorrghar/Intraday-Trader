#!/usr/bin/env python3
"""Wealth Builder Pro — AI Auto Trader (Dry Run).

Uses Claude to pick 1 intraday setup, validates it, and either:
- DRY_RUN mode: logs what it WOULD do (default)
- LIVE mode: places real orders via Groww API

Run daily at 9:00 AM IST via cron on EC2.

Usage:
    python3 -m llm.auto_trader              # dry run (default)
    python3 -m llm.auto_trader --live       # real orders (careful!)
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

BUDGET = 5000  # Max ₹ per day
MAX_TRADES = 4  # Max trades per day
MAX_LOSS_PCT = 2.0  # Max stop loss % from entry
MIN_RR_RATIO = 2.0  # Minimum risk:reward ratio


@dataclass
class TradeSetup:
    action: str  # BUY or SKIP
    stock: str = ""
    nse_symbol: str = ""
    entry: float = 0
    target: float = 0
    stop_loss: float = 0
    quantity: int = 0
    rationale: str = ""
    reason: str = ""  # for SKIP


@dataclass
class TradeResult:
    date: str
    mode: str  # DRY_RUN or LIVE
    setup: dict
    validation: dict
    executed: bool
    order_id: str = ""
    error: str = ""


def get_market_data():
    """Gather market data for Claude's analysis."""
    data = {}

    # FII/DII
    try:
        from fetchers.nse_fii_dii import fetch_fii_dii
        os.makedirs('cache', exist_ok=True)
        fii = fetch_fii_dii('cache')
        data['fii_dii'] = {
            "date": fii.date, "fii_net": fii.fii_net, "dii_net": fii.dii_net,
        }
    except Exception as e:
        logger.warning("FII/DII fetch failed: %s", e)

    # Bulk deals
    try:
        from fetchers.nse_bulk_deals import fetch_bulk_deals
        deals = fetch_bulk_deals()
        data['bulk_deals'] = [
            {"stock": d.security_name, "client": d.client_name, "qty": d.quantity, "price": d.price}
            for d in deals[:10]
        ]
    except Exception as e:
        logger.warning("Bulk deals fetch failed: %s", e)

    # Market indices
    try:
        from fetchers.market_indices import fetch_indices
        indices = fetch_indices('cache')
        data['indices'] = [
            {"name": i.name, "value": i.last_price, "change_pct": i.change_percent}
            for i in indices
        ]
    except Exception as e:
        logger.warning("Indices fetch failed: %s", e)

    # Fallback: fetch indices directly if fetcher failed
    if not data.get('indices'):
        try:
            import requests as _req
            s = _req.Session()
            s.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            })
            r = s.get('https://www.nseindia.com/api/allIndices', timeout=15)
            if r.status_code == 200:
                nse_data = r.json()
                targets = {'NIFTY 50', 'NIFTY BANK', 'NIFTY MIDCAP 100'}
                data['indices'] = []
                for i in nse_data.get('data', []):
                    name = i.get('index', '')
                    if name in targets:
                        data['indices'].append({
                            "name": name,
                            "value": i.get('last', 0),
                            "change_pct": i.get('percentChange', 0),
                            "open": i.get('open', 0),
                            "high": i.get('high', 0),
                            "low": i.get('low', 0),
                        })
                # Also grab top gainers/losers for Claude
                top_movers = []
                for i in nse_data.get('data', [])[:50]:
                    pct = i.get('percentChange', 0)
                    if isinstance(pct, (int, float)) and abs(pct) > 1.5:
                        top_movers.append({
                            "name": i.get('index', ''),
                            "value": i.get('last', 0),
                            "change_pct": pct,
                        })
                if top_movers:
                    data['top_movers'] = sorted(top_movers, key=lambda x: abs(x['change_pct']), reverse=True)[:10]
                print(f"  ✅ Direct NSE indices: {len(data['indices'])} fetched")
        except Exception as e2:
            logger.warning("Direct indices fetch also failed: %s", e2)

    # Groww live data for top stocks (if available)
    try:
        from fetchers.groww_api import GrowwClient
        client = GrowwClient()
        client.authenticate()
        watchlist = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                     "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
                     "TATAMOTORS", "NHPC", "IRFC", "RVNL", "SUZLON"]
        quotes = []
        for sym in watchlist:
            try:
                q = client.get_quote("NSE", "CASH", sym)
                quotes.append({
                    "symbol": sym, "ltp": q.ltp,
                    "open": q.open, "high": q.high, "low": q.low, "close": q.close,
                    "volume": q.volume,
                })
            except Exception:
                pass
        data['live_quotes'] = quotes
    except Exception as e:
        logger.warning("Groww quotes failed: %s", e)

    # Fallback: fetch stock quotes from NSE if Groww failed
    if not data.get('live_quotes'):
        try:
            import requests as _req
            s = _req.Session()
            s.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            })
            watchlist = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
                         "SBIN", "BHARTIARTL", "ITC", "NHPC", "IRFC", "RVNL", "SUZLON",
                         "TATAMOTORS", "COALINDIA", "NTPC"]
            quotes = []
            for sym in watchlist:
                try:
                    r = s.get(f'https://www.nseindia.com/api/quote-equity?symbol={sym}', timeout=10)
                    if r.status_code == 200:
                        d = r.json()
                        pi = d.get('priceInfo', {})
                        quotes.append({
                            "symbol": sym,
                            "ltp": pi.get('lastPrice', 0),
                            "open": pi.get('open', 0),
                            "high": pi.get('intraDayHighLow', {}).get('max', 0),
                            "low": pi.get('intraDayHighLow', {}).get('min', 0),
                            "close": pi.get('previousClose', 0),
                            "change_pct": pi.get('pChange', 0),
                        })
                except Exception:
                    pass
            if quotes:
                data['live_quotes'] = quotes
                print(f"  ✅ Direct NSE quotes: {len(quotes)} stocks fetched")
        except Exception as e2:
            logger.warning("Direct NSE quotes also failed: %s", e2)

    return data


def ask_claude_for_pick(market_data: dict) -> TradeSetup:
    """Send market data to Claude and get 1 intraday pick."""
    from llm.bedrock_client import BedrockClient

    region = os.environ.get("BEDROCK_REGION", "us-east-1")
    model = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
    client = BedrockClient(region=region, model_id=model)

    today = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")

    system_prompt = f"""You are an intraday trading bot for Indian markets. Budget: ₹{BUDGET} total across all picks.

RULES:
- Pick EXACTLY 4 stocks for intraday LONG trades, or fewer if market looks bad
- Each stock price must be under ₹500 (so we can buy multiple shares)
- Entry must be a LIMIT order price (not market order)
- Stop loss must be within {MAX_LOSS_PCT}% of entry
- Target must give at least {MIN_RR_RATIO}:1 reward:risk ratio
- Total cost of ALL picks combined must be under ₹{BUDGET}
- Only pick HIGH or MEDIUM confidence setups
- Use ONLY real NSE-listed stocks
- If market conditions are terrible, return fewer picks or empty list

Respond with EXACTLY this JSON:
{{
  "picks": [
    {{
      "stock": "Company Name",
      "nse_symbol": "SYMBOL",
      "entry": 0.00,
      "target": 0.00,
      "stop_loss": 0.00,
      "quantity": 0,
      "confidence": "HIGH or MEDIUM",
      "rationale": "Why this setup works"
    }}
  ],
  "market_mood": "1 line on overall market sentiment",
  "skip_reason": "Only if returning 0 picks"
}}

Total cost across all picks (sum of entry × quantity) must be under ₹{BUDGET}."""

    user_prompt = f"""Date: {today}

MARKET DATA:
{json.dumps(market_data, indent=2)}

Pick up to 4 intraday setups within ₹{BUDGET} total budget."""

    response = client.invoke(system_prompt, user_prompt)
    if not response:
        return [TradeSetup(action="SKIP", reason="Claude returned empty response")]

    picks_data = response.get("picks", [])
    market_mood = response.get("market_mood", "")
    skip_reason = response.get("skip_reason", "")

    if not picks_data:
        return [TradeSetup(action="SKIP", reason=skip_reason or "No picks from Claude")]

    setups = []
    for p in picks_data[:MAX_TRADES]:
        setups.append(TradeSetup(
            action="BUY",
            stock=p.get("stock", ""),
            nse_symbol=p.get("nse_symbol", ""),
            entry=p.get("entry", 0),
            target=p.get("target", 0),
            stop_loss=p.get("stop_loss", 0),
            quantity=p.get("quantity", 0),
            rationale=f"[{p.get('confidence', '')}] {p.get('rationale', '')}",
        ))

    if market_mood:
        print(f"  📊 Market mood: {market_mood}")

    return setups


def validate_setup(setup: TradeSetup) -> dict:
    """Validate the trade setup against safety rules."""
    errors = []

    if setup.action == "SKIP":
        return {"valid": True, "skip": True, "reason": setup.reason}

    if not setup.nse_symbol:
        errors.append("No NSE symbol")
    if setup.entry <= 0:
        errors.append("Invalid entry price")
    if setup.target <= setup.entry:
        errors.append(f"Target {setup.target} must be above entry {setup.entry}")
    if setup.stop_loss <= 0 or setup.stop_loss >= setup.entry:
        errors.append(f"Stop loss {setup.stop_loss} must be below entry {setup.entry}")
    if setup.quantity <= 0:
        errors.append("Invalid quantity")

    # Budget check
    total_cost = setup.entry * setup.quantity
    if total_cost > BUDGET:
        errors.append(f"Cost ₹{total_cost:.0f} exceeds budget ₹{BUDGET}")

    # Stop loss % check
    if setup.entry > 0:
        sl_pct = (setup.entry - setup.stop_loss) / setup.entry * 100
        if sl_pct > MAX_LOSS_PCT:
            errors.append(f"Stop loss {sl_pct:.1f}% exceeds max {MAX_LOSS_PCT}%")

    # Risk:reward check
    if setup.entry > 0 and setup.stop_loss > 0:
        risk = setup.entry - setup.stop_loss
        reward = setup.target - setup.entry
        if risk > 0:
            rr = reward / risk
            if rr < MIN_RR_RATIO:
                errors.append(f"R:R {rr:.1f} below minimum {MIN_RR_RATIO}")

    return {"valid": len(errors) == 0, "skip": False, "errors": errors}


def execute_trade(setup: TradeSetup, live: bool = False) -> TradeResult:
    """Execute or dry-run the trade."""
    now = datetime.now(IST)
    mode = "LIVE" if live else "DRY_RUN"
    validation = validate_setup(setup)

    result = TradeResult(
        date=now.strftime("%Y-%m-%d %H:%M IST"),
        mode=mode,
        setup=asdict(setup),
        validation=validation,
        executed=False,
    )

    if validation.get("skip"):
        print(f"  ⏭️  SKIP: {setup.reason}")
        return result

    if not validation["valid"]:
        print(f"  ❌ Validation failed: {validation['errors']}")
        result.error = str(validation["errors"])
        return result

    if not live:
        print(f"  📝 DRY RUN: Would BUY {setup.quantity}x {setup.nse_symbol} @ ₹{setup.entry}")
        print(f"     Target: ₹{setup.target} | SL: ₹{setup.stop_loss}")
        print(f"     Cost: ₹{setup.entry * setup.quantity:.0f}")
        print(f"     Rationale: {setup.rationale}")
        result.executed = True
        return result

    # LIVE mode
    try:
        from fetchers.groww_api import GrowwClient
        client = GrowwClient()
        client.authenticate()

        order = client.place_order(
            trading_symbol=setup.nse_symbol,
            exchange="NSE",
            segment="CASH",
            transaction_type="BUY",
            order_type="LIMIT",
            product="INTRADAY",
            quantity=setup.quantity,
            price=setup.entry,
        )
        result.order_id = order.get("order_id", "")
        result.executed = True
        print(f"  ✅ LIVE ORDER: BUY {setup.quantity}x {setup.nse_symbol} @ ₹{setup.entry}")
        print(f"     Order ID: {result.order_id}")

        # Place stop loss order
        sl_order = client.place_order(
            trading_symbol=setup.nse_symbol,
            exchange="NSE",
            segment="CASH",
            transaction_type="SELL",
            order_type="SL",
            product="INTRADAY",
            quantity=setup.quantity,
            price=setup.stop_loss,
            trigger_price=setup.stop_loss,
        )
        print(f"     SL Order ID: {sl_order.get('order_id', '')}")

    except Exception as e:
        result.error = str(e)
        print(f"  ❌ Order failed: {e}")

    return result


def save_result(result: TradeResult):
    """Save trade result to log file."""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "trades")
    os.makedirs(log_dir, exist_ok=True)

    date_str = datetime.now(IST).strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"trade_{date_str}.json")

    # Append to daily log
    trades = []
    if os.path.exists(log_file):
        with open(log_file) as f:
            trades = json.load(f)

    trades.append(asdict(result))

    with open(log_file, "w") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)

    print(f"  💾 Logged to {log_file}")


def send_notification_multi(results: list):
    """Send single email with all picks."""
    try:
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml")
        if not os.path.exists(config_path):
            print("  ⚠️ No config.yaml — skipping email")
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        aws = config.get("aws", {})
        sender = aws.get("ses_sender", "")
        recipient = aws.get("ses_recipient", "")
        region = aws.get("region", "ap-south-1")

        if not sender or not recipient:
            print("  ⚠️ No SES email configured — skipping")
            return

        now = datetime.now(IST).strftime("%d-%b-%Y %H:%M IST")
        picks = [(s, r) for s, r in results if s.action == "BUY"]
        skips = [(s, r) for s, r in results if s.action == "SKIP"]

        if not picks:
            subject = f"🤖 Auto Trader — NO PICKS ({now})"
            body = f"<h2>No trades today</h2><p>{skips[0][0].reason if skips else 'No data'}</p>"
        else:
            subject = f"🤖 Auto Trader — {len(picks)} PICKS ({now})"
            rows = ""
            total_cost = 0
            for s, r in picks:
                cost = s.entry * s.quantity
                total_cost += cost
                rows += f"""<tr>
                    <td style="padding:8px;border-bottom:1px solid #eee"><b>{s.stock}</b><br><span style="color:gray;font-size:12px">{s.nse_symbol}</span></td>
                    <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">₹{s.entry}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;color:green">₹{s.target}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;color:red">₹{s.stop_loss}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">{s.quantity}</td>
                    <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">₹{cost:.0f}</td>
                </tr>
                <tr><td colspan="6" style="padding:4px 8px;font-size:11px;color:#555;border-bottom:2px solid #ddd">{s.rationale}</td></tr>"""

            body = f"""<h2>🤖 {len(picks)} Intraday Picks — {now}</h2>
            <table style="width:100%;border-collapse:collapse;font-size:14px">
            <tr style="background:#f5f5f5">
                <th style="padding:8px;text-align:left">Stock</th>
                <th style="padding:8px;text-align:right">Entry</th>
                <th style="padding:8px;text-align:right">Target</th>
                <th style="padding:8px;text-align:right">SL</th>
                <th style="padding:8px;text-align:right">Qty</th>
                <th style="padding:8px;text-align:right">Cost</th>
            </tr>
            {rows}
            <tr style="background:#f0f0f0;font-weight:bold">
                <td colspan="5" style="padding:8px">Total</td>
                <td style="padding:8px;text-align:right">₹{total_cost:.0f}</td>
            </tr>
            </table>
            <p style="color:gray;font-size:12px;margin-top:16px">⚠️ DRY RUN — no real orders placed. Budget: ₹{BUDGET}</p>"""

        from reports.ses_sender import send_email
        sent = send_email(body, subject, sender, recipient, region)
        if sent:
            print(f"  📧 Email sent to {recipient}")
        else:
            print(f"  ⚠️ Email failed")
    except Exception as e:
        print(f"  ⚠️ Email error: {e}")


def main():
    live = "--live" in sys.argv

    print("")
    print("=" * 50)
    print(f"🤖 Auto Trader — {'LIVE' if live else 'DRY RUN'}")
    print(f"   Budget: ₹{BUDGET} | Max trades: {MAX_TRADES}")
    print(f"   Time: {datetime.now(IST).strftime('%d-%b-%Y %H:%M IST')}")
    print("=" * 50)

    if live:
        print("  ⚠️  LIVE MODE — Real orders will be placed!")
        print("")

    # Step 1: Gather market data
    print("\n📡 Gathering market data...")
    market_data = get_market_data()
    print(f"  Data keys: {list(market_data.keys())}")

    # Step 2: Ask Claude for picks
    print("\n🤖 Asking Claude for intraday picks...")
    setups = ask_claude_for_pick(market_data)
    print(f"  Claude returned {len(setups)} pick(s)")

    # Step 3: Validate and execute each pick
    all_results = []
    for i, setup in enumerate(setups):
        print(f"\n{'💰' if live else '📝'} Pick #{i+1}: {setup.nse_symbol or 'SKIP'}...")
        result = execute_trade(setup, live=live)
        save_result(result)
        all_results.append((setup, result))

    # Step 4: Send single email with all picks
    send_notification_multi(all_results)

    print("\n" + "=" * 50)
    print("✅ Done")
    print("=" * 50)


if __name__ == "__main__":
    main()
