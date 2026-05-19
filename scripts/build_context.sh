#!/bin/bash
cd ~/dev-sandbox
OUT=.kiro/steering/CONTEXT.md
{
  echo "# PROJECT CONTEXT (auto-generated $(date '+%Y-%m-%d %H:%M IST'))"
  echo ""
  echo "Paste this entire file into new Bedrock chat for full project context."
  echo ""
  for f in RULES STATE STRATEGY LEARNING GLOSSARY; do
    echo ""
    echo "================================================================"
    echo "# === $f.md ==="
    echo "================================================================"
    cat .kiro/steering/$f.md
  done
} > $OUT
echo "Built $OUT ($(wc -l < $OUT) lines)"
