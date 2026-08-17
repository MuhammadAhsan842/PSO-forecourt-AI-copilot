"""Config loader.

Two layers:
  * ``Settings`` — env-driven runtime settings (pydantic-settings). Reads .env.
  * YAML loaders (``load_cameras``, ``load_presets``, ``load_zones``) — file-driven,
    static-ish topology. Each one resolves env-var references (e.g. ``rtsp_env``) into
    real values at load time.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, env-first."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PSO_",
        extra="ignore",
        case_sensitive=False,
    )

    timezone: str = "Asia/Karachi"
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8080

    db_url: str = "sqlite+aiosqlite:///./data/pso.db"
    snapshot_dir: Path = Path("./data/snapshots")
    retention_days: int = 30

    yolo_weights: Path = Path("./models/yolo11n.pt")
    inference_fps: int = 8
    conf_threshold: float = 0.35
    device: str = "auto"

    config_dir: Path = Path("./config")

    @property
    def zones_path(self) -> Path:
        return self.config_dir / "zones.yaml"

    @property
    def cameras_path(self) -> Path:
        return self.config_dir / "cameras.yaml"

    @property
    def presets_path(self) -> Path:
        return self.config_dir / "presets.yaml"

    @property
    def settings_yaml_path(self) -> Path:
        return self.config_dir / "settings.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# --- YAML topology models -------------------------------------------------------------


class CameraConfig(BaseModel):
    id: str
    name: str
    role: str
    is_ptz: bool = False
    fps: int = 8
    rtsp_env: str
    host_env: str | None = None
    onvif_port_env: str | None = None
    user_env: str | None = None
    pass_env: str | None = None
    model_hint: str | None = None
    presets: dict[str, str] = Field(default_factory=dict)

    # Resolved at load time from env
    rtsp_url: str = ""
    host: str | None = None
    onvif_port: int | None = None
    user: str | None = None
    password: str | None = None


class ZonePolygon(BaseModel):
    id: str
    kind: str
    polygon: list[list[float]]
    pump_id: str | None = None
    settle_seconds: float | None = None
    dwell_seconds: float | None = None
    min_vehicles: int | None = None
    entry_alert: bool = False


class ZoneLine(BaseModel):
    id: str
    kind: str
    a: list[float]
    b: list[float]
    direction: str | None = None


class CameraZoneConfig(BaseModel):
    frame: dict[str, int] = Field(default_factory=lambda: {"width": 1920, "height": 1080})
    zones: list[ZonePolygon] = Field(default_factory=list)
    lines: list[ZoneLine] = Field(default_factory=list)


class ZonesConfig(BaseModel):
    after_hours: dict[str, str] = Field(default_factory=dict)
    cameras: dict[str, CameraZoneConfig] = Field(default_factory=dict)


class Preset(BaseModel):
    description: str = ""
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0
    focus: str | float = "auto"
    exposure: dict[str, Any] = Field(default_factory=dict)


class PresetsConfig(BaseModel):
    presets: dict[str, dict[str, Preset]] = Field(default_factory=dict)


# --- Loaders --------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file missing: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {path}")
    return data


def _resolve_env(name: str | None, default: str | None = None) -> str | None:
    if not name:
        return default
    return os.environ.get(name, default)


def load_cameras(path: Path | None = None) -> list[CameraConfig]:
    settings = get_settings()
    payload = _read_yaml(path or settings.cameras_path)
    out: list[CameraConfig] = []
    for raw in payload.get("cameras", []):
        cam = CameraConfig.model_validate(raw)
        cam.rtsp_url = _resolve_env(cam.rtsp_env, "") or ""
        cam.host = _resolve_env(cam.host_env)
        port_str = _resolve_env(cam.onvif_port_env, "80")
        cam.onvif_port = int(port_str) if port_str else None
        cam.user = _resolve_env(cam.user_env)
        cam.password = _resolve_env(cam.pass_env)
        out.append(cam)
    return out


def load_zones(path: Path | None = None) -> ZonesConfig:
    settings = get_settings()
    return ZonesConfig.model_validate(_read_yaml(path or settings.zones_path))


def load_presets(path: Path | None = None) -> PresetsConfig:
    settings = get_settings()
    return PresetsConfig.model_validate(_read_yaml(path or settings.presets_path))


def load_settings_yaml(path: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    return _read_yaml(path or settings.settings_yaml_path)
