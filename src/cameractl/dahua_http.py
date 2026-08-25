"""Dahua HTTP CGI camera control — the programmatic exposure/WDR path.

ONVIF Imaging exposes only part of a Dahua camera's imaging surface; the vendor
HTTP CGI (`configManager.cgi`) exposes all of it — exposure mode, shutter, gain,
WDR, backlight — which is what we need to un-glare the meter (§3) from code.

Design that keeps this honest and robust across firmware:

  * ``get_config(name)`` reads the LIVE config table (e.g. ``VideoInExposure``) and
    returns it as a flat ``{key: value}`` dict. We read the real schema before we
    write, instead of hard-coding keys that differ between camera generations.
  * ``set_config(params)`` writes back only the keys we intend to change.
  * Typed helpers (``set_exposure_manual``, ``set_auto_exposure``, ``set_wdr``,
    ``set_backlight``) build the common Dahua key names, but everything funnels
    through the generic get/set so a firmware quirk is a config change, not a code
    change.

Addressing a camera BEHIND the NVR: point ``host``/``port`` at the camera's
NVR *virtual-host* endpoint (NVR IP + the per-channel mapped port). The same
client then talks to the camera directly — no code change.

All methods raise ``DahuaHTTPError`` on failure; callers log-and-continue.
"""

from __future__ import annotations

from typing import Any

from src.common.logging import get_logger

log = get_logger(__name__)


class DahuaHTTPError(RuntimeError):
    """Raised when a Dahua CGI call fails."""


def _parse_config_lines(text: str) -> dict[str, str]:
    """Parse ``key=value`` CGI output into a flat dict (keys keep their paths)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


class DahuaCameraHTTP:
    """Thin, testable wrapper over Dahua's HTTP CGI (digest auth)."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        *,
        port: int = 80,
        use_https: bool = False,
        config_channel: int = 0,   # 0-based index into VideoIn* config arrays
        snapshot_channel: int = 1,  # 1-based channel for snapshot.cgi
        timeout: float = 5.0,
        session: Any | None = None,
    ):
        if not (host and user and password):
            raise DahuaHTTPError("host/user/password required")
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.scheme = "https" if use_https else "http"
        self.config_channel = config_channel
        self.snapshot_channel = snapshot_channel
        self.timeout = timeout
        self._session = session  # inject a mock in tests

    # --- transport ---------------------------------------------------------

    def _client(self):
        if self._session is not None:
            return self._session
        try:
            import requests
            from requests.auth import HTTPDigestAuth
        except Exception as exc:  # pragma: no cover
            raise DahuaHTTPError(f"requests not installed: {exc}") from exc
        sess = requests.Session()
        sess.auth = HTTPDigestAuth(self.user, self.password)
        self._session = sess
        return sess

    def _base(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def _get(self, path: str, *, raw: bool = False):
        url = f"{self._base()}{path}"
        try:
            resp = self._client().get(url, timeout=self.timeout)
        except Exception as exc:
            raise DahuaHTTPError(f"GET {path} failed: {exc}") from exc
        if resp.status_code != 200:
            raise DahuaHTTPError(f"GET {path} -> HTTP {resp.status_code}")
        return resp.content if raw else resp.text

    # --- generic config ----------------------------------------------------

    def get_config(self, name: str) -> dict[str, str]:
        """Read a config table, e.g. ``get_config("VideoInExposure")``."""
        text = self._get(f"/cgi-bin/configManager.cgi?action=getConfig&name={name}")
        return _parse_config_lines(text)

    def set_config(self, params: dict[str, Any]) -> None:
        """Write config keys. Keys are full Dahua paths (already channel-indexed)."""
        if not params:
            return
        query = "&".join(f"{k}={_fmt(v)}" for k, v in params.items())
        text = self._get(f"/cgi-bin/configManager.cgi?action=setConfig&{query}")
        if "OK" not in text and "ok" not in text:
            # Dahua returns "OK" on success; anything else is suspect.
            raise DahuaHTTPError(f"setConfig did not return OK: {text[:120]!r}")
        log.info("dahua_set_config", extra={"context": {"keys": list(params)}})

    # --- imaging helpers ---------------------------------------------------

    def set_auto_exposure(self) -> None:
        ch = self.config_channel
        self.set_config({f"VideoInExposure[{ch}][0].Mode": 0})

    def set_exposure_manual(
        self,
        *,
        shutter: str | None = None,   # e.g. "1/1000" or a ms value your firmware accepts
        gain: int | None = None,      # 0..100
        compensation: int | None = None,  # 0..100 (exposure compensation)
    ) -> None:
        """Set manual exposure. ``Mode=1`` is manual on Dahua CGI."""
        ch = self.config_channel
        params: dict[str, Any] = {f"VideoInExposure[{ch}][0].Mode": 1}
        if shutter is not None:
            params[f"VideoInExposure[{ch}][0].Shutter"] = shutter
        if gain is not None:
            params[f"VideoInExposure[{ch}][0].Gain"] = gain
        if compensation is not None:
            params[f"VideoInExposure[{ch}][0].Compensation"] = compensation
        self.set_config(params)

    def set_wdr(self, enabled: bool, value: int = 50) -> None:
        """Wide Dynamic Range: Mode 1 = on. ``value`` is strength 0..100."""
        ch = self.config_channel
        self.set_config(
            {
                f"VideoInWideDynamicRange[{ch}][0].Mode": 1 if enabled else 0,
                f"VideoInWideDynamicRange[{ch}][0].Value": max(0, min(100, value)),
            }
        )

    def set_backlight(self, mode: str) -> None:
        """Backlight compensation. mode: 'off' | 'blc' | 'wdr' | 'hlc'."""
        ch = self.config_channel
        code = {"off": 0, "blc": 1, "wdr": 2, "hlc": 3}.get(mode.lower())
        if code is None:
            raise DahuaHTTPError(f"unknown backlight mode: {mode}")
        self.set_config({f"VideoInBacklight[{ch}][0].Mode": code})

    # --- snapshot ----------------------------------------------------------

    def snapshot(self) -> bytes:
        """Grab a still JPEG straight from the camera CGI (bytes)."""
        return self._get(
            f"/cgi-bin/snapshot.cgi?channel={self.snapshot_channel}", raw=True
        )


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
