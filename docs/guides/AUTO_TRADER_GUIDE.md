# Auto Trader — Daily Guide

EC2 runs everything automatically. You just check results.

## What Happens Every Day (Weekdays Only)

| Time (IST) | Time (Denmark) | What EC2 Does |
|------------|---------------|---------------|
| 9:15 AM | 5:45 AM | Picks 1 intraday stock using Claude AI (dry run — no real money) |
| 3:45 PM | 12:15 PM | Checks if the pick was a WIN or LOSS |

## When You Wake Up — Check Morning Pick

```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
cat ~/wealth-builder-pro/output/trades/cron.log
```

You'll see something like:
```
DRY RUN: Would BUY 54x NHPC @ ₹92.50
Target: ₹95.00 | SL: ₹91.00
Cost: ₹4,995
```

Or if market looked bad:
```
SKIP: No high-confidence setup today
```

## After Lunch (Denmark) — Check EOD Result

Same command:
```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
cat ~/wealth-builder-pro/output/trades/cron.log
```

You'll see the result added:
```
🟢 WIN — Target ₹95 HIT! Profit: ₹135
```
or
```
🔴 LOSS — Stop loss hit. Loss: ₹81
```

## Check Full Scorecard (Anytime)

```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
cd ~/wealth-builder-pro
source venv/bin/activate
python3 -m llm.check_trade
```

Shows running stats:
```
Wins: 3 | Losses: 2 | Hit rate: 60%
Total P&L: ₹420
```

## Check a Specific Day

```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
cat ~/wealth-builder-pro/output/trades/trade_2026-03-20.json
```

## What the Grades Mean

| Grade | Meaning |
|-------|---------|
| 🟢 WIN | Target price was hit during the day |
| 🔴 LOSS | Stop loss was hit during the day |
| 🟡 OPEN WIN | Neither hit, but stock closed above entry |
| 🟠 OPEN LOSS | Neither hit, stock closed below entry |
| ⚪ MISSED | Entry price was never reached |
| ⏭️ SKIP | Claude said no good setup today |

## Important Notes

- This is DRY RUN only — no real money is being used
- EC2 must be running for cron to work (don't stop it)
- Groww API token expires daily at 6 AM IST — auto-trader re-authenticates each run
- Run for 2 weeks, check hit rate. If >50% with good R:R, then consider live mode
- Market is closed on weekends and Indian holidays — cron only runs Mon-Fri

## If Something Breaks

Check the cron log for errors:
```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
tail -50 ~/wealth-builder-pro/output/trades/cron.log
```

Check if cron is running:
```bash
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@3.108.156.101
sudo systemctl status crond
crontab -l
```
