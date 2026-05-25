# Sanity Check System

## Purpose

The sanity check catches deployment mistakes before they break trading. It runs:
1. **After every code deploy** (manually via `bash scripts/sanity_check.sh`)
2. **Every night at 11:55 PM IST** (automated via cron)

If any check fails, the output clearly states **DO NOT PROCEED** and lists what's broken.

## When to Run

| Trigger | How |
|---------|-----|
| After `./sync_to_ec2.sh` | `bash scripts/sanity_check.sh` |
| After editing config | `bash scripts/sanity_check.sh` |
| After `scripts/ec2_setup.sh` | `bash scripts/sanity_check.sh` |
| Nightly (automated) | Cron at 18:25 UTC (11:55 PM IST) |
| Before going live | `bash scripts/sanity_check.sh` |

## Check Layers (Sequential)

Checks run in strict order. If a layer fails, subsequent layers are skipped (they'd fail anyway).

### Layer 1: EC2 Connectivity
- EC2 reachable via SSH
- EC2 timezone is UTC (cron times depend on this)

### Layer 2: File System & Paths
- `run_daily.sh` has EC2 paths (not Mac `/Users/...` paths)
- `run_fno_daily.sh` has EC2 paths
- APP_DIR points to `/home/ec2-user/dev-sandbox`
- Lock file mechanism exists in scripts
- No stale lock files blocking future runs
- Scripts are executable

### Layer 3: Cron Configuration
- ec2-user crontab has correct entries
- Root crontab is empty (no duplicate processes)
- FnO fires at 3:50 UTC (9:20 IST)
- Intraday fires at 3:55 UTC (9:25 IST)
- All entries are weekday-only (Mon-Fri)

### Layer 4: AWS & Bedrock Auth
- `AWS_PROFILE=vishal-admin` is set in cron scripts
- `~/.aws/credentials` file exists
- `vishal-admin` profile exists in credentials
- Bedrock LLM actually responds (live API call)

### Layer 5: Python Runtime
- `.venv/bin/python` exists and is executable
- All critical modules import without errors:
  - intraday.dashboard
  - fno.dashboard
  - intraday.auth_server
  - intraday.scanner
  - intraday.selector
  - fno.paper_engine
  - llm.bedrock_client
  - pyotp

### Layer 6: Config Validation
- `bedrock_model_id` is set
- `bedrock_region` is set
- Intraday capital > ₹1,000
- Per-trade capital > ₹1,000
- Daily loss limit > 0
- FnO mode is "paper" or "live"
- Dhan credentials are present (client_id, api_key, totp_secret, pin)

### Layer 7: Data Access
- NSE market data fetch works (sectors, gainers, losers)
- Dhan TOTP authentication works (generates valid token)

### Layer 8: End-to-End Pipeline
- Full pipeline runs: config → DB → scan → pre-filter
- Candidates are found and filtered

## Output Format

```
═══════════════════════════════════════════════════════════════
  🔍 POST-DEPLOY SANITY CHECK
  Run at: 2026-05-05 14:30:00
  Target: ec2-user@13.206.144.6:~/dev-sandbox
═══════════════════════════════════════════════════════════════

━━━ Layer 1: EC2 Connectivity ━━━
  ✅ EC2 reachable at 13.206.144.6
  ✅ EC2 timezone is UTC

━━━ Layer 2: File System & Paths ━━━
  ✅ run_daily.sh has EC2 paths
  ...

═══════════════════════════════════════════════════════════════
  ✅ ALL 22 CHECKS PASSED — safe to run
  🚀 Cron will fire correctly tomorrow morning
═══════════════════════════════════════════════════════════════
```

## Viewing Nightly Results

```bash
# Check today's sanity log
ssh ec2-user@13.206.144.6 "cat ~/dev-sandbox/logs/sanity_$(date +%Y-%m-%d).log"
```

## Known Issues This Catches

| # | Issue | Layer |
|---|-------|-------|
| 1 | Mac paths in EC2 scripts after sync | 2 |
| 2 | Scripts not executable | 2 |
| 3 | Stale lock files blocking runs | 2 |
| 4 | Root crontab causing duplicates | 3 |
| 5 | Cron times in IST instead of UTC | 3 |
| 6 | Weekend cron entries | 3 |
| 7 | AWS_PROFILE not set in scripts | 4 |
| 8 | Stale/expired AWS credentials | 4 |
| 9 | Bedrock model ID wrong | 4 |
| 10 | Missing Python packages | 5 |
| 11 | Import errors after code change | 5 |
| 12 | Config values zeroed or missing | 6 |
| 13 | Dhan credentials incomplete | 6 |
| 14 | NSE data fetch broken | 7 |
| 15 | Dhan TOTP auth broken | 7 |
| 16 | Full pipeline crash | 8 |

## Adding New Checks

Edit `scripts/sanity_check.sh`. Follow the pattern:
```bash
if <condition>; then
    pass "Description of what's correct"
else
    fail "Description of what's wrong — how to fix"
fi
```

For critical failures that should stop subsequent checks:
```bash
LAYER_FAILED="<layer_number>"
layer_check
```
