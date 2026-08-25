"""Retention purge — the §9 privacy commitment made operational.

"Footage/snapshots stay on the local box; retention configurable (default ~30
days) with auto-purge." This runs both halves in one call:

  * DB rows (events, feedback, readings) older than the cutoff, and
  * snapshot folders older than the cutoff,

so a documented retention window is actually enforced, not just promised. Wired
to a manual admin endpoint and intended to be scheduled daily on-site.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.common.config import get_settings
from src.common.logging import get_logger
from src.storage import repository
from src.storage.db import get_session
from src.storage.snapshots import purge_older_than

log = get_logger(__name__)


async def run_retention_purge(retention_days: int | None = None) -> dict:
    """Purge DB rows and snapshot folders older than ``retention_days``."""
    days = retention_days if retention_days is not None else get_settings().retention_days
    cutoff = datetime.utcnow() - timedelta(days=days)

    db_removed: dict[str, int] = {}
    async for session in get_session():
        db_removed = await repository.purge_rows_older_than(session, cutoff)
        break

    snapshot_folders = purge_older_than(days)
    result = {
        "retention_days": days,
        "cutoff": cutoff.isoformat() + "Z",
        "db_rows_removed": db_removed,
        "snapshot_folders_removed": snapshot_folders,
    }
    log.info("retention_purge", extra={"context": result})
    return result
