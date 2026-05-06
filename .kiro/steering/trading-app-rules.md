
## Changes Made on May 6 2026 — DO NOT REVERT

### Config Changes (already optimized — do not change without asking)
- entry_delay_minutes: 15 (was 5) — enters at 9:30 AM IST
- min_confidence_score: 7 base, 8 for vishal-live (was 5/4)
- vix_threshold: 18 intraday, 22 fno, 16 vishal-live (was 30/35)

### Profile Settings (already correct — do not change)
vishal-live (REAL MONEY):
  - daily_capital_limit: 10000
  - per_trade_max_capital: 4000
  - max_trades_per_day: 2
  - daily_loss_limit: 600
  - min_confidence_score: 8
  - vix_threshold: 16

vishal paper:
  - daily_capital_limit: 300000
  - per_trade_max_capital: 60000
  - max_trades_per_day: 5
  - daily_loss_limit: 9000
  - min_confidence_score: 7
  - vix_threshold: 18

neha paper (mirrors vishal paper):
  - daily_capital_limit: 300000
  - per_trade_max_capital: 60000
  - max_trades_per_day: 5
  - daily_loss_limit: 9000
  - min_confidence_score: 7
  - vix_threshold: 18

### Code Fixes (already done — do not touch)
- intraday/dhan_broker.py: validity: "DAY" added to order payload
- run_daily.sh: LIVE_FLAG variable added, passes --live to Python
- These fixes are verified working — do not modify

### Pending Work (do these in order, one at a time)
1. Update intraday prompt in intraday/selector.py
2. Update FnO prompt in fno/strategy_engine.py
3. Add --local flag to scripts/sanity_check.sh
4. Add Telegram alerts
5. Fix SL order placement (move to monitor after BUY confirmed)

### Rules for Kiro
- Do not change any config values without explicit instruction
- Do not touch dhan_broker.py without explicit instruction
- Do not touch run_daily.sh without explicit instruction
- Always check current value before suggesting a change
- Always ask "are you sure?" before changing vishal-live config
