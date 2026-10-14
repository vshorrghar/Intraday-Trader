# Shared Dhan token (client_id 1110941563) — DH-906 flap + fix

ROOT CAUSE (confirmed 2026-10-14):
- Dhan = ONE active session per client_id. 1110941563 is shared by
  vishal, vishal-s3, vishal-live-v2.
- pre_auth_dhan.py (cron 45 3) mints the shared token -> config/.dhan_token_1110941563.json
- auth_server.py:~504 reuses that token IF file date==today (good, no re-auth).
- BUG: if ANY context does a fresh TOTP for 1110941563 after pre_auth
  (other tab, laptop, stale-date path), Dhan invalidates the shared token
  server-side WITHOUT rewriting the file -> file looks valid, API says DH-906.
- Observed: token JWT valid till next 03:45, pre_auth ran once, yet DH-906.
  Single re-mint -> HTTP 200. = session was stolen, not expired.

SESSION RULE (manual, until fixed):
- Only pre_auth_dhan.py authenticates 1110941563, once pre-market.
- Everything else READS config/.dhan_token_1110941563.json (never fresh-TOTP).
- Detector reads file read-only (commit b841267) = correct.

FIX NEXT SESSION (shared-core, verify carefully, money-adjacent):
1. Add loud-fail: any consumer that gets DH-906/non-200 must LOG ERROR and
   return UNKNOWN — NEVER silent-empty (false "0 orphans" = live-money unsafe).
2. Enforce single-auth: consumers load shared file; if token dead, FAIL LOUD,
   do NOT silently re-auth (silent re-auth steals the session + hides the bug).
3. Audit every authenticate_broker call for 1110941563 profiles across BOTH
   tabs; route all through shared-file path.
4. Open question: does Dhan token have a real TTL < 24h? JWT exp says 24h but
   verify it isn't invalidated earlier by Dhan server policy.

STATUS: re-minted 2026-10-14 07:11 UTC, HTTP 200. Hold the line - no re-auth.

## HARD RULE (live-trading constraint, effective 2026-10-14)
Until single-auth enforcement ships, treat as inviolable on BOTH tabs:
- NOBODY re-auths 1110941563 mid-session. No manual pre_auth, no fresh-TOTP
  authenticate_broker. If both tabs re-mint, the session ping-pongs = flapping.
- All consumers READ config/.dhan_token_1110941563.json. Detector read-only
  (b841267) is the correct pattern — every other consumer must match it.
- KNOWN LATENT RISK: intraday V3 crons (orchestrator */15, monitor :07/:22/:37/:52)
  call authenticate_broker, which reuses the shared token ONLY if file date==today.
  If the file is stale/missing, they FALL THROUGH to fresh TOTP = session steal.
  So the V3 crons are NOT yet guaranteed single-auth. Fixing that (read shared
  file, fail loud if dead, never fresh-TOTP) is the intraday half of this fix.
