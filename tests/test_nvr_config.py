"""NVR-fronted camera config: RTSP URL is built from host + channel."""

from __future__ import annotations

import os
from pathlib import Path

from src.common.config import build_nvr_rtsp_url, load_cameras


def test_build_nvr_rtsp_url() -> None:
    url = build_nvr_rtsp_url(
        host="192.168.1.114", user="admin", password="secret", channel=3, subtype=1
    )
    assert url == "rtsp://admin:secret@192.168.1.114:554/cam/realmonitor?channel=3&subtype=1"


def test_build_nvr_rtsp_url_without_creds() -> None:
    url = build_nvr_rtsp_url(host="10.0.0.5", user=None, password=None, channel=1)
    assert url == "rtsp://10.0.0.5:554/cam/realmonitor?channel=1&subtype=0"


def test_loader_builds_rtsp_from_nvr_channel(tmp_path: Path) -> None:
    cfg = tmp_path / "cameras.yaml"
    cfg.write_text(
        """
cameras:
  - id: pump_a
    name: Pump A
    role: fixed_meter
    nvr_channel: 2
    rtsp_env: CAM_PA_RTSP
    host_env: CAM_PA_HOST
    user_env: CAM_PA_USER
    pass_env: CAM_PA_PASS
"""
    )
    os.environ["CAM_PA_HOST"] = "192.168.1.114"
    os.environ["CAM_PA_USER"] = "admin"
    os.environ["CAM_PA_PASS"] = "pw"
    os.environ.pop("CAM_PA_RTSP", None)  # no explicit URL → must be built

    cams = load_cameras(cfg)
    pa = cams[0]
    assert pa.rtsp_url == "rtsp://admin:pw@192.168.1.114:554/cam/realmonitor?channel=2&subtype=0"
