# Wealth Builder Pro — Super Simple Guide

## What Is This?

An app that looks at your stock and mutual fund portfolio from Groww, uses AI (Claude) to tell you what to BUY, HOLD, SELL, or EXIT, and shows it all in a nice dashboard in your browser.

## Where Is Everything?

```
~/kiro/websites/w-builder/     ← This is your app folder
```

Open Terminal and type:
```bash
cd ~/kiro/websites/w-builder
```

You're now in the app folder. Everything runs from here.

## The 3 Things You Need To Know

### 1. See Your Dashboard (takes 5 seconds)

If your laptop restarted or the dashboard isn't showing:

```bash
cd ~/kiro/websites/w-builder/output/reports
python3 -m http.server 8877 &
```

Then open Chrome and go to: **http://localhost:8877/dashboard.html**

That's it. Your last analysis is still there.

### 2. Run Fresh Analysis (takes 5 minutes)

When you want fresh AI verdicts with latest market data:

```bash
cd ~/kiro/websites/w-builder
./go.sh
```

It will ask you to paste credentials. Here's how:

1. Go to Isengard in your browser
2. Copy the 3 export lines (they look like `export AWS_ACCESS_KEY_ID=...`)
3. Paste them ALL at once into Terminal
4. Press Enter on an empty line

The script does everything automatically:
- Picks your latest Groww files from Downloads
- Sends code + files to EC2 server in India
- Runs AI analysis on EC2
- Pulls results back to your Mac
- Opens the dashboard in Chrome

### 3. Update Your Portfolio

When you download new files from Groww app:

1. Download these from Groww → they go to ~/Downloads/:
   - Stocks Holdings Statement
   - Mutual Funds
   - Stocks P&L Report (optional)

2. Run `./go.sh` — it automatically finds the latest files in Downloads

That's literally it. The script handles everything.

## What The Dashboard Shows

| Tab | What It Means |
|-----|--------------|
| 📊 Stocks | All your stocks with BUY/HOLD/SELL/EXIT verdict from AI |
| 🏦 MF | All your mutual funds with CONTINUE/STOP/SWITCH SIP advice |
| 📈 Long-Term | New stocks AI recommends you buy for 1-3 years |
| ⚡ Intraday | Trading setups for tomorrow with exact prices |
| 🌐 Market | FII/DII flows, which sectors are hot, promoter signals |
| 🎯 Goal | How many years to reach ₹10 Crore with different scenarios |

## Color Codes

- 🟢 Green = BUY or CONTINUE SIP (good, keep going)
- 🟡 Yellow = HOLD (wait and watch)
- 🔴 Red = SELL or STOP SIP (get out)
- 🟣 Purple = EXIT (get out NOW)

## If Something Goes Wrong

| Problem | What To Do |
|---------|-----------|
| Dashboard is blank | Run: `cd ~/kiro/websites/w-builder/output/reports && python3 -m http.server 8877 &` then go to http://localhost:8877/dashboard.html |
| "localhost:8877 refused" | Same as above — the server isn't running, start it |
| Directory listing instead of dashboard | Go to http://localhost:8877/dashboard.html (not just localhost:8877) |
| "security token invalid" | Your AWS creds expired. Get fresh ones from Isengard, run `./go.sh` again |
| "Connection timed out" | EC2 server is stopped. Go to AWS Console → EC2 → Start the instance |
| "Could not parse credentials" | Make sure you paste ALL 3 export lines from Isengard, then press Enter on empty line |
| Laptop restarted | Just start the dashboard server again (see "Dashboard is blank" above). Your data is still there. |
| Kiro restarted | Your code is fine. Kiro only loses chat memory, not your files. Paste the recovery prompt from RECOVERY_PROMPT.md |

## Important Files (Don't Delete These!)

| File | What It Does |
|------|-------------|
| `go.sh` | The magic one-command script |
| `output/reports/dashboard.html` | Your dashboard |
| `output/reports/data.json` | Dashboard data (AI verdicts, portfolio) |
| `input/*.xlsx` | Your Groww export files |
| `~/Downloads/wealth-builder-pro.pem` | SSH key for EC2 server |

## How It Actually Works (Behind The Scenes)

```
Your Mac (Denmark)                    EC2 Server (Mumbai, India)
┌─────────────────────┐              ┌──────────────────────────┐
│ Your Groww XLSX      │──── go.sh ──→│ Reads your XLSX files    │
│ files from Downloads │   sends to   │ Fetches NSE/AMFI data    │
│                      │              │ Asks Claude AI to analyze │
│ Dashboard in Chrome  │←── go.sh ───│ Sends results back       │
│ localhost:8877       │   pulls back │                          │
└─────────────────────┘              └──────────────────────────┘
```

Why EC2 in India? Because Indian stock websites (NSE, AMFI, Screener) block access from Denmark. The EC2 server in Mumbai can reach them.

## Costs

- EC2 running 24/7: ~$30/month (stop it when not using to save money)
- Claude AI per analysis: ~₹5-10 per run
- Total if you run once daily: ~$35/month

## Quick Reference

```bash
# See dashboard
cd ~/kiro/websites/w-builder/output/reports && python3 -m http.server 8877 &
# Then open: http://localhost:8877/dashboard.html

# Run fresh analysis
cd ~/kiro/websites/w-builder && ./go.sh

# Run tests (check everything works)
cd ~/kiro/websites/w-builder && python3 -m pytest tests/ -q

# Test parsers only (no AWS needed)
cd ~/kiro/websites/w-builder && ./run_local.sh test
```
