# RULES.md — Intraday Trader Project

**Purpose**: Behavioral rules and project facts that rarely change. Paste this at the start of every new AI chat along with STATE.md.

**Audience**: Any AI assistant (Claude, Kiro, Cursor, etc.) working on this project.

**Rule for AI**: Read this entire document before responding to any question. Never skip sections. If asked to do something that violates a rule here, refuse and quote the rule.

---

## SECTION 1: WHAT THIS PROJECT IS

**Name**: Intraday Trader (multi-strategy auto-trader)

**Type**: AI-augmented multi-strategy auto-trader for NSE India.

**Architecture principle**: Python rules do 90% of decisions. LLM (Claude Sonnet 4.5 via AWS Bedrock) does final ranking from 20 pre-filtered candidates. NOT an "AI picks stocks" system.

**Strategies**:
| Module | Status | Hold Time | Order Type |
|--------|--------|-----------|------------|
| Intraday | LIVE (since May 12 2026) | <1 day | INTRADAY (MIS) |
| F&O | Paper active | 1-30 days | NRML |
| Swing | To build | 2-10 days | CNC delivery |
| Positional | To build | 1-6 months | CNC delivery |

**Profiles**:
| Profile | Type | Capital | Runs on EC2 | Status |
|---------|------|---------|-------------|--------|
| vishal-live | Real money, intraday | INR 10,000 | OLD (13.206.144.6) | LIVE |
| neha-live | Real money, intraday | INR 10,000 funded | NEW (13.202.63.223) | LIVE since 2026-05-14 |
| vishal | Paper trading | INR 3,00,000 | OLD | Active |
| neha | Paper trading | INR 3,00,000 | OLD | Active |

**Profit target (aspirational)**: INR 20,000-30,000 per day combined.

**Reality**: INR 25K per day requires INR 15-30L deployed + 12-18 months validation. Currently INR 10K deployed.

**Capital scaling plan** (only scale after proof):
- Phase 1 (now): INR 10K live
- Phase 2 (after 50 profitable trades): INR 50K
- Phase 3 (after 3 months consistent): INR 2L
- Phase 4 (after 6 months consistent): INR 5L
- Phase 5 (12+ months proof): up to INR 25L

---

## SECTION 2: CRITICAL OPERATIONAL RULES

### Rule 1: Git Flow Is Strictly One-Way
EC2 (edit + commit + push) -> GitHub -> Mac (pull only)

NEVER push from Mac. Reasons:
- Mac is corporate machine
- AWS IT monitors git pushes
- Push from Mac means email to manager and side project exposed
- Project uses private Isengard account, must stay invisible

Correct flow always:
1. Edit files on EC2 (heredoc, see Rule 11)
2. cd ~/dev-sandbox && git add + git commit + git push
3. On Mac: git pull (read-only)

Exception: None. Even one-line README change pushes from EC2.

### Rule 2: Private Project — Zero Corporate Footprint
- AWS Isengard account (personal, free, hidden)
- Never reference work email, work tools, or corporate accounts in code/commits
- Don't trigger any IT monitoring

### Rule 3: Steering Files Are Authoritative
- Location: ~/dev-sandbox/.kiro/steering/RULES.md (this file)
- Location: ~/dev-sandbox/.kiro/steering/STATE.md (current state, daily updates)
- Location: ~/dev-sandbox/.kiro/steering/HISTORY.md (archived state, append-only)
- Any AI must read RULES.md + STATE.md BEFORE suggesting changes
- vishal-live changes need explicit approval

### Rule 4: File Editing Rules
- EC2 direct edit (heredoc): config/*.yaml, LLM prompts, small string changes, .py code patches
- All edits on EC2 only (per Rule 1)
- NEVER: sed on .py files (caused syntax errors May 6)
- NEVER: nano, vim, or interactive editors for .py files (see Rule 11)
- Acceptable interactive edit: ~/.aws/credentials, non-code config files (rare)

### Rule 5: Verification Required
- Never say "done" without proof
- Run import test: .venv/bin/python -c "import module; print('OK')"
- Run grep verification on changed lines
- Stop on second failure — don't chain attempts

### Rule 6: One Problem At A Time
- Fix what was asked
- Report other bugs but don't fix without explicit approval
- vishal-live changes: especially explicit approval needed

### Rule 7: SSH Recovery
- If SSH breaks: bash ~/kiro/websites/intraday-trader/scripts/enable_ssh.sh (run from Mac)
- User: ec2-user (NOT ubuntu)
- Key: ~/Downloads/wealth-builder-pro.pem
- IP: 13.206.144.6

### Rule 8: AWS Credentials On EC2 — Use Static vishal-admin Profile

EC2 has static profiles in ~/.aws/credentials:
- [default] — do not use for project work
- [vishal-admin] — USE THIS for all project work

Region setup in ~/.aws/config:
- default region: us-east-1 (Bedrock lives here)
- ap-south-1 used for S3/CloudFront/EC2 (set via AWS_DEFAULT_REGION when needed)

#### Standard Setup (start of any EC2 session)
export AWS_PROFILE=vishal-admin aws sts get-caller-identity
#### When AWS Commands Fail
Symptom: "Unable to locate credentials" / "ExpiredToken" / wrong account ID.

Fix — clear stale env tokens, reset profile:
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN export AWS_PROFILE=vishal-admin export AWS_DEFAULT_REGION=ap-south-1 aws sts get-caller-identity
#### Never Do
- IMDSv2 instance role token fetching (curl http://169.254.169.254/...) — conflicts with vishal-admin
- Use [default] profile for project work — wrong identity
- Export raw AWS_ACCESS_KEY_ID — use AWS_PROFILE instead

### Rule 9: Wrong Files — Do Not Run
- scripts/deploy.sh — Wealth Builder Pro project (different)
- build_dashboard.py — Wealth Builder Pro (reads XLSX)

### Rule 10: Date Awareness
- Current period: May 2026
- NSE 2026 holidays documented in Section 9
- Weekend logs don't exist (markets closed) — not a bug
- Holiday logs don't exist — check NSE calendar before assuming bug

### Rule 11: Code Edits Use Heredoc, Never Interactive Editors
- NEVER use nano, vim, or any interactive editor for .py files
- ALWAYS use Python heredoc (PYEOF) for file edits on EC2
- Pattern:
cd ~/dev-sandbox && .venv/bin/python3 <<PYEOF from pathlib import Path f = Path("path/to/file.py") src = f.read_text() OLD = """...exact block...""" NEW = """...replacement...""" assert OLD in src, "OLD block not found" if NEW in src: print("Already applied"); raise SystemExit(0) f.write_text(src.replace(OLD, NEW)) print("Patched") PYEOF
- Always check OLD exists before replace
- Check NEW not already present (idempotent)
- Always follow with grep verification + import test (Rule 5)
- Why: scriptable, repeatable, no typo risk, works cleanly over SSH

### Rule 12: Every Command States Where To Run
- Always prefix: # [EC2] or # [MAC]
- No exceptions

### Rule 13: Before Touching Any File
1. Read the actual error from logs first
2. Show what was found
3. State what's about to change and why
4. Wait for approval before changing

### Rule 14: Definition Of Done
- Done = command output proving it works
- Never say "it should work"
- Never say done without proof output

### Rule 15: If Fix Fails
- Stop after second failure
- Do not chain more attempts
- Rethink and explain before trying again

### Rule 16: Real Money Rules
- vishal-live is real money — any change needs explicit approval
- Paper accounts (vishal, neha): can run freely
- Scale capital only after 60% win rate proven on paper
- When in doubt, protect capital first

### Rule 17: Business Mindset
- Every fix must serve the trading goal — safe capital + consistent profit
- Think like a business partner, not just a code fixer
- Flag anything that could lose real money immediately
- A working trade that makes money beats perfect code that never runs

### Rule 18: Don't Lecture On Already-Solved Problems
If RULES or STATE says X is done/handled, don't lecture about X. Examples:
- "Use Python rules instead of LLM" — already does. 30+ rules.
- "You need backtesting" — on the pending list, help build it
- "Risk management?" — has VIX gates, R:R minimums, capital limits, daily loss caps
- "Start small" — already at INR 10K live, INR 3L paper

### Rule 19: EC2 Clock Sync (TOTP Depends On It)

Dhan TOTP authentication requires EC2 clock within 30 seconds of real time.
If clock drifts, all TOTP logins fail with "Invalid TOTP" — looks like config/credential issue but is actually time drift.

#### Health Check (run when TOTP fails)
timedatectl
Must show:
- System clock synchronized: yes
- NTP service: active

#### If Clock Not Synchronized — Fix
grep "^server|^pool" /etc/chrony.conf sudo systemctl restart chronyd sudo chronyc -a makestep timedatectl chronyc tracking chronyc sources
#### Prevention
- chrony already configured with AWS time server 169.254.169.123
- Do NOT add duplicate server entries to /etc/chrony.conf (caused issue May 12)
- If editing chrony.conf, always check for duplicates after

#### When TOTP Fails — Diagnostic Order
1. Check timedatectl first (most common cause)
2. Check totp_secret in profile yaml
3. Check Dhan PIN
4. Check Dhan API rate limiting (3 attempts then locked briefly)

### Rule 20: Multi-EC2 Architecture (since 2026-05-14)

Project now runs on TWO EC2 instances due to Dhan one-IP-per-account constraint.

OLD EC2 (13.206.144.6) runs:
- vishal-live (real money intraday)
- vishal (paper intraday)
- neha (paper intraday)
- All F&O paper crons
- Dashboard S3 sync (every hour)
- Sanity check, EOD reports

NEW EC2 (13.202.63.223) runs:
- neha-live (real money intraday) ONLY
- No dashboard sync (avoids S3 race)
- No F&O
- No paper profiles

Rules for multi-EC2 work:
1. Profile yamls are gitignored. config/profiles/*.yaml contains TOTP/PIN. NEVER in git. Manually patched on each EC2 separately.
2. All git commits + pushes from OLD EC2 only. Rule 1 still applies. NEW EC2 receives code via git pull.
3. Code edits made on OLD EC2, pushed to GitHub, NEW EC2 pulls. Profile yamls excepted (manual sync per Rule 20.1).
4. Cron isolation enforced. NEW EC2 cron contains ONLY neha-live entries. Verify before any AMI re-clone.
5. Time sync independent. Both EC2s run chrony separately. Rule 19 applies to both.
6. AWS profile vishal-admin works on both. Credentials cloned via AMI. Same Account ID 176767908884.

When NEW EC2 needs code update:
  cd ~/dev-sandbox && git pull
  Profile yaml changes: apply heredoc patch manually on NEW EC2 separately.

Rule 20.7: After ANY push from OLD EC2, immediately remind user to pull on NEW EC2.
This applies to code, steering docs, configs — anything tracked in git.
AI assistant must surface this reminder automatically without being asked.
Format: "✅ Pushed to GitHub. ⚠️ Now sync NEW EC2: cd ~/dev-sandbox && git pull"
No exceptions. Even for one-line doc commits.
Reason: NEW EC2 reading stale STATE.md/RULES.md leads to wrong real-money decisions Monday morning.

Failure modes to watch:
- EIP detached from NEW EC2 -> orders fail with DH-905 Invalid IP
- vishal-admin credentials expire on NEW EC2 (AMI was cloned at point in time)
- Cron file replaced via crontab edit -> could re-introduce removed entries

Dashboard architecture issue (deferred):
Both EC2s writing to one S3 bucket creates race on shared files (history.json, latest.json). Currently NEW EC2 does not sync. Neha dashboard data lives locally on NEW EC2. Fix later via per-profile S3 prefixes, or one EC2 pulls others data via SSH then syncs once.

---

---


### Rule 21: Steering Doc Reading Order (since 2026-05-15)

Project now has 9 steering docs. AI assistants should read in this order based on task:

For trading code changes:
1. RULES.md (this file)
2. STATE.md (current state)
3. STRATEGY.md (scanner/executor logic + active bugs)
4. GLOSSARY.md (term definitions)

For F&O work specifically:
5. FNO_STRATEGY.md (playbook + Bug T status)
6. TECHNICAL_DOC.md (DB schemas + cron)

For business/scaling decisions:
7. BUSINESS_DOC.md (capital phases)
8. LEARNING.md (daily journal + patterns)

For historical context:
9. HISTORY.md (archived state)

Minimum context for new AI session: RULES + STATE + STRATEGY.

For F&O-specific session: above + FNO_STRATEGY + GLOSSARY.

For business decisions: above + BUSINESS_DOC + LEARNING.

Total docs at .kiro/steering/: RULES, STATE, HISTORY, STRATEGY, LEARNING, GLOSSARY, BUSINESS_DOC, TECHNICAL_DOC, FNO_STRATEGY.

If a doc is updated during a session, the AI assistant must:
1. Note the change in commit message
2. Surface it in next session pickup
3. Not silently skip it

---

## SECTION 3: PROJECT DIRECTORY STRUCTURE

### EC2 (where ALL edits + commits + pushes happen)
~/dev-sandbox/ project root ~/dev-sandbox/.kiro/steering/ steering files (RULES.md, STATE.md, HISTORY.md) ~/dev-sandbox/intraday/ intraday module (live trading) ~/dev-sandbox/fno/ F&O module (paper) ~/dev-sandbox/swing/ swing module (TO BUILD) ~/dev-sandbox/positional/ positional module (TO BUILD) ~/dev-sandbox/fetchers/ NSE/Dhan/news/fundamentals ~/dev-sandbox/database/ per-profile SQLite DBs ~/dev-sandbox/config/profiles/ profile yamls (vishal-live.yaml, neha-live.yaml, vishal.yaml, neha.yaml) ~/dev-sandbox/logs/ daily logs (intraday__.log) ~/dev-sandbox/dashboard/ dashboard JSON + HTML for S3 ~/dev-sandbox/scripts/ sync, sanity, eod, etc. ~/dev-sandbox/.venv/ Python venv (use .venv/bin/python) ~/dev-sandbox/cache/ market data cache (gitignored) ~/dev-sandbox/alerts/ telegram.py ~/dev-sandbox/backtest/ empty, TO BUILD ~/dev-sandbox/docs/ DHAN_CHARGES.md and other reference docs
### Mac (READ-ONLY — git pull only)
~/kiro/websites/intraday-trader/ same project, mirror via git pull ~/Downloads/wealth-builder-pro.pem SSH key (reused, NOT WBP project)
### Critical Path Mappings
| Item | Path |
|------|------|
| RULES.md (this file) | ~/dev-sandbox/.kiro/steering/RULES.md |
| STATE.md (current state) | ~/dev-sandbox/.kiro/steering/STATE.md |
| HISTORY.md (archive) | ~/dev-sandbox/.kiro/steering/HISTORY.md |
| Live profile config | ~/dev-sandbox/config/profiles/vishal-live.yaml |
| Live trading log | ~/dev-sandbox/logs/intraday_vishal-live_.log |
| Live profile DB | ~/dev-sandbox/database/vishal-live.db |
| Python interpreter | ~/dev-sandbox/.venv/bin/python (NOT system python) |
| AWS credentials | ~/.aws/credentials (vishal-admin profile) |
| AWS config | ~/.aws/config |

### Never Confuse
- Mac path ~/kiro/websites/intraday-trader/ = read-only mirror
- EC2 path ~/dev-sandbox/ = source of truth, all edits here
- Commands telling you to cd ~/dev-sandbox MUST be run on EC2 (via SSH)

---

## SECTION 4: INFRASTRUCTURE

| Item | Value |
|------|-------|
| EC2 Instance ID (OLD — vishal+paper) | i-0256713c061011a5f |
| EC2 Public IP (OLD) | 13.206.144.6 |
| EC2 Instance ID (NEW — neha-live only) | i-0233c705c9104383e |
| EC2 Public IP (NEW) | 13.202.63.223 |
| EC2 Type (both) | t3.medium |
| EC2 Region (both) | ap-south-1 (Mumbai) |
| EC2 IAM Role | EpoxyChronicleInstanceRole (not used, vishal-admin profile used instead) |
| SSH Key | ~/Downloads/wealth-builder-pro.pem |
| SSH User | ec2-user |
| AWS Account | Isengard private (vishal-admin profile in ~/.aws/credentials) |
| AWS Profile (use this) | vishal-admin |
| Bedrock Region | us-east-1 |
| Bedrock Model | Claude Sonnet 4.5 |
| S3 Bucket | dev-sandbox-dashboard-176767908884 (PRIVATE) |
| CloudFront Distribution | E3NXP6TCRJKVX1 |
| CloudFront URL | https://d2q1cy3ph7jbd0.cloudfront.net |
| Onboarding S3 Bucket | intraday-onboarding-176767908884 |
| Onboarding CloudFront ID | E1V3MJSHBAA4SM |
| Onboarding URL | https://d1pt3c87z185fv.cloudfront.net |
| Onboarding S3 Bucket | intraday-onboarding-176767908884 |
| Onboarding CloudFront ID | E1V3MJSHBAA4SM |
| Onboarding URL | https://d1pt3c87z185fv.cloudfront.net |
| GitHub Repo | https://github.com/vshorrghar/Intraday-Trader.git |
| Broker | Dhan REST API v2 |
| Dhan Whitelisted IP (vishal account) | 13.206.144.6 |
| Dhan Whitelisted IP (neha account) | 13.202.63.223 |
| Dhan IP rule | Each account requires unique IP (one IP cannot be on two accounts) |
| Time sync | chrony with AWS server 169.254.169.123 |

### Dashboard URLs
| Profile | URL |
|---------|-----|
| Main | https://d2q1cy3ph7jbd0.cloudfront.net |
| vishal-live | https://d2q1cy3ph7jbd0.cloudfront.net?profile=vishal-live |
| vishal | https://d2q1cy3ph7jbd0.cloudfront.net?profile=vishal |
| neha | https://d2q1cy3ph7jbd0.cloudfront.net?profile=neha |
| neha-live | https://d2q1cy3ph7jbd0.cloudfront.net?profile=neha-live |

Passwords: SHA-256 hashed in dashboard/api/passwords.json. vishal/vishal-live share password. neha/neha-live separate.

---

## SECTION 5: PROFILE CAPITAL LIMITS (DO NOT CHANGE WITHOUT APPROVAL)

### vishal-live (REAL MONEY)
| Setting | Value |
|---------|-------|
| daily_capital_limit | INR 15,000 (raised from 10K on May 14) |
| per_trade_max_capital | INR 4,500 (raised from 4K on May 14) |
| max_trades_per_day | 3 (raised from 2 on May 14) |
| daily_loss_limit | INR 900 (raised from 600 on May 14) |
| min_confidence_score | 7 |
| vix_threshold | 20 (raised from 18 on May 14) |

### neha-live (REAL MONEY, INR 10,000 funded)
| Setting | Value |
|---------|-------|
| daily_capital_limit | INR 10,000 |
| per_trade_max_capital | INR 4,000 |
| max_trades_per_day | 3 (raised from 2 on May 14) |
| daily_loss_limit | INR 900 (raised from 600 on May 14) |
| min_confidence_score | 8 |
| vix_threshold | 20 (raised from 16 on May 14) |

### vishal (PAPER)
| Setting | Value |
|---------|-------|
| daily_capital_limit | INR 3,00,000 |
| per_trade_max_capital | INR 50,000 (was 60K, lowered May 14) |
| max_trades_per_day | 6 (raised from 5 on May 14) |
| daily_loss_limit | INR 9,000 |
| min_confidence_score | 7 |
| vix_threshold | 18 |

### neha (PAPER, mirrors vishal paper)
Same as vishal paper.

### F&O (paper, all profiles)
| Setting | Value |
|---------|-------|
| paper_capital | INR 50,000 |
| daily_capital_limit | INR 50,000 |
| per_trade_max_capital | INR 25,000 |
| daily_loss_limit | INR 5,000 |
| max_lots_per_trade | 1 |
| min_confidence_score | 8 |
| vix_threshold | 22 |

---

## SECTION 6: HARD-CODED TRADING RULES (30+ RULES)

### Confidence & VIX
| Rule | Value | Location |
|------|-------|----------|
| Min confidence (paper) | 7 | profile yaml |
| Min confidence (vishal-live) | 7 | vishal-live.yaml |
| Min confidence (neha-live) | 8 | neha-live.yaml |
| Min R:R | 2.0 | selector.py |
| VIX threshold (vishal-live) | 20 | vishal-live.yaml |
| VIX threshold (neha-live) | 20 | neha-live.yaml |
| VIX threshold (paper intraday) | 18 | profile yaml |
| VIX threshold (FnO) | 22 | profile yaml |
| VIX SKIP level (fixed) | > 25 | risk_manager.py |
| VIX REDUCE level (fixed) | > 22 reduce to 1 trade | risk_manager.py |

### Volume & Volatility
| Rule | Value |
|------|-------|
| Volume min (scan) | 500K |
| Volume min (LLM prompt) | 2M |
| High volatility gap | >3% |
| High volatility day range | >5% |

### Trade Setup
| Rule | Value |
|------|-------|
| Entry delay | 15 min (9:30 AM IST) |
| Force exit time | 15:15 IST |
| Monitor interval | 300s (5 min) |
| Trailing SL trigger | 0.5% profit |
| Partial book at target | 50% |
| SL width (normal) | 1.8% |
| SL width (high VIX) | 2.0% |
| Target width | 3.6 to 4% |
| NSE tick size (price rounding) | INR 0.05 |

### Late Session Gates (after 11 AM IST)
- Gate 1: Max trades placed -> SKIP
- Gate 2: Loss > 50% of daily limit -> SKIP
- Gate 3: Breadth gate REMOVED May 12

### Scanner Scoring (RS-First v3, since May 14)
Located in intraday/scanner.py. Replaces volume-dominated v1.

Signal 1: Intraday continuation (change_from_open) — 0-5 pts
Signal 2: Momentum strength (change_pct) — 0-8 pts (boosted from 0-4)
Signal 3: Price near day high — 0-2 pts
Signal 4: Volume confirmation — 0-2 pts (confirms only, doesn't lead)
Signal 5: FNO liquidity bonus — 0-1 pt
Signal 6: Sector rotation bonus — 0-5 pts (top 3 sector +3, outperforming sector +2)

Penalties:
- Fade detector: -3 if fell >3% from day high, -1 if >1.5% (replaces old chasing penalty)
- Trap detector: -5 gap with no sector support, -2 buying climax at 52w high

Time multiplier (applied to final score):
- First hour (9:30-10:30): 1.5x — best entries
- Sweet spot (10:30-11:45): 1.0x
- Caution (11:45-13:15): 0.7x
- Late session (after 13:15): 0.4x

See STRATEGY.md for full evolution log.

### F&O Specific
- Naked selling time block: After 14:00 IST
- Directional buy time block: After 13:00 IST
- Naked selling confluence min: 75
- Hedged strategy confluence min: 50
- Paper history required: 2 weeks before naked selling

### Cron Schedule (updated 2026-05-14 — continuous scanning)

OLD EC2 (13.206.144.6) — runs vishal-live + paper profiles + F&O:
Continuous intraday scanning every 15 min, 9:30 AM - 1:00 PM IST (4:00-7:30 UTC)
*/15 4-7 * * 1-5 cd ~/dev-sandbox && bash run_daily.sh --profile vishal-live --live >> logs/cron_vishal_live.log 2>&1 */15 4-7 * * 1-5 cd ~/dev-sandbox && bash run_daily.sh --profile vishal >> logs/cron_vishal.log 2>&1 */15 4-7 * * 1-5 cd ~/dev-sandbox && bash run_daily.sh --profile neha >> logs/cron_neha.log 2>&1

F&O paper (all profiles, single run at market open)
50 3 * * 1-5 run_fno_daily.sh --profile vishal (9:20 AM) 52 3 * * 1-5 run_fno_daily.sh --profile neha (9:22 AM) 54 3 * * 1-5 run_fno_daily.sh --profile vishal-live (9:24 AM, paper mode)

Top performers capture (3:35 PM IST = 10:05 UTC, 20 min after close)
5 10 * * 1-5 cd ~/dev-sandbox && .venv/bin/python3 scripts/capture_top_performers.py >> logs/top_performers.log 2>&1

Dashboard sync + CloudFront invalidation (hourly 9 AM - 5 PM IST)
0 3-10 * * 1-5 (S3 sync + CloudFront invalidation)

NEW EC2 (13.202.63.223) — runs neha-live ONLY:
Continuous neha-live scanning every 15 min
*/15 4-7 * * 1-5 cd ~/dev-sandbox && export AWS_PROFILE=vishal-admin && .venv/bin/python3 run_intraday.py --profile neha-live --live >> logs/cron_neha_live.log 2>&1

Why continuous (every 15 min):
- Catches mid-session breakouts
- Idempotent (run_daily.sh checks for active positions, skips if max trades hit)
- Late session gates prevent revenge trading after 11 AM IST
- Real money trade limits enforce max 3/day even with continuous attempts
---

## SECTION 7: ARCHITECTURE OVERVIEW

### Intraday Module (intraday/) — LIVE
| File | Role |
|------|------|
| scanner.py | Pre-market: fetches Nifty 500, scores LONG + SHORT setups |
| selector.py | Pre-filter (Python rules) + LLM call + validation |
| executor.py | Places entry + SL orders (direction-aware), tick-aligned prices, waits for fill before SL |
| monitor.py | Position tracking, trailing SL, target/SL/force exit, calls broker SELL, direction-aware P&L |
| risk_manager.py | VIX gate, position sizing, daily loss cap |
| models.py | TradeSetup, PositionState, IntraConfig dataclasses |
| dhan_broker.py | Dhan REST API v2 (with get_order_list method) |
| broker_base.py | Abstract BrokerClient interface |
| auth_server.py | TOTP auth, per-profile session management, DryRunBrokerClient |
| dashboard.py | Writes JSON for web dashboard |
| charges.py | Charge calculators (intraday/delivery/futures/options) |

### F&O Module (fno/) — PAPER ACTIVE
| File | Role |
|------|------|
| strategy_engine.py | 7-strategy playbook + LLM strategy selection |
| quant_engine.py | IV percentile, OI velocity, IV skew, GEX, VRP signals |
| risk_manager.py | Confluence check, margin check, DTE rules |
| monitor.py | Position monitoring + broker exit orders |
| models.py | FnO config, strategy dataclasses |
| dashboard.py | FnO dashboard JSON writer |

### Swing Module (swing/) — TO BUILD
Planned: scanner.py, selector.py, executor.py (CNC), monitor.py (daily), risk_manager.py (5-10% target, 3-5% SL, 5-15 day hold), models.py.
Cron: daily 4 PM IST after market close.

### Positional Module (positional/) — TO BUILD
Planned: scanner.py (52w breakouts, value picks), selector.py (with fundamentals), executor.py (large CNC), monitor.py (weekly), risk_manager.py (20-50% target, 10-15% SL, 1-6 month hold), models.py.
Cron: weekly Monday 4 PM IST.

### Other Modules
| Module | Files | Status |
|--------|-------|--------|
| fetchers/ | dhan_api.py, nse_fetcher.py, nse_market_movers.py | Active |
| fetchers/news_fetcher.py | News sentiment per stock | TO BUILD |
| fetchers/options_fetcher.py | NSE option chain, ATM strike, IV percentile | ACTIVE (since May 14) |
| fetchers/fundamentals_fetcher.py | P/E, P/B, ROE for positional | TO BUILD |
| database/ | db_manager.py (SQLite per-profile) + daily_top_performers table | Active |
| alerts/ | telegram.py | Config-aware, ready (set token in config.yaml to activate) |
| backtest/ | EMPTY | TO BUILD |

### Orchestrators
| File | Purpose | Status |
|------|---------|--------|
| run_intraday.py | Main intraday pipeline (14 phases) | Active |
| run_fno.py | Main F&O pipeline | Active |
| run_swing.py | Swing pipeline | TO BUILD |
| run_positional.py | Positional pipeline | TO BUILD |
| run_daily.sh | Cron wrapper (parses --profile, --live) | Active |
| run_fno_daily.sh | F&O cron wrapper | Active |
| run_swing_daily.sh | Swing cron wrapper | TO BUILD |
| run_positional_weekly.sh | Positional cron wrapper | TO BUILD |
| scripts/sync_to_ec2.sh | Mac -> EC2 deploy (legacy, prefer EC2 direct edit) | Active |
| scripts/enable_ssh.sh | Re-enables SSH when Mac IP changes | Active |
| scripts/sanity_check.sh | 9-layer health check (--local works) | Active |
| scripts/eod_summary.sh | EOD trade summary | Active |
| scripts/capture_top_performers.py | Daily top 20 NSE movers + why_missed reasons | Active (since May 14) |
| scripts/sync_top_performers.py | Sync top performers to dashboard JSON | Active (since May 14) |
| scripts/sync_docs.py | Sync steering docs to dashboard War Room tab | Active |

---

## SECTION 8: STOCK SELECTION FLOW (INTRADAY — REFERENCE FOR ALL STRATEGIES)

### Step 1: Candidate Fetch (scanner.py)
- Source: NSE Nifty 500 API
- Filters: price INR 50 to INR 5000, volume > 500K
- Scores each stock for LONG and SHORT
- Output: Top 15 LONG + Top 15 SHORT = 30 candidates

### Step 2: Pre-Filter (selector.py::pre_filter_candidates)
Python rules only — no LLM:
- Price range filter
- High volatility flag if abs(gap_pct) > 3.0%
- Sector alignment (prefer green sectors)
- Cap at 20 candidates

### Step 3: Pre-LLM Calculations (Python)
- VIX reading
- Market breadth %
- Market condition (BULLISH/NEUTRAL/BEARISH)
- Trade history (last 30 days per symbol)
- Sector ranking

### Step 4: LLM Call (Claude Sonnet 4.5 via Bedrock)
LLM decides: Which 1-5 stocks, entry/target/SL prices, confidence (1-10), strategy type, skip flag.
Python decides: Quantity, capital allocation, VIX/loss gates, late session gates, order timing, exit execution.

### Step 5: Post-LLM Validation (validate_pick)
- Required fields present
- confidence >= config.min_confidence_score
- R:R >= 2.0
- Direction logic (LONG: target > entry > SL, SHORT: target < entry < SL)
- Reject high_volatility

### Step 6: Position Sizing (risk_manager.py)
- Per-trade capital cap
- Daily capital limit
- VIX-based reduction (>threshold = halve max trades)
- Late session gates

### Step 7: Execution (executor.py)
- Entry: BUY for LONG, SELL for SHORT
- Wait up to 10s for fill (poll every 2s)
- SL: SELL for LONG, BUY for SHORT (opposite direction)
- All prices rounded to NSE tick (INR 0.05) — Dhan rejects non-tick prices (omsErrorCode 16283)
- DB stores actual filled qty

### Step 8: Monitoring (monitor.py)
- 5-min interval
- Trailing SL after 0.5% profit
- 50% partial book at target
- Force exit at 15:15 IST
- Broker exit orders (not just DB updates)
- Direction-aware P&L

---

## SECTION 9: NSE 2026 HOLIDAYS + QUICK REFERENCE COMMANDS

### NSE 2026 Holidays (markets closed, no logs expected)
- Jan 26 — Republic Day
- Mar 25 — Holi
- Apr 14 — Dr. Ambedkar Jayanti
- Apr 17 — Good Friday
- May 1 — Maharashtra Day
- Jun 5 — Eid ul-Adha (tentative)
- Aug 15 — Independence Day
- Oct 2 — Gandhi Jayanti
- Oct 24 — Dussehra (tentative)
- Nov 14 — Diwali Laxmi Puja (tentative)
- Nov 28 — Gurunanak Jayanti (tentative)
- Dec 25 — Christmas

Always check NSE holiday calendar before assuming missing logs = bug.

### Quick Reference Commands

[EC2] Start of session — set AWS profile
export AWS_PROFILE=vishal-admin aws sts get-caller-identity
[EC2] If AWS commands fail
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN export AWS_PROFILE=vishal-admin export AWS_DEFAULT_REGION=ap-south-1
[EC2] Watch live session
tail -f ~/dev-sandbox/logs/intraday_vishal-live_$(date +%Y-%m-%d).log
[EC2] EOD summary all profiles
for p in vishal-live vishal neha; do echo "--- $p ---" grep -E "Placed|P&L|STOPPED|TARGET" ~/dev-sandbox/logs/intraday_${p}_$(date +%Y-%m-%d).log 2>/dev/null | tail -5 done
[EC2] Check all profiles single command
for p in vishal-live vishal neha neha-live; do echo "=== $p ===" && grep -E "Placed|STOPPED|TARGET|FORCE|P&L|VIX|ERROR|Pick|Sized" ~/dev-sandbox/logs/intraday_${p}_$(date +%Y-%m-%d).log 2>/dev/null | tail -5 || echo "NO LOG"; done
[EC2] Sanity check
bash scripts/sanity_check.sh --local
[EC2] Manual run
cd ~/dev-sandbox && export AWS_PROFILE=vishal-admin && .venv/bin/python run_intraday.py --force --profile vishal-live --live
[EC2] Sync dashboard manually
export AWS_PROFILE=vishal-admin cd ~/dev-sandbox && aws s3 sync dashboard/ s3://dev-sandbox-dashboard-176767908884/ --delete aws cloudfront create-invalidation --distribution-id E3NXP6TCRJKVX1 --paths "/*"
[EC2] Kill all
bash ~/dev-sandbox/scripts/STOP
[EC2] Git status (always check before any work)
cd ~/dev-sandbox && git log --oneline -5 && git status
[EC2] Time sync health check
timedatectl chronyc tracking chronyc sources
[EC2] Time sync fix (if drifted)
sudo systemctl restart chronyd sudo chronyc -a makestep timedatectl
[MAC] SSH from Mac
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@13.206.144.6
[MAC] Enable SSH (if Mac IP changed)
bash ~/kiro/websites/intraday-trader/scripts/enable_ssh.sh
[MAC] Pull latest
cd ~/kiro/websites/intraday-trader && git pull
### How To Resume Any Chat With Any AI
Paste RULES.md (this file) + STATE.md + your question.

Any AI that lectures without reading both docs is wasting your time.

End of RULES.md
