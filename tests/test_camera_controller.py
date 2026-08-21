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


def test_set_exposure_http_uses_dahua_client() -> None:
    from src.cameractl.dahua_http import DahuaCameraHTTP

    class _MockSession:
        def __init__(self):
            self.calls = []

        def get(self, url, timeout=None):
            self.calls.append(url)
            return type("R", (), {"text": "OK", "status_code": 200, "content": b""})()

    ctrl = CameraController(_cam(host="192.168.1.114", user="admin", password="x"))
    sess = _MockSession()
    # Inject a client backed by the mock session.
    ctrl._http = DahuaCameraHTTP("192.168.1.114", "admin", "x", session=sess)

    ctrl.set_exposure_http(mode="manual", shutter="1/1000", gain=30, wdr=True, backlight="blc")
    joined = " ".join(sess.calls)
    assert "VideoInExposure[0][0].Mode=1" in joined
    assert "VideoInExposure[0][0].Shutter=1/1000" in joined
    assert "VideoInWideDynamicRange[0][0].Mode=1" in joined
    assert "VideoInBacklight[0][0].Mode=1" in joined


def test_set_exposure_http_wraps_errors() -> None:
    from src.cameractl.dahua_http import DahuaCameraHTTP

    class _BadSession:
        def get(self, url, timeout=None):
            return type("R", (), {"text": "", "status_code": 401, "content": b""})()

    ctrl = CameraController(_cam(host="192.168.1.114", user="admin", password="x"))
    ctrl._http = DahuaCameraHTTP("192.168.1.114", "admin", "x", session=_BadSession())
    with pytest.raises(ControlError):
        ctrl.set_exposure_http(mode="auto")
