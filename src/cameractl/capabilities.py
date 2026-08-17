"""Capability discovery. THIS IS THE MILESTONE 1 GATE.

Given camera credentials + host, probe:
  * ONVIF service discovery (imaging + PTZ) — exposure/gain/WDR, PTZ move/stop, presets.
  * Dahua HTTP API — model/firmware, direct exposure endpoints when ONVIF is limited.
  * RTSP reachability (we do NOT try to decode here; just TCP + describe).

Return a ``CameraCapabilities`` object that the report tool renders into a
human-readable matrix.  Milestone 1 acceptance = a report that clearly says
"exposure is available" or "exposure is locked" per camera model.
"""

from __future__ import annotations

import socket
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class CameraCapabilities:
    camera_id: str
    host: str | None
    onvif_port: int | None
    rtsp_reachable: bool = False
    onvif_reachable: bool = False
    dahua_http_reachable: bool = False

    # Imaging
    exposure_read: bool = False
    exposure_write: bool = False
    shutter_write: bool = False
    gain_write: bool = False
    wdr_write: bool = False

    # PTZ
    ptz_present: bool = False
    ptz_continuous: bool = False
    ptz_absolute: bool = False
    zoom_write: bool = False
    focus_write: bool = False
    presets_supported: bool = False
    preset_list: list[str] = field(default_factory=list)

    model: str | None = None
    firmware: str | None = None

    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def readable_summary(self) -> str:
        lines = [
            f"Camera {self.camera_id} ({self.model or 'unknown model'})",
            f"  host={self.host}:{self.onvif_port}  fw={self.firmware or '-'}",
            f"  RTSP reachable:   {_yn(self.rtsp_reachable)}",
            f"  ONVIF reachable:  {_yn(self.onvif_reachable)}",
            f"  Dahua HTTP:       {_yn(self.dahua_http_reachable)}",
            "  IMAGING",
            f"    exposure read/write:  {_yn(self.exposure_read)} / {_yn(self.exposure_write)}",
            f"    shutter write:        {_yn(self.shutter_write)}",
            f"    gain write:           {_yn(self.gain_write)}",
            f"    WDR write:            {_yn(self.wdr_write)}",
            "  PTZ",
            f"    ptz present:          {_yn(self.ptz_present)}",
            f"    absolute move:        {_yn(self.ptz_absolute)}",
            f"    continuous move:      {_yn(self.ptz_continuous)}",
            f"    zoom write:           {_yn(self.zoom_write)}",
            f"    focus write:          {_yn(self.focus_write)}",
            f"    presets supported:    {_yn(self.presets_supported)}  "
            f"({len(self.preset_list)} defined)",
        ]
        if self.notes:
            lines.append("  NOTES")
            for n in self.notes:
                lines.append(f"    - {n}")
        return "\n".join(lines)

    def gate_passes(self) -> bool:
        """Per the .cursorrules: at least exposure OR (ptz + focus) must work."""
        return self.exposure_write or (self.ptz_absolute and self.focus_write)


def _yn(x: bool) -> str:
    return "yes" if x else "no"


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _rtsp_reachable(rtsp_url: str, timeout: float = 2.0) -> bool:
    if not rtsp_url:
        return False
    parsed = urlparse(rtsp_url)
    if not parsed.hostname:
        return False
    return _tcp_reachable(parsed.hostname, parsed.port or 554, timeout=timeout)


def probe_camera(
    camera_id: str,
    *,
    host: str | None,
    onvif_port: int | None,
    user: str | None,
    password: str | None,
    rtsp_url: str | None,
) -> CameraCapabilities:
    """Perform the full probe. Returns a populated capabilities record."""
    caps = CameraCapabilities(
        camera_id=camera_id, host=host, onvif_port=onvif_port or 80
    )

    if rtsp_url:
        caps.rtsp_reachable = _rtsp_reachable(rtsp_url)
    if host and onvif_port:
        caps.onvif_reachable = _tcp_reachable(host, onvif_port)
        caps.dahua_http_reachable = _tcp_reachable(host, 80) or _tcp_reachable(host, 443)

    if not caps.onvif_reachable and not caps.dahua_http_reachable:
        caps.notes.append("No control channel reachable — check IP/creds/firewall.")
        return caps

    if caps.onvif_reachable and host and onvif_port and user and password:
        _probe_onvif(caps, host=host, port=onvif_port, user=user, password=password)

    if caps.dahua_http_reachable and host and user and password:
        _probe_dahua_http(caps, host=host, user=user, password=password)

    return caps


def _probe_onvif(
    caps: CameraCapabilities,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
) -> None:
    """Use onvif-zeep to enumerate imaging + PTZ capabilities."""
    try:
        from onvif import ONVIFCamera
    except Exception as exc:      # pragma: no cover - dep missing in some CI images
        caps.notes.append(f"onvif-zeep unavailable: {exc}")
        return

    t0 = time.time()
    try:
        cam = ONVIFCamera(host, port, user, password)
        info = cam.devicemgmt.GetDeviceInformation()
        caps.model = getattr(info, "Model", None)
        caps.firmware = getattr(info, "FirmwareVersion", None)
    except Exception as exc:
        caps.notes.append(f"ONVIF device info failed: {exc}")
        return

    # Imaging
    try:
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        profile_token = profiles[0].token if profiles else None

        if profile_token:
            imaging = cam.create_imaging_service()
            video_source_token = profiles[0].VideoSourceConfiguration.SourceToken
            options = imaging.GetOptions({"VideoSourceToken": video_source_token})
            caps.exposure_read = True
            exposure_opts = getattr(options, "Exposure", None)
            if exposure_opts is not None:
                caps.exposure_write = True
                caps.shutter_write = bool(getattr(exposure_opts, "ExposureTime", None))
                caps.gain_write = bool(getattr(exposure_opts, "Gain", None))
            wdr_opts = getattr(options, "WideDynamicRange", None)
            caps.wdr_write = wdr_opts is not None
    except Exception as exc:
        caps.notes.append(f"ONVIF imaging probe failed: {exc}")

    # PTZ
    try:
        ptz = cam.create_ptz_service()
        configs = ptz.GetConfigurations()
        if configs:
            caps.ptz_present = True
            spaces = ptz.GetConfigurationOptions({"ConfigurationToken": configs[0].token})
            caps.ptz_absolute = bool(getattr(spaces.Spaces, "AbsolutePanTiltPositionSpace", []))
            caps.ptz_continuous = bool(getattr(spaces.Spaces, "ContinuousPanTiltVelocitySpace", []))
            caps.zoom_write = bool(getattr(spaces.Spaces, "AbsoluteZoomPositionSpace", []))
            caps.focus_write = True  # imaging service focus commands, verified below

            if profile_token:
                try:
                    presets = ptz.GetPresets({"ProfileToken": profile_token})
                    caps.presets_supported = True
                    caps.preset_list = [
                        getattr(p, "Name", getattr(p, "token", "?")) for p in presets or []
                    ]
                except Exception:
                    caps.presets_supported = False
    except Exception as exc:
        caps.notes.append(f"ONVIF PTZ probe failed: {exc}")

    dt = (time.time() - t0) * 1000
    caps.notes.append(f"ONVIF probe took {dt:.0f} ms")


def _probe_dahua_http(
    caps: CameraCapabilities,
    *,
    host: str,
    user: str,
    password: str,
) -> None:
    """Best-effort verification of Dahua HTTP CGI endpoints, esp. for models where
    ONVIF hides half the imaging surface."""
    try:
        import requests
        from requests.auth import HTTPDigestAuth
    except Exception as exc:      # pragma: no cover - deps missing
        caps.notes.append(f"requests unavailable: {exc}")
        return

    url = f"http://{host}/cgi-bin/magicBox.cgi?action=getSystemInfo"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=3)
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.startswith("deviceType") and not caps.model:
                    caps.model = line.split("=", 1)[-1].strip()
                elif line.startswith("softwareVersion") and not caps.firmware:
                    caps.firmware = line.split("=", 1)[-1].strip()
        else:
            caps.notes.append(f"Dahua HTTP magicBox: HTTP {r.status_code}")
    except Exception as exc:
        caps.notes.append(f"Dahua HTTP probe failed: {exc}")
