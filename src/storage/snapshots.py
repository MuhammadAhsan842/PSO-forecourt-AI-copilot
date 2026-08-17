"""Snapshot writer.

Snapshots are pilot-critical: every alert carries one. Stored under
``settings.snapshot_dir`` bucketed by date so the retention purge can drop full
folders. Path returned is RELATIVE to ``snapshot_dir`` — that's what goes in the
DB, so moving the root doesn't break references.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Protocol

import numpy as np

from src.common.config import get_settings
from src.common.logging import get_logger

log = get_logger(__name__)


class ImageEncoder(Protocol):
    def imwrite(self, path: str, image: np.ndarray) -> bool: ...


def _cv2_encoder() -> ImageEncoder | None:
    try:
        import cv2

        return cv2  # cv2 has an imwrite that satisfies the protocol
    except Exception:
        return None


def save_snapshot(
    image: np.ndarray | None,
    *,
    camera_id: str,
    tag: str = "event",
    encoder: ImageEncoder | None = None,
) -> str | None:
    """Save ``image`` and return its relative path (or None if nothing to save)."""
    if image is None:
        return None

    settings = get_settings()
    now = datetime.utcnow()
    subdir = now.strftime("%Y-%m-%d")
    root = settings.snapshot_dir / subdir
    root.mkdir(parents=True, exist_ok=True)

    rel_name = f"{camera_id}_{tag}_{now.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
    abs_path = root / rel_name

    encoder = encoder or _cv2_encoder()
    if encoder is None:      # pragma: no cover - only in envs without cv2 installed
        log.warning("snapshot_encoder_missing", extra={"camera_id": camera_id})
        return None

    ok = encoder.imwrite(str(abs_path), image)
    if not ok:
        log.warning("snapshot_write_failed", extra={"camera_id": camera_id})
        return None

    return f"{subdir}/{rel_name}"


def purge_older_than(days: int) -> int:
    """Delete snapshot folders older than ``days``. Returns count removed."""
    from shutil import rmtree

    root = get_settings().snapshot_dir
    if not root.exists():
        return 0

    cutoff = datetime.utcnow().date()
    removed = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            when = datetime.strptime(child.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if (cutoff - when).days > days:
            rmtree(child, ignore_errors=True)
            removed += 1
    return removed


def project_root_relative(rel: str) -> Path:
    return get_settings().snapshot_dir / rel
