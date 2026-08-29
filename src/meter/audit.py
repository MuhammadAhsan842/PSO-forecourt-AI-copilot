"""Append-only audit log for control actions (PTZ, ROI). Never write secrets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOG = Path("data/audit/meter.jsonl")


def audit(action: str, *, actor: str = "ops", **fields: Any) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "action": action,
        "actor": actor,
        **{k: v for k, v in fields.items() if k not in {"password", "pass", "token"}},
    }
    with _LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
