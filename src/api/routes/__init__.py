"""FastAPI routers, one file per concern."""

from . import admin, events, feedback, meter, nvr, snapshots, stats, system

__all__ = ["admin", "events", "feedback", "meter", "nvr", "snapshots", "stats", "system"]
