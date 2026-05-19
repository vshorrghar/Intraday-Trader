#!/usr/bin/env python3
"""
CLI for swing trading manual overrides.

Usage:
    python scripts/swing_control.py pause vishal-live "Iran-Israel war"
    python scripts/swing_control.py resume vishal-live
    python scripts/swing_control.py exit vishal-live HDFCBANK "Earnings approach"
    python scripts/swing_control.py status vishal-live
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swing.manual_override import (
    pause_swing_trading,
    resume_swing_trading,
    manual_exit_position,
    list_status,
)


def main():
    if len(sys.argv) < 3:
        print("Usage: swing_control.py <command> <profile> [args...]")
        print("Commands: pause, resume, exit, status")
        sys.exit(1)

    command = sys.argv[1]
    profile = sys.argv[2]

    if command == "pause":
        reason = sys.argv[3] if len(sys.argv) > 3 else "manual pause"
        pause_swing_trading(profile, reason)
        print(f"✅ Swing trading PAUSED for {profile}: {reason}")

    elif command == "resume":
        resume_swing_trading(profile)
        print(f"✅ Swing trading RESUMED for {profile}")

    elif command == "exit":
        if len(sys.argv) < 5:
            print("Usage: swing_control.py exit <profile> <symbol> <reason>")
            sys.exit(1)
        symbol = sys.argv[3]
        reason = sys.argv[4]
        manual_exit_position(profile, symbol, reason)
        print(f"✅ {symbol} added to exit queue for {profile}: {reason}")

    elif command == "status":
        status = list_status(profile)
        print(f"Profile: {status['profile']}")
        print(f"Paused: {status['paused']}" + (f" ({status['pause_reason']})" if status['paused'] else ""))
        print(f"Manual exit queue: {status['queue_count']} items")
        for item in status['manual_exit_queue']:
            print(f"  - {item['symbol']}: {item['reason']} (queued {item['queued_at']})")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
