"""Rules — pure functions over the current camera state. Easy to unit-test.

Each rule takes a small ``RuleContext`` (tracks + config + clock) and returns a
list of ``EventProposal`` objects. The engine deduplicates via a cooldown and
emits them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, time

from src.common.types import EventKind, Track
from src.events.geometry import Line, Zone


@dataclass
class EventProposal:
    kind: EventKind
    camera_id: str
    track_id: int | None = None
    zone_id: str | None = None
    confidence: float = 1.0
    payload: dict = field(default_factory=dict)

    def dedupe_key(self) -> str:
        return f"{self.camera_id}|{self.kind.value}|{self.track_id}|{self.zone_id}"


@dataclass
class RuleContext:
    camera_id: str
    now: datetime
    tracks: list[Track]
    zones: list[Zone]
    lines: list[Line]
    prev_bboxes: dict[int, tuple] = field(default_factory=dict)  # track_id -> BoundingBox(prev)
    settings: dict = field(default_factory=dict)


# ------------- individual rules ---------------------------------------------------------


def restricted_entry(ctx: RuleContext) -> list[EventProposal]:
    proposals: list[EventProposal] = []
    for zone in ctx.zones:
        if zone.kind != "restricted":
            continue
        for track in ctx.tracks:
            if zone.contains(track.bbox):
                proposals.append(
                    EventProposal(
                        kind=EventKind.RESTRICTED_ENTRY,
                        camera_id=ctx.camera_id,
                        track_id=track.track_id,
                        zone_id=zone.id,
                        confidence=track.confidence,
                        payload={"class": track.class_name},
                    )
                )
    return proposals


def queue_dwell(ctx: RuleContext) -> list[EventProposal]:
    proposals: list[EventProposal] = []
    for zone in ctx.zones:
        if zone.kind != "queue":
            continue
        dwell_s = float(zone.meta.get("dwell_seconds", 60))
        min_v = int(zone.meta.get("min_vehicles", 3))
        inside = [t for t in ctx.tracks if zone.contains(t.bbox) and t.class_name != "person"]
        long_dwellers = [t for t in inside if t.age_seconds >= dwell_s]
        if len(long_dwellers) >= min_v:
            proposals.append(
                EventProposal(
                    kind=EventKind.QUEUE_DWELL,
                    camera_id=ctx.camera_id,
                    zone_id=zone.id,
                    confidence=1.0,
                    payload={
                        "vehicles": len(long_dwellers),
                        "dwell_seconds_threshold": dwell_s,
                    },
                )
            )
    return proposals


def loitering(ctx: RuleContext) -> list[EventProposal]:
    loit_s = float(ctx.settings.get("loitering_seconds", 90))
    proposals: list[EventProposal] = []
    for t in ctx.tracks:
        if t.class_name != "person":
            continue
        if t.age_seconds >= loit_s:
            proposals.append(
                EventProposal(
                    kind=EventKind.LOITERING,
                    camera_id=ctx.camera_id,
                    track_id=t.track_id,
                    confidence=t.confidence,
                    payload={"age_seconds": round(t.age_seconds, 1)},
                )
            )
    return proposals


def vehicle_settled_at_pump(ctx: RuleContext) -> list[EventProposal]:
    """Fires when a vehicle has been inside a pump_bay zone long enough to serve.

    Trigger for the M8 capture sequencer (meter → plate).
    """
    proposals: list[EventProposal] = []
    for zone in ctx.zones:
        if zone.kind != "pump_bay":
            continue
        settle_s = float(zone.meta.get("settle_seconds", 3))
        for t in ctx.tracks:
            if t.class_name == "person":
                continue
            if zone.contains(t.bbox) and t.age_seconds >= settle_s:
                proposals.append(
                    EventProposal(
                        kind=EventKind.VEHICLE_SETTLED_AT_PUMP,
                        camera_id=ctx.camera_id,
                        track_id=t.track_id,
                        zone_id=zone.id,
                        confidence=t.confidence,
                        payload={
                            "pump_id": zone.meta.get("pump_id"),
                            "class": t.class_name,
                        },
                    )
                )
    return proposals


def after_hours_presence(ctx: RuleContext) -> list[EventProposal]:
    after = ctx.settings.get("after_hours") or {}
    if not after:
        return []
    if not _within_after_hours(ctx.now.time(), after.get("start"), after.get("stop")):
        return []
    proposals: list[EventProposal] = []
    for t in ctx.tracks:
        proposals.append(
            EventProposal(
                kind=EventKind.AFTER_HOURS_PRESENCE,
                camera_id=ctx.camera_id,
                track_id=t.track_id,
                confidence=t.confidence,
                payload={"class": t.class_name, "hour": ctx.now.strftime("%H:%M")},
            )
        )
    return proposals


# ------------- helpers ------------------------------------------------------------------


def _within_after_hours(now: time, start_str: str | None, stop_str: str | None) -> bool:
    if not start_str or not stop_str:
        return False
    start = _parse_hhmm(start_str)
    stop = _parse_hhmm(stop_str)
    if start == stop:
        return False
    if start < stop:                       # e.g. 09:00 -> 17:00
        return start <= now < stop
    return now >= start or now < stop      # wraps midnight


def _parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


ALL_RULES = {
    "restricted_entry": restricted_entry,
    "queue_dwell": queue_dwell,
    "loitering": loitering,
    "vehicle_settled_at_pump": vehicle_settled_at_pump,
    "after_hours_presence": after_hours_presence,
}


def run_rules(names: Iterable[str], ctx: RuleContext) -> list[EventProposal]:
    out: list[EventProposal] = []
    for name in names:
        rule = ALL_RULES.get(name)
        if rule is None:
            continue
        out.extend(rule(ctx))
    return out
