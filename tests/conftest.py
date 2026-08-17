"""pytest fixtures shared across the suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make ``src`` and ``scripts`` importable when running pytest at the repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Redirect data + config to a per-run tmp dir so tests never touch real data.
os.environ.setdefault("PSO_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("PSO_SNAPSHOT_DIR", str(ROOT / "data" / "snapshots"))


@pytest.fixture
def frozen_now() -> pytest.FixtureRequest:
    from datetime import datetime

    return datetime(2026, 8, 17, 12, 0, 0)
