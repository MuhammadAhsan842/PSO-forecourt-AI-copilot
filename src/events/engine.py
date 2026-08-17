"""Event engine — glue between tracker output and event proposals.

Owns per-camera state:
  * Zone / line geometry (from ``zones.yaml``).
  * Previous-frame bboxes per track (for line-crossing).
  * Per (kind, key) cooldowns to prevent alert storms.

The engine emits ``EventRecord`` instances via an ``EventSink`` — the API is a
concrete sink (writes to DB + WebSocket), tests use a list sink.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.common.logging import get_logger
from src.common.types import EventRecord, Track
from src.events.geometry import Line, Zone, polygon_from_pairs
from src.events.rules import EventProposal, RuleContext, run_rules

log = get_logger(__name__)


class EventSink(Protocol):
    def emit(self, event: EventRecord) -> None: ...


class ListSink:
    """Simple in-process sink for tests + demos."""

    def __init__(self) -> None:
        self.events: list[EventRecord] = []

    def emit(self, event: EventRecord) -> None:
        self.events.append(event)


@dataclass
class _CameraState:
    camera_id: str
    zones: list[Zone]
    lines: list[Line]
    last_bboxes: dict[int, tuple] = None  # type: ignore[assignment]
    last_seen_at: dict[int, float] = None  # type: ignore[assignment]
    cooldowns: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.last_bboxes = {}
        self.last_seen_at = {}
        self.cooldowns = {}


class EventEngine:
    def __init__(
        self,
        *,
        enabled_rules: Iterable[str],
        cooldown_seconds: dict[str, float] | None = None,
        settings: dict | None = None,
        clock: Callable[[], datetime] = datetime.utcnow,
    ):
        self.enabled_rules = list(enabled_rules)
        self.cooldowns = {k: float(v) for k, v in (cooldown_seconds or {}).items()}
        self.settings = settings or {}
        self.clock = clock
        self._cameras: dict[str, _CameraState] = {}

    # --- configuration -----------------------------------------------------

    def configure_camera(
        self,
        camera_id: str,
        *,
        zones_cfg: list[dict],
        lines_cfg: list[dict],
    ) -> None:
        zones: list[Zone] = []
        for z in zones_cfg:
            zones.append(
                Zone(
                    id=z["id"],
                    kind=z["kind"],
                    polygon=polygon_from_pairs(z["polygon"]),
                    meta={
                        k: v
                        for k, v in z.items()
                        if k not in {"id", "kind", "polygon"}
                    },
                )
            )
        lines: list[Line] = []
        for line in lines_cfg:
            lines.append(
                Line(
                    id=line["id"],
                    kind=line["kind"],
                    a=(line["a"][0], line["a"][1]),
                    b=(line["b"][0], line["b"][1]),
                    direction=line.get("direction"),
                )
            )
        self._cameras[camera_id] = _CameraState(camera_id=camera_id, zones=zones, lines=lines)
        log.info(
            "engine_camera_configured",
            extra={"camera_id": camera_id, "context": {"zones": len(zones), "lines": len(lines)}},
        )

    # --- tick --------------------------------------------------------------

    def tick(
        self,
        camera_id: str,
        tracks: list[Track],
        sink: EventSink,
    ) -> list[EventRecord]:
        state = self._cameras.get(camera_id)
        if state is None:
            log.warning("engine_unconfigured_camera", extra={"camera_id": camera_id})
            return []

        now = self.clock()

        # Update age_seconds using first-seen timestamps. Respect an incoming
        # ``age_seconds`` from the tracker when it's larger than what we can
        # compute from our own first-seen ledger (tracker may have seen this id
        # before the engine started ticking on this camera).
        wall = time.time()
        for t in tracks:
            first = state.last_seen_at.get(t.track_id)
            if first is None:
                state.last_seen_at[t.track_id] = wall - float(t.age_seconds or 0.0)
                computed = float(t.age_seconds or 0.0)
            else:
                computed = max(0.0, wall - first)
            t.age_seconds = max(computed, float(t.age_seconds or 0.0))

        active_ids = {t.track_id for t in tracks}
        state.last_seen_at = {tid: v for tid, v in state.last_seen_at.items() if tid in active_ids}

        ctx = RuleContext(
            camera_id=camera_id,
            now=now,
            tracks=tracks,
            zones=state.zones,
            lines=state.lines,
            prev_bboxes=dict(state.last_bboxes),
            settings=self.settings,
        )
        proposals = run_rules(self.enabled_rules, ctx)

        emitted: list[EventRecord] = []
        for p in proposals:
            key = p.dedupe_key()
            cd = self.cooldowns.get(p.kind.value, 0.0)
            last = state.cooldowns.get(key, 0.0)
            if cd and (wall - last) < cd:
                continue
            state.cooldowns[key] = wall
            record = EventRecord(
                id=_gen_id(now, p),
                kind=p.kind,
                camera_id=p.camera_id,
                track_id=p.track_id,
                zone_id=p.zone_id,
                confidence=p.confidence,
                payload=p.payload,
                ts=now,
            )
            sink.emit(record)
            emitted.append(record)
            log.info(
                "event_emitted",
                extra={
                    "camera_id": p.camera_id,
                    "track_id": p.track_id,
                    "zone_id": p.zone_id,
                    "event": p.kind.value,
                    "context": p.payload,
                },
            )

        # Snapshot bboxes for the next tick's line-crossing checks
        state.last_bboxes = {t.track_id: t.bbox for t in tracks}
        return emitted


def _gen_id(when: datetime, p: EventProposal) -> str:
    return f"{p.kind.value}-{when.strftime('%Y%m%dT%H%M%S%f')}-{p.track_id or 'x'}-{p.zone_id or 'x'}"
