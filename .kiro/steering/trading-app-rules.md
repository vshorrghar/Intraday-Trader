
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

## CRITICAL: Folder Paths — Never Confuse These

### Mac (Kiro environment):
~/kiro/websites/intraday-trader    ← THIS is the project on Mac
NOT ~/dev-sandbox — that folder does NOT exist on Mac

### EC2:
~/dev-sandbox    ← THIS is the project on EC2

### Every command Kiro writes must use correct path:
- If command runs on Mac:   ~/kiro/websites/intraday-trader
- If command runs on EC2:   ~/dev-sandbox

### Sync command (run from Mac):
cd ~/kiro/websites/intraday-trader && bash scripts/sync_to_ec2.sh

### Git pull (run from Mac):
cd ~/kiro/websites/intraday-trader && git pull origin main


## Rule: Where To Edit Different File Types

### Edit on EC2, push from EC2, pull to Mac:
- config/*.yaml
- config/profiles/*.yaml  
- LLM prompts (string changes inside .py files)
- Any small text/string change in .py files

### Edit on Mac (Kiro), sync to EC2, push from EC2:
- New Python functions or classes
- New files
- Structural code changes
- HTML/CSS/JS files

### Never:
- Use sed on .py files
- Push from Mac (Code Defender blocks it)
- Edit config/profiles/*.yaml on Mac (credentials)

