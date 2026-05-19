# Dashboard Redesign v2 + Telegram Bot — Kiro Brief

## NORTH STAR
Swing-first design with live Dhan P&L on every screen — never display calculated, assumed, or DB-derived numbers for real money. If Dhan API fails, show "data unavailable" instead of stale numbers.

## WHAT EXISTS ALREADY
- scripts/sync_dhan_live.py — pulls /v2/positions, /v2/orders, /v2/fundlimit every 5 min
- dashboard/api/vishal-live/dhan_live.json — real Dhan data (tested, working)
- danish-eq reference at /home/ec2-user/danish-eq/ on EC2-NEW (13.202.63.223)
  - Vanilla HTML/CSS/JS, dark theme, tab navigation, JSON data layer
  - Telegram bot: simple requests.post, config from YAML

## KEY DIFFERENCES FROM DANISH-EQ
- danish-eq = swing only, single profile, DKK, US/EU markets
- intraday-trader = 3 strategies (intraday + swing + F&O), 4 profiles, INR, NSE India
- Real money (LIVE) + paper profiles with visual distinction
- Dhan API as sole P&L source for live profiles

## DESIGN SYSTEM (borrow from danish-eq)
- Background: #0f1117, Card: #1e2130, Border: #2a2d3a
- Accent: #6366f1, Green: #10b981, Red: #ef4444, Yellow: #f59e0b
- Font: system-ui, monospace for numbers
- Vanilla HTML/CSS/JS (no framework)

## TAB STRUCTURE (10 tabs)
1. Dashboard (landing — 6 stat tiles from Dhan, today's picks, mini scanner)
2. Intraday Signals (today's picks with confidence/entry/target/SL cards)
3. Swing Signals (PRIMARY — multi-day hold, trail SL visualization)
4. Portfolio (open positions from Dhan, color-coded status)
5. Scanner (Nifty 500 heatmap + table)
6. Risk Dashboard (daily loss cap, VIX, position concentration)
7. History (30-day trades, CSV export)
8. Universe (4-tier Indian market: Nifty50/Next50/500/FNO)
9. F&O (paper strategies, MTM from option chain)
10. War Room (top 20 movers, scanner accuracy, AI commentary)

## PROFILE SWITCHER
- Top-bar dropdown: All Profiles / vishal-live 🔴 / vishal 📝 / neha-live ⏸ / neha 📝
- Real money cards: red left border + 🔴 LIVE badge
- Paper cards: yellow left border + 📝 PAPER badge

## DATA SOURCES
- Live profiles: Dhan API via dhan_live.json (every 5 min auto, manual refresh button)
- Paper profiles: SQLite DB
- Manual refresh: click ⟳ → instant Dhan fetch (30s cooldown)
- Stale threshold: >10 min = warning badge, >30 min = "unavailable"

## TELEGRAM BOT
- Single bot, 6 notification streams:
  1. Intraday picks (9:35 AM)
  2. Swing signals (4 PM)
  3. Real-time trade alerts
  4. P&L alerts on close
  5. Daily summary (3:30 PM)
  6. Critical alerts (loss limit hit)
- python-telegram-bot or simple requests.post
- Config: config/telegram.yaml (gitignored)
- Slash commands: /status, /today, /picks, /swing, /risk, /stop, /help

## PHASES
- Phase 1 (Week 1): Design system CSS + Universe + Risk + Profile switcher + Header
- Phase 2 (Week 2): Dhan sync wiring + Dashboard + Portfolio + Intraday Signals
- Phase 3 (Week 3): Swing + Scanner + F&O + History
- Phase 4 (Week 4): War Room + Telegram bot + Mobile + Performance

## CRITICAL RULES
- Rule 1: commits from EC2-OLD only
- Rule 16: real money — Dhan API only, never DB-derived P&L
- Rule 11: heredoc for .py edits
- Old dashboard preserved at dashboard/old/ for fallback
- Each phase = one commit, push, S3 sync, CloudFront invalidation

## ANTI-PATTERNS
- No Bootstrap
- No full-page refresh (component-level only)
- No DB-derived P&L for live profiles
- No new dependencies without approval
- No pushing from Mac
