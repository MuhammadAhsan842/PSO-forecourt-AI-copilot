"""Camera controller — the API used by the capture sequencer (M8) and preset
management (M3). All operations are best-effort; a locked control returns a
clear ``ControlError`` that callers handle rather than crash on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.common.config import CameraConfig
from src.common.logging import get_logger

log = get_logger(__name__)


class ControlError(RuntimeError):
    """Raised when a camera-side control cannot be performed."""


@dataclass
class Preset:
    name: str
    pan: float
    tilt: float
    zoom: float
    focus: float | str = "auto"
    exposure: dict[str, Any] | None = None


class CameraController:
    """Wrap ONVIF (imaging + PTZ) + Dahua HTTP behind one small surface.

    All methods raise ``ControlError`` on failure — callers log-and-continue.
    """

    def __init__(self, camera: CameraConfig):
        self.camera = camera
        self._onvif = None
        self._media = None
        self._imaging = None
        self._ptz = None
        self._profile_token: str | None = None
        self._video_source_token: str | None = None
        self._http = None  # lazily-built Dahua HTTP CGI client

    # ------- Dahua HTTP CGI (primary imaging-control path) -----------------

    def _http_client(self):
        """Build (once) the Dahua HTTP client, addressing the camera even when it
        sits behind the NVR (via the virtual-host port)."""
        if self._http is not None:
            return self._http
        from src.cameractl.dahua_http import DahuaCameraHTTP

        cam = self.camera
        if not (cam.host and cam.user and cam.password):
            raise ControlError("camera credentials missing for HTTP control")
        # Behind an NVR: talk to the camera on the NVR IP + its virtual-host port.
        port = cam.vhost_port or cam.http_port
        self._http = DahuaCameraHTTP(
            cam.host, cam.user, cam.password,
            port=port, use_https=cam.use_https,
            snapshot_channel=cam.nvr_channel or 1,
        )
        return self._http

    # ------- lifecycle -----------------------------------------------------

    def connect(self) -> None:
        if not (self.camera.host and self.camera.user and self.camera.password):
            raise ControlError("camera credentials missing (host/user/pass)")

        try:
            from onvif import ONVIFCamera
        except Exception as exc:
            raise ControlError(f"onvif-zeep not installed: {exc}") from exc

        try:
            cam = ONVIFCamera(
                self.camera.host,
                self.camera.onvif_port or 80,
                self.camera.user,
                self.camera.password,
            )
            self._onvif = cam
            self._media = cam.create_media_service()
            profiles = self._media.GetProfiles()
            if not profiles:
                raise ControlError("no media profiles reported by camera")
            self._profile_token = profiles[0].token
            self._video_source_token = profiles[0].VideoSourceConfiguration.SourceToken
            self._imaging = cam.create_imaging_service()
            try:
                self._ptz = cam.create_ptz_service()
            except Exception:
                self._ptz = None
        except Exception as exc:
            raise ControlError(f"ONVIF connect failed: {exc}") from exc

        log.info(
            "camera_connected",
            extra={
                "camera_id": self.camera.id,
                "context": {
                    "host": self.camera.host,
                    "profile": self._profile_token,
                    "has_ptz": self._ptz is not None,
                },
            },
        )

    # ------- imaging -------------------------------------------------------

    def set_exposure_http(
        self,
        *,
        mode: str = "manual",
        shutter: str | None = None,
        gain: int | None = None,
        wdr: bool | None = None,
        wdr_value: int = 50,
        backlight: str | None = None,
    ) -> None:
        """Set exposure/WDR via the Dahua HTTP CGI — the reliable programmatic path.

        This is what un-glares the meter from code (§3). Works on a directly-
        addressable camera or one behind the NVR virtual host. Raises ControlError
        on any failure so the caller degrades gracefully.
        """
        from src.cameractl.dahua_http import DahuaHTTPError

        try:
            http = self._http_client()
            if mode == "auto":
                http.set_auto_exposure()
            else:
                http.set_exposure_manual(shutter=shutter, gain=gain)
            if wdr is not None:
                http.set_wdr(wdr, value=wdr_value)
            if backlight is not None:
                http.set_backlight(backlight)
        except DahuaHTTPError as exc:
            raise ControlError(f"set_exposure_http failed: {exc}") from exc
        log.info(
            "exposure_set_http",
            extra={
                "camera_id": self.camera.id,
                "context": {"mode": mode, "shutter": shutter, "gain": gain, "wdr": wdr,
                            "backlight": backlight},
            },
        )

    def snapshot_http(self) -> bytes:
        """Grab a still straight from the camera CGI (bytes)."""
        from src.cameractl.dahua_http import DahuaHTTPError

        try:
            return self._http_client().snapshot()
        except DahuaHTTPError as exc:
            raise ControlError(f"snapshot_http failed: {exc}") from exc

    def set_exposure(
        self,
        *,
        mode: str = "manual",
        shutter_ms: float | None = None,
        gain_db: float | None = None,
        wdr: bool | None = None,
    ) -> None:
        """Push exposure settings over ONVIF. ``mode`` is "auto" or "manual".

        Prefer ``set_exposure_http`` for Dahua — ONVIF imaging is often a partial
        surface. This remains for ONVIF-only devices.
        """
        if self._imaging is None or self._video_source_token is None:
            raise ControlError("imaging service not initialized (call connect() first)")

        exposure: dict[str, Any] = {"Mode": "AUTO" if mode == "auto" else "MANUAL"}
        if shutter_ms is not None:
            # ONVIF uses seconds; camera uses inverse of shutter speed
            exposure["ExposureTime"] = shutter_ms / 1000.0
        if gain_db is not None:
            exposure["Gain"] = gain_db

        body: dict[str, Any] = {
            "VideoSourceToken": self._video_source_token,
            "ImagingSettings": {"Exposure": exposure},
        }
        if wdr is not None:
            body["ImagingSettings"]["WideDynamicRange"] = {
                "Mode": "ON" if wdr else "OFF"
            }

        try:
            self._imaging.SetImagingSettings(body)
        except Exception as exc:
            raise ControlError(f"set_exposure failed: {exc}") from exc

        log.info(
            "exposure_set",
            extra={
                "camera_id": self.camera.id,
                "context": {"mode": mode, "shutter_ms": shutter_ms, "gain_db": gain_db, "wdr": wdr},
            },
        )

    def set_focus(self, position: float | str) -> None:
        """position: float in 0..1 or "auto"."""
        if self._imaging is None or self._video_source_token is None:
            raise ControlError("imaging service not initialized")

        if position == "auto":
            move = {"VideoSourceToken": self._video_source_token, "Focus": {"Continuous": {"Speed": 0.5}}}
        else:
            move = {
                "VideoSourceToken": self._video_source_token,
                "Focus": {"Absolute": {"Position": float(position), "Speed": 1.0}},
            }
        try:
            self._imaging.Move(move)
        except Exception as exc:
            raise ControlError(f"set_focus failed: {exc}") from exc

        log.info(
            "focus_set",
            extra={"camera_id": self.camera.id, "context": {"position": position}},
        )

    # ------- PTZ -----------------------------------------------------------

    def move_absolute(self, pan: float, tilt: float, zoom: float) -> None:
        if self._ptz is None or self._profile_token is None:
            raise ControlError("PTZ not available")
        try:
            self._ptz.AbsoluteMove(
                {
                    "ProfileToken": self._profile_token,
                    "Position": {
                        "PanTilt": {"x": pan, "y": tilt},
                        "Zoom": {"x": zoom},
                    },
                    "Speed": {
                        "PanTilt": {"x": 1.0, "y": 1.0},
                        "Zoom": {"x": 1.0},
                    },
                }
            )
        except Exception as exc:
            raise ControlError(f"move_absolute failed: {exc}") from exc

        log.info(
            "ptz_absolute",
            extra={
                "camera_id": self.camera.id,
                "context": {"pan": pan, "tilt": tilt, "zoom": zoom},
            },
        )

    def stop(self) -> None:
        if self._ptz is None or self._profile_token is None:
            return
        try:
            self._ptz.Stop({"ProfileToken": self._profile_token, "PanTilt": True, "Zoom": True})
        except Exception as exc:
            raise ControlError(f"stop failed: {exc}") from exc

    def save_preset(self, name: str) -> str:
        if self._ptz is None or self._profile_token is None:
            raise ControlError("PTZ not available")
        try:
            token = self._ptz.SetPreset(
                {"ProfileToken": self._profile_token, "PresetName": name}
            )
        except Exception as exc:
            raise ControlError(f"save_preset failed: {exc}") from exc
        log.info("preset_saved", extra={"camera_id": self.camera.id, "context": {"name": name, "token": token}})
        return str(token)

    def recall_preset(self, token: str) -> None:
        if self._ptz is None or self._profile_token is None:
            raise ControlError("PTZ not available")
        try:
            self._ptz.GotoPreset(
                {
                    "ProfileToken": self._profile_token,
                    "PresetToken": token,
                    "Speed": {"PanTilt": {"x": 1.0, "y": 1.0}, "Zoom": {"x": 1.0}},
                }
            )
        except Exception as exc:
            raise ControlError(f"recall_preset failed: {exc}") from exc

        log.info(
            "preset_recalled",
            extra={"camera_id": self.camera.id, "context": {"token": token}},
        )

    def list_presets(self) -> list[dict[str, str]]:
        if self._ptz is None or self._profile_token is None:
            return []
        try:
            items = self._ptz.GetPresets({"ProfileToken": self._profile_token}) or []
        except Exception as exc:
            raise ControlError(f"list_presets failed: {exc}") from exc
        return [
            {"token": str(getattr(p, "token", "?")), "name": str(getattr(p, "Name", "?"))}
            for p in items
        ]
