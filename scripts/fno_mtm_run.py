"""F&O Mark-to-Market runner. Run via fno_mtm_update.sh wrapper."""
import sys
from pathlib import Path

# Ensure project root is in path (works regardless of cwd)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fno.monitor import update_all_open_strategies

# Note: vishal-live F&O cron disabled (real money account, no F&O paper)
for p in ["vishal", "neha"]:
    try:
        result = update_all_open_strategies(p)
        print(f"{p}: {result}")
    except Exception as e:
        print(f"{p}: ERROR - {e}")
