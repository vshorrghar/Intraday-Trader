#!/usr/bin/env python3
"""Fix all known issues on EC2. Run once after sync."""
import re

# 1. Fix config_loader.py
print("Fixing config_loader.py...")
with open("config/config_loader.py") as f:
    content = f.read()

fixes = {
    'data["portfolio"]': 'data.get("portfolio", {})',
    'data["schedule"]': 'data.get("schedule", {})',
    'data["cache"]': 'data.get("cache", {"dir": "cache"})',
    'data["dashboard"]': 'data.get("dashboard", {"output_dir": "dashboard", "api_dir": "dashboard/api"})',
    'data["investor"]': 'data.get("investor", {"name": "User"})',
    'portfolio["stocks_xlsx"]': 'portfolio.get("stocks_xlsx", "")',
    'portfolio["mf_xlsx"]': 'portfolio.get("mf_xlsx", "")',
    'portfolio["pnl_xlsx"]': 'portfolio.get("pnl_xlsx", "")',
    'dashboard["output_dir"]': 'dashboard.get("output_dir", "dashboard")',
    'investor["name"]': 'investor.get("name", "User")',
    'schedule["morning_brief"]': 'schedule.get("morning_brief", "03:15")',
    'schedule["midday_snapshot"]': 'schedule.get("midday_snapshot", "07:00")',
    'schedule["eod_report"]': 'schedule.get("eod_report", "10:45")',
    'schedule["midday_threshold_pct"]': 'schedule.get("midday_threshold_pct", 2.0)',
    'aws["region"]': 'aws.get("region", "ap-south-1")',
    'aws["s3_bucket"]': 'aws.get("s3_bucket", "")',
    'aws["ses_sender"]': 'aws.get("ses_sender", "")',
    'aws["ses_recipient"]': 'aws.get("ses_recipient", "")',
}

for old, new in fixes.items():
    content = content.replace(old, new)

# Fix _REQUIRED_KEYS
content = re.sub(
    r'_REQUIRED_KEYS.*?\]',
    '_REQUIRED_KEYS: list[tuple[str, ...]] = [\n    ("aws", "bedrock_model_id"),\n    ("aws", "bedrock_region"),\n    ("database", "path"),\n]',
    content,
    count=1,
    flags=re.DOTALL
)

with open("config/config_loader.py", "w") as f:
    f.write(content)
print("  Done")

# 2. Verify it loads
print("Verifying config loads...")
from config.config_loader import load_config, load_intraday_config
c = load_config("config/config.yaml")
i = load_intraday_config("config/config.yaml")
print(f"  OK: db={c.db_path}, capital={i.daily_capital_limit}")

# 3. Verify profile loads
print("Verifying profiles...")
from config.profile_loader import load_profile
for name in ["vishal", "neha", "vishal-live"]:
    try:
        p = load_profile(name)
        print(f"  {name}: OK capital={p['intraday']['daily_capital_limit']}")
    except Exception as e:
        print(f"  {name}: FAILED - {e}")

print("\nAll fixes applied.")
