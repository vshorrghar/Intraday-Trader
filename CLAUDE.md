# Read This Before Any AI-Assisted Work

## You Are Working On A Live Trading System

Real money is deployed (₹10K). One wrong fix = real loss.

## Mandatory Reading Order

1. `.kiro/steering/trading-app-rules.md` — All 11+ behavioral rules
2. The "Complete Project Context" doc the user pastes
3. Last 5 commits: `git log --oneline -5`

## Top 5 Rules You Will Forget

1. **EC2 edits only.** Mac is read-only. `~/dev-sandbox` (EC2) vs `~/kiro/websites/intraday-trader` (Mac).
2. **No sed on .py files.** Use Python heredoc (PYEOF) — see Rule 11.
3. **Verify before saying done.** grep + import test. Two failures = stop.
4. **One problem at a time.** Don't fix bonus bugs without approval.
5. **vishal-live = real money.** Extra approval needed for any change to it.

## Directory Quick Ref

| Where | Path |
|-------|------|
| EC2 project | `~/dev-sandbox/` |
| Mac mirror (read-only) | `~/kiro/websites/intraday-trader/` |
| Steering file | `.kiro/steering/trading-app-rules.md` |
| Live config | `config/profiles/vishal-live.yaml` |
| Live log | `logs/intraday_vishal-live_.log` |
| Python | `.venv/bin/python` |

## Confirm You Read This

Reply: "CLAUDE.md read. Steering file pending. Paste context doc when ready."
