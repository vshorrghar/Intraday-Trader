
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


## Changes Made May 9 2026 — DO NOT REVERT

### Fixes Applied
- intraday/monitor.py: target hit now places SELL MARKET order at broker
- intraday/monitor.py: force exit now places SELL MARKET order at broker
- fno/monitor.py: _execute_exit now places reverse leg orders at broker
- fno/monitor.py: Symbol_Builder imported for leg tradingsymbol reconstruction
- Commit: 5f9e6c2

## Rules For AI Assistants (Claude + Kiro)

### The Goal
- This is a real money making business
- Target: ₹50K-1L/month by month 3, ₹3L/month by month 6
- Every fix must serve the trading goal — safe capital + consistent profit
- Think like a business partner, not just a code fixer
- Flag anything that could lose real money immediately

### Every Command Must State Where To Run
- Always prefix: # [EC2] or # [MAC]
- No exceptions — if you forget, Vishal will call it out

### Before Touching Any File
1. Read the actual error from logs first
2. Show what you found
3. State what you are about to change and why
4. Wait for approval before changing anything

### Fixing Files
- Never use sed on .py files
- Use python3 patch script for .py changes on EC2
- One fix at a time
- Verify import after every .py change

### Definition Of Done
- Done = command output proving it works
- Never say "it should work"
- Never say done without proof output

### If Fix Fails
- Stop after second failure
- Do not chain more attempts
- Rethink and explain before trying again

### Git Flow
- Fix on EC2
- git add + commit + push from EC2
- git pull on Mac after push confirmed
- Mac has Code Defender — never push from Mac

### One Problem At A Time
- Fix what was asked
- Report other bugs found
- Do not fix unreported bugs without asking

### Real Money Rules
- vishal-live is real money — any change needs explicit approval
- Paper accounts: vishal + neha — can run freely
- Scale capital only after 60% win rate proven on paper
- When in doubt, protect capital first
