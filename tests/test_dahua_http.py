"""Dahua HTTP CGI client — verified against a mocked session (no camera needed)."""

from __future__ import annotations

import pytest

from src.cameractl.dahua_http import DahuaCameraHTTP, DahuaHTTPError, _parse_config_lines


class _Resp:
    def __init__(self, text="OK", status=200, content=b""):
        self.text = text
        self.status_code = status
        self.content = content


class _MockSession:
    """Records GET URLs and returns programmed responses."""

    def __init__(self, response: _Resp | None = None):
        self.calls: list[str] = []
        self._response = response or _Resp()

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self._response


def _client(session):
    return DahuaCameraHTTP("192.168.1.114", "admin", "pw", port=80, session=session)


def test_parse_config_lines() -> None:
    text = "table.VideoInExposure[0][0].Mode=0\ntable.VideoInExposure[0][0].Gain=50\n"
    parsed = _parse_config_lines(text)
    assert parsed["table.VideoInExposure[0][0].Mode"] == "0"
    assert parsed["table.VideoInExposure[0][0].Gain"] == "50"


def test_set_manual_exposure_builds_expected_cgi() -> None:
    sess = _MockSession(_Resp("OK"))
    _client(sess).set_exposure_manual(shutter="1/1000", gain=40)
    url = sess.calls[-1]
    assert "action=setConfig" in url
    assert "VideoInExposure[0][0].Mode=1" in url
    assert "VideoInExposure[0][0].Shutter=1/1000" in url
    assert "VideoInExposure[0][0].Gain=40" in url


def test_set_wdr_on() -> None:
    sess = _MockSession(_Resp("OK"))
    _client(sess).set_wdr(True, value=70)
    url = sess.calls[-1]
    assert "VideoInWideDynamicRange[0][0].Mode=1" in url
    assert "VideoInWideDynamicRange[0][0].Value=70" in url


def test_backlight_mode_mapping_and_bad_mode() -> None:
    sess = _MockSession(_Resp("OK"))
    c = _client(sess)
    c.set_backlight("blc")
    assert "VideoInBacklight[0][0].Mode=1" in sess.calls[-1]
    with pytest.raises(DahuaHTTPError):
        c.set_backlight("nonsense")


def test_setconfig_without_ok_raises() -> None:
    sess = _MockSession(_Resp("Error: bad param", status=200))
    with pytest.raises(DahuaHTTPError):
        _client(sess).set_wdr(True)


def test_http_error_status_raises() -> None:
    sess = _MockSession(_Resp("", status=401))
    with pytest.raises(DahuaHTTPError):
        _client(sess).get_config("VideoInExposure")


def test_snapshot_returns_bytes() -> None:
    sess = _MockSession(_Resp(content=b"\xff\xd8jpegbytes"))
    data = _client(sess).snapshot()
    assert data.startswith(b"\xff\xd8")
    assert "snapshot.cgi?channel=1" in sess.calls[-1]
