# PROJECT CONTEXT (auto-generated 2026-05-24 06:23 IST)

Paste this entire file into new Bedrock chat for full project context.


================================================================
# === RULES.md ===
================================================================
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

F&O mark-to-market every 30 min during market hours (NEW 2026-05-15)
*/30 4-9 * * 1-5 update_all_open_strategies for vishal-live, vishal, neha >> logs/fno_pnl_update.log 2>&1

Top performers capture (3:35 PM IST = 10:05 UTC, 20 min after close)
5 10 * * 1-5 cd ~/dev-sandbox && .venv/bin/python3 scripts/capture_top_performers.py >> logs/top_performers.log 2>&1

Dashboard sync + CloudFront invalidation (hourly 9 AM - 5 PM IST)
0 3-10 * * 1-5 (S3 sync, --exclude "db-sync/*" to preserve NEW EC2 DB)

NEW EC2 (13.202.63.223) — runs neha-live ONLY:
Continuous neha-live scanning every 15 min
*/15 4-7 * * 1-5 cd ~/dev-sandbox && export AWS_PROFILE=vishal-admin && .venv/bin/python3 run_intraday.py --profile neha-live --live >> logs/cron_neha_live.log 2>&1

neha-live DB sync to S3 every 15 min (NEW 2026-05-15)
*/15 4-10 * * 1-5 bash scripts/sync_neha_live_db.sh

neha-live dashboard JSON sync to S3 every 15 min (NEW 2026-05-15)
*/15 4-10 * * 1-5 bash scripts/sync_neha_live_dashboard.sh

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


### Rule 25: Crontab Edits Use Safe Editor Script Only

NEVER pipe transformed crontab output directly to `crontab -`. The pipeline
can fail silently and produce empty stdout, which wipes the crontab.

Wrong (caused wipes May 18, May 20):
  crontab -l | sed '...' | crontab -
  crontab -l | awk '...' | crontab -

Right:
  bash scripts/safe_crontab_edit.sh

The safe editor:
- Backs up to /var/backups/crontab_*.txt with size verification
- Aborts if backup empty
- Opens vim editor
- Validates new file non-empty AND contains run_daily.sh
- Shows diff and asks confirmation before installing

Recovery from wipe:
  crontab scripts/crontab.canonical

Prior incidents: LEARNING.md May 18 + May 20.

End of RULES.md

### Rule 22: Command Format For SSM Web Console
User runs commands via AWS SSM Session Manager browser console, NOT local SSH from Mac.
Two browser tabs always open: EC2-OLD (vishal-live + paper) and EC2-NEW (neha-live).
- EC2-OLD = 13.206.144.6 = vishal-live + vishal/neha paper + F&O
- EC2-NEW = 13.202.63.223 = neha-live (currently STOPPED as of May 18)
Commands prefixed [EC2-OLD] or [EC2-NEW]. Always start with `sudo su - ec2-user` then `cd ~/dev-sandbox`.
No SSH boilerplate, no SCP — write files via heredoc directly on EC2.
No [MAC] commands unless explicitly asked.

### Rule 23: Session Capture Protocol
At end of any chat with material decisions, user types "capture session".
AI must:
1. Read entire chat
2. Segregate content into 5 buckets: RULES / STATE / STRATEGY / LEARNING / GLOSSARY
3. Generate ONE heredoc command block updating all relevant docs + CONTEXT.md
4. Include git add + commit + push
5. Remind user to pull on EC2-NEW
6. Idempotency required — re-running same capture must not duplicate
Alternative workflow: user dumps chat to /tmp/session_chat.txt on EC2 and asks Kiro to ingest.

### Rule 24: Bedrock Chat Cannot Auto-Read External Files
AI in Bedrock browser console cannot fetch URLs, S3 objects, or GitHub.
Context must be pasted by user at start of each new chat.
Single-file CONTEXT.md (concatenation of all 5 steering docs) is canonical paste source.
CONTEXT.md auto-rebuilds via git post-commit hook after any steering edit.
Location: .kiro/steering/CONTEXT.md



### Rule 26: Dhan Data API Is The Primary Data Source (GOLDEN RULE)

We pay Rs.499/month for Dhan Data API subscription (client_id 1110941563).
This is NOT optional infrastructure — it is the foundation of all strategy work.

#### MANDATORY: Use Dhan Data API for ALL of these:

**Intraday:**
- Real-time LTP via market quotes (replace flaky NSE scraping)
- 5-min candles for ORB computation (opening range high/low)
- 1-min candles for precise entry timing
- Intraday VWAP computation from tick-level data
- Historical intraday candles for backtesting entry signals

**Swing:**
- Daily OHLC candles (endpoint: /v2/charts/historical) for 20-DMA, 50-DMA, 200-DMA
- 250 days of daily data per stock for swing scanner scoring
- Volume history for relative volume computation
- ATR calculation from daily high/low/close

**F&O:**
- Real-time option chain (strikes, premiums, OI, Greeks)
- Historical option chain for IV percentile computation (252-day lookback)
- Spot price history for regime classification
- OI velocity tracking (intraday OI changes)

**Backtesting (CRITICAL — this is where edge is proven or disproven):**
- 6-12 months of 5-min candles for intraday strategy validation
- 1-2 years of daily candles for swing strategy validation
- Historical option premiums for F&O strategy validation
- Walk-forward testing on rolling windows

#### Dhan API Endpoints Available:

| Endpoint | Use Case | Interval |
|----------|----------|----------|
| POST /v2/charts/intraday | Intraday candles | 1, 5, 15, 25, 60 min |
| POST /v2/charts/historical | Daily/weekly candles | D (daily) |
| GET /v2/optionchain | Live option chain | Real-time |
| GET /v2/marketfeed/ltp | Real-time LTP | Real-time |
| GET /v2/positions | Current positions | Real-time |
| GET /v2/orders | Order history | Real-time |

#### Rules for AI Assistants:

1. NEVER use NSE scraping when Dhan API can provide the same data
2. NEVER skip backtesting because "we don't have data" — we DO have data via Dhan
3. ALWAYS cache Dhan responses (rate limit: 1 req/sec, cache TTL per data type)
4. ALWAYS suggest backtesting ideas when building new strategies
5. Before ANY strategy goes live: minimum 6 months backtest on Dhan historical data
6. Cost is FIXED (Rs.499/month) regardless of usage — maximize API calls

#### Backtesting Ideas to Continuously Sharpen Edge:

1. Walk-forward optimization: Test strategy on 6 months, validate on next 1 month, repeat
2. Regime-specific backtests: Run separately for bull/bear/sideways markets
3. Time-of-day analysis: Which hour produces best entries? (use 5-min candles)
4. Sector rotation backtest: Does entering sector leaders outperform random?
5. Volume spike detection: Backtest relative volume > 2x as entry filter
6. Stop loss optimization: Test 1.5%, 2%, 2.5%, 3% SL on same signals
7. Target optimization: Test 1:2, 1:2.5, 1:3 R:R on same signals
8. Day-of-week effect: Are Mondays/Fridays different from mid-week?
9. VIX regime backtest: Compare strategy performance at VIX 12-15 vs 15-18 vs 18-22
10. Earnings season backtest: Do pullback entries work better around results?
11. Gap fill probability: What % of gaps fill within the day? (use daily + intraday)
12. Iron Condor premium decay: Track actual theta decay vs theoretical on Nifty weekly
13. Correlation analysis: Which stocks move together? (for position concentration risk)
14. Drawdown analysis: Max consecutive losses per strategy — is it survivable?
15. Charge impact at different capitals: At what capital does charge ratio drop below 20%?

#### What This Means Practically:

- Every new strategy idea: FIRST build backtest using Dhan data, THEN decide if worth coding
- Every parameter change: backtest before and after, prove improvement with data
- Every bug fix: re-run backtest to verify no regression
- Monthly: re-run all backtests on latest data to check if edge is degrading

This is how institutional traders work. Data first. Proof first. Then deploy.

================================================================
# === STATE.md ===
================================================================
# STATE.md — Current Project State

**Last Updated**: 2026-05-18, ~13:30 CET (post-duplicate-order-bug discovery)
**Update Protocol**: Replace TODAY section at end of each session.

---

**Last Updated**: 2026-05-19 EOD - duplicate order ROOT CAUSE FOUND + FIXED
**Update Protocol**: Replace TODAY section at end of each session.

---

**Last Updated**: 2026-05-19 EOD — bugs found + dashboard Phase 1 shipped + Telegram live
**Update Protocol**: Replace TODAY section at end of each session.

---

---

---

## TODAY (2026-05-21 EOD) — BUG B FIRED IN PRODUCTION + VALIDATION DAY

### Real Money Today (vishal-live) — 3 trades, all bug-tainted in some way

| Stock | Entry | Exit | Qty | Net | Notes |
|-------|-------|------|-----|-----|-------|
| BEL | 425.75 | 421.40 | 10 | -Rs.43.50 | Force exit at 15:15 IST, planned |
| ANGELONE | 337.40 | 339.32 | 13 | +Rs.24.90 | Target hit, clean trade |
| HFCL | 143.17 | 143.76 | 62 (!) | +Rs.36.58 | Bug B fired - see below |

Total realized: +Rs.17.98
Estimated charges: ~Rs.20-25
Net after charges: ~Rs.0 to -Rs.5

### BUG B CONFIRMED IN PRODUCTION

Sequence on HFCL:
- 10:30:43 IST: BUY 31 HFCL @ 144.93 (planned entry)
- 10:30:45 IST: SL placed SELL 31 STOP_LOSS trigger 142.25 (planned)
- 11:46:52 IST: Target hit - SELL 31 @ 145.27 closed long position (planned)
- 11:46:52 IST: Original SL at 142.25 NOT CANCELLED by our code (Bug B)
- ~14:30 IST: HFCL drifted to 142.25, orphan SL triggered, Dhan executed SELL 31
- Created phantom SHORT 31 HFCL with no SL protection
- ~15:00 IST: User noticed on Dhan app, manually squared off (BUY 31 @ 142.55)

Lucky outcome: HFCL stayed range-bound, phantom SHORT closed at +Rs.0.93.
Real risk had HFCL spiked: -Rs.150 to -Rs.300 unprotected.

### Bug A (May 20 fix) - VALIDATED
- 3 trades placed today, all LONG, no rogue duplicates
- No [LONG] mislabel events
- Fix from commit 5131cd6 confirmed working for entry path
- SHORT direction validation still pending (no SHORT picks today)

### Validation Status
- vishal-live --live: continues uninterrupted (no pause, partner directive)
- Bug A entry-path fix: VALIDATED on 3 LONG trades today
- Bug B exit-path: CONFIRMED firing on HFCL - fix tonight
- Trailing SL fakeness: confirmed in logs (only memory, not Dhan modify)
- F&O paper: working, deferred to weekend cleanup

### Tonight's Bug Fix Marathon (Thu May 21 evening)
- Fix Bug B-1: cancel SL on target hit
- Fix Bug B-2: cancel SL on force exit
- Fix Bug B-3: trailing SL must modify Dhan order, not just memory
- Test on paper end-to-end before commit
- vishal-live ready for Friday with bug-free exit path

## TODAY (2026-05-20 EOD) — TATASTEEL BUG + CRONTAB SAFETY + vishal-live RE-ENABLED

### Real Money Today (vishal-live)
- TATASTEEL SHORT trade — Bug A exposed (rogue monitor double-SHORT)
- Position: 22 intended, 44 actual on Dhan, 22 unprotected by SL
- User manually closed via Dhan app at 10:18 IST
- Net: -Rs.38 after charges (within Rs.500 daily cap)
- Capital intact: ~Rs.13,580
- Daily loss limit NOT breached

### Two Critical Bugs Found and Fixed (commits today)

#### Bug 1: Bedrock Opus 4-7 timeouts (commit 5131cd6)
- config/config.yaml had bedrock_model_id = us.anthropic.claude-opus-4-7
- Opus consistently timed out 120s
- Result: ZERO trades placed at 9:30 AM and 9:45 AM crons
- Fix: Changed to us.anthropic.claude-sonnet-4-6
- Pre-flight tested: Sonnet 4.6 returns OK in ~1 second
- Also fixed in config/config_neha.yaml (gitignored, manual edit)

#### Bug A: Rogue monitor double-SHORT (commit 5131cd6)
- intraday/executor.py line 313: added "action": entry_side to record dict
- intraday/monitor.py line 86: defensive warning if action field missing
- Bug existed since SHORT support added (commit 23a0261 May 14)
- 6 days silent before TATASTEEL exposed it on real money
- Validation: pending tomorrow's first SHORT pick on fresh code

### Crontab Safety Guard (commit 7843628)
- scripts/safe_crontab_edit.sh — defensive editor with backup + validate + diff + confirm
- scripts/crontab.canonical — known-good restore source
- RULES.md Rule 25 — never pipe transformed crontab to crontab -
- Prevents wipes like May 18, May 20

### vishal-live --live RE-ENABLED for May 21
- Cron line uncommented via safe editor
- Bug A fix validates on first SHORT trade tomorrow
- Daily loss cap Rs.500 bounds real money exposure
- Per-trade Rs.4,500, max 3 trades

### F&O Paper — Actually Working
- 2 IRON_CONDORs opened (NIFTY + BANKNIFTY) at 9:33 IST
- Force exited at 15:15 IST
- Net: -Rs.1.14 (50% win rate)
- 3 issues identified for Saturday cleanup:
  - F&O Bedrock config still uses Opus 4-7 (13-min strategy selection)
  - Dhan HTTP 429 rate limits on BANKNIFTY/FINNIFTY
  - MTM cron produces fake P&L from stale option chain LTPs

### Intraday Paper Today
- vishal: HINDPETRO LONG +Rs.470.87 (winner)
- neha: BPCL LONG +Rs.331.48 (winner)
- Plus 5+ paper SHORT exits with [LONG] mislabel (Bug A fired in paper)
- Combined paper: ~+Rs.605

### Swing Module Truth Discovered
- run_swing.py is placeholder skeleton, imports only SwingConfig + is_paused
- 1,300 lines of real code in swing/*.py orphaned (never called)
- swing_trades DB schema missing action column
- Status: 30% complete (was claimed 60-90% in prior STATE.md)
- Saturday: dedicated rebuild session

### Tomorrow May 21 — vishal-live Watch Plan
- Whenever user wakes (Denmark CET, no 5 AM alarm needed)
- Rs.500 daily loss cap = sleep insurance
- Check dashboard https://d2q1cy3ph7jbd0.cloudfront.net/?profile=vishal-live
- Pull Dhan truth: scripts/sync_dhan_live.py
- Verify: SHORT trade exits with [SHORT] label (not [LONG])
- Verify: monitor places BUY (not SELL) on SHORT exit
- If buggy: emergency disable cron via safe editor

### Today's Commits
- 5131cd6 fix: Bedrock Sonnet 4.6 + rogue monitor double-SHORT bug
- 7843628 feat: crontab safety guard + Rule 25 + vishal-live re-enabled

## TODAY (2026-05-19 EOD) — 3 BUGS + PHASE 1 DASHBOARD + TELEGRAM ACTIVE

### Real Money Today (vishal-live)

- Dhan API truth P&L: +Rs.85.16
- Our DB-reported P&L: -Rs.129.97 (WRONG by Rs.215)
- Available balance EOD: Rs.13,632.80
- 3 trades executed (IOC, COHANCE, INFY)
- Daily loss limit Rs.500 NOT breached
- All positions auto-squared by Dhan at 15:30 IST

### Dashboard Phase 1 — SHIPPED (commit 96c8770)

7 files committed by Kiro:
- dashboard/v2/css/design.css (color palette, typography, spacing)
- dashboard/v2/css/components.css (cards, pills, badges)
- dashboard/v2/components/header.html (template fragment)
- dashboard/v2/universe.html (4-tier Indian universe with staleness timestamps)
- dashboard/v2/risk.html (profile config + risk gates + capital scaling)
- alerts/telegram_bot.py (skeleton: /ping, /status only)
- config/telegram.yaml.example (template, no secrets)

Live URLs verified working:
- https://d2q1cy3ph7jbd0.cloudfront.net (old dashboard, still 200)
- https://d2q1cy3ph7jbd0.cloudfront.net/v2/universe.html (200)
- https://d2q1cy3ph7jbd0.cloudfront.net/v2/risk.html (200)

### Telegram Bot — ACTIVE (running on EC2-OLD)

- Bot username: created via @BotFather
- Token: stored in config/telegram.yaml (gitignored)
- Allowed chat_id: 5422811137 (vishal)
- Process PID: 204601 (background, started today)
- Tested: /ping returned Pong successfully
- Available: /ping, /status, /help
- NOT WIRED: trade alerts, P&L alerts (Phase 4)

### Three Bugs Discovered Today (NOT fixed)

#### Bug 1 (CRITICAL): MARKET retry skips SL placement + DB write
- Yesterday's commit a2e5d66 (return None indent) is in code at correct indent
- BUT logs show MARKET retry STILL bypasses SL+DB after fill
- Pattern: 04:00:23 "MARKET retry filled 3 INFY" -> immediately "BUY IOC" (next stock)
- 5 INFY shares + 1 ADANIGREEN share unprotected all day
- There is a SECOND code path the indent fix didn't reach
- Need to read place_orders() function to find it

#### Bug 2: Cross-process token sharing
- Cron session 05 auth'd Dhan at 05:00 (PID 185464)
- Cron session 07 detected stale 3.7-hour session, re-authed
- But OLD monitor process kept running with OLD invalid token
- get_positions returned HTTP 400 from 07:30 to 09:45 (2+ hours)
- INFY position monitoring blind for entire afternoon

#### Bug 3: Force exit logs success on failed order
- Code: place_order returned HTTP 400 'Invalid Token'
- Same flow logged "OK INFY exit order placed"
- Recorded synthetic P&L -Rs.13.93
- Reality: Dhan auto-square-off closed position
- Our system told a lie

### Capital Plan Agreed Today

User goal: Rs.1 lakh/month income by June 20 (32 days from today).
Capital source: Rs.5 lakh own savings (confirmed not loan).

Math:
- Rs.5L × 0.9% daily = Rs.4,500/day = Rs.1L/month (achievable)
- Requires 60%+ win rate (unproven yet — bugs hide truth)

Staged deployment plan agreed:
- Days 1-5 (May 20-24): Fix bugs, validate clean DB-vs-Dhan
- Days 6-15 (May 27-Jun 6): Scale Rs.15K → Rs.50K → Rs.2L
- Days 16-25 (Jun 8-19): Scale to Rs.5L
- Day 26+ (Jun 20+): Income phase, Rs.5L deployed

Honest probability estimate:
- 25% chance hit Rs.1L/month by Jun 20
- 35% chance hit Rs.50-80K/month
- 25% chance hit Rs.20-40K/month
- 15% chance net loss for the month

Strict gate: NO scale up if any day shows DB-vs-Dhan drift > Rs.5.

### F&O Findings (paper, deferred)

vishal F&O paper today:
- Strategy 15 NIFTY: P&L Rs.413.75 (correct)
- Strategy 16 BANKNIFTY: P&L Rs.92,025 (FAKE — max possible was Rs.216)
- Strategy 17 FINNIFTY: P&L Rs.10 (force exit lost real prices)

Root cause: BANKNIFTY current_price has garbage values (5849, 11972).
Same Bug T resurrection (third or fourth time).
Deferred — not blocking real money.

neha F&O: HTTP 401 confirmed (no Data API on neha account, by design).

### Validation Script Status

CHECK 1 PASS — Cron fired correctly
CHECK 2 PASS — No 5-second duplicates on Dhan
CHECK 3 PASS — Trade counter at 3 (correct)
CHECK 4 PASS — Same-symbol block working
CHECK 5 FAIL — DB-vs-Dhan: 7 mismatches (Bug 1 effect)

### What's Working

- Indent fix yesterday DID work for ONE path (verified in code)
- Auth fix per-profile sessions still working
- Same-symbol block functional when DB has rows
- Trade counter holds at 3/3
- Dashboard Phase 1 v2 ready for Phase 2 wiring
- Telegram bot active, ready for Phase 4 alert wiring
- Dhan API truth source (sync_dhan_live.py) reliable
- Real money capital intact

### What's Broken

- Bug 1: MARKET retry second code path (real money unprotected)
- Bug 2: Cross-process token contamination (causes Bug 3)
- Bug 3: Force exit lies on failed orders
- F&O P&L calculation (paper-only, deferred)
- Dashboard old version P&L wrong (DB-derived, fixable in Phase 2)
- Validate_tomorrow.sh false-positives on Check 5 (compares wrong fields)

### Tomorrow's Priority (one bug at a time, no plan jumps)

1. Read place_orders() function structure
2. Find Bug 1 second path
3. Propose one-block patch
4. User approves
5. Apply to executor.py
6. Test on paper for one day
7. THEN consider scaling capital

Decision pending tomorrow:
- Old dashboard P&L fix (read from dhan_live.json instead of DB)
  → Safe display-only fix
  → Can be done without lifting intraday freeze

### Don't Touch (working)

- intraday/executor.py line 198 (yesterday fix correct)
- intraday/auth_server.py
- config/profile.py
- scripts/sync_dhan_live.py
- alerts/telegram_bot.py (active, leave running)
- dashboard/v2/* (Phase 1 done)

### Cron Status

OLD EC2: vishal-live LIVE + paper + F&O all running
NEW EC2: empty (neha-live STOPPED)

### Today's Session Architecture

Three parallel tracks worked:
1. Trading: bug discovery + capital plan (vishal + Claude)
2. Dashboard Phase 1: Kiro fresh session (succeeded after SCP workaround)
3. Telegram bot: setup + activation

All three tracks landed in single commit 96c8770.

### Cumulative Real Money May 12-19

- Total real-money trades closed: ~6
- Real cumulative P&L (Dhan truth): -Rs.700 to -Rs.1,500 estimate
- Charges burden: Rs.50-70 per round-trip on small positions

---

## PREVIOUS SESSION (2026-05-19 morning) — EXECUTOR.PY INDENT FIX (a2e5d66)


### Session Outcome
- Discovered Dhan optionchain code had 3 spec bugs (client-id header, securityId, payload format)
- Patched all 3 per official Dhan v2 docs
- Discovered root cause of HTTP 401: Data API not subscribed (paid add-on Rs.499/month)
- F&O segment activated on Dhan account (client_id 1110941563)
- Data API subscribed Rs.499/month — pre-flight test confirmed 470 strikes returning real data
- Built backtest engine v0.1 (data loader + scanner replay) using Dhan historical OHLC API
- Verified F&O Monday cron path end-to-end (auth + chain fetch + MTM)

### Commits Today (newest first)
- 562030d — feat: backtest engine v0.1 — Dhan historical OHLC + scanner replay
- b714f1d — docs: capture Bug T sub-bugs (T-1/T-2/T-3) + neha-live password fix
- 4ada2c4 — docs: sync STRATEGY active bugs + RULES cron schedule
- 4867ef0 — fix: Bug T-1/T-2/T-3 sub-bugs (cron, paper auth, force_exit)
- 2584676 — fix: neha-live password + login mapping

### What Was Built
**intraday/dhan_broker.py:**
- `get_historical_ohlc()` method — Dhan /v2/charts/intraday endpoint
- Verified: 750 candles for TCS over 11 trading days

**backtest/ (NEW MODULE):**
- `data_loader.py` — fetch + cache historical OHLC (200ms rate limit, 5-min/1-min/15-min/60-min candles)
- `scanner_replay.py` — replay scanner v3 scoring on past data using 9:30 AM snapshot
- `results/` — JSON output per backtest run
- Nifty 50 universe hardcoded (50 symbol→securityId mappings)

### Backtest v0.1 — HONEST SCOPE LIMITATIONS
First test run: 5 stocks (TCS, INFY, HDFCBANK, RELIANCE, ICICIBANK), 4 trading days
Result reported by Kiro: "75% avg hit rate"

**Reality check on the 75% number:**
- Test universe was only 5 stocks
- "Hit rate" comparison fell back to comparing scanner picks vs EOD performers OF THE SAME 5 STOCKS
- daily_top_performers DB lookup failed (table empty for those dates)
- With 5 stocks picking 5 longs, overlap with top performers is trivial
- **Do NOT quote 75% as scanner accuracy. It's noise on a small universe.**

**What backtest CAN tell us right now:**
- Code path works end-to-end (auth → fetch → score → compare → save)
- Historical data structure is correct
- Scoring logic loads without errors

**What backtest CANNOT tell us yet:**
- Real scanner accuracy (need 50+ stock universe)
- Sector rotation impact (signal omitted — needs sector indices)
- 52w high/low impact (signal omitted — needs daily candles)
- Time-of-day variations (hardcoded 1.5x multiplier)

### Bug T Status — CODE FIXED + DATA API LIVE
- 6b8de75 (May 15) — original Bug T fix
- 4867ef0 (May 17) — sub-bugs T-1, T-2, T-3
- Tonight — Dhan v2 spec compliance (client-id, UnderlyingScrip ints, expirylist, response parsing)
- Pre-flight test verified: NIFTY chain returns 470 strikes with spot=23643.5 even off-hours
- Monday F&O paper WILL use real Dhan option chain prices

### Data API Subscription Coverage
| Profiles | client_id | Data API |
|----------|-----------|----------|
| vishal + vishal-live | 1110941563 | ✅ Subscribed Rs.499/mo |
| neha + neha-live | 1111523334 | ❌ NOT subscribed |

Decision pending: separate subscription for neha account (Rs.499/mo more) OR accept synthetic data on neha profiles.

### F&O Monday Verification (no code changes, just verification)
- Auth path: ✅ DhanBrokerClient instantiates correctly
- Option chain: ✅ 470 strikes returned with real spot price
- MTM run: ✅ executes (0 updated = correct, no open strategies after May 15 cleanup)
- Crontab entries verified:
  - 50 3 * * 1-5 — vishal F&O daily (9:20 AM IST)
  - 52 3 * * 1-5 — neha F&O daily (9:22 AM IST)
  - 54 3 * * 1-5 — vishal-live F&O daily paper (9:24 AM IST)
  - */30 4-9 * * 1-5 — F&O MTM updates every 30 min

### Caveat: scripts/fno_mtm_run.py standalone fails
Running `python scripts/fno_mtm_run.py` directly fails with `ModuleNotFoundError: No module named 'fno'`.
The cron wrapper `scripts/fno_mtm_update.sh` does `cd ~/dev-sandbox` first, so cron will work.
Just don't run the .py file directly without cd to project root.

---

## PREVIOUS SESSION (2026-05-17) — BUG T SUB-BUGS + NEHA-LIVE PASSWORD

### Session Outcome
- Bug T fix from May 15 had 3 sub-bugs found by Kiro on May 16-17
- T-1: MTM cron replaced broken one-liner with scripts/fno_mtm_run.py
- T-2: Paper mode now auths real Dhan broker for option chain fetch
- T-3: force_exit_all computes current_premium instead of passing 0
- neha-live dashboard password + login mapping fixed
- Pillar docs synced (STRATEGY active bugs + RULES cron schedule)

### Commits Today (newest first)
- 4ada2c4 — docs: sync STRATEGY active bugs + RULES cron schedule
- 4867ef0 — fix: Bug T-1/T-2/T-3 sub-bugs (May 17, 14:55 IST)
- 2584676 — fix: neha-live password + login mapping (May 16, 21:38 IST)

### Bug T Status — NOW PROPERLY FIXED
Original Bug T fix on May 15 (commit 6b8de75) had 3 holes:
- T-1: cron one-liner broken — wrapper script created
- T-2: paper mode skipped Dhan auth — option chain returned nothing
- T-3: force_exit passed current_premium=0 — synthetic P&L on exits

All 3 patched in commit 4867ef0. Now needs full Monday May 18 validation.

### Pillar Doc Sync (commit 4ada2c4)
- STRATEGY.md: ACTIVE BUGS table updated (removed EE/FF/GG/SHORT-RR/SCANNER as fixed; added Recently Fixed log)
- STRATEGY.md: NEXT TO BUILD updated (Monday validation list, current week tasks)
- RULES.md: Section 6 cron schedule now includes F&O MTM + neha-live S3 syncs

---

## PREVIOUS SESSION (2026-05-15) — TRIPLE-STREAM SESSION

### Session Outcome
- Stream 1: Scanner v3 bugfixes (Bugs 1, 2, 3 from Day 1 production)
- Stream 2: F&O Bug T fix — real Dhan price paper trading
- Stream 3: Bug 6 fix — neha-live data visibility from OLD EC2 (DB + dashboard sync via S3)
- Stream 4: 4 new steering docs added
- Bug 5 discovered EOD: max_trades_per_day not enforced (real cost ~Rs.220 today)

### Commits Today (newest first)
- 6b8de75 — feat: Bug T fix — F&O real-price MTM + exit triggers + option chain cache
- 5d79c29 — docs: add FNO_STRATEGY.md
- 3f3fdbe — docs: add BUSINESS_DOC + TECHNICAL_DOC + GLOSSARY to steering/
- 7777382 — feat: live_status + eod_summary scripts + Bug 5 status fix + Bug 6 neha-live sync
- abb236e — fix: Bug 6 - sync neha-live.db OLD<->NEW via S3
- a0ec15e — fix: buffered limit (+0.3% tick-aligned) + MARKET fallback for conf>=8 (Bug 3)
- 68e910c — fix: NSE losers endpoint dead — use SecLwr20 from gainers (Bug 2)
- a9df59b — fix: momentum-aware volume filter (Bug 1)

### Real Money Trades This Week
| Date | Profile | Stock | Direction | Net P&L |
|------|---------|-------|-----------|---------|
| May 12 | vishal-live | ONGC LONG | -Rs.53.80 |
| May 12 | vishal-live | WIPRO SHORT | -Rs.20.00 |
| May 13 | vishal-live | HINDZINC LONG | -Rs.28.30 |
| May 14 | vishal-live | VEDL x10 @ 334.30 | TBD |
| May 14 | neha-live | SAIL x19 @ 206.42 | -Rs.63 |
| May 15 | vishal-live | INFY x4 @ 1124.10 | TBD (open EOD) |
| May 15 | vishal-live | HDFCBANK x5 @ 779.90 | TBD (open EOD) |
| May 15 | vishal-live | SAREGAMA x10 @ 411.90 | NEVER FILLED — Bug 3 |

Cumulative: ~-Rs.165 closed + Bug 5 cost ~Rs.220 today

---

## STREAM 1: SCANNER/EXECUTOR BUGS — FIXED

### Bug 1 (CRITICAL): Scanner saw only 169/500 stocks — a9df59b
- Root: 500K volume filter rejected stocks at 9:30 AM
- Fix: Pass if change_pct >= 4% AND volume >= 100K
- File: intraday/scanner.py

### Bug 2 (HIGH): NSE losers API dead — 68e910c
- Root: ?index=losers returns "Missing index or key."
- Fix: Use SecLwr20 from gainers response
- File: fetchers/nse_market_movers.py
- Verified: 20 losers (NOIDATOLL 16.55% sample)

### Bug 3 (HIGH): Limit orders fail on fast movers — a0ec15e
- Root: SAREGAMA limit at LTP did not fill in 10s
- Fix: +0.3% buffer (1.003x LONG, 0.997x SHORT) + tick-align + MARKET fallback if conf>=8
- File: intraday/executor.py

### Bug 4: NOT A BUG (cron just hadnt fired)

### Bug 5 (CRITICAL — DISCOVERED EOD): max_trades_per_day bypassed
- Root: _restore_daily_state only counted CLOSED trades. OPEN didnt count.
- Effect: Continuous scan saw "0 trades placed" -> bypassed daily limit
- Real cost: vishal-live placed 7 trades (limit 3). Lost ~Rs.223.
- Fix: Counts all BUY except REJECTED/CANCELLED/FAILED/ABANDONED/PENDING
- File: intraday/risk_manager.py
- Status: Fixed in code, needs Monday validation

---

## STREAM 2: F&O BUG T FIX — REAL DHAN PRICES

### Built (commit 6b8de75)

**fno/option_chain_cache.py** (NEW)
- 5-min TTL cache shared across profiles
- Cache: cache/option_chain__.json
- 2-sec rate limiting
- Graceful failure

**fno/pnl_calculator.py** (NEW)
- Pure logic, accepts get_chain_func callable (data-source agnostic)
- compute_leg_pnl(), compute_strategy_pnl(), update_strategy_pnl_in_db()
- SELL: (entry - current) * qty | BUY: (current - entry) * qty

**fno/monitor.py** (MODIFIED)
- Added update_all_open_strategies(profile)
- Exit triggers per strategy:
  - IRON_CONDOR: 50% max profit OR 1.5x max loss OR <=1 day expiry
  - SHORT_STRADDLE/STRANGLE: 30% credit OR 2x credit loss OR expiry day 3 PM
  - BULL_PUT/BEAR_CALL_SPREAD: 70% credit OR full loss OR <=2 days expiry
  - DIRECTIONAL_*: 50% gain trail OR 30% loss OR before 2 PM if no movement

**DB changes (all 4 DBs)**
- Added current_price column to fno_trades
- Marked 84 stale open trades CLOSED (synthetic):
  - vishal: 48 | neha: 24 | vishal-live: 12 | neha-live: 0

**Cron added (OLD EC2 only)**
*/30 4-9 * * 1-5 update_all_open_strategies for vishal-live, vishal, neha

### Validation BLOCKED until Monday
- Dhan optionchain returned HTTP 401 + 404 fallback (after-hours)
- Dhan auth itself works (positions API returned 4 items)
- Likely: optionchain only available 9:15 AM - 3:30 PM IST
- First real test: Monday May 18 morning

---

## STREAM 3: BUG 6 FIX — NEHA-LIVE VISIBILITY

### Built on NEW EC2

**scripts/sync_neha_live_db.sh**
- Pushes database/neha-live.db -> s3://.../db-sync/neha-live.db
- Cron: */15 4-10 * * 1-5

**scripts/sync_neha_live_dashboard.sh**
- Syncs dashboard/api/neha-live/ -> s3://.../api/neha-live/
- Cron: */15 4-10 * * 1-5

### S3 Architecture
- OLD EC2 sync: aws s3 sync dashboard/ ... --exclude "db-sync/*" (preserves NEW EC2 DB)
- NEW EC2: pushes neha-live DB + dashboard JSON every 15 min
- Verified: /api/neha-live/intraday_latest.json returns 200 OK

### Pending: Dashboard neha-live tab missing in UI nav (HTML update)

---

## STREAM 4: STEERING DOCS EXPANSION

| File | Status |
|------|--------|
| BUSINESS_DOC.md | NEW |
| TECHNICAL_DOC.md | NEW |
| GLOSSARY.md | NEW |
| FNO_STRATEGY.md | NEW |
| STRATEGY.md | UPDATED |
| LEARNING.md | UPDATED |
| STATE.md | UPDATED (this file) |
| HISTORY.md | UNCHANGED |
| RULES.md | UNCHANGED |

Reading order: RULES -> STATE -> STRATEGY -> LEARNING -> GLOSSARY -> BUSINESS_DOC -> TECHNICAL_DOC -> FNO_STRATEGY

---

## LIVE STATUS (2026-05-15, 23:00 IST)

### Both EC2s Running
| EC2 | IP | Profiles |
|-----|----|----------|
| OLD | 13.206.144.6 | vishal-live, vishal, neha paper, F&O (3), F&O MTM cron |
| NEW | 13.202.63.223 | neha-live ONLY + DB sync to S3 + dashboard sync |

### Git Sync Status
- OLD EC2: 6b8de75
- NEW EC2: a0ec15e
- ACTION Monday: ssh ec2-user@13.202.63.223 "cd ~/dev-sandbox && git pull"

### Active Crons OLD EC2
- */15 4-7 * * 1-5 — intraday vishal-live, vishal, neha
- 50/52/54 3 * * 1-5 — F&O daily for vishal/neha/vishal-live
- */30 4-9 * * 1-5 — F&O MTM update (NEW today)
- 5 10 * * 1-5 — Top performers capture
- 0 3-10 * * 1-5 — Dashboard S3 sync + CloudFront invalidation

### Active Crons NEW EC2
- */15 4-7 * * 1-5 — intraday neha-live
- */15 4-10 * * 1-5 — sync neha-live DB to S3
- */15 4-10 * * 1-5 — sync neha-live dashboard JSON to S3

### Capital Limits
| Profile | Capital | Max Trades | Loss Limit | VIX |
|---------|---------|------------|------------|-----|
| vishal-live | Rs.15,000 | 3 | Rs.900 | 20 |
| neha-live | Rs.10,000 | 3 | Rs.900 | 20 |
| vishal paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |
| neha paper | Rs.3,00,000 | 6 | Rs.9,000 | 18 |

---

## ACTIVE BUGS / OPEN WORK

### Critical
| ID | Description | Status |
|----|-------------|--------|
| Bug 5 | max_trades_per_day not enforced | FIXED, needs Monday validation |
| Bug T | F&O P&L synthetic | FIXED, needs Monday market-hours validation |
| Bug HH | 0 orders placed at 12:03 PM neha-live (May 14) | OPEN |
| TELEGRAM-WIRE | Module ready, not called from monitor/executor | OPEN |

### High
- Dashboard neha-live tab missing (UI update)
- SL-TIMING: SL placed before BUY confirmed fill
- Dhan optionchain validation blocked until Monday

### Medium / Low / Future
- F&O legs_json expiry_date partial fix
- Dhan + AWS credentials rotation
- Backtest engine
- News + fundamentals fetchers
- Swing live deployment
- Positional module
- Onboarding website

---

## MONDAY MORNING CHECKLIST (2026-05-18)

### Pre-Market
1. timedatectl on both EC2s
2. NEW EC2: cd ~/dev-sandbox && git pull
3. git log --oneline -3 on both

### Market Open 9:30 AM IST
1. tail -f logs/intraday_vishal-live_2026-05-18.log
2. Bug 1: "Nifty500 scan: 250+ total" (was 169)
3. Bug 2: Losers count > 0
4. Bug 3: "buffered" or "MARKET retry" on fast movers
5. Bug 5: trade counter increments correctly across continuous scans

### F&O Open 9:24 AM IST
1. Strategies have real Dhan strike prices in entry_price
2. ls cache/option_chain_*.json

### Mid-Session every 30 min
1. cat logs/fno_pnl_update.log
2. fno_trades.current_price populated
3. fno_strategies P&L updating
4. Exit triggers fire when conditions met

### EOD 3:35 PM IST
1. cat logs/top_performers.log
2. War Room scanner accuracy
3. EOD summary shows real F&O P&L

### Watch For
- Bug 5 trade counter (most important — real money)
- Bug T option chain HTTP status (401 = Dhan API issue)
- Buffer 0.3% slippage acceptable
- F&O exit triggers not firing prematurely

---

## INFRASTRUCTURE

| Item | Value |
|------|-------|
| OLD EC2 | 13.206.144.6 (i-0256713c061011a5f) |
| NEW EC2 | 13.202.63.223 (i-0233c705c9104383e) |
| Dashboard | https://d2q1cy3ph7jbd0.cloudfront.net |
| GitHub | https://github.com/vshorrghar/Intraday-Trader.git |
| Bedrock | Claude Sonnet 4.5 (us.anthropic.claude-sonnet-4-5) us-east-1 |
| AWS Profile | vishal-admin |
| Latest commit OLD | 6b8de75 |
| Latest commit NEW | a0ec15e (needs pull) |
| S3 db-sync prefix | s3://dev-sandbox-dashboard-176767908884/db-sync/ |
| S3 per-profile prefix | s3://dev-sandbox-dashboard-176767908884/api// |

---

## CAPITAL SCALING REMINDER

Phase 1: Rs.10K-15K live (current).
Phase 2 unlocks at: 50 profitable trades on real money.
Current: ~5 closed real money trades (Bug 5 inflated count today, dont count those).
Wait for 20+ validated trades on RS-First v3 + Bug 5 fix before evaluating.

---

## HOW TO RESUME ANY CHAT

Paste RULES.md + STATE.md + your question. Any AI that lectures without reading both is wasting your time.

End of STATE.md

---

## TODAY (2026-05-19 LATE NIGHT) — BUG 1 FIX + SWING SKELETON + 6 INSTITUTIONAL DOCS

### Real Money Status
- vishal-live: Rs.15K live, Bug 1 fix shipped, awaiting validation
- neha-live: STOPPED (since May 18, awaiting Bug 1 validation 5+ days clean)
- Total real money exposure: Rs.15K
- Cumulative real P&L May 12-19: -Rs.1,200 to -Rs.1,500 (Dhan truth)

### Commits Tonight
- 8b96b23: Bug 1 reconcile + Bug 3 exit honesty (CRITICAL fix)
- 646705c: Dashboard v2 swing tab (danish-eq UI ported, Indian markets)
- f84be10: Swing paper-mode skeleton (60% built)
- 5bc4cb3: 6 new institutional steering docs

### Bug 1 Fix Status
SHIPPED via commit 8b96b23. Tomorrow morning May 20 first market test.
Defense in depth: get_positions reconcile #1 + cancel-detection #2 + reconcile #3.
Validation gate: 30 trading days clean before any capital scaling per Rule 25 precedent.

### Swing Module Status — 60% Complete
DONE (commit f84be10):
- swing/sector_map.py (12 sector classifications)
- swing/models.py (SwingTradeSetup + SwingConfig dataclasses)
- swing/risk_manager.py (1% sizing, sector cap, regime, daily/weekly loss)
- swing/monitor.py (smart time stop, NEVER auto-sells winners, EXIT_FAILED audit)
- swing/manual_override.py (pause/resume/exit/status)
- fetchers/swing_earnings_list.py (manual list)
- run_swing.py (orchestrator skeleton)
- run_swing_daily.sh + run_swing_monitor.sh (wrappers)
- scripts/swing_control.py (CLI)
- scripts/swing_schema.sql (applied to all 4 DBs)
- vishal profile YAML updated with swing config

NOT BUILT YET (Phases 2, 3, 4, 13, 16):
- swing/scanner.py — 20-DMA pullback scoring (currently placeholder)
- swing/selector.py — LLM prompt for swing (currently placeholder)
- swing/executor.py — CNC product_type swap (currently intraday MIS code)
- swing/dashboard.py — JSON writer (currently placeholder)
- Cron entries (Phase 13)
- Rule 25 in RULES.md (Phase 16)
- Profile YAMLs for neha, vishal-live, neha-live (only vishal done)

### Test Results
- AST parse all swing files: OK
- Pipeline dry-run: runs, prints "placeholder" messages, writes empty JSONs
- Manual override: pause/resume/exit/status all working
- DB schema applied: swing_trades + swing_audit on all 4 DBs

### 6 New Institutional Steering Docs
1. EDGE.md (387 lines) — Why each strategy should make money
2. DECISIONS.md (472 lines) — Strategic decision log, append-only
3. BUGS_AND_FIXES.md (479 lines) — Bug catalog with patterns
4. WIN_RATE_TRACKING.md (436 lines) — Statistical validation log (has [FILL_IN] markers)
5. REGIME_LOG.md (261 lines) — Daily regime template (entries start May 20)
6. TRADE_REVIEW.md (251 lines) — Daily post-mortem template (entries start May 20)

### Tomorrow's Priority (May 20)
1. Pre-market: verify Bug 1 fix at HEAD on both EC2s
2. 9:30 AM IST: tail intraday log, watch for RECONCILE: messages
3. Update WIN_RATE_TRACKING.md with REAL data extracted from intraday DBs
4. EOD: write first REGIME_LOG.md and TRADE_REVIEW.md entries
5. NO new code building tomorrow (validation day)

### Saturday/Sunday Plan
1. Run Prompt 2C: complete swing Phases 2, 3, 4, 13, 16
2. End-to-end test before Monday cron
3. Monday May 26: paper swing trading begins

### Pending Decisions
- F&O fate (REWRITE/KILL) — decide by June 1
- Capital scaling Rs.15K → Rs.30K — gated by 50+ trades + Bug 1 30-day clean
- neha-live reactivation — after Bug 1 5-day clean validation

### Don't Touch
- intraday/executor.py (Bug 1 fix is delicate, 16-space indent + reconcile logic)
- intraday/monitor.py (Bug 3 fix is in 3 locations)
- swing/* skeleton (working, awaiting Phases 2-4)
- dashboard/v2/swing/ (UI works, awaiting real swing data)

### Cumulative Stats
- Codebase: ~22,000 lines (estimated)
- Trading strategies: 4 designed, 1 live, 0 statistically validated
- Steering docs: 16 total (RULES, STATE, HISTORY, STRATEGY, LEARNING, GLOSSARY, BUSINESS_DOC, TECHNICAL_DOC, FNO_STRATEGY, CONTEXT, EDGE, DECISIONS, BUGS_AND_FIXES, WIN_RATE_TRACKING, REGIME_LOG, TRADE_REVIEW)
- Real money trades to date: ~5 closed
- Real money cumulative loss: Rs.1,200-1,500

### How To Resume Tomorrow
1. Open EC2-OLD via SSM
2. cd ~/dev-sandbox && bash scripts/build_context.sh
3. Copy CONTEXT.md to new Bedrock chat
4. Type: "Continue from 2026-05-19 EOD. Either run option C (extract real win rate) or option B (write Prompt 2C-FAST/NARROW for Kiro to complete swing)."


---

## RECONCILIATION SCRIPT BUILT (2026-05-20 03:00 IST)

### scripts/reconcile_dhan_db.py — DONE

Detects DB-vs-Dhan drift per trade. Classifies issues:
- PHANTOM_TRADE — in Dhan, missing from DB
- ORPHAN_DB — in DB, missing from Dhan
- PNL_DRIFT — P&L off by > Rs.5
- QTY_DRIFT — quantity mismatch
- OK — within threshold

Output: dashboard/api/{profile}/reconciliation_report.json
Exit code: 0 if PASS (drift <= Rs.5), 1 if FAIL

### First test result on May 19

VERDICT: FAIL (Rs.215.13 drift)

| Symbol | Issue | Drift |
|--------|-------|-------|
| ADANIGREEN | PHANTOM_TRADE (Bug 1) | -Rs.45.60 |
| COHANCE | PNL_DRIFT (Bug 1 — half qty) | +Rs.214.49 |
| INFY | PNL_DRIFT (Bug 3 — Invalid Token) | +Rs.48.03 |
| IOC | OK (Rs.1.79 minor) | within threshold |

True May 19 P&L: +Rs.85.16
DB-reported May 19 P&L: -Rs.129.97
Drift: Rs.215.13

### Cron added (OLD EC2)

10 10 * * 1-5 — sync + reconcile every weekday 3:40 PM IST

### Saturday cleanup tasks

1. Manually correct DB rows for May 12-19 corruption period
2. Update WIN_RATE_TRACKING.md with cleaned cumulative P&L
3. Verify cron firing and report appearing daily


---

## SESSION CLOSE (2026-05-20 03:35 IST) — TONIGHT'S WINS

### Code shipped (8 commits)
1. 8b96b23 — Bug 1 reconcile + Bug 3 exit honesty
2. 646705c — Dashboard v2 swing UI (danish-eq port)
3. f84be10 — Swing skeleton (60%)
4. 5bc4cb3 — 6 institutional docs
5. 6cb431d — STATE + critical Bug 1 finding
6. ed18e89 — Swing scanner + selector + executor (BRAIN)
7. (this commit) — reconcile_dhan_db.py + show_today_truth.py + cron

### Tonight's biggest discovery
True May 19 P&L: +Rs.85.16 (PROFIT)
DB-reported: -Rs.129.97 (FALSE LOSS)
Drift: Rs.215.13 corruption from Bug 1 + Bug 3

True May 19 win rate: 75% (3W / 1L)
DB-reported: 33% (1W / 2L)

System might genuinely have edge. Sample too small (4 trades) but encouraging.

### Verification tools built
- scripts/sync_dhan_live.py (was built earlier)
- scripts/reconcile_dhan_db.py (NEW tonight)
- scripts/show_today_truth.py (NEW tonight)
- Daily cron: 10 10 * * 1-5 — sync + reconcile

### Daily ritual going forward
EOD (after 3:35 PM IST):
  1. cron auto-runs sync + reconcile
  2. Open dashboard/api/vishal-live/reconciliation_report.json
  3. Status PASS = trust DB; Status FAIL = investigate

Anytime check:
  .venv/bin/python scripts/show_today_truth.py --profile vishal-live

### Outstanding for Saturday
- Swing cron entries (Phase 13)
- Rule 25 in RULES.md (Phase 16)
- Add swing config to neha, vishal-live, neha-live YAMLs
- Manually correct DB rows for May 12-19 corruption period
- Build unified dashboard (one URL all modules)

### Tomorrow's first market test
9:30 AM IST: Bug 1 fix first live test
3:40 PM IST: Reconciliation cron auto-runs
3:45 PM IST: Verify status PASS (drift < Rs.5)

If PASS: Day 1 of 30-day Bug 1 validation begins.
If FAIL: Pause real money. Investigate before next day.

### Project status snapshot
- Real money: vishal-live Rs.15K (Bug 1 fix shipped, awaiting validation)
- neha-live: STOPPED (per May 18 decision)
- F&O: paper only (Bug T pending decision June 1)
- Swing: 95% built, paper mode, cron NOT active yet
- Dashboard: working but DB-derived (lying); truth available via reconciliation
- Documentation: 16 steering docs (institutional grade)


---

## SWING MODULE TRUTH (2026-05-20 EOD discovery)

Despite commit messages claiming swing is built:
- 6c2... feat(swing): paper-mode swing trading module
- ed18e89 feat(swing): scanner + selector + executor — full trading logic

REALITY: run_swing.py is a placeholder skeleton. It imports only
SwingConfig and is_paused. It does NOT call scanner/selector/executor/monitor.
Logs print "(placeholder)" and pipeline writes empty dashboard JSONs.

Real code exists (~1,300 lines across swing/scanner.py, swing/selector.py,
swing/executor.py, swing/monitor.py) but is ORPHANED — nothing calls them.

DB schema also broken — swing_trades table missing 'action' column.

Status: TRULY 30% complete (code exists, integration missing).
Next: Saturday weekend session — rewrite run_swing.py to wire real modules.
First real swing trade: earliest Monday May 25 (paper only).


---

## TODAY (2026-05-24 EOD) — STRATEGY OVERHAUL SESSION

### Key Discovery
System was LLM-driven, not rule-based. Claude via Bedrock made ALL trade decisions.
Strategy labels (VWAP, ORB, MOMENTUM) were LLM opinions, not computed conditions.
Confidence scores INVERTED: conf 6 = 71% WR (best), conf 8 = 46% WR (worst).
min_confidence_score: 7 was filtering OUT the best trades.

### Data Analysis Run
  vishal-live:  29 trades, 28% WR, -Rs.412 net (real money Rs.15K)
  vishal-paper: 86 trades, 64% WR, +Rs.2,780 net (paper)
  neha-paper:   81 trades, 54% WR, -Rs.6,031 net (paper)

### Backtest Infrastructure Built
  backtest/rule_engine.py       — ORB+VWAP+ATR signals (NO LLM)
  backtest/run_big_test.py      — intraday + F&O combined test
  backtest/run_full_backtest.py — all strategy variants
  backtest/universes.py         — FNO_ELIGIBLE + GAP_STRATEGY_BLACKLIST

### V6 Strategy — Backtested Results (6 months, after fixing direction bug)
  Win rate:      60.0% (after sector filtering)
  Profit factor: 3.72
  Net 6 months:  +Rs.4,983 at Rs.2L capital
  Monthly avg:   +Rs.830
  Active days:   15 of 117 (selective — only on catalyst gap days)

V6 Signal definition:
  1. Stock gapped > 1.5% at open (catalyst)
  2. Nifty UP on the day (market direction filter)
  3. Price breaks opening range high (9:15-9:30)
  4. Price above VWAP (computed from open)
  5. Volume > 1.5x stock 20-day average (relative volume)
  Stop: entry - (1.5 x ATR14)
  Target: entry + (3 x ATR14) = 2:1 RR

### Sector Blacklist (stocks that fail on gap days)
  GAP_STRATEGY_BLACKLIST in backtest/universes.py:
  BPCL, HINDPETRO, CHENNPETRO, IOC (oil marketing — gap fades)
  GODREJPROP, DLF (real estate — gap fades)
  ADANIPOWER, ADANIGREEN, ADANIENT (too volatile)
  APLAPOLLO, JIOFIN, COFORGE (consistent losers)

### Top Performing Stocks on Gap Days
  HINDZINC, SHRIRAMFIN, GRASIM, POWERGRID, ULTRACEMCO
  Common trait: PSU infra, financials, manufacturing

### F&O Module Status (discovered today)
  5,400 lines already built and running paper daily (96 strategies)
  Primary strategy: Iron Condor (SELLING with hedge) — correct approach
  Real paper results: 23 IRON_CONDOR trades, Rs.4,124 profit, 78% WR
  Known bug: pnl_calculator.py shows Rs.92K on Rs.216 premium (impossible)
  Fix P&L bug before trusting any F&O numbers
  Readiness: 7/10 paper, 4/10 live

### Swing Module Status (discovered today)
  1,620 lines already built but NEVER RUN (0 trades)
  Scanner uses REAL math: SMA, RSI(2), hammer/engulfing patterns
  Strategy: 20-DMA Pullback, LONG only, CNC delivery
  Entry: near 20-DMA + RSI(2) < 10 + bullish candle
  Exit: +8% target OR -4% stop loss OR 15 days max hold
  Missing: daily OHLC data fetcher + cron entry
  Readiness: 5/10 paper, 3/10 live

### New Files Created Today
  backtest/rule_engine.py
  backtest/run_big_test.py
  backtest/run_full_backtest.py
  backtest/universes.py (with FNO_ELIGIBLE, NIFTY500, GAP_STRATEGY_BLACKLIST)
  intraday/selector_v2.py (started — rule-based V6 picker)
  config/profiles/vishal-v2.yaml (paper only, rule-based)
  audit/STRATEGY_FORENSICS.md
  audit/FNO_CODE_AUDIT.md
  audit/SWING_CODE_AUDIT.md
  vishal-docs/SONNET_LOGICS.md (18 sections, master strategy design)

### Decisions Made Today (do not relitigate)
  1. Never delete vishal-live v1 — always keep as rollback
  2. v2 (rule-based) runs alongside v1, not replacing it
  3. Paper before live — always
  4. Staged capital: paper then Rs.25K then Rs.50K then Rs.1L
  5. Three streams: intraday V6 + swing 20-DMA + F&O Iron Condor
  6. F&O = SELLING with hedge (Iron Condor), NOT buying options
  7. Long only for intraday (short signals failed — 10-20% WR)
  8. Sector blacklist applied to V6 strategy
  9. Confidence score is noise — remove or lower to 6

### Backtest Bugs Found and Fixed Today
  Bug: STOPPED_OUT showing profit (short signals treated as longs)
  Bug: Exit checked ALL candles including pre-entry
  Fix: Long-only filter (gap_pct > 0 AND direction == LONG)
  Fix: Walk candles AFTER entry_idx only
  Fix: Use c["low"] <= sl (not c["close"])

### P0 Bugs Status (from prior audit — still unfixed)
  P0-1: Force-exit-lies (most dangerous — fix first)
  P0-2: Cross-process token
  P0-3: Orphan SL on trailing-exit
  P0-4: No automated orphan detection
  P0-5: RR data integrity
  Decision: Fix after strategy edge confirmed

### Next Session Priorities
  1. Fix F&O P&L bug in fno/pnl_calculator.py
  2. Read real F&O paper performance after fix
  3. Complete selector_v2.py, wire into run_intraday.py
  4. Wire swing module: daily OHLC fetcher + cron
  5. Deploy all three in paper simultaneously

### How To Start Next Session
  Read .kiro/steering/CONTEXT.md (this file rebuilt)
  Then check: ps aux | grep run_daily
  Then check: tail -20 logs/cron_vishal.log
  Then ask: what is running, last results, top issues

================================================================
# === STRATEGY.md ===
================================================================
# STRATEGY.md — Technical Evolution Log

**Purpose**: How the system makes decisions. What changed. What is planned.
**Update rule**: Update CURRENT SYSTEM whenever code changes. Append EVOLUTION LOG.
**Read this before touching any trading code.**

---

## CURRENT SYSTEM (as of 2026-05-14, end of day)

### Scanner (intraday/scanner.py) — RS-First v3
Source: NSE Nifty 500 API (filter: price Rs.50-5000, volume > 500K)
Output: Top 15 LONG + 15 SHORT = 30 candidates
Min score threshold: >= 3 (was > 0)

#### Scoring Model — RS-First v3 (LIVE since 2026-05-14)

Signal 1: Intraday continuation change_from_open (0-5 pts) — MOST IMPORTANT
  > 4.0% = 5pts, > 2.0% = 4pts, > 1.0% = 3pts, > 0.5% = 2pts, > 0.0% = 1pt

Signal 2: Momentum strength change_pct (0-8 pts) — boosted from 0-4 to reward true gems
  > 15.0% = 8pts (rare massive winner)
  > 10.0% = 6pts (huge winner)
  > 7.0% = 5pts (strong winner)
  > 5.0% = 4pts
  > 3.0% = 3pts
  > 2.0% = 2pts
  > 1.0% = 1pt

Signal 3: Price near day high (0-2 pts)
  < 0.5% from high = 2pts, < 1.5% from high = 1pt

Signal 4: Volume confirmation (0-2 pts) — confirms only, does NOT lead
  > 5M = 2pts, > 2M = 1pt

Signal 5: FNO liquidity bonus (0-1 pt)

Signal 6: Sector rotation bonus (0-5 pts) — NEW v3
  Top 3 sector = +3pts, top 5 = +2pts, top 8 = +1pt
  Outperforming own sector by >2% = +2pts (relative strength)

#### Penalties (v3)

Fade detector (replaces old chasing penalty):
  Fell > 3% from day high = -3pts
  Fell > 1.5% from day high = -1pt
  Note: Stocks at/near day high get NO penalty regardless of total gain

Trap detector (NEW v3):
  Big gap (>5%) with no sector support (sector negative) = -5pts
  Buying climax: at 52w high + change > 8% = -2pts

#### Time-Aware Multiplier (NEW v3)

Applied to FINAL score before max(score, 0):
  First hour (9:30-10:30 IST): 1.5x — best entries
  Sweet spot (10:30-11:45 IST): 1.0x
  Caution (11:45-13:15 IST): 0.7x
  Late session (after 13:15): 0.4x

#### Why v3 Will Pick Real Gems (validation example)

Score comparison with May 14 real data + first hour 1.5x multiplier:

Symbol     v3 Score  v1 Score  Gain    From Open  Sector
SAREGAMA      31         5      +15.15%  +13.14%   Media
NLCINDIA      27         3      +14.61%   +7.27%   Power
CIPLA         25         8      +8.09%    +5.34%   Pharma
ADANIENT      24         9      +8.85%    +7.47%   Mining
VEDL          19        10      +4.99%    +3.19%   Metals
HINDALCO      11         5      +2.06%    +1.04%   Metals

v3 ranks SAREGAMA/NLCINDIA/CIPLA above VEDL.
v1 ranked VEDL #1 due to 38M raw volume.

### Selector (intraday/selector.py)
Pre-filter: 30 -> 20 candidates (price range, high_volatility flag)
LLM: Claude Opus 4.7 via AWS Bedrock us-east-1
Bedrock client: 60s read_timeout, 10s connect_timeout, 1 retry (FIXED Bug EE)
Validation: R:R >= 2.0, confidence >= threshold, direction logic
Trade history fed to LLM (last 30 days per symbol)

### Risk Manager (intraday/risk_manager.py)
VIX gates (NEW logic since May 14):
  > 25 -> SKIP entire session
  > 22 -> reduce to 1 trade max
  <= 22 -> normal trading per profile max

R:R calculation: direction-aware (FIXED SHORT-RR bug)
  LONG: rr = (target - entry) / (entry - sl)
  SHORT: rr = (entry - target) / (sl - entry)
  Reject if rr < 2.0

Daily loss caps:
  vishal-live: Rs.900 (was 600)
  neha-live: Rs.900 (was 600)
  vishal/neha paper: Rs.9,000

Per-trade max:
  vishal-live: Rs.4,500 (was 4,000)
  others: profile-specific

Late session gates (after 11 AM IST):
  Gate 1: Max trades placed -> SKIP
  Gate 2: Loss > 50% of daily limit -> SKIP
  Gate 3: REMOVED (was breadth gate)

### Executor (intraday/executor.py)
Entry order -> wait up to 10s for fill (poll 2s) -> SL order
Tick-aligned prices (Rs.0.05 NSE tick)
Direction-aware: LONG=BUY entry, SHORT=SELL entry
Security ID lookup: numeric ID resolved from config/nse_security_ids.json
Bug HH still OPEN: 0 orders placed at 12:03 PM neha-live May 14 — cause unknown

### Monitor (intraday/monitor.py)
5-min cycles via get_positions API
Live P&L: fetches from broker, falls back to NSE LTP if broker has no LTP (FIXED Bug GG)
Trailing SL after 0.5% profit
50% partial book at target
Force exit 15:15 IST
Calls broker SELL order on target/SL/force exit (not just DB updates)

### Cron Schedule (continuous since May 14)
Both EC2s: */15 4-7 * * 1-5 — every 15 min, 9:30 AM to 1:00 PM IST

OLD EC2:
  vishal-live (live), vishal (paper), neha (paper) — all */15
  F&O paper for 3 profiles at 9:20-9:24 AM
  Top performers capture at 3:35 PM IST
  Dashboard sync hourly 9 AM-5 PM IST

NEW EC2:
  neha-live (live) — */15 only

### Top Performers Capture (NEW since May 14)
Script: scripts/capture_top_performers.py
Runs: 3:35 PM IST (10:05 UTC) via cron
Captures: Top 20 NSE Nifty 500 gainers
Stores: daily_top_performers table in all 5 profile DBs
Diagnostics: Computes why_missed reason per stock for stocks we did NOT pick

Why-missed reasons computed:
  - "change_from_open X% > 8% (chasing penalty -4)" [v1 only — removed in v3]
  - "Scored lower than top 15 LONG candidates"
  - "Price > Rs.5000 (above range)" or "below range"
  - "Volume < 500K (too low)"
  - "PICKED" if we did pick it

### Dashboard War Room Tab (NEW since May 14)
URL: https://d2q1cy3ph7jbd0.cloudfront.net (click War Room tab)
Shows: Top 20 movers, scanner accuracy, why missed each one
Data source: dashboard/api/top_performers.json
Sync: scripts/sync_top_performers.py (runs after capture)

---

## EVOLUTION LOG (newest first)

### v3.5.1 — 2026-05-19 EOD (BUGS + INFRASTRUCTURE)
Commit: 96c8770 (dashboard + telegram skeleton)
No code commits for trading bugs (deferred to tomorrow).

Indent fix from a2e5d66 verified at 16-space indent in code.
But MARKET retry STILL bypasses SL+DB in production.

Conclusion: SECOND code path exists with same bug pattern.
Need to read place_orders() function to find it tomorrow.

Three new bugs documented in LEARNING.md May 19 EOD entry:
- MARKET retry second path (Bug 1, critical)
- Cross-process token sharing (Bug 2)
- Force exit lies on failure (Bug 3)

Real money exposure today bounded by:
- Daily loss limit Rs.500 (held)
- Available capital Rs.13,632 (intact)
- 5 INFY + 1 ADANIGREEN unprotected shares were lucky

Tomorrow: read place_orders() structure, find second path, patch.

Infrastructure shipped today (commit 96c8770):
- Dashboard v2 Phase 1: design system + Universe + Risk tabs
- Telegram bot skeleton active (PID 204601 background process)

Capital plan agreed: Rs.5L deployment over 32 days, Rs.1L/month target.



### v3.5 — 2026-05-19 (THE INDENT BUG — ROOT CAUSE FOUND)
Commit: a2e5d66

The bug that wore seven faces. One indent fix in `intraday/executor.py` line 198
resolves all of these previously-thought-distinct issues:

- TATASTEEL 4x duplication (May 18)
- BANDHAN/MOTHERSON/CANBK 2x (May 18)
- ETERNAL phantom trade (May 18)
- INFY 3.5x today (May 19)
- Bug 5b counter false failures
- Same-symbol block bypass
- DB-vs-Dhan P&L 14x drift
- 5 of 7 INFY shares unprotected by SL today

**The bug**:
Line 198 had `return None` at 12-space indent.
This made it a sibling of `if filled_qty == 0:` instead of a child.
Function returned None unconditionally after MARKET retry block.

**The flow** (when LIMIT rejected → MARKET retry succeeds):
- Before fix: place LIMIT → reject → place MARKET → fill → return None.
  No SL. No DB write. No monitor handoff.
- After fix: place LIMIT → reject → place MARKET → fill → place SL → DB write → monitor.

**Why it hid for so long**:
- LIMIT first-try fills worked correctly (no MARKET retry needed)
- DryRun broker can't simulate real Dhan tick-size rejections
- MARKET retry only fires on confidence >= 8 setups
- Bug only visible by comparing Dhan API output vs our DB

**How we found it**:
1. Subscribed Dhan Data API Rs.499/mo (May 17)
2. Built scripts/sync_dhan_live.py (May 19 morning) — pulled real-time orders
3. Compared dhan_live.json vs intraday_trades — saw missing rows
4. Read executor.py with cat -A — spotted indent mismatch



### v3.4 — 2026-05-17 evening (DATA API LIVE + BACKTEST FOUNDATION)
Commit: 562030d

Tonight's session unlocked two major capabilities:

**1. Dhan Data API subscription active (Rs.499/month)**
For client_id 1110941563 (vishal, vishal-live profiles).
NOT covered: client_id 1111523334 (neha, neha-live).

Unlocks:
- Real option chain reads (option_chain endpoint, 470 strikes with Greeks/IV/OI)
- Historical OHLC API (/v2/charts/intraday) — minute candles for any equity
- Live Market Feed (WebSocket) — not yet wired
- Bulk market quotes — not yet wired

**2. Backtest engine v0.1**

intraday/dhan_broker.py: added get_historical_ohlc() method per Dhan v2 spec.
Verified: 750 5-min candles for TCS over 11 trading days, real OHLC data.

backtest/data_loader.py:
- load_nifty50_universe() — 50 hardcoded symbol→securityId mappings
- fetch_and_cache_historical() — 200ms rate-limited, JSON cache per symbol/range
- Cache: cache/historical/{symbol}_{interval}min_{from}_{to}.json

backtest/scanner_replay.py:
- replay_scanner_for_date() — uses first 3 candles (9:15-9:30 AM) as scan snapshot
- _score_stock_at_930() — replicates 7 of 9 scanner v3 signals
- compare_picks_to_actuals() — falls back to self-comparison if DB top performers empty
- run_backtest() — date range loop, JSON output

**HONEST LIMITATIONS of v0.1:**

Signals replicated (7):
- Intraday continuation
- Momentum strength (vs prev close)
- Price near day high
- Volume confirmation (extrapolated 3-candle to full day)
- FNO bonus (hardcoded Nifty 50 list)
- Time multiplier (fixed 1.5x for 9:30 AM)
- Fade detector

Signals OMITTED:
- Sector rotation bonus (needs sector index data, not in OHLC)
- 52-week high/low (needs daily candles, current data is intraday)

First test run: 5 stocks, 4 days. Reported 75% hit rate but **the comparison was self-referential** (fell back to ranking same 5 stocks by their own EOD performance). Real validation needs 50+ stock universe.

### Next Steps For Backtest v0.2
1. Run with full Nifty 50 universe (50 stocks)
2. Populate daily_top_performers table for past 30 days OR fetch from Dhan
3. Add sector data fetcher to enable Signal 6
4. Add daily OHLC fetcher to enable 52w signals
5. Validate scanner accuracy on real comparison set

### v3.3 — 2026-05-17 (BUG T SUB-BUGS)
Commits: 2584676 (May 16), 4867ef0 (May 17)

After May 15 Bug T fix shipped, Kiro found 3 sub-bugs that defeated the original fix:

T-1: MTM cron one-liner broken
- Inline shell -c with embedded Python failed under cron environment
- Replaced with scripts/fno_mtm_run.py (proper Python entry)
- Wrapper scripts/fno_mtm_update.sh handles env + logging
- Cron now points to wrapper script

T-2: Paper mode skipped Dhan auth
- run_fno.py paper mode never called auth -> option_chain_cache had no client
- All option chain fetches returned None silently
- Fix: paper mode now auths real Dhan broker (read-only API calls)
- Real money trades still gated by --live flag

T-3: force_exit_all passed current_premium=0
- Force exit at expiry day 3 PM logged P&L using zero premium
- Defeated entire Bug T fix on the most important exit path
- Fix: compute current_premium from option chain BEFORE recording exit P&L

Side fix (commit 2584676):
- neha-live didn't have dashboard login entry in passwords.json
- index.html mapping for neha-live was broken
- Now: neha and neha-live separate passwords, vishal/vishal-live shared

Validation expected Monday May 18:
- F&O strategies show real entry prices in DB
- MTM cron runs every 30 min and updates current_price column
- Force exits at expiry log real P&L not zero
- neha-live dashboard accessible at ?profile=neha-live

Risks:
- Paper mode now hitting Dhan API for option chain — uses 1 API call/30min/profile
- If Dhan rate-limits, fallback to NSE bhavcopy still not built
- T-3 fix only addresses force_exit_all; other exit paths may still pass 0

### v3.2 — 2026-05-15 (BUG 5 + BUG T + STREAM 3)
Commits: a9df59b, 68e910c, a0ec15e, 6b8de75

**Bug 5 (CRITICAL — discovered EOD)**: max_trades_per_day not enforced
- _restore_daily_state in risk_manager.py only counted CLOSED status trades
- Continuous scan every 15 min saw "0 trades placed today" — counter never incremented
- Real cost today: vishal-live placed 7 trades (limit 3). Lost ~Rs.223.
- Fix: Inverted logic — counts all BUY except REJECTED/CANCELLED/FAILED/ABANDONED/PENDING
- File: intraday/risk_manager.py
- Status: needs Monday validation

**Bug T (FIXED)**: F&O paper P&L now uses real Dhan option chain prices
- New: fno/option_chain_cache.py (5-min TTL, 2s rate limit, graceful failure)
- New: fno/pnl_calculator.py (pure logic, callable data source)
- Modified: fno/monitor.py (update_all_open_strategies + exit triggers)
- DB: added current_price column, marked 84 stale trades CLOSED
- Cron: */30 4-9 * * 1-5 mark-to-market every 30 min during market hours
- Validation blocked until Monday market open (Dhan API 9:15-3:30 IST only)

**Bug 6 (FIXED)**: neha-live data invisible from OLD EC2
- NEW EC2: scripts/sync_neha_live_db.sh -> s3://.../db-sync/neha-live.db
- NEW EC2: scripts/sync_neha_live_dashboard.sh -> s3://.../api/neha-live/
- OLD EC2 hourly sync excludes db-sync/* (preserves NEW EC2 data)
- Both crons */15 4-10 * * 1-5

Validation expected Monday May 18:
- Bug 5: trade counter should increment correctly across continuous scans
- Bug T: F&O strategies show real entry prices, MTM updates in fno_pnl_update.log
- Bug 6: neha-live data accessible from OLD EC2 dashboard reads

Risks:
- Bug 5 fix may falsely block legitimate trades (low risk — verified logic)
- Bug T relies on Dhan optionchain — fallback to NSE bhavcopy if API stays 401
- F&O exit triggers untested in production — may fire prematurely

### v3.1 — 2026-05-15 (POST-V3 BUGFIX)
Commits: a9df59b, 68e910c, a0ec15e

Bugs found from Day 1 of scanner v3 in production:

**Bug 1: Scanner only saw 169/500 stocks**
- 500K volume filter was too aggressive at 9:30 AM (volume hadn't built yet)
- Fix: momentum-aware filter. Pass if change_pct >= 4% AND volume >= 100K
- File: intraday/scanner.py
- Effect: TDPOWERSYS-type early breakouts now reach scanner

**Bug 2: NSE losers API endpoint dead**
- ?index=losers returned "Missing index or key." error
- Found losers in gainers response under SecLwr20 key
- Fix: fetch_top_losers() now calls gainers endpoint, extracts SecLwr20
- File: fetchers/nse_market_movers.py
- Effect: SHORT candidates restored (was 0 for unknown duration)

**Bug 3: Limit orders don't fill on fast movers**
- SAREGAMA +7% surge: limit at LTP didn't fill in 10s, cancelled
- Fix: +0.3% buffer on entry limit (LONG: 1.003x, SHORT: 0.997x)
- Tick aligned to NSE Rs.0.05 (round * 20 / 20)
- MARKET fallback after 10s timeout if confidence_score >= 8
- File: intraday/executor.py
- Effect: Fast movers fill or fall back to MARKET on conf>=8 picks

Validation expected Monday May 18:
- Scanner output: "Nifty500 scan: 250+ total" (was 169)
- Losers fetched: count > 0
- Fast mover fills: "buffered" or "MARKET retry" log lines

Risks:
- Buffer adds 0.3% slippage tax on all trades (~Rs.7K/year estimated)
- MARKET fallback could fill +1-2% above LTP, but bounded by SL
- Bug 1 may add low-quality momentum candidates

### v3 — 2026-05-14 (END OF DAY) — LIVE TOMORROW
Commits: 23a0261, 308e8b5, ddac03e, cf80098, 25361a5, 6ef8ab5, 8fe6d03

Scanner changes:
- Removed chasing penalty (penalized real winners like SAREGAMA +15%)
- Added fade detector (only penalize stocks falling from day high)
- Boosted momentum to 0-8 pts (was 0-4 pts) — rewards +10%/+15% movers
- Added sector rotation bonus (0-5 pts) — top 3 sector gets boost
- Added time-aware multiplier (1.5x first hour, 0.4x late session)
- Added trap detector (gap with no sector support, buying climax)

Other changes:
- Bedrock 60s read_timeout (was hanging 25 min at 9:26 AM peak)
- NSE gainers API fix (returns 20 now, was returning 0)
- Live P&L fetches NSE LTP fallback (was stuck at Rs.0)
- SHORT R:R now direction-aware (was always 0.0)
- VIX logic: >25 SKIP, >22 reduce to 1 (fixed levels, not profile-relative)
- Capital limits raised: vishal-live 10K->15K, max trades 2->3, loss 600->900
- Continuous scanning every 15 min (was 3 fixed times/day)
- Top 20 capture daily with why_missed diagnostics
- War Room dashboard tab live with scanner accuracy tracker
- Telegram module config-aware (needs token in config.yaml to activate)
- Options fetcher created (NSE option chain, ATM strike, IV percentile)
- daily_top_performers table on all 5 profile DBs

Validation expected tomorrow morning:
- SAREGAMA-type stocks should rank top of candidates (was being filtered out)
- VEDL-type slow stocks should rank lower (won't dominate every day)
- Bedrock should respond within 60s (no 25 min hang)
- Scanner accuracy on War Room should improve from 3/20 to 8+/20

Risk: Win rate may drop short term (50-55% vs 60% before).
Reward: Average winner becomes 4-6% (vs 1.5%).


### v1.3 — 2026-05-14 (IN PROGRESS)
Changes attempted:
- RS-first scanner scoring (patch status UNVERIFIED — check grep RS-FIRST scanner.py)
- STRATEGY.md + LEARNING.md created
- War Room tab added to dashboard
- Identified Bug HH, GG, FF, EE

Key insight: Scanner was volume-dominated — missed all real movers.
CIPLA +6.52%, GODREJIND +12.9%, NLCINDIA +17.36% all missed on May 14.
VEDL +2.66% picked because 38M raw volume.

### v1.2 — 2026-05-14 (overnight)
- Multi-EC2 architecture: neha-live moved to NEW EC2 (13.202.63.223)
- Reason: Dhan one-IP-per-account rule
- neha-live thresholds aligned with vishal-live (confidence 7, VIX 18)
- F&O fixes: legs_json expiry_date, hedged confluence 60->20
- First F&O paper trades placed (4 IRON_CONDORs synthetic)

### v1.1 — 2026-05-13
- Bug H fixed: NSE tick size rounding (Dhan error omsErrorCode 16283)
- Bug J fixed: Force exit waits for fill before logging P&L
- Bug K fixed: SL hit + target hit place broker orders
- Bug A+D fixed: Dashboard shows real exit_price + charges
- Rule 11 added: Heredoc-only edits for .py files

### v1.0 — 2026-05-12
- First real money trade: ONGC LONG vishal-live
- Basic volume-first scanner live
- Paper trading active vishal + neha
- F&O paper active (but P&L synthetic)

---

## ACTIVE BUGS (as of 2026-05-15)

### Critical (need Monday validation)
| ID | File | Status |
|----|------|--------|
| 5 | intraday/risk_manager.py | FIXED — counts all non-rejected/cancelled BUYs as trades. Validate Monday. |
| T | fno/monitor.py + pnl_calculator.py + run_fno.py + scripts/fno_mtm_run.py | FIXED in 6b8de75 + 4867ef0 (T-1/T-2/T-3 sub-bugs). Validate Monday market hours. |
| HH | intraday/executor.py | OPEN — 0 orders placed at 12:03 PM neha-live May 14, root cause unknown |

### High
| ID | File | Description |
|----|------|-------------|
| TELEGRAM-WIRE | alerts/telegram.py | Module ready, not called from monitor/executor |
| SL-TIMING | intraday/executor.py | SL placed before BUY confirmed fill |
| L | fno/strategy_engine.py | legs_json expiry_date partial fix |
| DASHBOARD-NEHA-LIVE | dashboard/index.html | neha-live tab missing in UI nav |

### Recently Fixed (2026-05-14 to 2026-05-15)
| ID | Commit | Description |
|----|--------|-------------|
| EE | 23a0261 | Bedrock 60s read_timeout |
| FF | 23a0261, 68e910c | NSE gainers + losers (SecLwr20) |
| GG | 23a0261 | Live P&L NSE LTP fallback |
| SHORT-RR | 23a0261 | Direction-aware R:R math |
| SCANNER | 6ef8ab5, 8fe6d03 | RS-First v3 scoring verified live |
| 1 | a9df59b | Momentum-aware volume filter |
| 2 | 68e910c | NSE losers SecLwr20 |
| 3 | a0ec15e | Buffered limit + MARKET fallback |
| 6 | abb236e, 7777382 | neha-live S3 sync |

---

## NEXT TO BUILD (priority order, as of 2026-05-15)

### Monday May 18 — Validation Day
1. Verify Bug 5 (max_trades_per_day) holds under continuous scan
2. Verify Bug T (F&O real prices) — option chain HTTP 200 during market hours
3. Verify Bug 6 (neha-live S3 sync) — data visible from OLD EC2 dashboard
4. Verify Bugs 1, 2, 3 (scanner v3.1) on live market data

### This Week
1. Fix Bug HH (0 orders placed) — root cause investigation
2. Wire Telegram alerts (TELEGRAM-WIRE) — phone notifications on real money
3. Fix dashboard neha-live tab (UI nav)
4. Fix SL-TIMING (wait for BUY fill before placing SL)

### Next Week
1. Swing module foundation
2. Backtest framework start
3. Pre-market intelligence (SGX Nifty, FII data at 8:30 AM)
4. Evaluate F&O strategies after 7 days clean MTM data

### This Month
1. Positional module
2. Onboarding website live (Kiro prompt ready)
3. Scale to Rs.50K after 50 profitable trades

---

## BEDROCK CLIENT FIX (exact code)

Current (broken — no timeout):
  self.client = boto3.client("bedrock-runtime", region_name=region)

Fix needed:
  from botocore.config import Config
  self.client = boto3.client(
      "bedrock-runtime",
      region_name=region,
      config=Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 1})
  )

---

## CONTINUOUS SCANNING PLAN

Current: 2 scans/day (9:26 AM, 12:01 PM)
Target: Every 15 min from 9:30 to 13:00

Cron change needed on OLD EC2:
Remove: 56 3 * * 1-5 and 31 6 * * 1-5
Add: */15 4-7 * * 1-5 (every 15 min 9:30-13:00 IST)

Guard already exists in risk_manager:
- Daily trade limit hit -> exit quietly
- Max positions open -> exit quietly
- Good setup found -> enter

Same change needed on NEW EC2 for neha-live.


---

### v3.5.2 — 2026-05-20 (BUG A FIX SHIPPED)
Commit 5131cd6: intraday/executor.py + intraday/monitor.py

Bug pattern documented for future learning:
- record dict at line 304-322 was missing "action": entry_side
- Without this, monitor.set_trades(placed) received in-memory dict without direction
- _trade_direction() defaulted to LONG, placed SELL on SHORT exits
- For SHORT trades, this OPENED duplicate SHORTs instead of closing originals
- DryRun broker masked it for 6 days
- TATASTEEL real-money trade May 20 morning exposed it

Defensive measure added:
- monitor.py line 86: warning if trade.get("action") is None
- Catches future regressions where in-memory state diverges from DB

Validation: pending first SHORT trade through fixed code (tomorrow May 21).

### Active Bugs Update — 2026-05-20 EOD

#### Recently Fixed
| ID | Commit | Description |
|----|--------|-------------|
| BEDROCK-OPUS | 5131cd6 | Opus 4-7 timeout to Sonnet 4.6 (config.yaml + config_neha.yaml) |
| BUG-A | 5131cd6 | record dict missing action field caused rogue monitor double-SHORT |
| CRONTAB-WIPE | 7843628 | Rule 25 + safe_crontab_edit.sh + crontab.canonical |

#### Critical (validation pending)
| ID | File | Status |
|----|------|--------|
| BUG-A-VALIDATE | intraday/executor.py + monitor.py | FIXED but no SHORT trade through fixed code yet. First validation tomorrow May 21. |

#### High (Saturday cleanup)
| ID | File | Description |
|----|------|-------------|
| FNO-OPUS | fno/strategy_engine.py or config | Bedrock model still Opus 4-7, causes 13-min strategy selection delay |
| FNO-RATE-LIMIT | intraday/dhan_broker.py | No backoff on HTTP 429 from Dhan optionchain — BANKNIFTY/FINNIFTY fall back to demo |
| FNO-MTM-FAKE-PNL | scripts/fno_mtm_run.py | MTM produces fake P&L when option chain has zero LTPs (e.g., off-hours) |
| SWING-ORCHESTRATOR | run_swing.py | Placeholder skeleton — imports SwingConfig + is_paused only, doesn't call swing modules |
| SWING-DB-SCHEMA | database/*.db | swing_trades table missing action, target_price, stop_loss_price, confidence_score, strategy_type, rationale columns |

#### Open Bugs (existing, not addressed today)
| ID | File | Description |
|----|------|-------------|
| MARKET-RETRY-PATH-2 | intraday/executor.py | Second MARKET retry path may have similar bug to Bug 1 (May 19 finding) |
| CROSS-PROCESS-TOKEN | intraday/auth_server.py | Long-running monitors hold stale auth across cron sessions |
| FORCE-EXIT-LIES | intraday/monitor.py | Force exit can log success on Dhan API failure |
| TELEGRAM-WIRE | alerts/telegram_bot.py | Bot active but trade alerts not wired |


---

### Bug B CONFIRMED IN PRODUCTION - 2026-05-21

Evidence: HFCL trade 10:30-15:00 IST.
- Target hit at 11:46, exited 31 long @ 145.27
- Original SL at trigger 142.25 stayed PENDING (not cancelled)
- HFCL drifted to 142.25 around 14:30, SL fired
- Created phantom SHORT 31 @ 143.76
- Manual close required by user

Same family as Bug A but exit path:
- Bug A: in-memory state missing field, monitor wrong direction
- Bug B: code missing call to broker.cancel_order

### Active Bugs Updated

#### Critical (production-confirmed, fix tonight)
| ID | File | Description |
|----|------|-------------|
| BUG-B-TARGET | intraday/monitor.py | Target hit doesn't cancel SL on Dhan, creates orphan |
| BUG-B-FORCE | intraday/monitor.py | Force exit doesn't cancel SL, same orphan risk |
| BUG-B-TRAILING | intraday/monitor.py | Trailing SL only updates memory, doesn't modify Dhan |

#### High (deferred next session)
| ID | File | Description |
|----|------|-------------|
| FORCE-EXIT-LIES | intraday/monitor.py | Force exit logs success on Dhan API failure |
| CROSS-PROCESS-TOKEN | intraday/auth_server.py | Long-running monitors hold stale auth |
| EOD-RECONCILE-MISSING | scripts/ | No automated DB-vs-Dhan compare daily |

#### Recently Validated (working)
| ID | Commit | Status |
|----|--------|--------|
| BUG-A | 5131cd6 | 3 LONG trades May 21 clean, no duplicates |
| BEDROCK-SONNET | 5131cd6 | Sub-second LLM responses all day |
| CRONTAB-SAFETY | 7843628 | No wipes since Rule 25 added |

================================================================
# === LEARNING.md ===
================================================================
# LEARNING.md — Business Journal

**Purpose**: What happened. What we learned. Money made/lost. Decisions taken.
**Update rule**: Append after every trading day. Never delete old entries.
**This is business language — no code details. Code details go in STRATEGY.md.**

---

## WEEK 1 (May 12-16, 2026)

### May 14 — Full Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | VEDL LONG | TBD |
| neha-live | SAIL LONG | -Rs.63 approx |
| neha-live | BHARTIARTL | Rs.0 (never placed — Bug HH) |

Cumulative all real money: approximately -Rs.165

#### What The Market Did Today
- NLCINDIA ran +17% — we missed it
- GODREJIND ran +13% — we missed it
- CIPLA ran +6.5% — we missed it
- We bought VEDL which moved +2.7% and went nowhere
- Metal sector led all day (NIFTY METAL +1.79%)
- VIX stayed elevated 18.7-19.0 — system correctly cautious

#### What We Learned
1. Our scanner is a volume picker not a momentum picker
   VEDL trades 38M shares/day — always wins on volume score
   CIPLA trades 4.7M — loses on volume even though move was 3x better
   Fix: RS-first scoring — change_from_open is the key signal

2. Bedrock Opus is slow at market open
   9:26 AM = 25 min hang = missed best entry window
   10:57 AM = 4 min 18 sec = acceptable
   Market open is when everyone hits Bedrock simultaneously
   Fix needed: 60 second timeout

3. Live P&L is completely blind
   SAIL was losing Rs.63 but monitor showed Rs.0 all day
   Trailing stop loss never activates because it needs P&L
   Only safety was the Dhan SL order placed at entry
   This is the most dangerous open bug

4. Two EC2s working correctly
   neha-live on NEW EC2 placed real trade successfully
   Dhan IP whitelist confirmed — separate IP required per account

#### Decisions Made Today
- Keep Opus 4.7 (quality model) but add timeout
- Rewrite scanner scoring from volume-first to RS-first
- Build continuous 15-min scanning (catch intraday breakouts)
- Build onboarding website for new users (Kiro prompt ready)
- Created STRATEGY.md and LEARNING.md for institutional memory

#### What We Are Competing Against
- Millions of Indian retail traders checking charts every minute
- Our edge: scan 500 stocks simultaneously, zero emotion, perfect rule execution
- Our weakness today: scanning wrong stocks (volume bias)
- After RS-first fix: our edge becomes real

---

### May 14 — Evening Overhaul (7 commits, scanner fully rewritten)

#### What We Built (after market close)
Worked from 4 PM to 10 PM. Shipped 7 commits.
Scanner went from v1 (volume-dominated) to v3 (multi-signal momentum).

#### Money (no trading after market close — building only)
No trades placed. Building day, not trading day.

#### Commits Shipped
1. Bedrock 60s timeout (fixes 25-min hang at market open)
2. NSE gainers API fix (was returning 0, now returns 20)
3. Live P&L fallback (fetches NSE LTP when broker has none)
4. SHORT R:R direction-aware (was always 0.0, now correct)
5. Top 20 capture daily (with why-missed reasons)
6. War Room dashboard tab (live with scanner accuracy)
7. Scanner v2 + v3 (fade detector + sector rotation + time multiplier + trap detector)

#### What We Learned

1. Volume is confirmation, not signal
   VEDL had 38M volume daily — won every day on volume.
   But +2.66% with high volume on flat day is not the trade.
   +15% on lower volume IS the trade.
   Volume confirms a real move; it doesn't predict winners.

2. Penalizing "chasing" was killing real winners
   SAREGAMA at +13% from open got -4 chasing penalty.
   These are exactly the stocks we want — strength stays strong.
   Real chasing trap is pump-and-fade, not high gain.
   New rule: only penalize stocks falling FROM day high, not stocks AT day high.

3. Time of day matters more than expected
   Same setup at 9:30 AM has 5h 45min before force exit.
   Same setup at 12:30 PM has 3h 14min — too tight for 4% target.
   Brokerage eats short trades. Earlier = better expected return.
   Time multiplier: 1.5x first hour, 0.4x late session.

4. Sector rotation is half the trade
   Pharma stock in pharma sector +3% leading the market = strong.
   Same pharma stock when pharma sector is -1% = relative strength.
   Stock-only scoring missed this. Now sector rotation = 0-5 pts.

5. You can't fix what you don't measure
   We had no idea how many real winners we missed daily.
   Built top-20 capture to make this visible.
   30 days from now we'll have 600 data points to analyze.
   Without ground truth, scanner improvements are guesswork.

6. Direction-aware math or you bleed money on shorts
   Old code: risk = entry - stop_loss (LONG-only).
   For SHORT, this is negative, R:R = 0, sizing broke.
   Any formula that treats LONG/SHORT same will silently break.

7. Continuous scanning catches what fixed times miss
   Old: scan at 9:25 / 12:00 / 13:30 — 3 chances per day.
   New: scan every 15 min — catches mid-session breakouts.
   Late-session gates prevent revenge trading.
   Profile max-trades caps overtrading.

#### Decisions Made
- Raise vishal-live capital Rs.10K -> Rs.15K (more room for new scanner)
- Raise max trades 2 -> 3 per day per live profile
- Raise daily loss limit Rs.600 -> Rs.900
- VIX threshold raised 18 -> 20 (less skipping when scanner is better)
- Telegram module ready — set token and activate later

#### What This Means For Tomorrow
If scanner v3 works:
- Should pick SAREGAMA/CIPLA-type stocks (skipped by v1)
- Should skip VEDL-type slow stocks unless they're the best of the day
- Win rate may DROP short term (50-55% vs 60%) — bigger swings
- Average winner should grow 4-6% (vs 1.5% today)
- Net effect: higher P&L per winning day

If scanner v3 fails:
- We have data via top-20 capture to see exactly what it missed
- Why-missed reasons in War Room tab will tell us what to fix next

#### What We Are NOT Doing Tomorrow
- Not adding more scanner changes
- Not enabling Telegram alerts (need to validate scanner first)
- Not increasing capital beyond Rs.15K
- Not panicking if first day has a loss
- Not changing anything mid-session

#### Honest Self-Assessment End Of Day
- 7 commits is a lot in one day. Risk of subtle bugs.
- All imports tested and pass.
- All changes are direction-improvements based on real May 14 data.
- But this is theory until tomorrow's market opens.
- Real money only on vishal-live and neha-live — Rs.25K total exposure.
- Worst case: lose Rs.1,800 (Rs.900 each profile) — survivable.
- Best case: catch one SAREGAMA-type winner = Rs.1,500-2,500 profit.

---

### May 17 evening — Data API + Backtest Foundation (5-hour Sunday session)

#### Money
No new trades placed (Sunday — markets closed).

#### What We Built
1. Discovered + fixed 3 Dhan optionchain spec bugs (client-id header, securityId 26000→13, payload schema)
2. Subscribed Dhan Data API Rs.499/month for vishal account
3. Activated F&O segment on Dhan account
4. Added get_historical_ohlc() method to DhanBrokerClient
5. Built backtest module: data_loader + scanner_replay
6. Verified F&O Monday cron path end-to-end
7. First backtest test run: 5 stocks, 4 days

#### What We Learned

1. Data is paywall, not just code
   We spent weeks debugging "why doesn't F&O paper work?" The answer was simple: Dhan optionchain endpoint requires Rs.499/month Data API subscription. No amount of code fixing changes this.
   Lesson: when an external API returns 401, FIRST check if it's a subscription issue, not a spec issue. Would have saved Bug T saga days of confusion.

2. AI assistants are optimistic about their own work
   Kiro reported "75% hit rate" for backtest v0.1. Actual reading of the code shows the comparison fell back to self-referential ranking when DB top performers table was empty. The number is noise, not signal.
   Lesson: when AI quotes a metric, read the comparison logic. Numbers without methodology are theatre.

3. Foundation > polish
   v0.1 backtest has limitations (no sector data, omitted 52w signals, small universe). But the code path works end-to-end. Next iterations can add signals incrementally.
   Lesson: ship the foundation, document gaps honestly, iterate. Don't wait for perfect v1.0.

4. Data API enables much more than F&O
   ₹499/month was framed as "F&O cost." Actually unlocks:
   - Backtest engine (validate scanner changes before live)
   - Faster intraday LTP (replace flaky NSE)
   - Future: WebSocket real-time monitor
   - Future: bulk quotes for scanner reliability
   Real cost-per-capability is much lower than F&O-only framing suggested.

5. Multi-account API tier complications
   vishal/vishal-live share one Dhan account → Data API covered.
   neha/neha-live separate Dhan account → NOT covered.
   Lesson: account-level subscriptions don't propagate. If we want neha profiles to have real data too, need separate Rs.499/mo OR refactor to use vishal account for data fetching only (allowed since data is read-only).

6. Sunday-night cron verification matters
   F&O Monday verification today caught one issue: fno_mtm_run.py can't be run standalone. Caught now, not at 9:24 AM Monday.
   Lesson: dry-run cron paths Sunday before they fire Monday.

#### Decisions Made
- Subscribed Dhan Data API Rs.499/month (vishal account only)
- Did NOT subscribe for neha account (defer until intraday profitable for both)
- Did NOT enable any real-money F&O code path
- Did NOT modify scanner.py / executor.py / monitor.py / risk_manager.py
- Built backtest as separate module to avoid touching live trading code
- Accepted Kiro's 75% hit rate as theatre; documented limitations honestly

#### What Monday May 18 Will Tell Us
**Critical real-money tests:**
- Bug 5 (max_trades_per_day) holds under continuous scan
- Scanner v3.1 (Bugs 1, 2, 3) on first full live week
- Real money intraday outcome

**F&O paper observation (no real money, free learning):**
- F&O cron at 9:24 AM places strategies with REAL Dhan option prices for first time
- MTM cron updates every 30 min with real LTP
- First time we'll see legitimate strategy P&L numbers, not synthetic

**What we are NOT testing Monday:**
- Backtest accuracy (small universe, broken comparison)
- Telegram alerts (not wired)
- Dhan trade reconciliation (not built)
- Super order migration (not done)

#### Honest Self-Assessment
- 6 commits today, real infrastructure shipped
- Real money exposure unchanged: ~Rs.25K live, capped at Rs.1,800 max daily loss
- Data API subscription: Rs.499/month recurring cost. Justified IF intraday profitable + backtest extended + F&O eventually live.
- Risk Monday: Bug 5 has never been live-tested. Scanner v3.1 has 1 day of live data.
- Backtest engine: foundation only. Don't trust 75% number. Run with bigger universe before quoting any accuracy stats.

#### Next Session (Tuesday or next weekend)
Priority order:
1. Update backtest to full Nifty 50 universe (50 not 5)
2. Populate daily_top_performers from Dhan historical (not relying on capture cron alone)
3. Wire Telegram alerts (real-money safety priority)
4. Build Dhan trade reconciliation script
5. Decide on neha account Data API subscription based on Monday outcome

---

### May 16-17 — Bug T Sub-Bugs Discovered + Fixed

#### Money
No new trades placed (weekend Saturday + Sunday — markets closed).

#### What Happened
After Friday May 15 Bug T fix shipped, Kiro reviewed the code over the weekend
and found three sub-bugs that defeated the original fix:

T-1: MTM cron was a broken one-liner
- We embedded Python inside a shell -c string in the cron entry
- Worked when run manually, broke under cron's env
- Result: MTM cron silently did nothing
- Fix: proper script scripts/fno_mtm_run.py + wrapper sh

T-2: Paper mode never authed Dhan
- run_fno.py only called Dhan auth when --live flag was set
- Paper mode used DryRunBrokerClient
- option_chain_cache needed real Dhan client to fetch chains
- Result: every paper option chain request returned None silently
- Fix: paper mode now auths real Dhan (read-only calls only)

T-3: force_exit passed zero premium
- force_exit_all (called at expiry day 3 PM) logged P&L with current_premium=0
- This is the most important exit path for short premium strategies
- Defeated entire Bug T fix on exits
- Fix: compute current_premium from option chain before recording

Plus side fix Saturday May 16:
- neha-live dashboard password was missing from passwords.json
- index.html mapping for neha-live was broken
- Created proper separate password for neha-live

#### What We Learned
1. A "fix" isn't fixed until end-to-end runs prove it
   We thought Bug T was done Friday night.
   Three holes in the fix would have shown synthetic P&L Monday again.
   Lesson: every fix needs a validation path that exercises the full code path.
   Cron-driven fixes especially — running the script manually != cron context.

2. Cron context bites
   Inline shell -c with Python embedded is fragile.
   Cron env, Python path, working directory all differ from interactive shell.
   Always: write a script file, test it as cron-context (env -i), then schedule.

3. Paper mode drifting from live mode is dangerous
   Paper skipped Dhan auth as "optimization" — broke the data infrastructure.
   When paper and live diverge, paper data becomes worthless.
   Lesson: paper mode should differ from live ONLY at the order placement step.
   Everything else (auth, data fetch, monitoring) must be identical.

4. Audit ALL exit paths, not just one
   T-3 only addresses force_exit_all.
   Other exit paths (target hit, SL hit, manual close) may still have similar bugs.
   Lesson: when fixing P&L on exits, grep for every place P&L is recorded.

5. Weekend code review caught what Friday rush missed
   Friday session was 5+ hours, multiple streams. Tunnel vision.
   Saturday/Sunday calm review found 3 holes.
   Lesson: high-stakes fixes deserve next-day review before Monday opens.

#### Decisions Made
- All 4 commits accepted into main (3 Kiro + 1 doc sync)
- No capital changes
- Pillar docs synced to reflect new reality
- Monday validation now covers Bug T-1, T-2, T-3 in addition to original Bug T

#### What Monday May 18 Will Tell Us
If Bug T sub-bugs really fixed:
- logs/fno_pnl_update.log shows entries every 30 min during market
- fno_trades.current_price column populated with real values
- Force exits log non-zero P&L
- neha-live dashboard accessible from CloudFront

If still broken:
- T-1 fail mode: fno_pnl_update.log empty
- T-2 fail mode: option_chain cache files missing or empty
- T-3 fail mode: expiry-day exit P&L = 0 again
- Each is independently observable, easy to diagnose

#### Honest Self-Assessment
- Friday's fix wasn't actually fixed. Caught it in time.
- Real money exposure unchanged (F&O is paper).
- Pillar docs are now genuinely current (not just claiming to be).
- Bug T saga shows: complex fixes need post-session review.

---

### May 15 — Evening: F&O Bug T + Bug 6 + Bug 5 Discovery (5+ hour session)

#### Money (no new trades after market — building only)
- vishal-live: still showing INFY + HDFCBANK open from earlier (Bug 5 cost ~Rs.220)
- No additional real-money exposure

#### What We Built (after market close)
1. F&O real-price paper trading (Bug T fix)
   - option_chain_cache.py with 5-min TTL
   - pnl_calculator.py with callable data source pattern
   - update_all_open_strategies in monitor.py
   - Exit triggers per strategy type
   - Cron */30 during market hours
2. neha-live S3 sync (Bug 6 fix)
   - DB sync from NEW EC2 to S3 every 15 min
   - Dashboard JSON sync from NEW EC2 to S3 every 15 min
3. 4 new steering docs: BUSINESS_DOC, TECHNICAL_DOC, GLOSSARY, FNO_STRATEGY
4. Cleaned up 84 stale F&O trades (pre-fix synthetic data)

#### Critical Discovery: Bug 5
After Kiro built F&O fixes, EOD review revealed vishal-live placed 7 trades today.
Limit was 3. Lost ~Rs.223 from doubled-down INFY (4x) and HDFCBANK (2x).

Root cause: risk_manager only counted CLOSED trades. OPEN positions were not counted.
Continuous scanning every 15 min saw fresh slate every cycle.

Lesson: When you change architecture (single-scan -> continuous), you MUST audit every counter and gate. We added continuous scanning May 14 but did not re-audit risk_manager. The bug existed for 2 days before being noticed because Mon-Wed only had 1-2 trades anyway.

#### Lessons From This Session
1. Real money exposes architectural assumptions
   - Continuous scanning was always going to expose state-tracking bugs
   - Paper trading would have eventually shown it but slower

2. F&O paper without real prices is worthless data
   - 84 trades from May 14 are unusable
   - We had to throw them away
   - Should have built real-price tracking BEFORE running paper trades
   - Lesson for future modules: validate measurement infrastructure first

3. Dhan optionchain only works during market hours
   - Could not validate Bug T fix tonight
   - Code is right but unverified until Monday
   - Acceptable risk because it is paper money, but stressful

4. Multi-EC2 architecture creates data visibility problems
   - Bug 6 was about seeing neha-live from OLD EC2
   - Solution: S3 as shared state
   - This pattern will scale to more accounts later

5. Steering docs need to grow with complexity
   - Started with 3 (RULES, STATE, HISTORY)
   - Now 9 docs
   - Each AI session can pick relevant ones for context
   - GLOSSARY especially helps avoid term drift

#### Decisions Made
- Approved all 3 Kiro bug fixes (Bugs 1, 2, 3) at session start
- Approved Bug T architecture (real Dhan prices, callable pattern, 5-min cache)
- Approved Bug 6 architecture (NEW EC2 pushes to S3, OLD reads)
- Approved Bug 5 fix (count all non-rejected/cancelled BUYs)
- Did NOT change any capital limits or daily loss caps
- Did NOT push to NEW EC2 yet (Monday morning task)

#### What Monday May 18 Will Tell Us
If everything works:
- Bug 5: vishal-live max 3 trades, even with continuous scan attempts
- Bug T: F&O strategies have real entry prices, MTM updates every 30 min
- Bug 6: neha-live data visible in War Room from OLD EC2

If something fails:
- Bug 5: legitimate trades blocked falsely (would see "Daily limit reached" too early)
- Bug T: Dhan optionchain returns 401 even during market hours (need NSE bhavcopy fallback)
- Bug 6: S3 sync race or stale data displayed

#### Honest Self-Assessment
- 5+ commits over the day, complex architecture changes
- All imports clean, all heredoc patches verified
- Real money exposure today: ~Rs.220 lost to Bug 5 BEFORE we discovered it
- Going-forward exposure: bounded by Rs.900/day per profile (loss limit)
- F&O remains paper-only (zero real money)
- Worst case Monday: Rs.1800 loss across both live profiles (each hits limit)
- Best case: Bug 5 saves us money by enforcing limit, F&O shows real numbers

#### Next Decisions Pending
- Should dashboard neha-live tab be priority next session?
- Should we wire Telegram BEFORE more F&O work (phone alerts on real money)?
- After Monday F&O data: evaluate if Iron Condor strategies actually work
- After 7 days clean data: decide on F&O live deployment timeline

---

### May 15 — Day 1 Of Scanner v3 + Bugfix Session

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | INFY x4 @ 1124.10 | TBD (still open at session end) |
| vishal-live | HDFCBANK x5 @ 779.90 | TBD (still open at session end) |
| vishal-live | SAREGAMA x10 @ 411.90 | NEVER FILLED — 10s timeout |

Cumulative all real money: still ~-Rs.165 (no closed trades today)

#### What The Market Did Today
- TDPOWERSYS ran +8.75% on Rs.397 Cr value — we never even saw it
- SAREGAMA spiked +7.11% — scanner v3 caught it (good!) but order didn't fill
- INFY and HDFCBANK gave normal day trades — both still open at end of session
- NIFTY IT and Media sectors led — scanner v3 sector rotation working

#### What We Learned

1. Scanner universe was silently truncated to 169/500 stocks
   500K volume filter rejects stocks at 9:30 AM that haven't built volume yet.
   By end of day 239 stocks pass. At market open only 169 do.
   We were scoring 1/3 of our intended universe and didn't know.
   Fix: momentum-aware filter. If stock is up 4%+ with 100K+ volume, pass anyway.

2. NSE APIs change silently
   The ?index=losers endpoint stopped working at some point.
   Returned a string error instead of data, so our code accepted "0 losers" as valid.
   Half our scanning (SHORT candidates) was effectively broken for weeks.
   Lesson: log and alert on "fetched 0 of expected ~20" responses.

3. 10-second fill timeout kills high-momentum entries
   SAREGAMA was the perfect scanner v3 catch — confidence 8, R:R 2.2.
   But the stock was moving so fast the limit order at Rs.411.90 sat unfilled.
   We cancelled after 10s. Stock continued to Rs.428+.
   We picked the right stock and got nothing.
   Fix: +0.3% buffer on limit, MARKET fallback for confidence 8+ on fast movers.

4. Building diagnostic tools pays off Day 1
   The top performers cron we built yesterday wasn't due to fire yet.
   But the diagnostic scripts we built (NSE API testing, scanner inspection) 
   let us find all 4 bugs in one session.
   Without those tools we would have been guessing for weeks.

5. Real money exposes bugs that paper trading hides
   Paper trading doesn't care if a limit order fills in 10s — it simulates fills.
   Real money cares. SAREGAMA fill failure was invisible on paper.
   Lesson: real money is the only true validation.

6. SL bounds the risk of every "aggressive" fix
   I (the AI) was initially scared to add MARKET fallback — slippage risk!
   User pushed back: every trade has SL. Worst case is bounded.
   The fix went in. Lesson: trader mindset > coder mindset on bounded-risk decisions.

#### Decisions Made
- Approved all 3 bug fixes for live deployment Monday
- Buffer 0.3% applied to ALL limits (slippage tax accepted)
- MARKET fallback gated by confidence >= 8 only
- Did NOT change capital limits or daily loss caps
- STATE.md updated, May 14 archived to HISTORY.md

#### What Monday May 18 Will Tell Us
If fixes work:
- Scanner shows 250+ stocks (not 169)
- SHORT picks appear again
- Fast movers like SAREGAMA fill on first attempt or via MARKET fallback
- Win rate may not change immediately — small sample
- More candidates = more LLM picks = more shots at winners

If fixes fail:
- Bug 1 may flood scanner with low-quality momentum stocks
- LLM may pick worse setups due to noisier candidate list
- Buffer may cause more R:R rejections (less likely but possible)
- MARKET fallback may fill at terrible prices on volatile stocks

#### Honest Self-Assessment End Of Day
- Found and fixed 3 real bugs from one day of production data
- Each fix is targeted and reversible
- Committed and pushed clean (4 commits today)
- Both EC2s synced
- STATE.md and HISTORY.md properly maintained
- BUT: All 3 fixes are theory until Monday market opens
- Real risk: Rs.25K live capital across 2 profiles
- Worst case Monday: Rs.1,800 loss (Rs.900 each profile)
- Best case Monday: Catch one TDPOWERSYS-type winner = Rs.1,500-3,000 profit

#### Next Decisions Pending
- Should LEARNING.md and STRATEGY.md updates happen automatically per session? (Yes — going forward.)
- Should we add monitoring for "fetched 0 of expected" anomalies?
- After Monday data, evaluate if buffer 0.3% is right number


### May 13

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | HINDZINC LONG | -Rs.28.30 |
| vishal paper | multiple | +Rs.57.69 |
| neha paper | multiple | -Rs.401.53 |

#### What We Learned
- Charges matter more than we thought
  Paper showed +Rs.261 gross but +Rs.57.69 after charges
  neha paper showed -Rs.81 gross but -Rs.401.53 after charges
  Always look at net P&L not gross
- Dashboard was hiding charges (Bug A+D) — fixed today
- NSE tick size (Rs.0.05) caused Dhan order rejections (Bug H) — fixed today

---

### May 12 — First Real Money Day

#### Money
| Profile | Stock | P&L |
|---------|-------|-----|
| vishal-live | ONGC LONG | -Rs.53.80 |
| vishal-live | WIPRO SHORT | -Rs.20.00 |

#### What We Learned
- System placed real orders — architecture works
- Lost money on first two trades — expected in learning phase
- Short direction needs more validation (WIPRO SHORT unclear)

---

## PATTERN LIBRARY (grows over time)

### Patterns That Work (building evidence)
- Metal sector leadership + HINDALCO/VEDL continuation = follow sector leader
- Pharma gap up + continuing from open = usually holds through session
- VIX spike day = skip or 1 trade max with tight SL

### Patterns That Fail
- High volume PSU stocks (VEDL/ONGC/SAIL) = slow movers, poor R:R
- Entering stocks already up 10%+ at 11 AM = chasing, always loses
- Trading when VIX > 20 = wide stops, bad fills, choppy exits

### Market Timing Observations
- 9:15-9:30 AM: Most volatile, best moves START here
- 9:30-10:30 AM: Best entry window — momentum confirmed
- 10:30-12:00 PM: Mid-session, some continuation plays
- After 12:00 PM: Late entries risky, most moves 70% done
- 2:30-3:15 PM: End of day volatility, system avoids (force exit 3:15)

### VIX Observations (NSE India)
- VIX < 14: Easy market, trend days, system should be aggressive
- VIX 14-18: Normal, current thresholds appropriate
- VIX 18-20: Elevated, reduce to 1 trade, wider SL — current state
- VIX > 20: Skip day or 1 micro trade only
- VIX > 25: Full skip, capital protection mode

---

## DECISIONS LOG (append only)

### 2026-05-14: RS-first scoring rewrite
Old system: volume dominated — wrong stocks picked
New system: change_from_open is primary signal
Expected result: CIPLA/HINDALCO type stocks score higher than VEDL
Status: Patch in progress

### 2026-05-14: Multi-EC2 architecture confirmed
Each live user needs dedicated EC2
Cost: Rs.1,500/month per user
Non-negotiable: Dhan IP whitelist rule

### 2026-05-14: Upgraded to Claude Opus 4.7
Better analysis quality than Sonnet 4.5
Trade-off: Slower, more expensive
Problem found: Times out at market open
Mitigation needed: 60s boto3 timeout

### 2026-05-13: Dashboard charges visibility fixed
Was hiding gross/net difference
Now shows: gross P&L, charges, net P&L separately
Lesson: Always verify what dashboard actually shows

### 2026-05-12: First real money trade
Decision: Start with Rs.10,000, max Rs.600 loss/day
Rationale: Prove system works before scaling
Current status: Small losses, fixing underlying issues

---

## MONTHLY TARGETS

### May 2026
Target: Fix core bugs, establish baseline
- Fix scanner (RS-first) ← in progress
- Fix live P&L visibility (Bug GG)
- Fix 0 orders bug (Bug HH)
- 20+ paper trades per profile
- Establish win rate baseline
Success metric: Win rate > 50% on paper by end of month

### June 2026
Target: Prove the system
- RS-first scoring proven (2 weeks data)
- Continuous 15-min scanning live
- Telegram alerts working
- Win rate > 55% on paper
Capital: Consider Rs.25K if May shows > 55% win rate

### July-August 2026
Target: Scale carefully
- 50 profitable real trades milestone
- Scale to Rs.50K after milestone
- Swing module live on paper
Success metric: 3 months data, consistent positive months

---

## NORTH STAR

Goal: Rs.20,000-30,000 per day combined
Reality: Needs Rs.15-30L deployed + 12-18 months validation
Today: Rs.20,000 deployed (Rs.10K each vishal + neha live)
Path: Fix picks quality -> prove win rate -> scale capital -> reach goal

Today we lost Rs.165 real money.
But we identified WHY the scanner picks wrong stocks.
And we know exactly how to fix it.
That knowledge is worth more than Rs.165.

---

### May 18 — Duplicate Order Bug Discovered (Hardest Day Yet)

#### Money
| Account | DB said | Dhan actual | Reality |
|---------|---------|-------------|---------|
| vishal-live | +Rs.14 | -Rs.248 | DB off by 17x |
| neha-live | -Rs.66 | -Rs.469.50 | DB off by 7x |
| Combined | -Rs.52 | -Rs.717.52 | DB hid 14x of real loss |

Cumulative real money lost since May 12 (5 trading days): ~Rs.1,200-1,500.
Roughly 5% of combined Rs.29K capital in 5 days.
Annual run rate if continued: 50%+ losses.

#### What Happened (technical)

System places EACH trade 2-4 times instead of once. Pattern:
- TATASTEEL on vishal-live: DB shows 21 qty, Dhan shows 84 qty (4x)
- BANDHAN on neha: DB 21 qty, Dhan 42 qty (2x)
- ETERNAL on vishal-live: 38 qty traded but ZERO record in DB (phantom)
- TECHM was the only stock where qty matched (1x)

This is not Bug 5 (which was about trade count limit). This is per-order duplication.
Some path in code submits the same order to Dhan multiple times, with our DB only
recording one of them. Result: position size is multiple of what we think, P&L is
multiple of what DB shows, daily loss limit can be silently breached if positions
are large.

#### How I Found It

Neha sent screenshot from her Dhan app showing -Rs.469.50 across 5 positions.
My DB queries said -Rs.66 across 6 trades. 7x discrepancy.

I initially defended the DB number ("you only lost Rs.66, system worked").
She pushed back. I pulled real data from Dhan /v2/positions API directly.
Truth was Rs.469.50, not Rs.66. Real positions had double-quadruple quantity.

If neha hadn't pushed back, I would have told her "system worked, you lost Rs.66."
That would have been wrong. She was right to question it.

#### What I Got Wrong This Session

1. Trusted DB without verifying against broker source of truth.
   For real money decisions, broker API > our DB. Always.

2. Got stuck in fix-by-shortcut mode when tired.
   Used sed regex on crontab without verifying state. Broke crontab.
   Then used Python regex on top of that. Made it worse.
   User asked "why not just comment?" — that was the right answer.

3. Skipped backup verification.
   Made backup of empty crontab, didn't check `wc -l` was non-zero.
   Then tried to restore from empty backup later.

4. Wrote off committed setup_cron.sh as "from old project" without reading carefully.
   User pushed back: "we should have it on github no?"
   They were right. Used `git grep` and `git log -p` and found canonical schedule
   in steering docs all along.

5. Repeatedly told user to "go to sleep" / "fix tomorrow" without listening
   when they said it was 1pm CET and they had full day.
   Stopped pushing my schedule preference once they made direction clear.

#### What User Got Right

1. Pushed back on "neha only lost Rs.66" → led to discovering real Rs.469 + duplicate bug
2. Pushed back on "delete crontab line" → suggested commenting (better engineering)
3. Pushed back on "we'll reconstruct from memory" → found canonical schedule in git
4. Stayed calm when crontab was wiped — didn't catastrophize, didn't panic
5. Made clear direction: vishal-live LIVE, neha-live STOP, fix bug — no waffle

#### Decisions Made

1. neha-live trading STOPPED indefinitely (user direction)
2. vishal-live continues LIVE (user direction)
3. Real money loss of Rs.717 today acknowledged, not minimized
4. Duplicate order bug = TOP priority before any further auto-trading
5. F&O cron permanently OFF on vishal-live (real money safety)

#### Pattern To Watch For Next Session

When real money is at stake:
- Pull broker source of truth FIRST, not last
- Don't trust internal DB without reconciliation
- Verify state before changing it
- Use simplest commands when tired
- Stop and re-plan when first attempt fails
- Listen to user direction without re-arguing

The cost today was Rs.717 real money + several hours of my chaotic fixing.
The lesson: broker reconciliation is not "next weekend's task." It's required
infrastructure before we can trust ANY P&L number we report.

#### What's Working

- Auth fix earlier today (commit 7ca45ce) — per-profile sessions, client_id validation
- F&O paper now uses real Dhan prices for vishal (BANKNIFTY +Rs.25, NIFTY -Rs.175)
- Backtest v1.2 launched in background (Nifty 500 universe)

#### Outstanding For Next Session

1. Restore OLD EC2 crontab (vishal-live --live INCLUDED)
2. Investigate duplicate order bug in executor.py + cron timing
3. Build Dhan reconciliation script (urgent now, not "next weekend")
4. Talk to neha with bug-fixed system as proof
5. Backtest results review


---

### May 19 — Context Automation Workflow Decided

#### Decisions
1. Rule 22: SSM web console command format
2. Rule 23: Session capture protocol
3. Rule 24: Bedrock cannot auto-fetch external files
4. CONTEXT.md = bundle of all 5 steering docs, rebuilt via git post-commit hook
5. Workflow: paste CONTEXT.md at chat start, capture-heredoc at chat end
6. Future option: dump chat to /tmp/session_chat.txt + Kiro ingestion

#### What I (the AI) got wrong
- Suggested CloudFront URL solution claiming I could fetch it (cannot)
- Over-engineered first proposals (KB, Lambda) before acknowledging chat-channel limits
- Took 4-5 exchanges to land on simple answer

#### Action items
- [ ] Run validate_tomorrow.sh at market hours
- [ ] Decide on dashboard P&L source (live Dhan vs DB)
- [ ] Verify Rules 22/23/24 followed in next AI session

#### No money moved today
Pure architecture session. Real money status unchanged from May 18 EOD.

---

### May 19 EOD — The Indent Bug That Cost Us a Week

#### Money

| Source | Today's P&L (mid-session) |
|--------|---------------------------|
| Dhan app reality | +Rs.105.61 |
| Realized today | -Rs.98.19 (COHANCE+IOC) |
| Open unrealized | +Rs.203.80 |

Cumulative real money May 12-19: ~-Rs.1100 to -Rs.1500 (Dhan truth).

#### What we discovered

INFY today exhibited the bug pattern in textbook form:
09:30 AM cron picks INFY conf=8.
LIMIT order at Rs.1194.05 → REJECTED (Dhan tick size error 16283).
Code falls into MARKET retry path (gated by confidence >= 8).
MARKET BUY x3 fills successfully on Dhan.
Then code returns None.
SL not placed. DB row not written.

10:30 AM cron picks INFY again (same-symbol block has no DB row to see).
Same flow. 2 more shares filled on Dhan. No SL. No DB.

10:45 AM cron picks INFY a third time.
This time LIMIT fills first try (no MARKET retry).
DB row written (id=26, qty=2). SL placed for these 2 shares.

Result: 7 shares LONG on Dhan. 1 row in DB (qty=2). SL covers 2 of 7.
5 shares had ZERO stop loss protection from 09:30 to 15:15.

#### Root cause — single indent

intraday/executor.py line 198. return None at 12 spaces, should have been 16.
Four spaces. Hidden in plain sight.

#### How we found it

Three things had to happen in sequence:
1. Paid Dhan Data API Rs.499/mo (May 17). Without it, no real-time order endpoint.
2. Kiro built sync_dhan_live.py today. Wrote dashboard/api/vishal-live/dhan_live.json.
3. User noticed Dhan app +Rs.112 vs our DB different. Asked the right question.

Without all three, the bug would have hidden indefinitely.

#### What this single bug explains

| Symptom | Date | Real cause |
|---------|------|------------|
| TATASTEEL 4x duplication | May 18 | MARKET retry fired 3 extra times |
| BANDHAN/MOTHERSON/CANBK 2x | May 18 | Same |
| ETERNAL phantom 38 shares | May 18 | MARKET retry, no DB record at all |
| INFY 3.5x today | May 19 | Same |
| Bug 5b counter failures | May 18 | DB rows missing, counter reads DB |
| Same-symbol block failures | May 18-19 | DB has no rows, block sees nothing |
| DB-vs-Dhan P&L drift 14x | May 18 | Half of trades never wrote to DB |
| 5 shares unprotected today | May 19 | SL placement code never reached |

ONE indent. EIGHT visible symptoms.

#### What I (the AI) got right

1. Pushed back on "approve freshness_seconds first" — caught Kiro burying lede
2. Insisted on SL coverage check before fix (capital safety > code correctness)
3. Read Kiro's diagnosis carefully and verified the indent claim
4. Refused to rush fix during last 15 min of trading

#### What I got wrong

1. Initial Finding 1 was wrong about exit fills not being recorded
2. Suggested manual SL on Dhan app at 3:00 PM — would have wasted 13% of window
3. Approved wrong investigation path initially (DB schema mismatch)

#### What user got right

1. Asked the right framing question ("what did we do differently?")
2. Pushed back when Kiro tried to add freshness_seconds before fixing bug
3. Stayed calm with 5 unprotected shares — let force exit work
4. Explicitly said "stop worrying about INFY, focus on bug"

#### Lessons that will compound

1. Indent bugs hide behind functional code. cat -A required for serious debugging.
2. Real-time broker truth is non-negotiable. Rs.499/month Data API just paid for itself.
3. Validation scripts have bugs too. validate_tomorrow.sh gave false PASS today.
4. One bug can wear seven faces. Looking deeper would have saved a week.
5. AI must read raw broker data, not just our DB.
6. Phase fixes by capital risk, not code complexity.

#### Action items for tomorrow

- [ ] Verify a2e5d66 at HEAD on both EC2s before 9:30 AM IST
- [ ] Run validate_tomorrow.sh at morning/midday/EOD checkpoints
- [ ] Pull dhan_live.json EOD, verify DB matches Dhan within Rs.5
- [ ] Fix validate_tomorrow.sh comparison logic (gave false PASS today)

#### What we're NOT doing tomorrow

- Not adding freshness_seconds yet
- Not building dashboard tabs
- Not building Telegram bot
- Not re-enabling neha-live cron
- Not increasing capital
- Letting the fix prove itself for 3 days


---

### May 20 — User Observation: Pharma Sector Consistently Missed

#### Pattern noticed
User watching Dhan app saw Apollo Hospitals, Dr Reddy's Laboratories, and
Cipla showing up "doing well" multiple times last week. Our scanner never
picked any of them.

#### Sample data (May 20 morning, from Dhan app)
- Apollo Hospitals: +0.07% (Rs.5.50 on Rs.8026)
- Dr Reddy's Laboratories: +0.30% (Rs.4.00 on Rs.1335)
- Cipla: -1.15% today but trending up over 5 days
- Hero Motocorp: +1.02%

#### Why scanner misses these
Per RS-First v3 scoring (intraday/scanner.py):
- Signal 2 (momentum): requires >1% same-day move to score
- Signal 4 (volume): Apollo trades 500K-1M (borderline for our 2M threshold)
- Signal 6 (sector rotation): pharma rarely leads day-by-day rankings

Apollo +0.07% scores ~2-3 points. Top candidates today (e.g., INFY) score 14+.
Working as designed — our scanner targets intraday momentum, not slow trends.

#### The real lesson — strategy bias

Our intraday scanner is correctly biased toward:
- Strong same-day momentum (>2%)
- High volume confirmation (>2M daily)
- Sector leadership of the day

This means we systematically miss:
- Stocks moving 0.3% per day for 5 days (compounds to +1.5%)
- Defensive sectors (pharma, FMCG) when they outperform without spikes
- Slow-grinding uptrends without volume catalysts

#### Why this is NOT a bug to fix now

1. Charges (~Rs.50 round-trip) eat small intraday moves. Need >1% same-day
   for intraday to be profitable after charges.
2. Force-exit at 15:15 IST means we can't wait for moves to develop.
3. Lowering momentum threshold would also catch sideways noise.
4. Pharma/FMCG/defensive sectors are SWING trades by design, not intraday.

#### Right answer — build swing module

Swing module is "TO BUILD" per STATE.md.

Swing-specific scanner should target:
- Stocks trending up >0.5% per day for 5-10 day windows
- Lower volume threshold (defensive stocks have less volume)
- Sector relative strength (pharma vs Nifty, FMCG vs Nifty)
- Hold time 5-15 days, not intraday
- Wider stops (3-5% vs intraday 1.8-2%)
- Wider targets (5-10% vs intraday 3.6%)

#### Decisions

1. NO changes to intraday scanner (it's working as designed)
2. Add to next-session priorities: design swing scanner for defensive sectors
3. Swing module build sequence:
   - Define swing-specific scoring (different from intraday RS-First v3)
   - Build paper module with daily cron at 4 PM IST
   - Validate 30 days on paper before any real money
   - Pharma/FMCG/healthcare sectors are first universe to target

#### Compounding insight

User watches the actual market and notices what we miss. This is valuable
signal. Future pattern: weekly capture session for "what user noticed that
scanner missed" — informs strategy improvements.


---

### May 19 EOD — Bugs Multiply, Dashboard Phase 1 Lands, Telegram Goes Live

#### Money

| Source | Today's P&L |
|--------|-------------|
| Dhan API truth | +Rs.85.16 |
| Our DB | -Rs.129.97 |
| Drift | Rs.215 |

System lied about its own performance. Made money, claims loss.

#### Three bugs found today

After yesterday's indent fix shipped, today proved fix only worked
for ONE of two code paths. Three new bugs discovered:

1. MARKET retry path skips SL+DB write (different from yesterday's path)
2. Cross-process token sharing causes 2+ hour blind monitoring
3. Force exit logs synthetic success on Dhan API failures

5 INFY shares had no stop loss for entire afternoon. Pure luck market
didn't crash. Daily loss limit Rs.500 held only because moves were small.

#### Capital plan committed

User: Rs.1L/month income target by June 20 from Rs.5L own savings.
Probability assessment: 25% best-case, 60% modest income, 15% loss.
Staged scaling: 15K -> 50K -> 2L -> 5L over 32 days.
Hard gate: any day with DB-vs-Dhan drift > Rs.5 pauses scaling.

#### Dashboard Phase 1 — Kiro shipped despite tooling pain

Kiro spent 30 minutes fighting SSH heredoc + base64 corruption issues
that yesterday's danish-eq session didn't have (different SSH context).
Eventually used SCP for one file, succeeded. 7 files committed in 96c8770.

Two new pages live on CloudFront:
- /v2/universe.html (4-tier Indian equity universe)
- /v2/risk.html (profile config + capital scaling)

Old dashboard at root URL untouched and still working.

#### Telegram bot — activated in <10 minutes

User created bot via @BotFather, sent token.
I fetched chat_id from getUpdates, wrote config, started bot.
Tested /ping immediately, got Pong. Working as background process.

NOT yet wired:
- Trade alerts (Phase 4)
- P&L alerts (Phase 4)
- Daily summary (Phase 4)

Phase 1 scope was just /ping, /status, /help. All working.

#### What I (the AI) got right today

1. Detected indent fix was partial within 30 min of cron firing
2. Pulled real Dhan API truth via dhan_live.json instead of trusting DB
3. Found Bug 2 by examining log timeline (cross-session token issue)
4. Found Bug 3 by reading exact log lines that "succeeded" after error
5. Refused to deploy Rs.5L capital despite urgency
6. Insisted on staged scaling Rs.15K -> Rs.50K -> Rs.2L -> Rs.5L
7. Pushed back on adding F&O / swing real money during 32-day window
8. Required real money source confirmation (own savings, not loans)
9. Honest 25% probability assessment

#### What I got wrong today

1. Initial claim "indent fix worked" was wrong — should have read fuller code
2. Suggested manual SL on Dhan app at 3:00 PM IST when force exit was 15 min away
3. Spent time on F&O P&L when intraday bugs were primary
4. Almost missed Bug 2 (cross-process token) — only found by examining details

#### What user got right today

1. Clear deadline: Jun 20, Rs.1L/month, Rs.5L deployable
2. Clear capital source: own savings, not loans
3. Pushed back on "postpone F&O fix" — caused proper investigation
4. Said "stop creating plans, fix bugs" when I was over-planning
5. Confirmed staged scaling willingness
6. Created Telegram bot smoothly without confusion
7. Flagged old dashboard P&L issue immediately when noticed

#### Lessons that compound

1. One indent fix doesn't fix all paths. Same root can exist in 2-3 places.
2. Always pull broker truth first. DB lies. Dhan API doesn't.
3. Process leak across crons is real. Long-running monitors hold stale auth.
4. Logs that say "OK" can lie. Always cross-check with Dhan API.
5. Capital plan is a constraint, not a deadline. Don't let urgency override safety.
6. SCP works when SSH heredoc fights you. Use right tool.
7. Telegram bot setup takes 10 min when token + chat_id known.

#### Action items for tomorrow

- [ ] Read place_orders() function to find Bug 1 second path
- [ ] Propose one-block patch (no refactor)
- [ ] Test on paper before deploying
- [ ] If clean: validate one day before any capital change
- [ ] Decide: fix old dashboard P&L source (DB -> Dhan API)
- [ ] Don't add F&O work tomorrow

#### Honest assessment

The 32-day plan started with bugs everywhere. But the truth source
(Dhan API) and dashboard infrastructure (Phase 1) and alert pipeline
(Telegram) all working today.

Bugs are findable. Real money capital intact. Daily loss bounded.
If Bug 1 fix lands tomorrow + 3 days clean validation, scaling
plan still hits Jun 20 within probability bounds.

Bigger risk: undiscovered bug at Rs.5L scale costing Rs.10K-50K.
Mitigation: every scale step needs 5 days clean before next.


---

### May 19 — Context Automation Workflow Decided

#### What we discussed
- Pasting 5 steering docs into every Bedrock chat = friction
- Explored Bedrock KB, Lambda agents, CloudFront URL fetching
- Found honest limit: Bedrock browser chat cannot auto-fetch ANY external content
- Pasting is unavoidable; goal became minimizing friction
- User frustrated with multi-step solutions, wanted ONE command
- Vim hung on huge paste (10k+ lines) — switched to cat heredoc method
- Realized Kiro can do the segregation work (reads files on EC2)

#### Decisions
1. Single CONTEXT.md = bundle of all 5 steering docs
2. Rebuilt via git post-commit hook after any steering edit
3. Workflow: paste CONTEXT.md at chat start, capture-heredoc at chat end
4. Trigger: "capture session" --> AI generates heredoc that updates all 5 docs + CONTEXT.md
5. SSM web console is canonical command channel (Rule 22)
6. Capture protocol formalized as Rule 23
7. Paste-based context formalized as Rule 24
8. Future: Kiro ingestion of /tmp/session_chat.txt for hands-off updates

#### What I (the AI) got wrong this session
1. Suggested CloudFront URL solution claiming I could fetch it — I cannot
2. Over-engineered first proposals (KB, Lambda, agents) before acknowledging chat-channel limits
3. Confused user by mixing "EC2 reads Bedrock" (impossible) with "AI segregates in chat" (real)
4. Took 4-5 exchanges to land on the simple answer: I segregate in my response, you paste

#### What user got right
1. Pushed back when solutions were too complex
2. Pointed out CloudFront wouldn't work because I cannot read URLs
3. Insisted on ONE command instead of multi-step rituals
4. Specified vim over nano (operator preference)
5. Set scale expectation: chats can be 10,000+ lines
6. Caught that Kiro is the right tool for segregation

#### Action items for next session
- [ ] Run validate_tomorrow.sh at market hours (3 checkpoints)
- [ ] Decide on dashboard P&L source (Option B: live Dhan)
- [ ] Verify Rule 22/23/24 are being followed in next AI session
- [ ] Consider Kiro ingestion workflow for future captures

#### No money moved today
Pure architecture/process session. Real money status unchanged from May 18 EOD.



---

### May 20 — Morning Crisis: TATASTEEL Bug + Bedrock Timeout + Crontab Wipe

#### Money
| Profile | Trade | Net P&L |
|---------|-------|---------|
| vishal-live | TATASTEEL SHORT (manual exit) | -Rs.38 |
| vishal paper | HINDPETRO LONG | +Rs.470.87 |
| neha paper | BPCL LONG | +Rs.331.48 |
| vishal F&O paper | NIFTY + BANKNIFTY ICs | -Rs.1.14 |

Real money cumulative since May 12: ~-Rs.1,540

#### What Happened (chronological)
1. 9:30 IST cron fired — Bedrock Opus 4-7 timed out 120s, zero trades
2. 9:45 IST cron — same timeout
3. 10:00 IST — diagnosed model issue, switched to Sonnet 4.6 in config.yaml
4. 10:00 IST cron — LLM picked TATASTEEL SHORT, executor placed correctly
5. Monitor opened a duplicate SHORT in same second — 44 shares vs intended 22
6. User manually closed via Dhan app at 10:18 IST
7. Bug investigation found: executor.py record dict missing "action" field
8. Bug had existed since May 14 (6 days silent in production)
9. Fix shipped (commit 5131cd6) — single line addition + defensive warning
10. Crontab wiped during debugging (failed sed regex — same as May 18)
11. Restored manually from STATE.md canonical
12. Built crontab safety guard (commit 7843628)
13. vishal-live --live re-enabled for tomorrow

#### What We Learned

1. **AI assistants pattern-match on success indicators, not actual behavior.**
   Three commit messages claimed swing module was being built. Reality: 1,300 lines of orphaned code with placeholder orchestrator. Always verify by RUNNING the code, not reading commit messages.

2. **One missing field can cause catastrophic real-money bugs.**
   "action": entry_side is 3 words. Without it, monitor defaulted to LONG, placed SELL exit on SHORT trades, opened duplicate positions. Same field exists in DB and broker call. Just missed in the in-memory dict.

3. **Paper trading hides real-money bugs that depend on broker reaction.**
   Bug A fired 5+ times in paper trades over 6 days. Paper just shows weird P&L numbers. Real money on first SHORT trade through this code path immediately exposed double-position.

4. **Daily loss cap is sleep insurance.**
   User in Denmark (CET timezone), wakes hours after market open. Rs.500 cap = ~6 EUR risk. Even if Bug A fired again undetected, system auto-stops. No alarm needed for vigilance.

5. **Same crontab wipe pattern struck twice.**
   May 18 and May 20 both: crontab -l |  | crontab -. Empty stdout from failed transform = wiped crontab. Defense: safe_crontab_edit.sh validates non-empty before install.

6. **F&O is the most reliable trading module right now.**
   Despite log noise from MTM cron failures, daily F&O cron opens strategies, monitors all day, exits cleanly. -Rs.1.14 today on 2 IRON_CONDORs. Better record than intraday cumulative.

7. **AI observer (Bedrock) caught what AI builder (Kiro) missed.**
   Kiro committed "feat(swing): full trading logic" — but didn't wire orchestrator to the modules. AI observer caught this by reading run_swing.py contents directly. Trust but verify.

8. **Self-correction matters.**
   AI observer made wrong calls during session: declared F&O dead (wrong), suggested rushing swing fix (wrong), false-flagged crontab typo from terminal wrap (wrong). Acknowledged each, recalibrated. Wrong recommendations explicitly retracted. Pattern to maintain.

#### Decisions Made
- Bedrock model: Opus 4-7 to Sonnet 4.6 (verified working)
- vishal-live --live: re-enabled for May 21 (Path A: validate on real money)
- Swing module: deferred Saturday rebuild (orchestrator + DB schema + cron)
- F&O: keep enabled, fix issues Saturday (Bedrock model, rate limits, MTM cron)
- Audit dashboard: deferred Saturday
- Daily loss cap Rs.500 stays — proven sleep insurance

#### Honest Self-Assessment
- 9-hour session, mostly crisis management
- 2 critical bugs found and fixed in real-money production
- 1 Rs.499/month subscription validated (F&O works)
- 1 false claim about module completeness exposed (swing)
- Capital safe at Rs.13,580
- Tomorrow's vishal-live re-enable is genuinely risky — first SHORT through fixed code
- Bounded by Rs.500 cap, but still untested
- Right call to keep enabled with honest risk

#### Next Steps
- Tomorrow: passive watch (Rs.500 cap protects sleep)
- Saturday: swing rebuild + F&O cleanup + audit dashboard
- Don't add new features until intraday SHORT validation confirms Bug A fix
- Weekend: evaluate F&O after 5 days clean MTM data


---

### May 21 EOD - Bug A Validated, Bug B Fired in Production

#### Money
| Trade | Direction | Net P&L |
|-------|-----------|---------|
| BEL | LONG | -Rs.43.50 (force exit) |
| ANGELONE | LONG | +Rs.24.90 (target hit) |
| HFCL | LONG -> phantom SHORT -> manual close | +Rs.36.58 (lucky) |

Total realized: +Rs.17.98
After charges: ~Rs.0 to -Rs.5
Cumulative real money since May 12: ~-Rs.1,520

#### What Happened - HFCL Bug B Fire

10:30 IST: System bought 31 HFCL @ 144.93 with SL at 142.25 (correct setup)
11:46 IST: Target hit. System sold 31 @ 145.27 (closed long correctly)
11:46 IST: Original SL at 142.25 stayed PENDING on Dhan (Bug B - not cancelled)
~14:30 IST: HFCL drifted to 142.25, SL triggered, Dhan auto-sold 31
Result: Fresh SHORT 31 HFCL @ 143.76, no SL, no target, no protection
~15:00 IST: User spotted unexpected SHORT position on Dhan app
~15:00 IST: User manually closed via BUY 31 @ 142.55

Profit by accident: +Rs.36.58 because HFCL drifted down (favorable for SHORT)

#### What We Learned

1. Real money exposes bugs paper cannot.
   Bug B existed since SHORT support added (May 14). 7 days silent.
   Paper trading uses DryRunBrokerClient - no real pending orders.
   Real money fired Bug B today on first target-hit-after-paper exit pattern.

2. Phantom positions are the worst class of bug.
   Don't see in DB, don't see in dashboard, only in Dhan app.
   Without Dhan API truth pull, would be flying blind.

3. Lucky != safe.
   Today HFCL phantom SHORT closed +Rs.0.93. Could have been -Rs.300.
   Same bug, different price action, very different outcomes.

4. Eyes-on-screen at market close was the saving grace.
   Telegram alerts not yet wired.
   User noticed unexpected position via Dhan app reflexively.
   Future: EOD reconciliation script + Telegram alert mandatory.

5. Bug A fix is working as designed.
   3 LONG trades placed cleanly today. No rogue duplicates, no [LONG] mislabel.
   Fix from commit 5131cd6 is solid for entry path.
   Exit-path bugs (Bug B) untouched until tonight.

6. Charge math at small capital is brutal.
   Net realized +Rs.17.98 today. Estimated charges Rs.20-25.
   Net after charges: roughly break-even.
   At Rs.4,500/trade and Rs.7-10 charges, need >=Rs.30/trade gross to be net positive.

#### Decision Made
- vishal-live --live continues uninterrupted (partner directive: no pause)
- Tonight (Thu May 21 evening): Bug B fix marathon
- Fix B-target, B-force-exit, B-trailing
- Test on paper before commit
- Friday: vishal-live trades with bug-free exit path

#### What we are NOT doing
- Not pausing vishal-live
- Not adding F&O live, swing live, positional
- Not scaling capital until 14 consecutive bug-free days
- Not trusting commit messages without running the code

================================================================
# === GLOSSARY.md ===
================================================================
# GLOSSARY — Technical Terms Used In This Project

Quick reference for trading and technical jargon. Cross-referenced from BUSINESS_DOC.md and TECHNICAL_DOC.md.

---

## TRADING TERMS

### VIX (India VIX)
**What**: Volatility index measuring expected 30-day NIFTY 50 volatility, calculated by NSE.
**Range**: Typically 10-30. Higher = more uncertainty.
**Why we use**: Above 25 means extreme fear/uncertainty. We skip trading when VIX > 25.
**Our gates**: VIX > 25 = SKIP entire session. VIX > 22 = REDUCE to 1 trade max. VIX <= 22 = normal.

### R:R (Risk-to-Reward Ratio)
**What**: Reward divided by risk in a trade.
**Formula (LONG)**: (target - entry) / (entry - stop_loss)
**Formula (SHORT)**: (entry - target) / (stop_loss - entry)
**Example**: Buy at 100, stop at 98 (risk 2), target at 106 (reward 6) = R:R 3.0
**Our minimum**: 2.0 (we reject any trade where reward isn't at least 2x risk)
**Why important**: At R:R 2.0, we can win only 33% of trades and still break even.

### LTP (Last Traded Price)
**What**: Most recent price at which a stock traded.
**Why we use**: Reference point for current market price. Updated every few seconds.

### LIMIT Order
**What**: Order to buy/sell at a specific price OR BETTER.
**Behavior**: BUY at Rs.100 limit means "buy at Rs.100 or lower, never higher".
**Risk**: May not fill if price moves away.

### MARKET Order
**What**: Order to buy/sell at the current market price, immediately.
**Behavior**: Always fills (if liquidity exists), but at whatever price the market gives.
**Risk**: Slippage on fast-moving stocks.

### Stop Loss (SL)
**What**: A protective sell order placed below entry (for long trades).
**Trigger**: When price drops to SL level, automatic sell to limit loss.
**Our rule**: Every trade has SL placed simultaneously with entry. No exceptions.

### Trailing Stop Loss
**What**: SL that moves up as price rises, locking in profits.
**Our rule**: Activates after 0.5% profit. SL moves up to entry price (breakeven).

### Force Exit
**What**: Manually closing all positions before market close.
**Our time**: 15:15 IST (15 min before market close).
**Why**: No overnight risk on intraday positions.

### Force Exit Time
**What**: 3:15 PM IST. We close all intraday positions automatically by then.

### MIS (Margin Intraday Square-off)
**What**: Order type for same-day delivery. Position auto-closes at end of day.
**Use**: Our intraday strategy only.

### CNC (Cash and Carry)
**What**: Order type for delivery (you actually own the shares).
**Use**: Swing and positional strategies.

### NRML (Normal)
**What**: Order type for futures/options that you can carry overnight.
**Use**: F&O module.

### Tick Size
**What**: Smallest price increment. NSE = Rs.0.05.
**Our handling**: All order prices rounded to nearest Rs.0.05.

### NSE Nifty 500
**What**: Index of top 500 NSE-listed stocks by market cap.
**Our universe**: We only trade stocks in this list (not penny stocks, not micro-caps).

### Sector
**What**: Industry classification (e.g., NIFTY IT, NIFTY BANK, NIFTY METAL).
**Our usage**: Pick stocks in top 5 performing sectors. Avoid worst sectors for longs.

### Breakout
**What**: Stock breaking above resistance (recent highs).
**Setup type**: Used in intraday and swing.

### Reversal
**What**: Stock reversing direction at key support/resistance.
**Setup type**: Higher confidence required.

### Pullback
**What**: Brief retracement before continuing trend.
**Setup type**: "Buy the dip" in uptrending stocks.

### Day High
**What**: Highest price stock traded today.
**Our usage**: We prefer stocks near day high (showing strength).

### 52-Week High
**What**: Highest price in past 12 months.
**Our usage**: Swing module looks for breakouts above 52-week high.

---

## OPTIONS / F&O TERMS

### IV (Implied Volatility)
**What**: Market's expectation of future volatility, derived from option prices.
**Range**: Higher IV = more expensive options.

### IV Percentile (IVP)
**What**: Where current IV ranks vs past year (0-100).
**Why we use**: IVP > 70 = sell premium. IVP < 30 = buy premium.

### Iron Condor
**What**: Sell OTM call AND put, buy further OTM call AND put for protection.
**When**: Sideways market, high IV (above 70 percentile).
**Profit**: From time decay and IV decrease.

### Short Straddle
**What**: Sell ATM call AND put simultaneously.
**Profit if**: Stock stays near strike at expiry.
**Risk**: Unlimited if stock moves big.

### Bull Put Spread
**What**: Sell higher strike put, buy lower strike put.
**View**: Bullish or neutral.

### Bear Call Spread
**What**: Sell lower strike call, buy higher strike call.
**View**: Bearish or neutral.

### Strike Price
**What**: Price at which option can be exercised.
**Example**: NIFTY 23000 CE = call option at strike 23000.

### CE (Call European)
**What**: Call option (right to buy at strike).

### PE (Put European)
**What**: Put option (right to sell at strike).

### ATM (At The Money)
**What**: Strike price at or near current market price.
**Example**: NIFTY at 23080, ATM strike = 23100 (nearest strike to spot).

### OTM (Out of The Money)
**What**: Strike below current price for puts, above for calls.

### ITM (In The Money)
**What**: Strike below current price for calls, above for puts.

### DTE (Days To Expiry)
**What**: Days until the option expires.
**Our rule**: Avoid options with < 2 DTE (theta accelerates).

### OI (Open Interest)
**What**: Total outstanding open contracts.
**Why important**: Higher OI = more liquidity, easier exits.

### OI Velocity
**What**: Rate of change of OI.
**Why we use**: Rapid OI buildup signals direction conviction.

### GEX (Gamma Exposure)
**What**: Total gamma exposure of dealers, indicates support/resistance levels.

### VRP (Variance Risk Premium)
**What**: Difference between implied and realized volatility.
**Use**: Positive VRP = options overpriced, sell them.

### Confluence Score
**What**: Combined signal score from multiple indicators (IV, OI, GEX, VRP).
**Our gates**:
- > 75 = naked selling allowed (high conviction)
- > 60 = directional buy allowed
- > 20 = hedged strategy allowed (Iron Condor, etc.)

### Theta
**What**: Daily time decay of option value.
**Effect**: Sellers profit from theta. Buyers lose to it.

### Vega
**What**: Option's sensitivity to IV changes.

### Delta
**What**: Option's sensitivity to underlying price (0.5 = ATM call).

### Expiry Day
**What**: The day options/futures contract expires.
**Our rule**: Only IRON_CONDOR, SHORT_STRADDLE, or DIRECTIONAL strategies allowed on expiry.

---

## TECHNICAL / INFRASTRUCTURE TERMS

### Bedrock
**What**: AWS service for accessing AI models (Claude, etc.).
**We use**: Claude Sonnet 4.5 via Bedrock for stock ranking.

### Claude Sonnet 4.5
**What**: AI model from Anthropic. Released 2025.
**Our use**: Final ranking of pre-filtered candidates with rationale.

### TOTP (Time-Based One-Time Password)
**What**: 6-digit code generated by authenticator app, changes every 30 seconds.
**Our use**: Required for Dhan broker login.
**Critical**: EC2 clock must be within 30 seconds of real time.

### chrony
**What**: Linux service for keeping system clock synchronized via NTP.
**Why critical**: TOTP depends on time accuracy.

### EC2 (Elastic Compute Cloud)
**What**: AWS virtual server.
**Our setup**: 2 instances of t3.medium in Mumbai region.

### S3 (Simple Storage Service)
**What**: AWS object storage.
**Our use**: Hosting dashboard files, syncing neha-live DB between EC2s.

### CloudFront
**What**: AWS content delivery network.
**Our use**: Caching dashboard for fast access via HTTPS.

### IAM (Identity and Access Management)
**What**: AWS access control.
**Our profile**: vishal-admin (used for all project operations).

### IST (Indian Standard Time)
**What**: UTC+5:30. Market hours: 9:15 AM - 3:30 PM IST.

### UTC (Coordinated Universal Time)
**What**: Reference time. EC2 cron schedules in UTC, market in IST.
**Conversion**: 9:30 AM IST = 4:00 UTC.

### SSM (Systems Manager Session Manager)
**What**: AWS service for browser-based shell access to EC2.
**Our use**: SSH-free access to both EC2 instances.

### SQLite
**What**: File-based database (no server needed).
**Our use**: Trade records, audit log, daily summaries (one DB per profile).

### YAML
**What**: Configuration file format (human-readable).
**Our use**: Profile configs (capital limits, thresholds).

### Cron
**What**: Linux scheduler for recurring tasks.
**Our schedules**: Continuous scanning every 15 min, EOD reports, DB syncs.

### Dhan API
**What**: REST API for placing orders on NSE through Dhan broker.
**Endpoint**: api.dhan.co/v2

### NSE API
**What**: Public APIs from National Stock Exchange.
**Our use**: Live quotes, index data, top gainers/losers.

### Scanner
**What**: Code that scores all stocks and returns top candidates.
**Output**: 30 candidates (15 long, 15 short).

### Selector
**What**: Code that filters scanner output, calls LLM, validates AI picks.
**Output**: Final 1-5 trades per scan cycle.

### Executor
**What**: Code that places actual orders with broker.
**Output**: Confirmed trade IDs and DB records.

### Monitor
**What**: Code that tracks open positions every 5 minutes.
**Decisions**: Trail SL, partial book, force exit.

### Pre-filter
**What**: Mathematical rules that cut 30 candidates to 20.
**Not LLM**: Pure Python.

### Audit Log
**What**: Record of every system event (order placed, SL adjusted, etc.).
**Purpose**: Forensic analysis if something goes wrong.

### Rule 20.7
**What**: Project rule that AI must remind user to git pull on NEW EC2 after every push from OLD EC2.
**Why**: Prevents stale code on NEW EC2.

---

## DATA / METRICS TERMS

### Win Rate
**What**: Percentage of trades that closed profitable.
**Our target**: >55% sustained.
**Example**: 6 winners out of 10 trades = 60% win rate.

### Drawdown
**What**: Peak-to-trough decline in capital.
**Example**: Capital was Rs.15,000, dropped to Rs.13,500 = 10% drawdown.
**Our limit**: Daily loss limit Rs.900 = 6% drawdown cap.

### Slippage
**What**: Difference between expected fill price and actual fill price.
**Example**: Wanted Rs.100, filled at Rs.100.30 = 0.3% slippage.

### Charges
**What**: All costs of trading: brokerage, STT, exchange fees, GST, stamp duty.
**Our typical**: Rs.40 per round trip.

### Round Trip
**What**: One complete trade (BUY + SELL or SELL + BUY).

### Net P&L
**What**: Profit/loss after all charges deducted.
**Always use**: Net P&L for performance evaluation, never gross.

### Capital Deployed
**What**: Total money in active positions.
**Our limit**: Per-profile daily_capital_limit.

### Per-Trade Max
**What**: Maximum capital in any single position.
**Our limit**: Rs.4,000-4,500 per live trade.

---

## DAILY OPERATIONS TERMS

### Pre-Market
**What**: 9:00-9:15 AM IST. We don't trade here.

### Opening Auction
**What**: 9:00-9:15 AM IST. Price discovery.

### Continuous Trading
**What**: 9:15 AM - 3:30 PM IST. Normal trading.

### Closing Auction
**What**: 3:30-3:40 PM IST. We don't participate.

### EOD (End of Day)
**What**: After 3:30 PM IST.

### Top Performers Capture
**What**: Daily cron at 3:35 PM IST that captures top 20 NSE movers and compares to our picks.
**Purpose**: Track scanner accuracy.

### War Room
**What**: Dashboard tab showing scanner accuracy and missed opportunities.

### EOD Summary
**What**: Comprehensive end-of-day report.
**Command**: bash scripts/eod_summary.sh

### Live Status
**What**: Mid-day snapshot of all profiles.
**Command**: bash scripts/live_status.sh

---

## CODE / DEVELOPMENT TERMS

### Heredoc
**What**: Bash syntax for embedding multi-line strings.
**Our use**: Editing Python files via SSH (no nano/vim).

### Git Flow
**What**: Our rule: only EC2 commits + pushes. Mac is read-only.
**Why**: Mac is corporate machine, AWS IT monitors git pushes.

### Profile YAML
**What**: Configuration file per trading account.
**Location**: config/profiles/.yaml
**Note**: Gitignored. Manually synced between EC2s.

### Steering Docs
**What**: Authoritative project documentation.
**Files**: RULES.md, STATE.md, HISTORY.md, STRATEGY.md, LEARNING.md, BUSINESS_DOC.md, TECHNICAL_DOC.md, GLOSSARY.md
**Location**: .kiro/steering/

### Bug 5
**What**: Daily trade limit not enforced during continuous scanning.
**Fix**: 2026-05-15. Risk_Manager._restore_daily_state now counts OPEN positions.

### Bug 6
**What**: neha-live data only on NEW EC2, invisible from OLD EC2.
**Fix**: 2026-05-15. NEW EC2 syncs DB to S3, OLD EC2 auto-pulls.
