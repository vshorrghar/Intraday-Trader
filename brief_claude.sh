#!/bin/bash
# brief_claude.sh — outputs the paste-block to brief the Claude partner
# at the start of a new session. Run: ./brief_claude.sh
cd "$(dirname "$0")"
echo "═══════════════════════════════════════════════════════════"
echo "  PASTE EVERYTHING BELOW TO CLAUDE (PARTNER) — NEW SESSION"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "## 1. THE CHARTER (your operating rules, partner)"
echo ""
cat .kiro/steering/CHARTER.md 2>/dev/null | grep -v "^---$" | grep -v "inclusion: auto"
echo ""
echo "## 2. CURRENT STATE (top of STATE.md)"
echo ""
head -50 .kiro/steering/STATE.md 2>/dev/null
echo ""
echo "## 3. MODULE STATUS SNAPSHOT"
echo ""
echo "Run date: $(date '+%Y-%m-%d %H:%M %Z')"
echo ""
echo "### Crontab (what's scheduled):"
crontab -l 2>/dev/null | grep -vE "^#" | grep -E "swing|fno|s3|vishal|intraday" | head -15
echo ""
echo "### Recent git commits:"
git log --oneline -5 2>/dev/null
echo ""
echo "## 4. LATEST CONTEXT (tail of CONTEXT.md)"
echo ""
tail -40 .kiro/steering/CONTEXT.md 2>/dev/null
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  END PASTE — Claude will resume as your trader-partner"
echo "═══════════════════════════════════════════════════════════"
