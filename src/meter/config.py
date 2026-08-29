"""Pump + ROI config for the meter pipeline. Credentials stay in .env."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.common.config import get_settings


class Rect(BaseModel):
    x: int
    y: int
    w: int
    h: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


class FieldLayout(BaseModel):
    digits: int = 4
    decimals: int = 2
    roi: Rect | None = None


class PumpConfig(BaseModel):
    id: str
    label: str = ""
    enabled: bool = True
    camera_id: str = "pump_a"
    nvr_channel: int
    is_ptz: bool = False
    preset_index: int | None = None
    preset_name: str | None = None
    # Physical flow ceiling. None = unknown; estimator will not invent a PSO rate.
    max_lpm: float | None = None
    settle_seconds: float = 2.0
    bezel: Rect
    fields: dict[str, FieldLayout] = Field(default_factory=dict)
    roi_version: int = 1
    frame_wh: tuple[int, int] = (3840, 2160)


def _meter_dir() -> Path:
    return get_settings().config_dir / "meter"


def load_pumps(path: Path | None = None) -> list[PumpConfig]:
    p = path or (_meter_dir() / "pumps.yaml")
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text()) or {}
    pumps: list[PumpConfig] = []
    for item in raw.get("pumps") or []:
        pumps.append(PumpConfig.model_validate(item))
    for pump in pumps:
        override = _latest_roi_override(pump.id, p.parent)
        if override is not None:
            pump.bezel = Rect.model_validate(override["bezel"])
            pump.roi_version = int(override.get("version", pump.roi_version))
            if override.get("fields"):
                merged = dict(pump.fields)
                for k, v in override["fields"].items():
                    merged[k] = FieldLayout.model_validate(v)
                pump.fields = merged
    return pumps


def _latest_roi_override(pump_id: str, meter_dir: Path) -> dict[str, Any] | None:
    roi_dir = meter_dir / "roi"
    if not roi_dir.exists():
        return None
    files = sorted(roi_dir.glob(f"{pump_id}_*.v*.yaml"))
    if not files:
        return None
    return yaml.safe_load(files[-1].read_text()) or None


def save_roi(pump_id: str, bezel: Rect, *, version: int, fields: dict | None = None) -> Path:
    roi_dir = _meter_dir() / "roi"
    roi_dir.mkdir(parents=True, exist_ok=True)
    path = roi_dir / f"{pump_id}_wide.v{version}.yaml"
    payload = {
        "pump_id": pump_id,
        "preset": "wide",
        "version": version,
        "bezel": bezel.model_dump(),
        "fields": fields or {},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def pump_by_id(pump_id: str, pumps: list[PumpConfig] | None = None) -> PumpConfig | None:
    for p in pumps if pumps is not None else load_pumps():
        if p.id == pump_id:
            return p
    return None


def meter_roi_for_channel(channel: int) -> tuple[int, int, int, int] | None:
    """Bezel crop for NVR live loupe. None if this channel has no meter pump."""
    for p in load_pumps():
        if p.enabled and p.nvr_channel == channel:
            return p.bezel.as_tuple()
    return None
