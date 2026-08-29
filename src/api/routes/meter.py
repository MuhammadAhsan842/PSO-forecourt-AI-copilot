"""Meter readings + health. Does not replace /events."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.websocket import broadcast_event
from src.common.types import EventKind
from src.meter.config import Rect, load_pumps, pump_by_id, save_roi
from src.meter.pipeline import MeterTick
from src.meter.supervisor import MeterSupervisor
from src.ocr.seven_seg import render_seven_seg
from src.storage import repository
from src.storage.db import DBSession, get_session

router = APIRouter(prefix="/meter", tags=["meter"])

_supervisor: MeterSupervisor | None = None


def get_supervisor() -> MeterSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = MeterSupervisor()
    return _supervisor


def tick_public(tick: MeterTick) -> dict[str, Any]:
    return {
        "ts": tick.ts.isoformat(),
        "pump_id": tick.pump_id,
        "camera_id": tick.camera_id,
        "optics_pass": tick.optics_pass,
        "litres_raw": tick.litres_raw,
        "amount_raw": tick.amount_raw,
        "rate_raw": tick.rate_raw,
        "litres_est": tick.litres_est,
        "rate_lps": tick.rate_lps,
        "confidence": tick.confidence,
        "confidence_tier": tick.confidence_tier,
        "provenance": tick.provenance,
        "needs_review": tick.needs_review,
        "source": tick.source,
        "state": tick.state,
        "fill_phase": tick.fill_phase,
        "flags": tick.flags,
        "T0": tick.t0,
        "T_final": tick.t_final,
        "amount": tick.amount,
        "optics": tick.optics,
        "camera_observed": True,
        "billed": False,
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    return get_supervisor().health()


@router.get("/pumps")
async def pumps() -> list[dict[str, Any]]:
    return [p.model_dump() for p in load_pumps()]


@router.get("/live")
async def live(pump_id: str | None = None) -> dict[str, Any]:
    sup = get_supervisor()
    if pump_id:
        tick = sup.latest(pump_id)
        if tick is None:
            raise HTTPException(404, f"no tick yet for {pump_id}")
        return tick_public(tick)
    latest = sup.latest()
    if not isinstance(latest, dict) or not latest:
        return {"pumps": []}
    return {"pumps": [tick_public(t) for t in latest.values()]}


@router.get("/readings")
async def readings(
    camera_id: str | None = None,
    limit: int = 50,
    session: DBSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await repository.list_readings(session, camera_id=camera_id, limit=limit)


REVIEW_KINDS = (
    EventKind.METER_NEEDS_REVIEW,
    EventKind.METER_UNBILLED,
    EventKind.METER_POS_MISMATCH,
    EventKind.METER_NO_VEHICLE,
    EventKind.METER_HEALTH,
    EventKind.METER_OPTICS_FAIL,
)


@router.get("/review")
async def review_queue(
    limit: int = 50,
    session: DBSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = await repository.list_events(session, limit=400)
    wanted = {k.value for k in REVIEW_KINDS}
    out = [e.model_dump(mode="json") for e in rows if e.kind.value in wanted]
    return out[:limit]


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    sup = get_supervisor()
    first = next(iter(sup.pipelines.values()), None)
    snap = first.metrics.snapshot() if first else {}
    return {"schema_version": 1, "metrics": snap, "health": sup.health()}


class RoiUpdate(BaseModel):
    x: int
    y: int
    w: int
    h: int
    version: int | None = None


@router.put("/roi/{pump_id}")
async def update_roi(pump_id: str, body: RoiUpdate) -> dict[str, Any]:
    pump = pump_by_id(pump_id)
    if pump is None:
        raise HTTPException(404, f"unknown pump {pump_id}")
    version = body.version or (pump.roi_version + 1)
    bezel = Rect(x=body.x, y=body.y, w=body.w, h=body.h)
    path = save_roi(pump_id, bezel, version=version)
    from src.meter.audit import audit

    audit("roi_update", pump_id=pump_id, version=version, **bezel.model_dump())
    pump.bezel = bezel
    pump.roi_version = version
    sup = get_supervisor()
    if pump_id in sup.pipelines:
        sup.pipelines[pump_id].pump.bezel = bezel
        sup.pipelines[pump_id].pump.roi_version = version
    return {"ok": True, "path": str(path), "bezel": bezel.model_dump(), "version": version}


class SimulateIn(BaseModel):
    values: list[str] = Field(
        default_factory=lambda: [
            "0000",
            "0125",
            "0250",
            "0500",
            "0750",
            "1000",
            "1000",
            "1000",
            "1000",
        ]
    )


@router.post("/simulate-fill")
async def simulate_fill(
    body: SimulateIn | None = None,
    session: DBSession = Depends(get_session),
) -> dict[str, Any]:
    """Offline synthetic fill — proves the pipeline + dashboard without a camera.

    Optics gate is off because the renderer is not ≥600×300. Live NVR path keeps the gate on.
    """
    from src.meter.config import FieldLayout, PumpConfig
    from src.meter.pipeline import MeterPipeline

    body = body or SimulateIn()
    sample = render_seven_seg(body.values[0].replace(".", ""), cell_w=70, cell_h=120)
    h, w = sample.shape[:2]
    pump = PumpConfig(
        id="m1",
        label="M1 synthetic",
        camera_id="pump_a",
        nvr_channel=9,
        bezel=Rect(x=0, y=0, w=w, h=h),
        fields={"litres": FieldLayout(digits=4, decimals=2)},
        settle_seconds=0.5,
    )
    pipe = MeterPipeline(pump, enforce_optics_gate=False)
    ts = datetime.utcnow()
    ticks = []
    events = []
    for i, raw in enumerate(body.values):
        frame = render_seven_seg(raw.replace(".", ""), cell_w=70, cell_h=120)
        tick = pipe.process_frame(frame, ts + timedelta(seconds=i * 0.4))
        ticks.append(tick_public(tick))
        snap = None
        if any(e.kind == EventKind.METER_FILL_FINAL for e in tick.events) and tick.bezel_frame is not None:
            from src.storage.snapshots import save_snapshot

            snap = save_snapshot(tick.bezel_frame, camera_id="pump_a", tag="meter_final")
        for ev in tick.events:
            payload = dict(ev.payload)
            if snap:
                payload["frames_ref"] = snap
            stored = await repository.create_event(
                session,
                kind=ev.kind,
                camera_id=ev.camera_id,
                zone_id=ev.zone_id,
                confidence=ev.confidence,
                snapshot_path=snap,
                payload=payload,
            )
            events.append(stored.model_dump(mode="json"))
            await broadcast_event(stored)
    last = ticks[-1]
    reading = await repository.create_reading(
        session,
        camera_id="pump_a",
        value=str(
            last.get("litres_est")
            if last.get("litres_est") is not None
            else last.get("litres_raw") or ""
        ),
        confidence=float(last.get("confidence") or 0),
        payload={
            "schema_version": 2,
            "pump_id": "m1",
            "provenance": last.get("provenance"),
            "confidence_tier": last.get("confidence_tier"),
            "needs_review": last.get("needs_review"),
            "source": last.get("source"),
            "billed": False,
            "camera_observed": True,
        },
    )
    return {"ticks": ticks, "events": events, "reading": reading, "billed": False}
