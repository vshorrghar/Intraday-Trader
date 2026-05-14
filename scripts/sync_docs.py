#!/usr/bin/env python3
"""Sync steering docs to dashboard API for viewing in dashboard."""
import json
from pathlib import Path

steering = Path("/home/ec2-user/dev-sandbox/.kiro/steering")
api = Path("/home/ec2-user/dev-sandbox/dashboard/api")

docs = {}
for fname in ["STRATEGY.md", "LEARNING.md", "RULES.md", "STATE.md"]:
    fpath = steering / fname
    if fpath.exists():
        docs[fname] = {
            "name": fname,
            "content": fpath.read_text(),
            "size": fpath.stat().st_size,
            "modified": fpath.stat().st_mtime,
        }
        print(f"Synced: {fname}")

out = api / "docs.json"
out.write_text(json.dumps(docs, indent=2))
print(f"Written: {out}")
