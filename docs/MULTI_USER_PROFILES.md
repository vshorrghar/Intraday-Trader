# Multi-User Profile System

## Overview

The trading platform supports multiple users running independently on the same EC2 instance. Each user gets:
- Their own Dhan broker credentials
- Their own database (separate P&L tracking)
- Their own dashboard URL
- Their own capital limits and risk settings
- Their own log files
- Their own lock files (no interference between users)

## Architecture

```
config/profiles/
├── _template.yaml      ← Copy this for new users
├── vishal.yaml         ← Active profile
└── neha.yaml           ← Add Dhan creds to activate

database/
├── vishal.db           ← Vishal's trades & P&L
└── neha.db             ← Neha's trades & P&L

dashboard/api/
├── vishal/
│   ├── intraday_latest.json
│   └── fno_latest.json
└── neha/
    ├── intraday_latest.json
    └── fno_latest.json

logs/
├── intraday_vishal_2026-05-05.log
├── fno_vishal_2026-05-05.log
├── intraday_neha_2026-05-05.log
└── fno_neha_2026-05-05.log
```

## Adding a New User

### Step 1: Copy the template

```bash
cp config/profiles/_template.yaml config/profiles/<name>.yaml
```

### Step 2: Fill in Dhan credentials

Edit `config/profiles/<name>.yaml`:

```yaml
profile:
  name: "neha"              # lowercase, no spaces
  display_name: "Neha"

dhan:
  client_id: "1234567890"   # From Dhan app → Profile
  api_key: "12345678"       # From api.dhan.co → Create App
  api_secret: "xxxx-xxxx"   # From api.dhan.co → Create App
  totp_secret: "ABCDEF..."  # From Dhan → Security → Enable TOTP → "Can't scan?"
  pin: "123456"             # 6-digit Dhan login PIN
```

### Step 3: Set capital limits

```yaml
intraday:
  daily_capital_limit: 100000     # Total capital per day
  per_trade_max_capital: 30000    # Max per single trade
  daily_loss_limit: 5000          # Stop trading if loss exceeds this

fno:
  mode: "paper"                   # Start with "paper", switch to "live" when ready
  paper_capital: 100000
  daily_loss_limit: 25000
```

### Step 4: Uncomment cron entries

In `scripts/ec2_setup.sh`, uncomment the user's cron lines:

```bash
# === NEHA ===
52 3 * * 1-5 /home/ec2-user/dev-sandbox/run_fno_daily.sh --profile neha
57 3 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
32 6 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
2 8 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh --profile neha
```

### Step 5: Deploy

```bash
./sync_to_ec2.sh
ssh ec2-user@13.206.144.6 "bash ~/dev-sandbox/scripts/ec2_setup.sh"
bash scripts/sanity_check.sh
```

### Step 6: Share dashboard URL

```
https://d2q1cy3ph7jbd0.cloudfront.net?profile=neha
```

## How It Works

### Profile Loading

`config/profile_loader.py` handles:
1. Auto-discovers all `config/profiles/*.yaml` files (skips `_template.yaml`)
2. Validates credentials (skips profiles with `REPLACE_ME`)
3. Deep-merges profile overrides with base `config/config.yaml`
4. Profile-specific values override base values

### Isolation

Each profile is completely isolated:
- **Database**: Separate SQLite file per user
- **Lock files**: Per-profile locks (`logs/.intraday_vishal.lock`, `logs/.fno_neha.lock`)
- **Logs**: Per-profile log files
- **Dashboard**: Per-profile JSON output directory
- **Cron**: Staggered by 2 minutes to avoid resource contention

### CLI Usage

```bash
# Run for specific profile
python run_intraday.py --force --profile vishal
python run_fno.py --force --profile neha

# Without --profile, uses base config.yaml (backward compatible)
python run_intraday.py --force
```

## Getting Dhan Credentials

1. **client_id** — Dhan app → Profile → Client ID
2. **api_key & api_secret** — Go to [api.dhan.co](https://api.dhan.co) → Login → Create App
3. **totp_secret** — Dhan app → Settings → Security → Enable TOTP → Click "Can't scan?" to see the secret key
4. **pin** — The 6-digit PIN used to login to Dhan

## Removing a User

1. Delete their profile: `rm config/profiles/<name>.yaml`
2. Comment out their cron entries in `scripts/ec2_setup.sh`
3. Re-run: `bash scripts/ec2_setup.sh`
4. Optionally delete their DB: `rm database/<name>.db`
