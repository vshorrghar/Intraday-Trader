"""Sync top performers from DB to dashboard JSON for War Room tab."""
import sqlite3, json, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IST = timezone(timedelta(hours=5, minutes=30))

def main():
    db_path = "database/vishal.db"  # paper DB has most complete data
    if not os.path.exists(db_path):
        print("DB not found"); return

    today = datetime.now(IST).strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get today's top performers
    rows = conn.execute("SELECT * FROM daily_top_performers WHERE date=? ORDER BY rank", (today,)).fetchall()

    # Get our picks today from trades
    our_picks = []
    try:
        trades = conn.execute("SELECT tradingsymbol FROM intraday_trades WHERE trade_date=? AND action='BUY'", (today,)).fetchall()
        our_picks = [t["tradingsymbol"] for t in trades]
    except Exception:
        pass

    # Get last 7 days
    history = conn.execute("SELECT date, rank, symbol, gain_pct, was_picked_by_us FROM daily_top_performers WHERE rank<=10 ORDER BY date DESC, rank LIMIT 70").fetchall()
    conn.close()

    if not rows:
        print(f"No top performers for {today}"); return

    vix = rows[0]["vix_that_day"] if rows else 0
    mood = rows[0]["market_mood"] if rows else "UNKNOWN"

    top_10 = []
    for r in rows[:10]:
        top_10.append({
            "rank": r["rank"],
            "symbol": r["symbol"],
            "gain_pct": r["gain_pct"],
            "change_from_open": r["change_from_open"],
            "volume": r["volume"],
            "sector": r["sector"] or "",
            "we_picked": bool(r["was_picked_by_us"]),
        })

    overlap = sum(1 for t in top_10 if t["we_picked"])

    output = {
        "date": today,
        "vix": vix,
        "market_mood": mood,
        "top_10": top_10,
        "our_picks_today": our_picks,
        "overlap": overlap,
        "miss_rate": f"{10-overlap}/10 missed today",
        "history": [dict(r) for r in history],
    }

    os.makedirs("dashboard/api", exist_ok=True)
    with open("dashboard/api/top_performers.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"Written dashboard/api/top_performers.json — {len(top_10)} entries, overlap {overlap}/10")

if __name__ == "__main__":
    main()
