"""Runtime supervisor: optional grabbers + latest ticks + health."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any

import numpy as np

from src.common.types import EventKind, EventRecord
from src.events.engine import EventSink, ListSink
from src.meter.config import PumpConfig, load_pumps
from src.meter.grabber import MeterGrabber
from src.meter.pipeline import MeterPipeline, MeterTick
from src.meter.pos import NullPosAdapter, PosAdapter
from src.meter.scheduler import PtzScheduler


class MeterSupervisor:
    def __init__(
        self,
        pumps: list[PumpConfig] | None = None,
        *,
        sink: EventSink | None = None,
        pos: PosAdapter | None = None,
        enforce_optics_gate: bool = True,
    ):
        self.pumps = [p for p in (pumps if pumps is not None else load_pumps()) if p.enabled]
        self.sink = sink or ListSink()
        self.pos = pos or NullPosAdapter()
        self.enforce_optics_gate = enforce_optics_gate
        self.pipelines = {
            p.id: MeterPipeline(p, enforce_optics_gate=enforce_optics_gate, pos=self.pos)
            for p in self.pumps
        }
        self.grabbers: dict[str, MeterGrabber] = {}
        self.scheduler = PtzScheduler(self.pumps)
        self._latest: dict[str, MeterTick] = {}
        self._lock = Lock()
        self._started = False
        self._stale_emitted: set[str] = set()

    def process_frame(self, pump_id: str, frame: np.ndarray, ts: datetime) -> MeterTick:
        pipe = self.pipelines.get(pump_id)
        if pipe is None:
            raise KeyError(pump_id)
        tick = pipe.process_frame(frame, ts)
        for ev in tick.events:
            self.sink.emit(ev)
        with self._lock:
            self._latest[pump_id] = tick
        return tick

    def latest(self, pump_id: str | None = None) -> MeterTick | dict[str, MeterTick] | None:
        with self._lock:
            if pump_id:
                return self._latest.get(pump_id)
            return dict(self._latest)

    def health(self) -> dict[str, Any]:
        with self._lock:
            ticks = dict(self._latest)
        pumps = []
        for p in self.pumps:
            tick = ticks.get(p.id)
            grab = self.grabbers.get(p.id)
            pumps.append(
                {
                    "pump_id": p.id,
                    "label": p.label,
                    "nvr_channel": p.nvr_channel,
                    "enabled": p.enabled,
                    "is_ptz": p.is_ptz,
                    "max_lpm": p.max_lpm,
                    "optics_pass": tick.optics_pass if tick else None,
                    "fill_phase": tick.fill_phase if tick else "idle",
                    "provenance": tick.provenance if tick else None,
                    "needs_review": tick.needs_review if tick else None,
                    "grabber_stale": grab.stale() if grab else None,
                    "supervisor_running": self._started,
                }
            )
        metrics = {}
        first = next(iter(self.pipelines.values()), None)
        if first is not None:
            metrics = first.metrics.snapshot()
        return {
            "schema_version": 1,
            "running": self._started,
            "n_pumps": len(self.pumps),
            "pumps": pumps,
            "metrics": metrics,
        }

    def note_stale(self, pump_id: str, ts: datetime) -> EventRecord | None:
        if pump_id in self._stale_emitted:
            return None
        self._stale_emitted.add(pump_id)
        pump = next((p for p in self.pumps if p.id == pump_id), None)
        cam = pump.camera_id if pump else pump_id
        rec = EventRecord(
            id=f"meter-health-stale-{pump_id}",
            kind=EventKind.METER_HEALTH,
            camera_id=cam,
            zone_id=pump_id,
            confidence=0.0,
            ts=ts,
            payload={
                "schema_version": 1,
                "pump_id": pump_id,
                "reason": "grabber_stale",
                "needs_review": True,
                "provenance": "optics-blocked",
            },
        )
        self.sink.emit(rec)
        return rec

    def tick_now(self) -> datetime:
        return datetime.now(UTC)
