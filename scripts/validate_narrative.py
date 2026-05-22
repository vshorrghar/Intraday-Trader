#!/usr/bin/env python3
"""Validate AI-generated audit narratives against ground truth.

Strict validator: extracts ALL verifiable claims, cross-references against
audit data, splits unverifiable into 3 buckets.

trust_score = verified / (verified + failed + structurally_skipped)
External-data and opinion claims excluded from denominator.

Usage:
    python scripts/validate_narrative.py --all
    python scripts/validate_narrative.py --profile vishal-live --date 2026-05-21
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = timezone(timedelta(hours=5, minutes=30))

REQUIRED_NARRATIVE_KEYS = {
    "what_went_right", "what_went_wrong", "patterns_observed",
    "bugs_or_risks_flagged", "recommendation"
}
LIST_KEYS = {"what_went_right", "what_went_wrong", "patterns_observed", "bugs_or_risks_flagged"}


def audit_dir(profile):
    return Path(__file__).parent.parent / "dashboard" / "api" / "v2" / profile / "audit"


def load_audit(profile, date):
    p = audit_dir(profile) / f"{date}.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════
# SCHEMA CHECK
# ═══════════════════════════════════════════════════════════

def check_schema(narrative):
    failures = []
    if not isinstance(narrative, dict):
        failures.append({"field": "narrative", "reason": "wrong_type"})
        return failures
    for key in REQUIRED_NARRATIVE_KEYS:
        if key not in narrative:
            failures.append({"field": key, "reason": "missing_field"})
    for key in LIST_KEYS:
        val = narrative.get(key)
        if val is not None:
            if not isinstance(val, list):
                failures.append({"field": key, "reason": "wrong_type"})
            elif len(val) == 0:
                failures.append({"field": key, "reason": "empty_list"})
            elif len(val) > 10:
                failures.append({"field": key, "reason": "too_many_items"})
            else:
                for i, item in enumerate(val):
                    if not isinstance(item, str) or item.strip() == "":
                        failures.append({"field": f"{key}[{i}]", "reason": "empty_item"})
    rec = narrative.get("recommendation")
    if rec is not None and (not isinstance(rec, str) or rec.strip() == ""):
        failures.append({"field": "recommendation", "reason": "empty"})
    return failures


# ═══════════════════════════════════════════════════════════
# CLAIM EXTRACTION + CLASSIFICATION
# ═══════════════════════════════════════════════════════════

def extract_all_claims(narrative, trades, summary, phase_status):
    """Extract ALL claims from narrative text, classify each."""
    claims = []  # Each: {text, field, type, verifiable, ...}

    all_bullets = []
    for key in LIST_KEYS:
        for i, item in enumerate(narrative.get(key, [])):
            all_bullets.append((f"{key}[{i}]", item))
    rec = narrative.get("recommendation", "")
    if rec:
        all_bullets.append(("recommendation", rec))

    trade_ids_in_audit = {t["trade_id"] for t in trades}
    symbols_in_audit = {t["tradingsymbol"].upper() for t in trades}

    for field, text in all_bullets:
        # --- Trade ID references ---
        for m in re.finditer(r'trade[_ ]?id[s]?\s*[=:]?\s*(\d+)', text, re.IGNORECASE):
            tid = int(m.group(1))
            claims.append({
                "field": field, "type": "trade_id_ref", "claim": f"trade_id {tid}",
                "verifiable": "structural", "trade_id": tid
            })

        # --- Per-trade PnL: "trade_id N ... +/-X.XX" or "SYMBOL ... +/-X.XX" ---
        for m in re.finditer(r'trade[_ ]?id\s*(\d+)[^.]*?([+-]?\d+\.\d{2})', text, re.IGNORECASE):
            tid = int(m.group(1))
            val = float(m.group(2))
            if abs(val) > 1:
                claims.append({
                    "field": field, "type": "per_trade_pnl", "claim": f"trade_id {tid} value {val}",
                    "verifiable": "structural", "trade_id": tid, "value": val
                })

        # --- Aggregate ratios: "X% charge-to-gross", "X% win rate" ---
        for m in re.finditer(r'(\d+\.?\d*)\s*%\s*(charge|win|loss|drag|return)', text, re.IGNORECASE):
            pct = float(m.group(1))
            subject = m.group(2).lower()
            claims.append({
                "field": field, "type": "aggregate_pct", "claim": f"{pct}% {subject}",
                "verifiable": "structural", "pct": pct, "subject": subject
            })

        # --- Phase status: "Phase N win rate is X% across Y trades" ---
        for m in re.finditer(r'(?:phase\s*\d?\s*)?win\s*rate\s*(?:is|of|at)?\s*(\d+\.?\d*)\s*%\s*(?:across|over|on)?\s*(\d+)\s*trade', text, re.IGNORECASE):
            pct = float(m.group(1))
            count = int(m.group(2))
            claims.append({
                "field": field, "type": "phase_win_rate",
                "claim": f"win rate {pct}% across {count} trades",
                "verifiable": "structural", "pct": pct, "count": count
            })

        # --- Count claims: "N of M stopped/force/wins/trades/LONG" ---
        for m in re.finditer(r'(\d+)\s*(?:of|out of|/)\s*(\d+)\s+(trade|win|loss|stop|force|long|short)', text, re.IGNORECASE):
            num = int(m.group(1))
            denom = int(m.group(2))
            subject = m.group(3).lower()
            claims.append({
                "field": field, "type": "count_ratio",
                "claim": f"{num} of {denom} {subject}",
                "verifiable": "structural", "num": num, "denom": denom, "subject": subject
            })

        # --- "all N trades/LONG/SHORT" ---
        for m in re.finditer(r'all\s+(\d+)\s+(trade|long|short|win|loss)', text, re.IGNORECASE):
            count = int(m.group(1))
            subject = m.group(2).lower()
            claims.append({
                "field": field, "type": "all_count",
                "claim": f"all {count} {subject}",
                "verifiable": "structural", "count": count, "subject": subject
            })

        # --- Symbol re-entry: "SYMBOL traded Nx" or "SYMBOL was traded N times" ---
        for m in re.finditer(r'([A-Z]{2,15})\s+(?:was\s+)?traded\s+(\d+)\s*(?:x|times)', text, re.IGNORECASE):
            symbol = m.group(1).upper()
            count = int(m.group(2))
            if symbol in symbols_in_audit:
                claims.append({
                    "field": field, "type": "symbol_reentry",
                    "claim": f"{symbol} traded {count}x",
                    "verifiable": "structural", "symbol": symbol, "count": count
                })

        # --- Summary-level values: "charges of N", "capital deployed N" ---
        for m in re.finditer(r'charges?\s+(?:of\s+)?(\d+\.?\d*)', text, re.IGNORECASE):
            val = float(m.group(1))
            if val > 10:
                claims.append({
                    "field": field, "type": "summary_charges",
                    "claim": f"charges {val}",
                    "verifiable": "structural", "value": val
                })

        # --- Drift amount: "drift of/Rs.X" ---
        for m in re.finditer(r'drift[^.]*?(\d+\.?\d+)\s*(?:Rs|INR)?', text, re.IGNORECASE):
            val = float(m.group(1))
            if val > 1:
                claims.append({
                    "field": field, "type": "drift_value",
                    "claim": f"drift {val}",
                    "verifiable": "structural", "value": val
                })

        # --- Confidence claims: "confidence N" or "confidence score N" ---
        for m in re.finditer(r'confidence\s*(?:score)?\s*(?:of|at|is)?\s*(\d+)', text, re.IGNORECASE):
            conf = int(m.group(1))
            if 1 <= conf <= 10:
                claims.append({
                    "field": field, "type": "confidence_value",
                    "claim": f"confidence {conf}",
                    "verifiable": "structural", "value": conf
                })

        # --- Entry-vs-open percentage (needs OHLC — external) ---
        for m in re.finditer(r'(\d+\.?\d*)\s*%\s*(?:above|below)\s*open', text, re.IGNORECASE):
            claims.append({
                "field": field, "type": "entry_vs_open",
                "claim": f"{m.group(1)}% vs open",
                "verifiable": "external_data_needed"
            })

        # --- VIX claims (needs external data) ---
        for m in re.finditer(r'VIX\s*(?:at|of|is)?\s*(\d+\.?\d*)', text, re.IGNORECASE):
            claims.append({
                "field": field, "type": "vix_value",
                "claim": f"VIX {m.group(1)}",
                "verifiable": "external_data_needed"
            })

        # --- Qualitative/opinion claims (no regex match = opinion) ---
        # If a bullet has NO extracted claims, classify entire bullet as opinion
        bullet_claims = [c for c in claims if c["field"] == field]
        if not bullet_claims:
            claims.append({
                "field": field, "type": "opinion",
                "claim": text[:100],
                "verifiable": "opinion"
            })

    return claims


# ═══════════════════════════════════════════════════════════
# GROUND-TRUTH VERIFICATION
# ═══════════════════════════════════════════════════════════

def verify_claims(claims, trades, summary, phase_status):
    """Verify each structural claim against audit data."""
    verified = []
    failed = []
    skipped = []  # structurally_verifiable_but_skipped
    external = []
    opinion = []

    trade_by_id = {t["trade_id"]: t for t in trades}
    total_trades = len(trades)

    for c in claims:
        if c["verifiable"] == "external_data_needed":
            external.append(c)
            continue
        if c["verifiable"] == "opinion":
            opinion.append(c)
            continue

        # --- Structural verification ---
        ctype = c["type"]

        if ctype == "trade_id_ref":
            if c["trade_id"] in trade_by_id:
                verified.append(c)
            else:
                failed.append({**c, "reason": "hallucinated_trade_id",
                               "expected": str(sorted(trade_by_id.keys())), "got": str(c["trade_id"])})

        elif ctype == "per_trade_pnl":
            tid = c["trade_id"]
            val = c["value"]
            if tid not in trade_by_id:
                failed.append({**c, "reason": "hallucinated_trade_id"})
                continue
            t = trade_by_id[tid]
            # Check against all numeric fields
            candidates = [t.get("pnl_db"), t.get("pnl_dhan"), t.get("pnl_net_estimated"),
                          t.get("charges_estimated"), t.get("entry_price"), t.get("exit_price")]
            candidates = [x for x in candidates if x is not None]
            matched = any(abs(val - x) < max(abs(x) * 0.02, 1.5) for x in candidates if x != 0)
            if matched:
                verified.append(c)
            else:
                # Might be a computed value — mark as skipped not failed
                skipped.append({**c, "reason": "value_not_in_trade_fields",
                                "expected": str([round(x, 2) for x in candidates]), "got": str(val)})

        elif ctype == "aggregate_pct":
            subject = c["subject"]
            pct = c["pct"]
            if "charge" in subject or "drag" in subject:
                total_charges = sum(t.get("charges_estimated", 0) for t in trades)
                gross = abs(sum(t.get("pnl_db", 0) for t in trades))
                if gross > 0:
                    actual_pct = round(total_charges / gross * 100, 1)
                    if abs(pct - actual_pct) < max(actual_pct * 0.05, 3):
                        verified.append(c)
                    else:
                        failed.append({**c, "reason": "wrong_pct",
                                       "expected": str(actual_pct), "got": str(pct)})
                else:
                    skipped.append({**c, "reason": "cannot_compute_zero_gross"})
            elif "win" in subject:
                # A1 fix: check phase_status.win_rate FIRST (narrative cites cumulative)
                ps_rate = (phase_status or {}).get("win_rate", None)
                day_rate = round(sum(1 for t in trades if t.get("won") is True) / total_trades * 100, 1) if total_trades > 0 else 0
                if ps_rate is not None and abs(pct - ps_rate) < 3:
                    verified.append(c)
                elif total_trades > 0 and abs(pct - day_rate) < 3:
                    verified.append(c)
                else:
                    failed.append({**c, "reason": "wrong_pct",
                                   "expected": f"phase={ps_rate} or day={day_rate}", "got": str(pct)})
            elif "return" in subject:
                skipped.append({**c, "reason": "return_pct_needs_capital_context"})
            else:
                skipped.append({**c, "reason": "unknown_pct_subject"})

        elif ctype == "phase_win_rate":
            ps = phase_status or {}
            actual_rate = ps.get("win_rate", 0)
            actual_count = ps.get("trades_this_phase", 0)
            rate_ok = abs(c["pct"] - actual_rate) < 3
            count_ok = c["count"] == actual_count
            if rate_ok and count_ok:
                verified.append(c)
            elif not count_ok:
                failed.append({**c, "reason": "wrong_phase_trade_count",
                               "expected": str(actual_count), "got": str(c["count"])})
            else:
                failed.append({**c, "reason": "wrong_phase_win_rate",
                               "expected": str(actual_rate), "got": str(c["pct"])})

        elif ctype == "count_ratio":
            denom = c["denom"]
            num = c["num"]
            subject = c["subject"]
            # Verify denominator = total trades OR phase_status fields
            if denom != total_trades and denom not in (total_trades - 1, total_trades + 1):
                # A4 fix: check if denominator matches phase_status fields
                ps = phase_status or {}
                phase_vals = [ps.get("trades_needed_next"), ps.get("trades_this_phase"), ps.get("trades_remaining")]
                if denom in [v for v in phase_vals if v is not None]:
                    if num == ps.get("trades_this_phase", -1) or num == ps.get("win_count", -1):
                        verified.append(c)
                    else:
                        skipped.append({**c, "reason": "phase_numerator_unmatched"})
                    continue
                skipped.append({**c, "reason": "denominator_mismatch_unknown_source"})
                continue
            # Compute actual count
            if "stop" in subject:
                actual = sum(1 for t in trades if t.get("outcome") == "STOPPED_OUT")
            elif "force" in subject:
                actual = sum(1 for t in trades if t.get("outcome") == "FORCE_EXITED")
            elif "win" in subject:
                actual = sum(1 for t in trades if t.get("won") is True)
            elif "loss" in subject:
                actual = sum(1 for t in trades if t.get("won") is False)
            elif "long" in subject:
                actual = sum(1 for t in trades if t.get("direction") == "LONG")
            elif "short" in subject:
                actual = sum(1 for t in trades if t.get("direction") == "SHORT")
            elif "trade" in subject:
                actual = total_trades
            else:
                skipped.append({**c, "reason": "unknown_count_subject"})
                continue
            if num == actual:
                verified.append(c)
            else:
                failed.append({**c, "reason": "wrong_count",
                               "expected": str(actual), "got": str(num)})

        elif ctype == "all_count":
            count = c["count"]
            subject = c["subject"]
            if "trade" in subject:
                actual = total_trades
            elif "long" in subject:
                actual = sum(1 for t in trades if t.get("direction") == "LONG")
            elif "short" in subject:
                actual = sum(1 for t in trades if t.get("direction") == "SHORT")
            elif "win" in subject:
                actual = sum(1 for t in trades if t.get("won") is True)
            else:
                skipped.append({**c, "reason": "unknown_all_subject"})
                continue
            if count == actual:
                verified.append(c)
            else:
                failed.append({**c, "reason": "wrong_all_count",
                               "expected": str(actual), "got": str(count)})

        elif ctype == "symbol_reentry":
            symbol = c["symbol"]
            count = c["count"]
            actual = sum(1 for t in trades if t.get("tradingsymbol", "").upper() == symbol)
            if count == actual:
                verified.append(c)
            else:
                failed.append({**c, "reason": "wrong_symbol_count",
                               "expected": str(actual), "got": str(count)})

        elif ctype == "summary_charges":
            val = c["value"]
            actual = round(sum(t.get("charges_estimated", 0) for t in trades), 2)
            if abs(val - actual) < max(actual * 0.02, 5):
                verified.append(c)
            else:
                failed.append({**c, "reason": "wrong_charges",
                               "expected": str(actual), "got": str(val)})

        elif ctype == "drift_value":
            val = c["value"]
            # A2 fix: check summary drift, per-trade pnl diff, qty_drift, and raw pnl values
            summary_drift = summary.get("drift_amount_rs", 0)
            trade_drifts = [abs(t.get("pnl_dhan", 0) - t.get("pnl_db", 0)) for t in trades]
            qty_drifts = [abs(t.get("qty_drift", 0)) for t in trades]
            trade_pnls = [abs(t.get("pnl_dhan", 0)) for t in trades] + [abs(t.get("pnl_db", 0)) for t in trades]
            all_candidates = [summary_drift] + trade_drifts + qty_drifts + trade_pnls
            if any(abs(val - d) < max(abs(d) * 0.05, 2) for d in all_candidates if d != 0):
                verified.append(c)
            elif val == 0 and summary_drift == 0:
                verified.append(c)
            else:
                skipped.append({**c, "reason": "drift_value_unmatched_but_plausible"})

        elif ctype == "confidence_value":
            conf = c["value"]
            actual_confs = [t.get("confidence") for t in trades if t.get("confidence")]
            if conf in actual_confs:
                verified.append(c)
            else:
                failed.append({**c, "reason": "wrong_confidence",
                               "expected": str(actual_confs), "got": str(conf)})

        else:
            skipped.append({**c, "reason": f"unhandled_type_{ctype}"})

    return verified, failed, skipped, external, opinion


# ═══════════════════════════════════════════════════════════
# MAIN VALIDATION
# ═══════════════════════════════════════════════════════════

def validate_one(profile, date):
    audit = load_audit(profile, date)
    if audit is None:
        return None

    narrative = audit.get("narrative")
    if narrative is None:
        return {"validated_at": datetime.now(IST).isoformat(), "schema_ok": False,
                "reason": "no_narrative", "trust_score": 0.0,
                "claims_total": 0, "verified": 0, "failed": 0,
                "structurally_skipped": 0, "external_data_needed": 0, "opinion": 0,
                "failures": []}

    trades = audit.get("trades", [])
    summary = audit.get("summary", {})
    phase_status = audit.get("phase_status", {})

    # Schema
    schema_failures = check_schema(narrative)
    if schema_failures:
        return {"validated_at": datetime.now(IST).isoformat(), "schema_ok": False,
                "trust_score": 0.0, "claims_total": 0, "verified": 0, "failed": len(schema_failures),
                "structurally_skipped": 0, "external_data_needed": 0, "opinion": 0,
                "failures": schema_failures}

    # Extract + verify
    claims = extract_all_claims(narrative, trades, summary, phase_status)
    verified, failed, skipped, external, opinion_claims = verify_claims(
        claims, trades, summary, phase_status)

    # Trust score: verified / (verified + failed + skipped)
    denom = len(verified) + len(failed) + len(skipped)
    trust_score = round(len(verified) / denom, 3) if denom > 0 else 1.0

    return {
        "validated_at": datetime.now(IST).isoformat(),
        "schema_ok": True,
        "trust_score": trust_score,
        "claims_total": len(claims),
        "verified": len(verified),
        "failed": len(failed),
        "structurally_skipped": len(skipped),
        "external_data_needed": len(external),
        "opinion": len(opinion_claims),
        "failures": [{"field": f.get("field"), "claim": f.get("claim"),
                      "reason": f.get("reason"), "expected": f.get("expected", ""),
                      "got": f.get("got", "")} for f in failed],
        "skipped_details": [{"field": s.get("field"), "claim": s.get("claim"),
                             "reason": s.get("reason")} for s in skipped],
    }


def write_validation(profile, date, validation):
    out_dir = audit_dir(profile)
    out_file = out_dir / f"{date}.validation.json"
    with open(out_file, "w") as f:
        json.dump(validation, f, indent=2, default=str)
    return out_file


def get_all_audits():
    base = Path(__file__).parent.parent / "dashboard" / "api" / "v2"
    audits = []
    for profile_dir in sorted(base.iterdir()):
        if not profile_dir.is_dir():
            continue
        audit_d = profile_dir / "audit"
        if not audit_d.exists():
            continue
        profile = profile_dir.name
        for f in sorted(audit_d.glob("*.json")):
            if f.name.endswith(".validation.json"):
                continue
            date = f.stem
            audits.append((profile, date))
    return audits


def main():
    parser = argparse.ArgumentParser(description="Validate audit narratives (strict)")
    parser.add_argument("--profile", help="Profile name")
    parser.add_argument("--date", help="Date YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="Validate all audits")
    args = parser.parse_args()

    if args.all:
        audits = get_all_audits()
    elif args.profile and args.date:
        audits = [(args.profile, args.date)]
    elif args.profile:
        audits = [(args.profile, datetime.now(IST).strftime("%Y-%m-%d"))]
    else:
        print("Usage: --all or --profile X --date Y")
        return

    results = []
    for profile, date in audits:
        v = validate_one(profile, date)
        if v is None:
            continue
        write_validation(profile, date, v)
        status = "PASS" if v["trust_score"] >= 0.9 else ("WARN" if v["trust_score"] >= 0.7 else "FAIL")
        print(f"  {status} {profile}/{date}: trust={v['trust_score']:.2f} "
              f"V={v['verified']} F={v['failed']} S={v['structurally_skipped']} "
              f"E={v['external_data_needed']} O={v['opinion']}")
        results.append({"profile": profile, "date": date, **v})

    # Summary
    if results:
        print(f"\n{'='*60}")
        print("VALIDATION SUMMARY (strict)")
        print(f"{'='*60}")
        high = [r for r in results if r["trust_score"] >= 0.9]
        mid = [r for r in results if 0.7 <= r["trust_score"] < 0.9]
        low = [r for r in results if r["trust_score"] < 0.7]
        print(f"  >= 0.9 (PASS):  {len(high)}")
        print(f"  0.7-0.9 (WARN): {len(mid)}")
        print(f"  < 0.7 (FAIL):   {len(low)}")
        print(f"  Total:          {len(results)}")
        total_v = sum(r["verified"] for r in results)
        total_f = sum(r["failed"] for r in results)
        total_s = sum(r["structurally_skipped"] for r in results)
        total_e = sum(r["external_data_needed"] for r in results)
        total_o = sum(r["opinion"] for r in results)
        print(f"\n  Claims breakdown across all audits:")
        print(f"    Verified:              {total_v}")
        print(f"    Failed:                {total_f}")
        print(f"    Structurally skipped:  {total_s}")
        print(f"    External data needed:  {total_e}")
        print(f"    Opinion/qualitative:   {total_o}")
        print(f"    Total:                 {total_v + total_f + total_s + total_e + total_o}")

        if failed_audits := [r for r in results if r["trust_score"] < 0.9]:
            print(f"\n--- AUDITS BELOW 0.9 ---")
            for r in failed_audits:
                print(f"\n  {r['profile']}/{r['date']}: trust={r['trust_score']:.2f}")
                for f in r.get("failures", [])[:5]:
                    print(f"    FAIL: [{f['reason']}] {f['claim']} "
                          f"(expected={f.get('expected','')}, got={f.get('got','')})")
                for s in r.get("skipped_details", [])[:3]:
                    print(f"    SKIP: [{s['reason']}] {s['claim']}")


if __name__ == "__main__":
    main()
