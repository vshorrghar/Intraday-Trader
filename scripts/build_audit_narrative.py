#!/usr/bin/env python3
"""Generate AI narrative for daily audit JSONs via AWS Bedrock.

Reads existing audit JSON, sends to Claude Sonnet 4.6 for analysis,
adds 'narrative' field to the same JSON file (atomic write).

Usage:
    python scripts/build_audit_narrative.py --profile vishal-live --date 2026-05-21
    python scripts/build_audit_narrative.py --profile vishal-live --backfill
    python scripts/build_audit_narrative.py --profile vishal-live --date 2026-05-21 --dry-run
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

SYSTEM_PROMPT = """You are a 30-year veteran institutional trader reviewing a day's trading log. Be brutally honest. Flag bugs. Identify patterns. Output JSON only, no prose.

Rules:
- Do not invent statistics
- Cite specific trades by symbol
- If drift_amount_rs > 0, flag it as bug risk
- If qty_drift != 0 on any trade, flag it as Bug A or Bug B class
- Tag each item with relevant trade symbols
- Keep each bullet to 1-2 sentences max
- Be actionable, not academic

Output this exact JSON structure (no markdown, no code fences):
{
  "what_went_right": ["bullet 1", "bullet 2"],
  "what_went_wrong": ["bullet 1", "bullet 2"],
  "patterns_observed": ["bullet 1"],
  "bugs_or_risks_flagged": ["bullet 1"],
  "recommendation": "one sentence, actionable"
}"""

COST_LOG = Path(__file__).parent.parent / "logs" / "bedrock_costs.log"
BEDROCK_REGION = "us-east-1"
MODEL_ID = "us.anthropic.claude-sonnet-4-6-20250514"


def audit_dir(profile):
    return Path(__file__).parent.parent / "dashboard" / "api" / "v2" / profile / "audit"


def load_audit(profile, date):
    p = audit_dir(profile) / f"{date}.json"
    if not p.exists():
        return None, p
    with open(p) as f:
        return json.load(f), p


def build_user_prompt(audit):
    """Build the user prompt from audit data (strip rationale to save tokens)."""
    # Create a condensed version for the prompt
    condensed = {
        "profile": audit["profile"],
        "date": audit["date"],
        "source": audit["source"],
        "summary": audit["summary"],
        "trades": [],
        "bugs_observed": audit.get("bugs_observed", []),
        "phase_status": audit.get("phase_status", {}),
    }
    for t in audit.get("trades", []):
        condensed["trades"].append({
            "trade_id": t["trade_id"],
            "symbol": t["tradingsymbol"],
            "direction": t["direction"],
            "entry_price": t["entry_price"],
            "exit_price": t["exit_price"],
            "qty_intended": t["qty_intended"],
            "qty_actual_dhan": t["qty_actual_dhan"],
            "qty_drift": t["qty_drift"],
            "qty_drift_reason": t["qty_drift_reason"],
            "rr_planned": t["rr_planned"],
            "confidence": t["confidence"],
            "strategy_type": t["strategy_type"],
            "outcome": t["outcome"],
            "won": t["won"],
            "pnl_db": t["pnl_db"],
            "pnl_dhan": t["pnl_dhan"],
            "pnl_net_estimated": t["pnl_net_estimated"],
            "tags": t["tags"],
            "rationale_summary": (t.get("rationale_llm") or "")[:200],
        })
    return f"Here is today's audit data:\n{json.dumps(condensed, indent=2)}"


def call_bedrock(user_prompt):
    """Call Bedrock Claude Sonnet 4.6 and return (response_text, input_tokens, output_tokens)."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime",
        region_name=BEDROCK_REGION,
        config=Config(read_timeout=60, connect_timeout=10, retries={"max_attempts": 1}),
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    })

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    return text, input_tokens, output_tokens


def parse_narrative(text):
    """Parse JSON from Bedrock response, handling potential markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fences
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def log_cost(date, profile, input_tokens, output_tokens):
    """Append cost entry to bedrock_costs.log."""
    cost_usd = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)
    cost_inr = cost_usd * 84  # approximate USD/INR
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_LOG, "a") as f:
        f.write(f"{date},{profile},{input_tokens},{output_tokens},{cost_usd:.6f},{cost_inr:.4f}\n")
    return cost_usd, cost_inr


def atomic_write_audit(audit, filepath):
    """Write audit JSON atomically (temp file + rename)."""
    dir_path = filepath.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(audit, f, indent=2, default=str)
        os.replace(tmp_path, str(filepath))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def process_one(profile, date, dry_run=False):
    """Process a single audit JSON."""
    audit, filepath = load_audit(profile, date)
    if audit is None:
        print(f"  SKIP: No audit JSON for {profile}/{date}")
        return False

    if audit.get("narrative") and not dry_run:
        print(f"  SKIP: {profile}/{date} already has narrative")
        return False

    if not audit.get("trades"):
        print(f"  SKIP: {profile}/{date} has 0 trades")
        return False

    user_prompt = build_user_prompt(audit)

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN: {profile} / {date}")
        print(f"{'='*60}")
        print(f"\n--- SYSTEM PROMPT ---")
        print(SYSTEM_PROMPT)
        print(f"\n--- USER PROMPT ({len(user_prompt)} chars, ~{len(user_prompt)//4} tokens) ---")
        print(user_prompt)
        print(f"\n--- EXPECTED OUTPUT SCHEMA ---")
        print(json.dumps({
            "what_went_right": ["..."],
            "what_went_wrong": ["..."],
            "patterns_observed": ["..."],
            "bugs_or_risks_flagged": ["..."],
            "recommendation": "..."
        }, indent=2))
        print(f"\nEstimated cost: ~$0.017 (Rs.1.40)")
        return True

    # Real Bedrock call
    print(f"  Calling Bedrock for {profile}/{date}...")
    os.environ.setdefault("AWS_PROFILE", "vishal-admin")
    text, input_tokens, output_tokens = call_bedrock(user_prompt)

    # Parse response
    narrative = parse_narrative(text)

    # Validate structure
    required_keys = {"what_went_right", "what_went_wrong", "patterns_observed",
                     "bugs_or_risks_flagged", "recommendation"}
    if not required_keys.issubset(set(narrative.keys())):
        print(f"  ERROR: Bedrock response missing keys. Got: {list(narrative.keys())}")
        print(f"  Raw: {text[:500]}")
        return False

    # Add narrative + metadata to audit
    audit["narrative"] = narrative
    audit["narrative_meta"] = {
        "model": MODEL_ID,
        "generated_at": datetime.now(IST).isoformat(),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

    # Atomic write
    atomic_write_audit(audit, filepath)

    # Log cost
    cost_usd, cost_inr = log_cost(date, profile, input_tokens, output_tokens)

    print(f"  OK: {profile}/{date} — {input_tokens} in / {output_tokens} out — ${cost_usd:.4f} (Rs.{cost_inr:.2f})")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate AI narrative for audit JSONs")
    parser.add_argument("--profile", required=True, help="Profile name")
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill", action="store_true", help="Process all audits missing narrative")
    parser.add_argument("--dry-run", action="store_true", help="Show prompt only, no Bedrock call")
    args = parser.parse_args()

    if args.backfill:
        # Process all audit JSONs missing narrative field
        d = audit_dir(args.profile)
        if not d.exists():
            print(f"No audit directory for {args.profile}")
            return
        files = sorted(d.glob("*.json"))
        processed = 0
        for f in files:
            date = f.stem  # YYYY-MM-DD
            if process_one(args.profile, date, dry_run=args.dry_run):
                processed += 1
        print(f"\nBackfill complete: {processed}/{len(files)} processed")
    else:
        date = args.date or datetime.now(IST).strftime("%Y-%m-%d")
        process_one(args.profile, date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
