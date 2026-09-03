"""Shared pytest configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def api_key() -> str:
    """The webhook.site API key for ``live_auth`` tests; skips when it is not set."""
    key = os.environ.get("WEBHOOK_SITE_API_KEY", "").strip()
    if not key:
        pytest.skip("WEBHOOK_SITE_API_KEY is not set")
    return key
