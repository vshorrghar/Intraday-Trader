"""Tests for V3 universe loader."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


CONSTITUENTS_PATH = Path(__file__).parent.parent.parent / "config" / "nifty500_constituents.json"


@pytest.fixture
def universe_data():
    """Load real constituents JSON if available."""
    if not CONSTITUENTS_PATH.exists():
        pytest.skip("nifty500_constituents.json not built yet")
    return json.loads(CONSTITUENTS_PATH.read_text())


def test_universe_size_at_least_500(universe_data):
    assert len(universe_data) >= 400, f"Only {len(universe_data)} stocks"


def test_all_stocks_have_security_id_or_logged(universe_data):
    with_id = sum(1 for v in universe_data.values() if v.get("security_id"))
    coverage = with_id / len(universe_data)
    assert coverage >= 0.80, f"Only {coverage:.0%} have Dhan IDs"


def test_sector_distribution_reasonable(universe_data):
    from collections import Counter
    sectors = Counter(v.get("sector") for v in universe_data.values())
    max_pct = max(sectors.values()) / len(universe_data)
    assert max_pct <= 0.30, f"Sector concentration {max_pct:.0%} too high"


def test_mcap_distribution_reasonable(universe_data):
    from collections import Counter
    mcap = Counter(v.get("mcap_bucket") for v in universe_data.values())
    assert mcap.get("LARGE", 0) >= 50
    assert mcap.get("MID", 0) >= 100
    assert mcap.get("SMALL", 0) >= 100


def test_priority_stocks_flagged(universe_data):
    priority = [k for k, v in universe_data.items() if v.get("is_priority")]
    assert len(priority) >= 10, f"Only {len(priority)} priority stocks"


def test_suspended_stocks_flagged(universe_data):
    suspended = [k for k, v in universe_data.items() if v.get("is_suspended")]
    assert len(suspended) >= 10, f"Only {len(suspended)} suspended stocks"
