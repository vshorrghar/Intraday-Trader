# 🌐 Wealth Manager Pro - Web Application Launch Guide

## 🎯 What You Have Now

A **professional-grade wealth management web application** with:

### Features Built:
- ✅ Modern UI with Tailwind CSS
- ✅ Drag & drop Excel file upload
- ✅ Auto-scan Downloads folder (warns if files > 3 days old)
- ✅ Real-time analysis progress tracking
- ✅ 6 Interactive dashboards
- ✅ Beautiful charts and visualizations
- ✅ Mobile-responsive design

### Dashboards:
1. **Overview** - Portfolio summary, market context, charts
2. **Intraday (10)** - Today's 10 trading picks
3. **Multibaggers** - Hidden gems (NO Nifty 50)
4. **Brutal Truth** - Honest portfolio assessment
5. **Actions** - Portfolio action recommendations
6. **AWS Costs** - Real-time cost monitoring

---

## 🚀 Quick Start (3 Steps)

### Step 1: Install Dependencies

```bash
cd ~/kiro/websites/w-builder

# Install Python packages
pip3 install -r requirements.txt

# Verify Flask installed
python3 -c "import flask; print(flask.__version__)"
```

### Step 2: Set AWS Credentials

```bash
# Export your AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# Verify
aws sts get-caller-identity
```

### Step 3: Launch Web App

```bash
# Start Flask server
python3 webapp/app.py
```

The app will start on: **http://localhost:5000**

Open in your browser!

---

## 📖 How to Use

### 1. Upload Portfolio Files

**Option A: Drag & Drop**
- Drag Excel files from Groww app directly onto the drop zone
- Files upload instantly

**Option B: Auto-Scan**
- Click "Scan Downloads" button
- App automatically finds latest Groww files in ~/Downloads
- Shows file age with warnings (> 3 days old)

**Option C: Browse Files**
- Click "Choose Files" button
- Select Excel files manually

### 2. Run Analysis

Once files are uploaded:
1. Click "Run Analysis" button (green button top-right)
2. Watch real-time progress bar
3. Results appear in ~2-3 minutes

### 3. Explore Dashboards

Switch between tabs to view:
- **Overview**: Your portfolio at a glance
- **Intraday**: 10 trading picks for today
- **Multibaggers**: Long-term wealth creators
- **Brutal Truth**: Honest assessment (junk flagged)
- **Actions**: What to buy/sell/hold/average
- **AWS Costs**: Keep bills in check

---

## 🎨 UI Features

### File Upload Zone
- **Green border** = Ready for drop
- **Blue border** = File hovering (drop it!)
- **File cards** = Show file type, size, age
- **⚠️ Warning icon** = File older than 3 days

### Progress Tracking
- Real-time progress bar (0-100%)
- Status messages ("Fetching market data...", "Running AI analysis...")
- Automatic updates every second

### Dashboard Cards
- **Purple gradient** = Portfolio value
- **Green gradient** = P&L
- **Blue gradient** = Holdings count
- **Yellow gradient** = AWS costs

### Charts
- **Doughnut chart** = Quality distribution (5 verdicts)
- **Bar chart** = Top 10 holdings by value

---

## 💾 Data Storage

### Uploaded Files
Location: `webapp/uploads/`
- Files saved with timestamp prefix
- Example: `20260409_143022_Stocks_Holdings_Statement.xlsx`

### Analysis Results
Location: `webapp/results/`
- JSON files with full analysis data
- Example: `analysis_20260409_143500.json`
- Can be reloaded later

---

## 🔧 Advanced Configuration

### Change Port (default 5000)

Edit `webapp/app.py` line at bottom:
```python
app.run(host='0.0.0.0', port=8080, debug=True)  # Change to 8080
```

### Change File Age Warning (default 3 days)

Edit `webapp/app.py` line 55:
```python
FILE_AGE_WARNING_DAYS = 7  # Change to 7 days
```

### Change Upload Size Limit (default 16MB)

Edit `webapp/app.py` line 62:
```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Change to 50MB
```

---

## 🌐 Access from Other Devices

### Access from Phone/Tablet on Same WiFi

1. Find your computer's IP address:
```bash
# Mac/Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Example output: 192.168.1.5
```

2. On your phone/tablet browser:
```
http://192.168.1.5:5000
```

3. Upload files or use analysis from mobile!

### Deploy to Cloud (Optional)

Deploy to Heroku, AWS EC2, or Digital Ocean for access from anywhere.

---

## 🎯 Workflow Example

**Morning Routine with Web App:**

```
8:50 AM - Open browser → http://localhost:5000
8:51 AM - Click "Scan Downloads" (auto-finds latest Groww files)
8:52 AM - Click "Run Analysis"
8:55 AM - Analysis completes, view dashboards
8:56 AM - Check "Intraday" tab → Copy 10 trading picks
8:57 AM - Check "Actions" tab → See HIGH priority actions
8:58 AM - Check "Brutal Truth" tab → Know your junk
8:59 AM - Ready for market open at 9:15 AM
```

---

## 📊 What Each Dashboard Shows

### 1. Overview Tab
- **Top section**: 4 stats cards (value, P&L, holdings, AWS cost)
- **Market context**: FII/DII flows, Nifty change
- **Charts**: 
  - Portfolio allocation (bar chart of top 10)
  - Quality distribution (pie chart of verdicts)

### 2. Intraday Tab
- 10 trading setups for today
- Each card shows:
  - Entry price, target, stop loss
  - Risk-reward ratio
  - Rationale with specific evidence

### 3. Multibagger Tab
- Hidden gems (NO Nifty 50)
- Small/mid caps only
- Shows:
  - Conviction score (1-10)
  - Current price → 3-year target
  - Growth drivers
  - Risks

### 4. Brutal Truth Tab
- Honest assessment of all holdings
- Color-coded by verdict:
  - Green border = QUALITY
  - Blue border = DECENT
  - Yellow border = MEDIOCRE
  - Orange border = WEAK
  - Red border = JUNK
- Penny positions (< ₹5K) marked with 💸

### 5. Actions Tab
- Specific recommendations for each holding
- Priority levels (HIGH/MEDIUM/LOW)
- Actions: BUY_MORE, AVERAGE_DOWN, HOLD_TIGHT, EXIT, etc.
- Quantity suggestions for averaging
- Crisis opportunities flagged

### 6. AWS Costs Tab
- Month-to-date cost
- Forecast month-end
- Cost by service (Bedrock, EC2, S3, etc.)

---

## 🐛 Troubleshooting

### "Connection refused" Error
```bash
# Make sure Flask is running
python3 webapp/app.py

# Should see:
# * Running on http://0.0.0.0:5000
```

### Files Not Uploading
- Check file size (< 16MB)
- Only .xlsx and .xls allowed
- Check browser console for errors (F12)

### "Analysis Failed" Error
- Check AWS credentials are valid:
```bash
aws sts get-caller-identity
```
- Check Holdings file is selected
- Check logs: `cat morning_analysis.log`

### Progress Bar Stuck
- Refresh page (F5)
- Check if Bedrock API throttling (retry in 1 minute)
- Check terminal for error messages

### Charts Not Showing
- Clear browser cache (Ctrl+Shift+R)
- Check if Chart.js CDN is loading (F12 → Network tab)

### Old File Warning Not Showing
- Files must be in ~/Downloads folder
- Must match Groww filename patterns
- Check `FILE_AGE_WARNING_DAYS` setting

---

## 🔐 Security Notes

### Local Use (Recommended)
- App runs on localhost:5000 by default
- Only accessible from your computer
- Safe for personal use

### Network Access (If Needed)
- Change `host='0.0.0.0'` to `host='127.0.0.1'` for localhost-only
- Don't expose to public internet without authentication
- Consider using VPN for remote access

---

## 💰 Costs

### Free Components:
- Flask web framework
- Tailwind CSS (CDN)
- Chart.js (CDN)
- File storage (local disk)

### AWS Costs (Same as Before):
- Bedrock API: ~$0.12 per analysis
- Monthly (30 runs): ~$3.60
- Total with EC2/S3: $5-35/month

---

## 🚀 Next Steps

### Enhancements You Can Add:

1. **PDF Export** - Export reports as PDF
2. **Historical Comparison** - Compare portfolio over time
3. **Email Reports** - Auto-email daily analysis
4. **Alerts** - Price target hit notifications
5. **Watchlist** - Track stocks you don't own yet
6. **News Feed** - Integrate stock news
7. **Performance Tracking** - Track pick success rate
8. **Portfolio Simulator** - What-if scenarios

---

## 📁 File Structure

```
webapp/
├── app.py                      # Flask backend (main server)
├── templates/
│   └── index.html             # Frontend HTML (main UI)
├── static/
│   ├── js/
│   │   └── main.js           # Frontend JavaScript
│   └── css/
│       └── (empty - using Tailwind CDN)
├── uploads/                   # Uploaded files storage
└── results/                   # Analysis results storage
```

---

## 📞 Quick Commands Reference

```bash
# Start web app
python3 webapp/app.py

# Install/update dependencies
pip3 install -r requirements.txt

# Check if running
curl http://localhost:5000/api/status

# View logs
tail -f morning_analysis.log

# Test file upload (CLI)
curl -F "file=@input/Stocks_Holdings_Statement.xlsx" http://localhost:5000/api/upload
```

---

## 🎉 Summary

You now have a **professional wealth management web application** with:

✅ Beautiful modern UI
✅ Drag & drop file upload
✅ Auto-scan Downloads folder
✅ Real-time progress tracking
✅ 6 interactive dashboards
✅ Charts and visualizations
✅ Mobile responsive design

**Launch it**: `python3 webapp/app.py`

**Access it**: `http://localhost:5000`

**Enjoy!** 🚀
