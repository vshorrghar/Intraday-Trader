"""Multi-profile configuration loader.

Auto-discovers profiles from config/profiles/*.yaml (excluding _template.yaml).
Merges profile-specific overrides with the base config/config.yaml.

Each profile gets:
- Its own Dhan credentials
- Its own database file
- Its own dashboard API directory
- Its own capital/risk limits

Usage:
    from config.profile_loader import load_all_profiles, load_profile

    # Load a specific profile
    profile = load_profile("vishal")

    # Discover all valid profiles
    profiles = load_all_profiles()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("config/profiles")
BASE_CONFIG = Path("config/config.yaml")


def load_all_profiles() -> list[dict]:
    """Discover and load all valid profiles.

    Returns list of merged config dicts, one per profile.
    Skips _template.yaml and any profile with REPLACE_ME values.
    """
    profiles = []
    if not PROFILES_DIR.exists():
        logger.warning("Profiles directory not found: %s", PROFILES_DIR)
        return profiles

    for f in sorted(PROFILES_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue  # Skip template

        try:
            profile = _load_and_merge(f)
            if _is_valid_profile(profile):
                profiles.append(profile)
                logger.info("Loaded profile: %s", profile["profile"]["name"])
            else:
                logger.warning("Skipping incomplete profile: %s", f.name)
        except Exception as exc:
            logger.error("Failed to load profile %s: %s", f.name, exc)

    return profiles


def load_profile(name: str) -> dict:
    """Load a specific profile by name.

    Args:
        name: Profile name (e.g. "vishal", "neha")

    Returns:
        Merged config dict with profile overrides applied.

    Raises:
        FileNotFoundError: If profile YAML doesn't exist.
        ValueError: If profile has REPLACE_ME values.
    """
    profile_path = PROFILES_DIR / f"{name}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    profile = _load_and_merge(profile_path)
    if not _is_valid_profile(profile):
        raise ValueError(f"Profile '{name}' has incomplete credentials (REPLACE_ME found)")

    return profile


def get_profile_names() -> list[str]:
    """Get list of all valid profile names."""
    names = []
    if not PROFILES_DIR.exists():
        return names

    for f in sorted(PROFILES_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        name = f.stem
        try:
            profile = _load_and_merge(f)
            if _is_valid_profile(profile):
                names.append(name)
        except Exception:
            pass

    return names


def _load_and_merge(profile_path: Path) -> dict:
    """Load base config and merge profile overrides on top."""
    # Load base
    with open(BASE_CONFIG) as f:
        base = yaml.safe_load(f)

    # Load profile
    with open(profile_path) as f:
        overrides = yaml.safe_load(f)

    # Deep merge: profile overrides win
    merged = _deep_merge(base, overrides)
    return merged


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict. Override wins."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _is_valid_profile(profile: dict) -> bool:
    """Check if a profile has all required fields filled (no REPLACE_ME)."""
    dhan = profile.get("dhan", {})
    required_fields = ["client_id", "api_key", "api_secret", "totp_secret", "pin"]

    for field in required_fields:
        value = dhan.get(field, "")
        if not value or "REPLACE_ME" in str(value):
            return False

    # Check profile name exists
    profile_info = profile.get("profile", {})
    if not profile_info.get("name") or "REPLACE_ME" in profile_info.get("name", ""):
        return False

    return True
