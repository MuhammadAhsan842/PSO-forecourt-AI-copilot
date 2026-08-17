"""FastAPI routers, one file per concern."""

from . import events, feedback, snapshots, stats, system

__all__ = ["events", "feedback", "snapshots", "stats", "system"]
