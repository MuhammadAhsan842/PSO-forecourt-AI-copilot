"""Camera controller: graceful ControlError paths (no live camera needed).

The controller wraps real ONVIF calls; here we verify it fails *loud but safe*
(raises ControlError, never crashes the pipeline) when misconfigured or when the
underlying service rejects a call — the §8 "degrade gracefully" contract.
"""

from __future__ import annotations

import pytest

from src.cameractl.controller import CameraController, ControlError
from src.common.config import CameraConfig


def _cam(**overrides) -> CameraConfig:
    base = {"id": "ptz1", "name": "PTZ 1", "role": "ptz", "rtsp_env": "X"}
    base.update(overrides)
    cam = CameraConfig(**base)
    cam.host = overrides.get("host")
    cam.user = overrides.get("user")
    cam.password = overrides.get("password")
    return cam


def test_connect_without_credentials_raises_control_error() -> None:
    ctrl = CameraController(_cam(host=None, user=None, password=None))
    with pytest.raises(ControlError):
        ctrl.connect()


def test_operations_before_connect_raise_control_error() -> None:
    ctrl = CameraController(_cam(host="1.2.3.4", user="admin", password="x"))
    with pytest.raises(ControlError):
        ctrl.set_exposure(mode="manual", shutter_ms=8.0)
    with pytest.raises(ControlError):
        ctrl.move_absolute(0.1, 0.2, 0.3)
    with pytest.raises(ControlError):
        ctrl.recall_preset("10")


def test_imaging_error_is_wrapped(monkeypatch) -> None:
    ctrl = CameraController(_cam(host="1.2.3.4", user="admin", password="x"))

    class _Boom:
        def SetImagingSettings(self, _body):  # noqa: N802 — matches ONVIF method name
            raise RuntimeError("device rejected")

    # Simulate a connected imaging service that rejects the call.
    ctrl._imaging = _Boom()
    ctrl._video_source_token = "vs0"
    with pytest.raises(ControlError) as exc:
        ctrl.set_exposure(mode="manual", shutter_ms=4.0)
    assert "set_exposure failed" in str(exc.value)


def test_list_presets_without_ptz_returns_empty() -> None:
    ctrl = CameraController(_cam(host="1.2.3.4", user="admin", password="x"))
    assert ctrl.list_presets() == []
