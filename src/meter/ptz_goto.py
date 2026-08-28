"""PTZ preset recall — ONVIF GotoPreset first, Dahua HTTP CGI fallback.

On this site the cameras sit behind a Dahua NVR. ONVIF against the NVR often
does not address a recorder channel; the HTTP CGI ``ptz.cgi`` with ``channel=N``
is the path that actually moved channel 10 on 2026-08-26.
"""

from __future__ import annotations

from src.cameractl.controller import CameraController, ControlError
from src.common.config import CameraConfig
from src.common.logging import get_logger

log = get_logger(__name__)


class PtzGotoError(RuntimeError):
    pass


def dahua_goto_preset_url(host: str, http_port: int, channel: int, preset_index: int) -> str:
    return (
        f"http://{host}:{http_port}/cgi-bin/ptz.cgi"
        f"?action=start&channel={channel}&code=GotoPreset"
        f"&arg1=0&arg2={preset_index}&arg3=0"
    )


def dahua_goto_preset(
    *,
    host: str,
    user: str,
    password: str,
    channel: int,
    preset_index: int,
    http_port: int = 80,
    timeout: float = 8.0,
) -> None:
    """Dahua NVR/camera: GotoPreset on a recorder channel (1-based)."""
    import requests
    from requests.auth import HTTPDigestAuth

    url = dahua_goto_preset_url(host, http_port, channel, preset_index)
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=timeout)
    except requests.RequestException as exc:
        raise PtzGotoError(f"Dahua GotoPreset network error: {exc}") from exc
    body = (r.text or "").strip()
    if r.status_code != 200 or "OK" not in body:
        raise PtzGotoError(f"Dahua GotoPreset failed HTTP {r.status_code}: {body[:200]!r}")
    log.info(
        "dahua_goto_preset",
        extra={"context": {"channel": channel, "preset_index": preset_index}},
    )


def dahua_list_presets(
    *,
    host: str,
    user: str,
    password: str,
    channel: int,
    http_port: int = 80,
    timeout: float = 8.0,
) -> list[dict[str, str]]:
    import requests
    from requests.auth import HTTPDigestAuth

    url = f"http://{host}:{http_port}/cgi-bin/ptz.cgi?action=getPresets&channel={channel}"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(user, password), timeout=timeout)
    except requests.RequestException as exc:
        raise PtzGotoError(f"Dahua getPresets network error: {exc}") from exc
    if r.status_code != 200:
        raise PtzGotoError(f"getPresets HTTP {r.status_code}")
    return parse_dahua_presets(r.text or "")


def parse_dahua_presets(body: str) -> list[dict[str, str]]:
    # presets[0].Index=1 / presets[0].Name=...
    by_i: dict[str, dict[str, str]] = {}
    for line in body.splitlines():
        if "=" not in line or "presets[" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        idx = key.split("[", 1)[-1].split("]", 1)[0]
        field = key.rsplit(".", 1)[-1]
        by_i.setdefault(idx, {})[field] = val
    return list(by_i.values())


def onvif_goto_preset(cam: CameraConfig, preset_name_or_token: str) -> None:
    ctrl = CameraController(cam)
    ctrl.connect()
    presets = ctrl.list_presets()
    if not presets:
        raise PtzGotoError("ONVIF connected but no PTZ presets (no PTZ service?)")
    token = None
    for p in presets:
        if p.get("token") == preset_name_or_token or p.get("name") == preset_name_or_token:
            token = p["token"]
            break
    if token is None:
        raise PtzGotoError(
            f"ONVIF preset {preset_name_or_token!r} not in {[p.get('name') for p in presets]}"
        )
    ctrl.recall_preset(token)


def goto_preset(
    *,
    host: str,
    user: str,
    password: str,
    channel: int,
    preset_index: int | None = None,
    preset_name: str | None = None,
    onvif_port: int = 80,
    http_port: int = 80,
    try_onvif: bool = True,
) -> str:
    """Return which backend succeeded: 'onvif' | 'dahua_http'."""
    if try_onvif and preset_name:
        cam = CameraConfig(
            id="optics_ptz",
            name="optics_ptz",
            role="ptz",
            is_ptz=True,
            rtsp_env="CAM_PUMP_A_RTSP",
            host=host,
            user=user,
            password=password,
            onvif_port=onvif_port,
            nvr_channel=channel,
            http_port=http_port,
        )
        try:
            onvif_goto_preset(cam, preset_name)
            return "onvif"
        except (ControlError, PtzGotoError) as exc:
            log.warning("onvif_goto_failed_falling_back", extra={"context": {"err": str(exc)}})

    if preset_index is None:
        raise PtzGotoError("need --preset-index for Dahua HTTP fallback (or a working ONVIF name)")
    dahua_goto_preset(
        host=host,
        user=user,
        password=password,
        channel=channel,
        preset_index=preset_index,
        http_port=http_port,
    )
    return "dahua_http"
