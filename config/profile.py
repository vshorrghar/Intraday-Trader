"""Multi-user profile resolver for Wealth Builder Pro.

Determines which config file to use based on:
1. --profile CLI argument (e.g., --profile neha)
2. USER_PROFILE environment variable (e.g., USER_PROFILE=neha)
3. Defaults to "vishal" (config/config.yaml)

Usage:
    from config.profile import get_config_path

    config_path = get_config_path()  # auto-detects from CLI/env
    config_path = get_config_path("neha")  # explicit
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Profile name → config file mapping
PROFILES: dict[str, str] = {
    "vishal": "config/config.yaml",
    "neha": "config/config_neha.yaml",
}

DEFAULT_PROFILE = "vishal"


def get_profile_name() -> str:
    """Detect active profile from CLI args or environment.

    Checks (in order):
    1. --profile <name> in sys.argv
    2. USER_PROFILE environment variable
    3. Falls back to DEFAULT_PROFILE
    """
    # Check CLI args
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--profile" and i + 1 < len(args):
            return args[i + 1].lower()
        if arg.startswith("--profile="):
            return arg.split("=", 1)[1].lower()

    # Check environment variable
    env_profile = os.environ.get("USER_PROFILE", "").strip().lower()
    if env_profile:
        return env_profile

    return DEFAULT_PROFILE


def set_profile_name(profile: str) -> None:
    """Set active profile via USER_PROFILE env var.

    Subsequent get_profile_name() calls will return this value
    (unless --profile CLI arg is also set, which takes precedence).
    """
    import os
    if profile:
        os.environ["USER_PROFILE"] = profile.strip().lower()




def get_config_path(profile: str | None = None) -> str:
    """Return the config file path for the given profile.

    Args:
        profile: Profile name. If None, auto-detects from CLI/env.

    Returns:
        Path to the config YAML file.

    Raises:
        ValueError: If the profile name is not recognized.
        FileNotFoundError: If the config file doesn't exist.
    """
    if profile is None:
        profile = get_profile_name()

    profile = profile.lower()

    if profile not in PROFILES:
        available = ", ".join(sorted(PROFILES.keys()))
        raise ValueError(
            f"Unknown profile '{profile}'. Available profiles: {available}"
        )

    config_path = PROFILES[profile]

    if not Path(config_path).exists():
        raise FileNotFoundError(
            f"Config file for profile '{profile}' not found: {config_path}"
        )

    return config_path


def get_session_file(profile: str | None = None) -> Path:
    """Return a profile-specific session file path.

    Each user gets their own broker session file so tokens don't collide.
    Every profile gets a suffixed file (no default-profile special case)
    to prevent cross-profile session contamination.
    """
    if profile is None:
        profile = get_profile_name()

    profile = profile.lower()

    return Path(f"config/.broker_session_{profile}.json")


def get_db_path(profile: str | None = None) -> str:
    """Return the database path for the given profile."""
    if profile is None:
        profile = get_profile_name()

    if profile == "neha":
        return "database/portfolio_neha.db"
    return "database/portfolio.db"
