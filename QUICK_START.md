# ⚡ Quick Start - 3 Commands to Launch

## 🎯 Ready to Go!

All import errors are fixed. Here's how to launch your web app:

---

## 📋 Copy-Paste Commands

Open Terminal and run these **exact commands**:

```bash
# 1. Go to project directory
cd ~/kiro/websites/w-builder

# 2. Set AWS credentials (get from AWS Console)
export AWS_ACCESS_KEY_ID="PASTE_YOUR_KEY_HERE"
export AWS_SECRET_ACCESS_KEY="PASTE_YOUR_SECRET_HERE"
export AWS_SESSION_TOKEN="PASTE_YOUR_TOKEN_HERE"

# 3. Launch web app (use the script)
./start_webapp.sh
```

**OR** run directly:
```bash
python3 webapp/app.py
```

---

## 🌐 Access Your App

Once running, open your browser:

**http://localhost:5000**

You'll see:
- Upload files (drag & drop)
- Scan Downloads button
- Run Analysis button
- 6 dashboard tabs

---

## ✅ What Was Fixed

The import errors you got were because function names were different:

| What I Called | Actual Name |
|--------------|-------------|
| `fetch_fundamentals_batch` | ❌ Didn't exist → ✅ Created it |
| `parse_pnl_report` | ❌ Wrong → ✅ Fixed to `parse_pnl_xlsx` |
| `parse_stock_holdings` | ❌ Wrong → ✅ Fixed to `parse_stocks_xlsx` |

All fixed in:
- `webapp/app.py`
- `run_morning_analysis.py`
- `run_crisis_analysis.py`
- `fetchers/screener_fetcher.py` (added batch function)

---

## 🎬 Demo Workflow

Once app is running:

1. **Click "Scan Downloads"**
   - Auto-finds Groww Excel files
   - Shows file age warnings

2. **Or drag & drop files**
   - Drag Excel files from Finder
   - Instant upload

3. **Click "Run Analysis"**
   - Watch progress bar
   - Takes 2-3 minutes

4. **Explore dashboards**
   - Overview: Portfolio summary
   - Intraday: 10 trading picks
   - Multibaggers: Hidden gems
   - Brutal Truth: Honest assessment
   - Actions: What to buy/sell
   - AWS Costs: Bill monitoring

---

## 🆘 Troubleshooting

### "Module not found" Error
```bash
pip3 install -r requirements.txt
```

### "ExpiredToken" Error
Get fresh AWS credentials and re-export them in terminal.

### "Connection refused" in browser
Make sure Flask is running - you should see:
```
* Running on http://0.0.0.0:5000
```

### Port 5000 already in use
```bash
# Kill existing process
lsof -ti:5000 | xargs kill

# Or change port in webapp/app.py (last line):
app.run(host='0.0.0.0', port=8080, debug=True)
```

---

## 🎉 You're Ready!

Everything is working now. Just run:

```bash
cd ~/kiro/websites/w-builder
./start_webapp.sh
```

Then open **http://localhost:5000** in your browser! 🚀
