"""NVR channel manifest — exposes the results of ``scripts/nvr_scan`` to the UI.

Reads ``data/nvr_scan/manifest.json`` on each request so the dashboard can pick
up a fresh scan without an API restart. The image files are served by the
StaticFiles mount registered in ``main.py`` under ``/nvr-stills``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/nvr", tags=["nvr"])


def _manifest_path() -> Path:
    return Path("data/nvr_scan/manifest.json")


@router.get("/channels")
async def list_channels() -> dict:
    p = _manifest_path()
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail="no NVR scan yet — run `python -m scripts.nvr_scan`",
        )
    return json.loads(p.read_text())
