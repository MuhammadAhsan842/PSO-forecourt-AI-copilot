"""Config + YAML loader round-trip tests."""

from __future__ import annotations

import os
from pathlib import Path

from src.common.config import load_cameras, load_presets, load_settings_yaml, load_zones


def test_cameras_yaml_loads(tmp_path: Path) -> None:
    os.environ["CAM_PTZ1_RTSP"] = "rtsp://demo/stream"
    os.environ["CAM_PTZ1_HOST"] = "10.0.0.1"
    os.environ["CAM_PTZ1_ONVIF_PORT"] = "80"
    os.environ["CAM_PTZ1_USER"] = "u"
    os.environ["CAM_PTZ1_PASS"] = "p"

    cams = load_cameras()
    assert cams
    cam = next((c for c in cams if c.id == "ptz1"), None)
    assert cam is not None
    assert cam.rtsp_url == "rtsp://demo/stream"
    assert cam.host == "10.0.0.1"
    assert cam.onvif_port == 80


def test_zones_and_presets_load() -> None:
    zones = load_zones()
    assert "ptz1" in zones.cameras
    presets = load_presets()
    assert "ptz1" in presets.presets
    assert "pump_a_meter" in presets.presets["ptz1"]


def test_settings_yaml_has_required_sections() -> None:
    s = load_settings_yaml()
    for key in ("inference", "events", "capture", "ocr", "api", "metrics"):
        assert key in s, f"settings.yaml missing '{key}'"
