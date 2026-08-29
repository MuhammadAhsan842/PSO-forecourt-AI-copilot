"""Versioned fill event contract (spec §9). Flat primitives for EventRecord.payload."""

from __future__ import annotations

from datetime import datetime
from typing import Any

FILL_SCHEMA_VERSION = 2


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat()


def fill_contract(
    *,
    pump_id: str,
    camera_id: str,
    preset_id: str | None = None,
    fill_start_ts: datetime | None = None,
    fill_end_ts: datetime | None = None,
    t0: float | None = None,
    t_final: float | None = None,
    litres: float | None = None,
    amount: float | None = None,
    unit_price_implied: float | None = None,
    per_reading_confidence: float = 0.0,
    final_total_confidence: float | None = None,
    flags: list[str] | None = None,
    frames_ref: str | None = None,
    provenance: str = "camera-observed",
    extra: dict[str, Any] | None = None,
) -> dict[str, str | int | float | bool | None]:
    disp = None
    if t_final is not None and t0 is not None:
        disp = round(float(t_final) - float(t0), 3)
    payload: dict[str, str | int | float | bool | None] = {
        "schema_version": FILL_SCHEMA_VERSION,
        "pump_id": pump_id,
        "camera_id": camera_id,
        "preset_id": preset_id,
        "fill_start_ts": _iso(fill_start_ts),
        "fill_end_ts": _iso(fill_end_ts),
        "T0": None if t0 is None else round(float(t0), 3),
        "T_final": None if t_final is None else round(float(t_final), 3),
        "amount": disp if amount is None else round(float(amount), 3),
        "litres": None if litres is None else round(float(litres), 3),
        "unit_price_implied": (
            None if unit_price_implied is None else round(float(unit_price_implied), 3)
        ),
        "per_reading_confidence": round(float(per_reading_confidence), 4),
        "final_total_confidence": (
            None
            if final_total_confidence is None
            else round(float(final_total_confidence), 4)
        ),
        "flags": ",".join(flags) if flags else "",
        "frames_ref": frames_ref,
        "provenance": provenance,
        "billed": False,
        "camera_observed": provenance != "pos-confirmed",
    }
    if extra:
        for k, v in extra.items():
            if k not in payload:
                payload[k] = v  # type: ignore[assignment]
    return payload
