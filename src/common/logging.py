"""Structured logging via loguru.

Rule: every alert log line carries ``camera_id`` and (when present) ``track_id`` and
``event`` fields, so a technician can filter the log to one camera or one track.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from loguru import logger

_configured: bool = False


def _serialize(record: dict[str, Any]) -> str:
    payload = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": record["message"],
        "logger": record["name"],
    }
    extra = record.get("extra") or {}
    for k in ("camera_id", "track_id", "event", "zone_id", "latency_ms"):
        if k in extra:
            payload[k] = extra[k]
    if "context" in extra:
        payload["context"] = extra["context"]
    return json.dumps(payload, default=str)


def _json_sink(message: Any) -> None:
    print(_serialize(message.record), file=sys.stdout, flush=True)


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    global _configured
    if _configured:
        return
    logger.remove()
    if json_output:
        logger.add(_json_sink, level=level)
    else:
        logger.add(
            sys.stdout,
            level=level,
            format="<green>{time:HH:mm:ss}</green> <level>{level: <8}</level> "
            "<cyan>{name}</cyan> - <level>{message}</level>",
        )
    _configured = True


def get_logger(name: str) -> Any:
    """Return a loguru logger bound with the module name."""
    return logger.bind(name=name)
